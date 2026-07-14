"""Inject HD2 Havok 2019 collision shapes into an extracted unit GLB.

This is an offline research/conversion tool. It reads an extracted Stingray
``.physics.main`` resource and a Filediver unit GLB, attaches each decoded hull
to the matching collision transform, and writes a new GLB plus an evidence
manifest. It never reads from or writes to the live game process.

The decoder supports convex/box, capsule, and sphere shapes, including compound
records containing several primitives. Compressed mesh shapes are reported but
not approximated. The resulting geometry is verified collision topology, not a
verified gameplay damage-zone mapping. Consumers must preserve that distinction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


GLB_JSON = 0x4E4F534A
GLB_BIN = 0x004E4942
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963


@dataclass(frozen=True)
class TagItem:
    type_index: int
    flags: int
    offset: int
    length: int


@dataclass
class Hull:
    record_index: int
    collider_hash: int
    property_hash: int
    bone_hash: int
    flags: int
    vertices: list[tuple[float, float, float]]
    triangles: list[tuple[int, int, int]]
    shape_tag: int
    destruction_tag: int
    shape_tag_codec_info: int
    root_user_data: int
    child_user_data: int
    havok_version: str
    shape_types: list[str]
    subshape_count: int


class UnsupportedShapeError(ValueError):
    def __init__(self, shape_types: list[str]):
        super().__init__(f"Unsupported Havok collision shape(s): {', '.join(shape_types) or 'unknown'}")
        self.shape_types = shape_types


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--physics",
        type=Path,
        help="Optional extracted .physics.main resource. At least this or --ragdoll-profile is required.",
    )
    parser.add_argument(
        "--ragdoll-profile",
        type=Path,
        help=(
            "Optional extracted .ragdoll_profile.main resource. Its serialized body-to-shape "
            "references are decoded and appended as articulated collision hulls."
        ),
    )
    parser.add_argument("--unit-glb", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--bones-json",
        type=Path,
        help="Optional Filediver bones JSON used only to attach human-readable bone names.",
    )
    parser.add_argument(
        "--bake-instance-transform",
        action="store_true",
        help="Deprecated compatibility flag; compound instance transforms are always baked into bone-local geometry.",
    )
    parser.add_argument(
        "--expected-hulls",
        type=int,
        help="Optional decoded-hull assertion. Omit for general enemy extraction.",
    )
    parser.add_argument(
        "--strip-textures",
        action="store_true",
        help="Replace render materials with a neutral material and remove embedded image payloads.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def murmur32(data: bytes, seed: int = 0) -> int:
    """Stingray's 32-bit name hash: the upper half of MurmurHash64A."""

    multiplier = 0xC6A4A7935BD1E995
    shift = 47
    mask = (1 << 64) - 1
    value = seed ^ ((multiplier * len(data)) & mask)
    whole = len(data) // 8 * 8
    for offset in range(0, whole, 8):
        item = int.from_bytes(data[offset : offset + 8], "little")
        item = item * multiplier & mask
        item ^= item >> shift
        item = item * multiplier & mask
        value ^= item
        value = value * multiplier & mask
    tail = data[whole:]
    for index, byte in enumerate(tail):
        value ^= byte << (index * 8)
    if tail:
        value = value * multiplier & mask
    value ^= value >> shift
    value = value * multiplier & mask
    value ^= value >> shift
    return value >> 32


def section(data: bytes, magic: bytes, start: int, end: int) -> tuple[int, int]:
    magic_offset = data.find(magic, start, end)
    if magic_offset < 4:
        raise ValueError(f"Missing {magic.decode('ascii', 'replace')} section")
    header_offset = magic_offset - 4
    size = int.from_bytes(data[header_offset:magic_offset], "big") & 0x3FFFFFFF
    if size < 8 or header_offset + size > end:
        raise ValueError(f"Invalid {magic!r} section size {size}")
    return magic_offset + 4, size - 8


def parse_items(data: bytes, start: int, end: int) -> list[TagItem]:
    item_start, item_size = section(data, b"ITEM", start, end)
    if item_size % 12:
        raise ValueError("Havok ITEM payload is not aligned to 12-byte entries")
    items = []
    for offset in range(item_start, item_start + item_size, 12):
        info, relative_offset, length = struct.unpack_from("<III", data, offset)
        items.append(TagItem(info & 0x00FFFFFF, info >> 24, relative_offset, length))
    return items


def one_item(items: Iterable[TagItem], type_index: int) -> TagItem:
    matches = [item for item in items if item.type_index == type_index]
    if len(matches) != 1:
        raise ValueError(f"Expected one Havok item of type {type_index}, found {len(matches)}")
    return matches[0]


def largest_item(items: Iterable[TagItem], type_index: int) -> TagItem:
    matches = [item for item in items if item.type_index == type_index]
    if not matches:
        raise ValueError(f"Expected a Havok item of type {type_index}")
    return max(matches, key=lambda item: item.length)


def transform_point(
    point: tuple[float, float, float], matrix_values: tuple[float, ...], scale: tuple[float, ...]
) -> tuple[float, float, float]:
    x, y, z = (point[index] * scale[index] for index in range(3))
    # hkTransformf stores three padded column vectors followed by translation.
    return (
        matrix_values[0] * x + matrix_values[4] * y + matrix_values[8] * z + matrix_values[12],
        matrix_values[1] * x + matrix_values[5] * y + matrix_values[9] * z + matrix_values[13],
        matrix_values[2] * x + matrix_values[6] * y + matrix_values[10] * z + matrix_values[14],
    )


def triangle_dot_plane(
    vertices: list[tuple[float, float, float]], triangle: tuple[int, int, int], plane: tuple[float, ...]
) -> float:
    a, b, c = (vertices[index] for index in triangle)
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return cross[0] * plane[0] + cross[1] * plane[1] + cross[2] * plane[2]


def unpack_var_uint(data: bytes, offset: int) -> tuple[int, int]:
    """Decode the Havok tagfile unsigned variable integer used by 2019 files."""

    first = data[offset]
    offset += 1
    if first & 0x80 == 0:
        return first & 0x7F, offset
    if first == 0xC3:
        return (data[offset] << 8) | data[offset + 1], offset + 2
    marker = first >> 3
    if 0x10 <= marker < 0x18:
        return ((first << 8) | data[offset]) & 0x3FFF, offset + 1
    if 0x18 <= marker < 0x1C:
        return ((first << 16) | (data[offset] << 8) | data[offset + 1]) & 0x1FFFFF, offset + 2
    if marker == 0x1C:
        return int.from_bytes(data[offset - 1 : offset + 3], "little") & 0x07FFFFFF, offset + 3
    if marker == 0x1D:
        value = (
            (first << 32)
            | (data[offset] << 24)
            | (data[offset + 1] << 16)
            | (data[offset + 2] << 8)
            | data[offset + 3]
        ) & 0x07FFFFFFFF
        return value, offset + 4
    if marker == 0x1E:
        return int.from_bytes(data[offset - 1 : offset + 7], "little") & 0x07FFFFFFFFFFFFFF, offset + 7
    raise ValueError(f"Unsupported Havok varint marker 0x{first:02x}")


def tag_type_names(data: bytes, tag_start: int, tag_end: int) -> list[str | None]:
    string_magic = b"TST1" if data.find(b"TST1", tag_start, tag_end) >= 0 else b"TSTR"
    names_start, names_size = section(data, string_magic, tag_start, tag_end)
    names = data[names_start : names_start + names_size].rstrip(b"\xff").decode("utf-8").split("\0")
    table_magic = b"TNA1" if data.find(b"TNA1", tag_start, tag_end) >= 0 else b"TNAM"
    offset, _ = section(data, table_magic, tag_start, tag_end)
    type_count, offset = unpack_var_uint(data, offset)
    result: list[str | None] = [None]
    for _ in range(type_count - 1):
        name_index, offset = unpack_var_uint(data, offset)
        template_count, offset = unpack_var_uint(data, offset)
        if name_index >= len(names):
            raise ValueError(f"Havok type-name index {name_index} exceeds string table")
        for _ in range(template_count):
            _, offset = unpack_var_uint(data, offset)
            _, offset = unpack_var_uint(data, offset)
        result.append(names[name_index])
    return result


def merge_geometry(
    vertices: list[tuple[float, float, float]],
    triangles: list[tuple[int, int, int]],
    addition_vertices: list[tuple[float, float, float]],
    addition_triangles: list[tuple[int, int, int]],
) -> None:
    base = len(vertices)
    vertices.extend(addition_vertices)
    triangles.extend((a + base, b + base, c + base) for a, b, c in addition_triangles)


def sphere_geometry(
    center: tuple[float, float, float], radius: float, latitude_steps: int = 8, longitude_steps: int = 14
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    radius = max(abs(radius), 0.001)
    vertices = []
    for latitude in range(latitude_steps + 1):
        phi = math.pi * latitude / latitude_steps
        for longitude in range(longitude_steps):
            theta = math.tau * longitude / longitude_steps
            vertices.append(
                (
                    center[0] + radius * math.sin(phi) * math.cos(theta),
                    center[1] + radius * math.cos(phi),
                    center[2] + radius * math.sin(phi) * math.sin(theta),
                )
            )
    triangles = []
    for latitude in range(latitude_steps):
        for longitude in range(longitude_steps):
            next_longitude = (longitude + 1) % longitude_steps
            a = latitude * longitude_steps + longitude
            b = latitude * longitude_steps + next_longitude
            c = (latitude + 1) * longitude_steps + longitude
            d = (latitude + 1) * longitude_steps + next_longitude
            if latitude:
                triangles.append((a, c, b))
            if latitude < latitude_steps - 1:
                triangles.append((b, c, d))
    return vertices, triangles


def capsule_geometry(
    start: tuple[float, float, float], end: tuple[float, float, float], radius: float
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    vertices, triangles = sphere_geometry(start, radius)
    end_vertices, end_triangles = sphere_geometry(end, radius)
    merge_geometry(vertices, triangles, end_vertices, end_triangles)
    axis = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
    length = math.sqrt(sum(component * component for component in axis))
    if length < 1e-6:
        return vertices, triangles
    direction = tuple(component / length for component in axis)
    helper = (0.0, 1.0, 0.0) if abs(direction[1]) < 0.9 else (1.0, 0.0, 0.0)
    u = (
        direction[1] * helper[2] - direction[2] * helper[1],
        direction[2] * helper[0] - direction[0] * helper[2],
        direction[0] * helper[1] - direction[1] * helper[0],
    )
    u_length = math.sqrt(sum(component * component for component in u))
    u = tuple(component / u_length for component in u)
    v = (
        direction[1] * u[2] - direction[2] * u[1],
        direction[2] * u[0] - direction[0] * u[2],
        direction[0] * u[1] - direction[1] * u[0],
    )
    ring_base = len(vertices)
    segments = 14
    for center in (start, end):
        for index in range(segments):
            angle = math.tau * index / segments
            vertices.append(
                tuple(
                    center[axis_index]
                    + radius * (math.cos(angle) * u[axis_index] + math.sin(angle) * v[axis_index])
                    for axis_index in range(3)
                )
            )
    for index in range(segments):
        following = (index + 1) % segments
        triangles.extend(
            (
                (ring_base + index, ring_base + segments + index, ring_base + following),
                (ring_base + following, ring_base + segments + index, ring_base + segments + following),
            )
        )
    return vertices, triangles


def geometry_items(
    items: list[TagItem], type_names: list[str | None], start: int, end: int
) -> list[tuple[TagItem, str]]:
    return [
        (item, type_names[item.type_index] or "")
        for item in items
        if start <= item.offset < end and item.type_index < len(type_names)
    ]


def convex_geometry(
    data: bytes,
    data_start: int,
    candidates: list[tuple[TagItem, str]],
    record_index: int,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    vertex_item = max((item for item, name in candidates if name == "hkFloat3"), key=lambda item: item.length)
    face_item = max(
        (item for item, name in candidates if name in {"hknpConvexHull::Face", "hknpConvexPolytopeShape::Face"}),
        key=lambda item: item.length,
    )
    plane_item = max((item for item, name in candidates if name == "hkVector4"), key=lambda item: item.length)
    index_item = max((item for item, name in candidates if name == "hkUint8"), key=lambda item: item.length)
    vertices = [
        struct.unpack_from("<3f", data, data_start + vertex_item.offset + index * 12)
        for index in range(vertex_item.length)
    ]
    planes = [
        struct.unpack_from("<4f", data, data_start + plane_item.offset + index * 16)
        for index in range(plane_item.length)
    ]
    faces = [
        struct.unpack_from("<HBB", data, data_start + face_item.offset + index * 4)
        for index in range(face_item.length)
    ]
    indices = data[data_start + index_item.offset : data_start + index_item.offset + index_item.length]
    if len(planes) != len(faces):
        raise ValueError(f"Collision record {record_index} has mismatched face/plane counts")
    triangles: list[tuple[int, int, int]] = []
    for face_index, (first_index, count, _) in enumerate(faces):
        polygon = list(indices[first_index : first_index + count])
        if len(polygon) != count or not polygon or max(polygon) >= len(vertices):
            raise ValueError(f"Collision record {record_index} contains an invalid convex face")
        for corner in range(1, len(polygon) - 1):
            triangle = (polygon[0], polygon[corner], polygon[corner + 1])
            if triangle_dot_plane(vertices, triangle, planes[face_index]) < 0:
                triangle = (triangle[0], triangle[2], triangle[1])
            triangles.append(triangle)
    return vertices, triangles


def compressed_mesh_geometry(
    data: bytes,
    data_start: int,
    candidates: list[tuple[TagItem, str]],
    record_index: int,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """Decode the single-section static mesh layout used by HD2 damage actors."""

    sections = [item for item, name in candidates if name == "hkcdStaticMeshTree::Section"]
    if len(sections) != 1 or sections[0].length != 1:
        raise UnsupportedShapeError(["hknpCompressedMeshShape(multi-section)"])
    section_item = sections[0]
    primitive_item = max(
        (item for item, name in candidates if name == "hkcdStaticMeshTree::Primitive"),
        key=lambda item: item.length,
    )
    packed_item = max(
        (item for item, name in candidates if name in {"unsigned int", "hkUint32"}),
        key=lambda item: item.length,
    )
    offset_x, offset_y, offset_z, scale_x, scale_y, scale_z = struct.unpack_from(
        "<6f", data, data_start + section_item.offset + 48
    )
    packed_values = struct.unpack_from(
        f"<{packed_item.length}I", data, data_start + packed_item.offset
    )
    vertices = [
        (
            offset_x + (value & 0x7FF) * scale_x,
            offset_y + ((value >> 11) & 0x7FF) * scale_y,
            offset_z + ((value >> 22) & 0x3FF) * scale_z,
        )
        for value in packed_values
    ]
    shared_items = [
        item for item, name in candidates if name in {"unsigned long long", "hkUint64"}
    ]
    shared_lookup_items = [item for item, name in candidates if name == "hkUint16"]
    if shared_items or shared_lookup_items:
        if len(shared_items) != 1 or len(shared_lookup_items) != 1:
            raise ValueError(
                f"Collision record {record_index} compressed mesh has an incomplete shared-vertex table"
            )
        shared_item = shared_items[0]
        shared_lookup_item = shared_lookup_items[0]
        shared_values = struct.unpack_from(
            f"<{shared_item.length}Q", data, data_start + shared_item.offset
        )
        shared_lookup = struct.unpack_from(
            f"<{shared_lookup_item.length}H", data, data_start + shared_lookup_item.offset
        )
        if not shared_lookup or max(shared_lookup) >= len(shared_values):
            raise ValueError(
                f"Collision record {record_index} compressed mesh has an invalid shared-vertex lookup"
            )
        shape_data_item = next(
            (
                item
                for item, name in candidates
                if name == "hknpCompressedMeshShapeData"
            ),
            None,
        )
        if shape_data_item is None:
            raise ValueError(
                f"Collision record {record_index} compressed mesh has shared vertices without shape data"
            )
        minimum = struct.unpack_from(
            "<3f", data, data_start + shape_data_item.offset + 48
        )
        maximum = struct.unpack_from(
            "<3f", data, data_start + shape_data_item.offset + 64
        )
        quantized_maximum = float((1 << 21) - 1)

        def decode_shared_vertex(value: int) -> tuple[float, float, float]:
            quantized = tuple((value >> (axis * 21)) & 0x1FFFFF for axis in range(3))
            return tuple(
                minimum[axis]
                + (maximum[axis] - minimum[axis]) * quantized[axis] / quantized_maximum
                for axis in range(3)
            )

        decoded_shared = [decode_shared_vertex(value) for value in shared_values]
        vertices.extend(decoded_shared[index] for index in shared_lookup)
    triangles = []
    for primitive_index in range(primitive_item.length):
        indices = tuple(data[data_start + primitive_item.offset + primitive_index * 4 + corner] for corner in range(4))
        if max(indices) >= len(vertices):
            raise ValueError(f"Collision record {record_index} compressed mesh has an invalid vertex index")
        triangles.append((indices[0], indices[1], indices[2]))
        if indices[3] not in indices[:3]:
            triangles.append((indices[0], indices[2], indices[3]))
    return vertices, triangles


def parse_hull(data: bytes, record_index: int, record_start: int, record_end: int) -> Hull:
    collider_hash, property_hash, bone_hash, flags = struct.unpack_from("<IIII", data, record_start)
    tag_header = data.find(b"TAG0", record_start, record_end) - 4
    if tag_header < record_start:
        raise ValueError(f"Collision record {record_index} has no embedded Havok tagfile")
    tag_size = int.from_bytes(data[tag_header : tag_header + 4], "big") & 0x3FFFFFFF
    tag_end = tag_header + tag_size
    if tag_end > record_end:
        raise ValueError(f"Collision record {record_index} tagfile crosses its record boundary")
    sdk_start, sdk_size = section(data, b"SDKV", tag_header, tag_end)
    havok_version = data[sdk_start : sdk_start + sdk_size].decode("ascii")
    if havok_version != "20190100":
        raise ValueError(f"Unsupported Havok version {havok_version!r}")
    data_start, data_size = section(data, b"DATA", tag_header, tag_end)
    items = parse_items(data, tag_header, tag_end)
    type_names = tag_type_names(data, tag_header, tag_end)
    named_items = [(item, type_names[item.type_index] or "") for item in items if item.type_index < len(type_names)]
    concrete_names = {
        "hknpConvexShape",
        "hknpBoxShape",
        "hknpCapsuleShape",
        "hknpSphereShape",
        "hknpCompressedMeshShape",
    }
    shapes = sorted(
        [(item, name) for item, name in named_items if name in concrete_names], key=lambda pair: pair[0].offset
    )
    compound = any(name == "hknpCompoundShape" for _, name in named_items)
    if compound:
        shapes = [(item, name) for item, name in shapes if item.offset > 0]
    if not shapes:
        other_shapes = sorted(
            {
                name
                for _, name in named_items
                if name.startswith("hknp") and name.endswith("Shape") and name not in {"hknpShape", "hknpCompoundShape", "hknpCompositeShape"}
            }
        )
        raise UnsupportedShapeError(other_shapes)
    instance_items = [item for item, name in named_items if name == "hkFreeListArrayElement"]
    instance_item = max(instance_items, key=lambda item: item.length) if compound and instance_items else None
    if compound and (instance_item is None or instance_item.length != len(shapes)):
        raise ValueError(
            f"Collision record {record_index} has {len(shapes)} shapes but "
            f"{instance_item.length if instance_item else 0} instances"
        )

    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    shape_tag = destruction_tag = 0
    for shape_index, (shape_item, shape_name) in enumerate(shapes):
        shape_end = shapes[shape_index + 1][0].offset if shape_index + 1 < len(shapes) else data_size
        candidates = geometry_items(items, type_names, shape_item.offset, shape_end)
        if shape_name in {"hknpConvexShape", "hknpBoxShape"}:
            part_vertices, part_triangles = convex_geometry(data, data_start, candidates, record_index)
        elif shape_name == "hknpCapsuleShape":
            point_item = max((item for item, name in candidates if name == "hkFloat3"), key=lambda item: item.length)
            if point_item.length != 2:
                raise ValueError(f"Collision record {record_index} capsule does not contain two endpoints")
            points = [
                struct.unpack_from("<3f", data, data_start + point_item.offset + point * 12) for point in range(2)
            ]
            # HD2's Havok 2019 tagfiles place hknpShape::convexRadius at
            # byte 32.  Offset 28 is the hk2018 layout and reads the shape's
            # dispatch/key metadata here, which collapses capsules to the
            # 1 mm safety minimum used by capsule_geometry().
            radius = struct.unpack_from("<f", data, data_start + shape_item.offset + 32)[0]
            part_vertices, part_triangles = capsule_geometry(points[0], points[1], radius)
        elif shape_name == "hknpSphereShape":
            point_item = max((item for item, name in candidates if name == "hkFloat3"), key=lambda item: item.length)
            center = struct.unpack_from("<3f", data, data_start + point_item.offset)
            radius = struct.unpack_from("<f", data, data_start + shape_item.offset + 32)[0]
            part_vertices, part_triangles = sphere_geometry(center, radius)
        elif shape_name == "hknpCompressedMeshShape":
            part_vertices, part_triangles = compressed_mesh_geometry(data, data_start, candidates, record_index)
        else:
            raise UnsupportedShapeError([shape_name])

        if instance_item is not None:
            instance_offset = data_start + instance_item.offset + shape_index * 112
            transform = struct.unpack_from("<16f", data, instance_offset)
            scale = struct.unpack_from("<4f", data, instance_offset + 64)
            part_vertices = [transform_point(vertex, transform, scale) for vertex in part_vertices]
            if shape_index == 0:
                shape_tag, destruction_tag = struct.unpack_from("<HH", data, instance_offset + 88)
        merge_geometry(vertices, triangles, part_vertices, part_triangles)

    root_item = next((item for item, name in named_items if name == "hknpCompoundShape"), shapes[0][0])
    root_offset = data_start + root_item.offset
    child_offset = data_start + shapes[0][0].offset
    return Hull(
        record_index=record_index,
        collider_hash=collider_hash,
        property_hash=property_hash,
        bone_hash=bone_hash,
        flags=flags,
        vertices=vertices,
        triangles=triangles,
        shape_tag=shape_tag,
        destruction_tag=destruction_tag,
        shape_tag_codec_info=(struct.unpack_from("<I", data, root_offset + 56)[0] if compound else 0),
        root_user_data=struct.unpack_from("<Q", data, root_offset + 40)[0],
        child_user_data=struct.unpack_from("<Q", data, child_offset + 40)[0],
        havok_version=havok_version,
        shape_types=[name for _, name in shapes],
        subshape_count=len(shapes),
    )


def decode_physics(path: Path) -> tuple[list[Hull], list[dict[str, Any]]]:
    data = path.read_bytes()
    if len(data) < 0x68:
        raise ValueError("Physics resource is too small")
    pointer_table = struct.unpack_from("<I", data, 0x4C)[0]
    count = struct.unpack_from("<I", data, pointer_table + 4)[0]
    starts = [
        pointer_table + struct.unpack_from("<I", data, pointer_table + 8 + index * 4)[0]
        for index in range(count)
    ]
    if starts != sorted(starts) or starts[-1] >= len(data):
        raise ValueError("Physics collision record table is invalid")
    hulls = []
    unsupported = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < count else len(data)
        try:
            hulls.append(parse_hull(data, index, start, end))
        except UnsupportedShapeError as error:
            collider_hash, property_hash, bone_hash, flags = struct.unpack_from("<IIII", data, start)
            unsupported.append(
                {
                    "recordIndex": index,
                    "colliderHash": f"{collider_hash:08x}",
                    "boneHash": f"{bone_hash:08x}",
                    "propertyHash": f"{property_hash:08x}",
                    "flags": flags,
                    "shapeTypes": error.shape_types,
                }
            )
    return hulls, unsupported


def decode_ragdoll_profile(path: Path, first_record_index: int) -> tuple[list[Hull], dict[int, str]]:
    """Decode the one-to-one body/shape table in an HD2 ragdoll profile.

    Each ``bodyCinfoWithAttachment`` stores an ITEM-table reference to its exact
    Havok shape at byte 0 and a reference to its serialized ``ragdoll_*`` body
    name at byte 24.  The body name matches the unit skeleton node after the
    prefix is removed, so no anatomy or ordering is inferred here.
    """

    data = path.read_bytes()
    if data[0x20:0x24] != b"RPR ":
        raise ValueError("Expected an HD2 RPR ragdoll-profile resource")
    tag_header = data.find(b"TAG0") - 4
    if tag_header < 0:
        raise ValueError("Ragdoll profile has no embedded Havok tagfile")
    tag_size = int.from_bytes(data[tag_header : tag_header + 4], "big") & 0x3FFFFFFF
    tag_end = tag_header + tag_size
    if tag_end > len(data):
        raise ValueError("Ragdoll tagfile crosses the resource boundary")
    sdk_start, sdk_size = section(data, b"SDKV", tag_header, tag_end)
    havok_version = data[sdk_start : sdk_start + sdk_size].decode("ascii")
    if havok_version != "20190100":
        raise ValueError(f"Unsupported Havok version {havok_version!r}")
    data_start, data_size = section(data, b"DATA", tag_header, tag_end)
    items = parse_items(data, tag_header, tag_end)
    type_names = tag_type_names(data, tag_header, tag_end)
    body_items = [
        item
        for item in items
        if item.type_index < len(type_names)
        and type_names[item.type_index] == "hknpPhysicsSystemData::bodyCinfoWithAttachment"
    ]
    if len(body_items) != 1:
        raise ValueError(f"Expected one ragdoll body table, found {len(body_items)}")
    body_item = body_items[0]
    following_offsets = sorted(item.offset for item in items if item.offset > body_item.offset)
    if not following_offsets:
        raise ValueError("Ragdoll body table has no following ITEM boundary")
    body_bytes = following_offsets[0] - body_item.offset
    if body_item.length < 1 or body_bytes % body_item.length:
        raise ValueError("Ragdoll body table has an invalid stride")
    body_stride = body_bytes // body_item.length
    if body_stride < 28:
        raise ValueError(f"Ragdoll body stride {body_stride} is too small")

    concrete_names = {
        "hknpConvexShape",
        "hknpBoxShape",
        "hknpCapsuleShape",
        "hknpSphereShape",
        "hknpCompressedMeshShape",
    }
    concrete_items = sorted(
        (
            item
            for item in items
            if item.type_index < len(type_names) and type_names[item.type_index] in concrete_names
        ),
        key=lambda item: item.offset,
    )
    next_shape_offset = {
        item.offset: (concrete_items[index + 1].offset if index + 1 < len(concrete_items) else data_size)
        for index, item in enumerate(concrete_items)
    }
    compressed_data_items = sorted(
        (
            item
            for item in items
            if item.type_index < len(type_names)
            and type_names[item.type_index] == "hknpCompressedMeshShapeData"
        ),
        key=lambda item: item.offset,
    )
    next_compressed_data_offset = {
        item.offset: (
            compressed_data_items[index + 1].offset
            if index + 1 < len(compressed_data_items)
            else data_size
        )
        for index, item in enumerate(compressed_data_items)
    }
    hulls: list[Hull] = []
    bone_names: dict[int, str] = {}
    seen_shape_items: set[int] = set()
    for body_index in range(body_item.length):
        body_offset = data_start + body_item.offset + body_index * body_stride
        shape_index, name_index = struct.unpack_from("<I20xI", data, body_offset)
        if shape_index >= len(items) or name_index >= len(items):
            raise ValueError(f"Ragdoll body {body_index} references an invalid ITEM index")
        shape_item = items[shape_index]
        shape_name = type_names[shape_item.type_index] or ""
        name_item = items[name_index]
        name_type = type_names[name_item.type_index] or ""
        if shape_name not in concrete_names or name_type != "char":
            raise ValueError(
                f"Ragdoll body {body_index} references {shape_name!r} and {name_type!r}, not shape/name items"
            )
        if shape_index in seen_shape_items:
            raise ValueError(f"Ragdoll shape ITEM {shape_index} is assigned to more than one body")
        seen_shape_items.add(shape_index)
        serialized_name = data[
            data_start + name_item.offset : data_start + name_item.offset + name_item.length
        ].rstrip(b"\0").decode("utf-8")
        if not serialized_name.startswith("ragdoll_"):
            raise ValueError(f"Unexpected ragdoll body name {serialized_name!r}")
        bone_name = serialized_name.removeprefix("ragdoll_")
        bone_hash = murmur32(bone_name.encode("utf-8"))
        bone_names[bone_hash] = bone_name
        candidates = geometry_items(
            items,
            type_names,
            shape_item.offset,
            next_shape_offset[shape_item.offset],
        )
        record_index = first_record_index + body_index
        if shape_name in {"hknpConvexShape", "hknpBoxShape"}:
            vertices, triangles = convex_geometry(data, data_start, candidates, record_index)
        elif shape_name == "hknpCapsuleShape":
            point_item = max((item for item, name in candidates if name == "hkFloat3"), key=lambda item: item.length)
            if point_item.length != 2:
                raise ValueError(f"Ragdoll body {body_index} capsule does not contain two endpoints")
            points = [
                struct.unpack_from("<3f", data, data_start + point_item.offset + point * 12)
                for point in range(2)
            ]
            radius = struct.unpack_from("<f", data, data_start + shape_item.offset + 32)[0]
            vertices, triangles = capsule_geometry(points[0], points[1], radius)
        elif shape_name == "hknpSphereShape":
            point_item = max((item for item, name in candidates if name == "hkFloat3"), key=lambda item: item.length)
            center = struct.unpack_from("<3f", data, data_start + point_item.offset)
            radius = struct.unpack_from("<f", data, data_start + shape_item.offset + 32)[0]
            vertices, triangles = sphere_geometry(center, radius)
        elif shape_name == "hknpCompressedMeshShape":
            shape_data_index = struct.unpack_from(
                "<I", data, data_start + shape_item.offset + 64
            )[0]
            if shape_data_index >= len(items):
                raise ValueError(
                    f"Ragdoll body {body_index} compressed mesh references an invalid shape-data ITEM"
                )
            shape_data_item = items[shape_data_index]
            shape_data_name = type_names[shape_data_item.type_index] or ""
            if shape_data_name != "hknpCompressedMeshShapeData":
                raise ValueError(
                    f"Ragdoll body {body_index} compressed mesh references {shape_data_name!r}, "
                    "not hknpCompressedMeshShapeData"
                )
            data_candidates = geometry_items(
                items,
                type_names,
                shape_data_item.offset,
                next_compressed_data_offset[shape_data_item.offset],
            )
            vertices, triangles = compressed_mesh_geometry(
                data, data_start, data_candidates, record_index
            )
        else:  # pragma: no cover - guarded by concrete_names
            raise UnsupportedShapeError([shape_name])
        user_data = struct.unpack_from("<Q", data, data_start + shape_item.offset + 40)[0]
        hulls.append(
            Hull(
                record_index=record_index,
                collider_hash=bone_hash,
                property_hash=0,
                bone_hash=bone_hash,
                flags=0,
                vertices=vertices,
                triangles=triangles,
                shape_tag=0xFFFF,
                destruction_tag=0xFFFF,
                shape_tag_codec_info=0,
                root_user_data=user_data,
                child_user_data=user_data,
                havok_version=havok_version,
                shape_types=[shape_name],
                subshape_count=1,
            )
        )
    if len(seen_shape_items) != body_item.length:
        raise ValueError("Ragdoll body-to-shape references are not one-to-one")
    return hulls, bone_names


def read_glb(path: Path) -> tuple[dict[str, Any], bytearray]:
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError("GLB is too small")
    magic, version, total_length = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or total_length != len(data):
        raise ValueError("Expected a complete GLB 2.0 file")
    offset = 12
    json_doc: dict[str, Any] | None = None
    binary = bytearray()
    while offset < len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == GLB_JSON:
            json_doc = json.loads(chunk.decode("utf-8").rstrip("\0 "))
        elif chunk_type == GLB_BIN:
            binary.extend(chunk)
    if json_doc is None:
        raise ValueError("GLB has no JSON chunk")
    return json_doc, binary


def aligned_append(buffer: bytearray, payload: bytes, alignment: int = 4) -> tuple[int, int]:
    while len(buffer) % alignment:
        buffer.append(0)
    offset = len(buffer)
    buffer.extend(payload)
    return offset, len(payload)


def strip_texture_payloads(document: dict[str, Any], binary: bytearray) -> bytearray:
    """Keep render geometry/skins while removing large embedded texture buffer views."""

    used_views: set[int] = set()
    for accessor in document.get("accessors", []):
        if "bufferView" in accessor:
            used_views.add(accessor["bufferView"])
        sparse = accessor.get("sparse", {})
        for key in ("indices", "values"):
            if "bufferView" in sparse.get(key, {}):
                used_views.add(sparse[key]["bufferView"])
    old_views = document.get("bufferViews", [])
    compact = bytearray()
    remap: dict[int, int] = {}
    new_views = []
    for old_index in sorted(used_views):
        view = dict(old_views[old_index])
        if view.get("buffer", 0) != 0:
            raise ValueError("Only single-buffer GLBs are supported")
        start = view.get("byteOffset", 0)
        payload = bytes(binary[start : start + view["byteLength"]])
        new_offset, _ = aligned_append(compact, payload)
        view["byteOffset"] = new_offset
        remap[old_index] = len(new_views)
        new_views.append(view)
    for accessor in document.get("accessors", []):
        if "bufferView" in accessor:
            accessor["bufferView"] = remap[accessor["bufferView"]]
        sparse = accessor.get("sparse", {})
        for key in ("indices", "values"):
            if "bufferView" in sparse.get(key, {}):
                sparse[key]["bufferView"] = remap[sparse[key]["bufferView"]]
    document["bufferViews"] = new_views
    document.pop("images", None)
    document.pop("textures", None)
    document.pop("samplers", None)
    document["materials"] = [
        {
            "name": "HD2 research render mesh",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.12, 0.15, 0.16, 1.0],
                "metallicFactor": 0.15,
                "roughnessFactor": 0.78,
            },
            "doubleSided": True,
        }
    ]
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            primitive["material"] = 0
    document.setdefault("buffers", [{"byteLength": 0}])
    document["buffers"][0]["byteLength"] = len(compact)
    return compact


def prepare_viewer_materials(document: dict[str, Any]) -> list[int]:
    """Preserve standard colors and make Stingray-only materials legible in glTF viewers.

    Most creature exports already contain standard glTF base-color textures. The
    Automaton vehicle shader instead combines ID masks, decals, and a material
    LUT at runtime, which a stock GLTFLoader cannot reproduce. Those materials
    receive a restrained gunmetal approximation while their embedded source
    textures and extras remain intact for future shader work.
    """

    approximated: list[int] = []
    for index, material in enumerate(document.get("materials", [])):
        name = material.get("name", "").lower()
        extras = material.get("extras", {})
        pbr = material.setdefault("pbrMetallicRoughness", {})
        if "baseColorTexture" in pbr:
            continue
        if "base_data" in extras or "id_masks_array" in extras or "material_lut" in extras:
            # Automaton armor is a dark, cool gunmetal in-game. The exact
            # albedo, wear, and paint are composed from the ID-mask array and
            # 23-column material LUT at runtime, which stock glTF cannot run.
            pbr["baseColorFactor"] = [0.18, 0.19, 0.20, 1.0]
            pbr["metallicFactor"] = 0.58
            pbr["roughnessFactor"] = 0.50
            # Filediver's base-data export retains useful tangent-space surface
            # detail. Reduce its strength because the packed channels are not a
            # perfect glTF normal map, but keep it instead of flattening armor.
            if "normalTexture" in material:
                material["normalTexture"]["scale"] = 0.32
            material.setdefault("extras", {})["hd2ViewerMaterial"] = "dark-gunmetal-lut-approximation"
            approximated.append(index)
        if "emissive" in name or "boteye" in name:
            pbr["baseColorFactor"] = [0.32, 0.015, 0.008, 1.0]
            pbr["metallicFactor"] = 0.25
            pbr["roughnessFactor"] = 0.42
            material["emissiveFactor"] = [1.0, 0.025, 0.01]
    return approximated


def mark_alternate_render_nodes_hidden(document: dict[str, Any]) -> list[str]:
    """Preserve damage-state meshes as evidence but never show them initially."""

    marked: list[str] = []
    for node in document.get("nodes", []):
        name = node.get("name", "")
        lowered = name.lower()
        if "mesh" in node and any(token in lowered for token in ("damaged", "destroyed")):
            node.setdefault("extras", {})["default_hidden"] = 1
            marked.append(name)
    return marked


def node_hash(node_name: str) -> int | None:
    if node_name.startswith("Bone_"):
        try:
            return int(node_name[5:], 16)
        except ValueError:
            return None
    return murmur32(node_name.encode("utf-8"))


def load_bone_names(path: Path | None) -> dict[int, str]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    names = payload.get("map", {})
    return {int(key, 16): value for key, value in names.items()}


def inject_hulls(
    document: dict[str, Any],
    binary: bytearray,
    hulls: list[Hull],
    bone_names: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    bone_names = bone_names or {}
    nodes = document.setdefault("nodes", [])
    node_by_hash: dict[int, int] = {}
    for index, node in enumerate(nodes):
        hashed = node_hash(node.get("name", ""))
        if hashed is not None:
            node_by_hash.setdefault(hashed, index)

    material_index = len(document.setdefault("materials", []))
    document["materials"].append(
        {
            "name": "HD2 decoded collision hull",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.9, 0.12, 0.08, 0.28],
                "metallicFactor": 0,
                "roughnessFactor": 1,
            },
            "alphaMode": "BLEND",
            "doubleSided": True,
        }
    )
    buffer_views = document.setdefault("bufferViews", [])
    accessors = document.setdefault("accessors", [])
    meshes = document.setdefault("meshes", [])
    manifest_entries = []

    for hull in hulls:
        parent_index = node_by_hash.get(hull.bone_hash, node_by_hash.get(hull.collider_hash))
        if parent_index is None:
            raise ValueError(
                f"No GLB bone/collision transform for record {hull.record_index} "
                f"(bone {hull.bone_hash:08x}, collider {hull.collider_hash:08x})"
            )
        parent = nodes[parent_index]

        vertex_payload = b"".join(struct.pack("<3f", *vertex) for vertex in hull.vertices)
        flat_indices = [index for triangle in hull.triangles for index in triangle]
        if max(flat_indices) > 65535:
            raise ValueError("Collision hull exceeds 16-bit GLB indices")
        index_payload = struct.pack(f"<{len(flat_indices)}H", *flat_indices)
        vertex_offset, vertex_length = aligned_append(binary, vertex_payload)
        index_offset, index_length = aligned_append(binary, index_payload)

        vertex_view = len(buffer_views)
        buffer_views.append(
            {"buffer": 0, "byteOffset": vertex_offset, "byteLength": vertex_length, "target": ARRAY_BUFFER}
        )
        index_view = len(buffer_views)
        buffer_views.append(
            {"buffer": 0, "byteOffset": index_offset, "byteLength": index_length, "target": ELEMENT_ARRAY_BUFFER}
        )
        vertex_accessor = len(accessors)
        accessors.append(
            {
                "bufferView": vertex_view,
                "componentType": 5126,
                "count": len(hull.vertices),
                "type": "VEC3",
                "min": [min(vertex[axis] for vertex in hull.vertices) for axis in range(3)],
                "max": [max(vertex[axis] for vertex in hull.vertices) for axis in range(3)],
            }
        )
        index_accessor = len(accessors)
        accessors.append(
            {
                "bufferView": index_view,
                "componentType": 5123,
                "count": len(flat_indices),
                "type": "SCALAR",
            }
        )
        mesh_index = len(meshes)
        meshes.append(
            {
                "name": f"collision_{hull.record_index:02d}_{node.get('name', hull.collider_hash):s}",
                "primitives": [
                    {
                        "attributes": {"POSITION": vertex_accessor},
                        "indices": index_accessor,
                        "material": material_index,
                        "mode": 4,
                    }
                ],
            }
        )
        node_index = len(nodes)
        node = {
            "name": f"hd2_collision_{hull.record_index:03d}_{hull.collider_hash:08x}",
            "mesh": mesh_index,
        }
        nodes.append(node)
        parent.setdefault("children", []).append(node_index)
        bone_name = bone_names.get(hull.bone_hash)
        node.setdefault("extras", {})["hd2Collision"] = {
            "recordIndex": hull.record_index,
            "colliderHash": f"{hull.collider_hash:08x}",
            "boneHash": f"{hull.bone_hash:08x}",
            "boneName": bone_name,
            "propertyHash": f"{hull.property_hash:08x}",
            "flags": hull.flags,
            "shapeTag": hull.shape_tag,
            "destructionTag": hull.destruction_tag,
            "geometryConfidence": "verified",
            "gameplayMappingConfidence": "unverified",
            "shapeTypes": hull.shape_types,
            "subshapeCount": hull.subshape_count,
        }
        sizes = [
            max(vertex[axis] for vertex in hull.vertices) - min(vertex[axis] for vertex in hull.vertices)
            for axis in range(3)
        ]
        manifest_entries.append(
            {
                "recordIndex": hull.record_index,
                "nodeIndex": node_index,
                "nodeName": node.get("name"),
                "parentNodeIndex": parent_index,
                "parentNodeName": parent.get("name"),
                "colliderHash": f"{hull.collider_hash:08x}",
                "boneHash": f"{hull.bone_hash:08x}",
                "boneName": bone_name,
                "vertices": len(hull.vertices),
                "triangles": len(hull.triangles),
                "localSize": [round(value, 6) for value in sizes],
                "geometryConfidence": "verified",
                "gameplayDamagePool": None,
                "shapeTypes": hull.shape_types,
                "subshapeCount": hull.subshape_count,
            }
        )

    document.setdefault("buffers", [{"byteLength": 0}])
    if len(document["buffers"]) != 1:
        raise ValueError("Only single-buffer GLBs are supported")
    document["buffers"][0]["byteLength"] = len(binary)
    document.setdefault("asset", {}).setdefault("extras", {})["hd2CollisionResearch"] = {
        "hullCount": len(hulls),
        "geometryConfidence": "verified",
        "gameplayMappingConfidence": "unverified",
    }
    return manifest_entries


def write_glb(path: Path, document: dict[str, Any], binary: bytearray) -> None:
    json_bytes = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_bytes += b" " * (-len(json_bytes) % 4)
    binary += b"\0" * (-len(binary) % 4)
    total_length = 12 + 8 + len(json_bytes) + 8 + len(binary)
    payload = bytearray(struct.pack("<4sII", b"glTF", 2, total_length))
    payload.extend(struct.pack("<II", len(json_bytes), GLB_JSON))
    payload.extend(json_bytes)
    payload.extend(struct.pack("<II", len(binary), GLB_BIN))
    payload.extend(binary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> None:
    args = parse_args()
    if not args.physics and not args.ragdoll_profile:
        raise ValueError("At least one collision source is required: --physics or --ragdoll-profile")
    physics = args.physics.resolve() if args.physics else None
    unit_glb = args.unit_glb.resolve()
    output = args.output.resolve()
    manifest_path = (args.manifest or output.with_suffix(".manifest.json")).resolve()
    hulls, unsupported = decode_physics(physics) if physics else ([], [])
    ragdoll_profile = args.ragdoll_profile.resolve() if args.ragdoll_profile else None
    ragdoll_hulls: list[Hull] = []
    ragdoll_bone_names: dict[int, str] = {}
    if ragdoll_profile:
        ragdoll_hulls, ragdoll_bone_names = decode_ragdoll_profile(ragdoll_profile, len(hulls))
        hulls.extend(ragdoll_hulls)
    if args.expected_hulls is not None and len(hulls) != args.expected_hulls:
        raise ValueError(f"Expected {args.expected_hulls} decoded hulls, found {len(hulls)}")
    document, binary = read_glb(unit_glb)
    hidden_alternate_nodes = mark_alternate_render_nodes_hidden(document)
    approximated_materials: list[int] = []
    if args.strip_textures:
        binary = strip_texture_payloads(document, binary)
    else:
        approximated_materials = prepare_viewer_materials(document)
    bone_names = load_bone_names(args.bones_json.resolve() if args.bones_json else None)
    bone_names.update(ragdoll_bone_names)
    entries = inject_hulls(document, binary, hulls, bone_names)
    write_glb(output, document, binary)

    metadata_sets = {
        "shapeTags": sorted({hull.shape_tag for hull in hulls}),
        "destructionTags": sorted({hull.destruction_tag for hull in hulls}),
        "shapeTagCodecInfo": sorted({hull.shape_tag_codec_info for hull in hulls}),
        "rootUserDataHex": sorted({f"{hull.root_user_data:016x}" for hull in hulls}),
        "childUserDataHex": sorted({f"{hull.child_user_data:016x}" for hull in hulls}),
    }
    manifest = {
        "schemaVersion": 1,
        "extractionDate": date.today().isoformat(),
        "source": {
            "physics": {"path": str(physics), "sha256": sha256(physics)} if physics else None,
            "ragdollProfile": (
                {"path": str(ragdoll_profile), "sha256": sha256(ragdoll_profile)}
                if ragdoll_profile
                else None
            ),
            "unitGlb": {"path": str(unit_glb), "sha256": sha256(unit_glb)},
            "bonesJson": (
                {"path": str(args.bones_json.resolve()), "sha256": sha256(args.bones_json.resolve())}
                if args.bones_json
                else None
            ),
            "havokVersion": sorted({hull.havok_version for hull in hulls}),
        },
        "output": {"path": str(output), "sha256": sha256(output)},
        "hullCount": len(hulls),
        "physicsRecordCount": len(hulls) + len(unsupported),
        "basePhysicsHullCount": len(hulls) - len(ragdoll_hulls),
        "ragdollHullCount": len(ragdoll_hulls),
        "ragdollMappingEvidence": (
            "Exact hknpPhysicsSystemData::bodyCinfoWithAttachment shape ITEM and ragdoll-name ITEM references"
            if ragdoll_hulls
            else None
        ),
        "unsupportedColliderCount": len(unsupported),
        "unsupportedColliders": unsupported,
        "vertexCount": sum(len(hull.vertices) for hull in hulls),
        "triangleCount": sum(len(hull.triangles) for hull in hulls),
        "geometryConfidence": "verified",
        "vertexSpace": "skeleton-bone-local-with-compound-instance-or-ragdoll-body-shape",
        "gameplayMappingConfidence": "unverified",
        "renderMaterials": {
            "mode": "neutral-stripped" if args.strip_textures else "embedded-game-materials",
            "embeddedImageCount": len(document.get("images", [])),
            "approximatedMaterialIndices": approximated_materials,
            "hiddenAlternateNodeNames": hidden_alternate_nodes,
        },
        "metadataSets": metadata_sets,
        "colliders": entries,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"Decoded {manifest['hullCount']} hulls, {manifest['vertexCount']} vertices, "
        f"and {manifest['triangleCount']} triangles into {output}"
    )
    print(f"Wrote evidence manifest to {manifest_path}")


if __name__ == "__main__":
    main()
