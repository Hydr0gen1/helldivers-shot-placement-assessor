"""Inspect an HD2 enemy archive for the data needed by the 3D accuracy gate.

Run with Blender 4.3, for example:

    blender --background --factory-startup --python tools/research_hd2_3d_gate.py -- \
        --game-data "C:/Program Files (x86)/Steam/steamapps/common/Helldivers 2/data" \
        --sdk "C:/path/to/Blender/4.3/scripts/addons" \
        --archive fac59cae01035deb

The script is deliberately read-only. It emits JSON to stdout and never writes to
the game installation.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
import re
import sys
from collections import Counter

import bpy
from bpy.props import PointerProperty


def parse_args() -> argparse.Namespace:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-data", required=True)
    parser.add_argument("--sdk", required=True, help="Directory containing the SDK add-on")
    parser.add_argument("--archive", required=True, help="Archive/package ID in hexadecimal")
    parser.add_argument("--thin-hashes", help="Optional Filediver thinhashes.txt for reverse-name lookup")
    parser.add_argument("--scan-related", action="store_true", help="Scan all package TOCs for matching file IDs")
    parser.add_argument("--verbose", action="store_true", help="Include all transforms and raw format strings")
    return parser.parse_args(args)


def ascii_strings(data: bytes, minimum: int = 4) -> list[str]:
    pattern = rb"[A-Za-z_][A-Za-z0-9_:. */<>-]{" + str(minimum - 1).encode("ascii") + rb",}"
    values = {item.decode("ascii", "replace").strip() for item in re.findall(pattern, data)}
    return sorted(value for value in values if sum(char.isalpha() for char in value) >= 3)


def hash_references(data: bytes, hashes: list[tuple[int, str | None]]) -> list[dict[str, object]]:
    references = []
    for value, name in hashes:
        needle = value.to_bytes(4, "little")
        offsets = []
        start = 0
        while True:
            offset = data.find(needle, start)
            if offset < 0:
                break
            offsets.append(offset)
            start = offset + 1
        if offsets:
            references.append(
                {"hash": f"{value:08x}", "name": name, "count": len(offsets), "offsets": offsets}
            )
    return references


def main() -> None:
    args = parse_args()
    sys.path.append(os.path.abspath(args.sdk))
    sdk = importlib.import_module("HD2SDK-CommunityEdition")

    game_data = os.path.abspath(args.game_data)
    sdk.Global_gamepath = game_data
    sdk.slim_init(game_data)
    sdk.LoadTypeHashes()
    sdk.LoadNameHashes()
    sdk.LoadBoneHashes(sdk.Global_bonehashpath, sdk.Global_BoneNames)

    thin_names: dict[int, str] = {}
    if args.thin_hashes:
        with open(args.thin_hashes, "r", encoding="utf-8") as names_file:
            for raw_name in names_file:
                name = raw_name.strip()
                if not name or name.startswith("//"):
                    continue
                thin_names.setdefault(sdk.hash_m.murmur32_hash(name.encode()), name)

    # The mesh parser consults import preferences even when no Blender objects are
    # created. Register only that property group, avoiding the add-on's updater and
    # every mutating/export operator.
    bpy.utils.register_class(sdk.Hd2ToolPanelSettings)
    bpy.types.Scene.Hd2ToolPanelSettings = PointerProperty(type=sdk.Hd2ToolPanelSettings)
    bpy.context.scene.Hd2ToolPanelSettings.ImportMaterials = False

    archive_path = os.path.join(game_data, args.archive)
    if args.scan_related:
        toc = sdk.Global_TocManager.LoadArchive(archive_path, SetActive=False)
    else:
        toc = sdk.StreamToc()
        if not toc.FromFile(archive_path, True):
            raise RuntimeError(f"Could not read archive {args.archive}")
    sdk.Global_TocManager.ActiveArchive = toc

    result: dict[str, object] = {
        "archive": args.archive,
        "archive_path": archive_path,
        "sdk_version": list(sdk.bl_info["version"]),
        "resource_types": [],
    }

    for type_id, entries in sorted(toc.TocDict.items()):
        result["resource_types"].append(
            {
                "type_id": f"{type_id:016x}",
                "type": sdk.GetTypeNameFromID(type_id),
                "entries": len(entries),
                "file_ids": [f"{file_id:016x}" for file_id in entries],
            }
        )

    unit_entries = toc.TocDict.get(sdk.UnitID, {})
    unit_entry = next(iter(unit_entries.values()), None)
    if unit_entry:
        with contextlib.redirect_stdout(io.StringIO()):
            unit_entry.Load(False, False)
        unit = unit_entry.LoadedData
        result["unit"] = {
            "file_id": f"{unit_entry.FileID:016x}",
            "version": unit.Version,
            "bones_ref": f"{unit.BonesRef:016x}",
            "state_machine_ref": f"{unit.StateMachineRef:016x}",
            "mesh_count": unit.NumMeshes,
            "raw_mesh_count": len(unit.RawMeshes),
            "transform_count": len(unit.TransformInfo.NameHashes),
            "transforms": [
                {
                    "index": index,
                    "hash": f"{name_hash:08x}",
                    "name": sdk.Global_BoneNames.get(name_hash),
                }
                for index, name_hash in enumerate(unit.TransformInfo.NameHashes)
                if args.verbose or sdk.Global_BoneNames.get(name_hash)
            ],
            "meshes": [
                {
                    "index": index,
                    "lod": mesh.LodIndex,
                    "mesh_id": mesh.MeshID,
                    "mesh_hash": f"{mesh.MeshID:08x}",
                    "mesh_name": sdk.Global_BoneNames.get(mesh.MeshID)
                    or thin_names.get(mesh.MeshID),
                    "culling_body": mesh.IsCullingBody(),
                    "static": mesh.IsStaticMesh(),
                    "vertices": len(mesh.VertexPositions),
                    "triangles": len(mesh.Indices),
                }
                for index, mesh in enumerate(unit.RawMeshes)
            ],
        }

        transform_hashes = [
            (name_hash, sdk.Global_BoneNames.get(name_hash))
            for name_hash in unit.TransformInfo.NameHashes
        ]
    else:
        transform_hashes = []

    if args.scan_related and unit_entry:
        related = []
        for archive in sdk.Global_TocManager.SearchArchives:
            matches = []
            for type_id, file_ids in archive.TocEntries.items():
                if unit_entry.FileID in file_ids:
                    matches.append(
                        {"type_id": f"{type_id:016x}", "type": sdk.GetTypeNameFromID(type_id)}
                    )
            if matches:
                related.append({"archive": archive.Name, "matches": matches})
        result["same_file_id_packages"] = related

    bone_entries = toc.TocDict.get(sdk.BoneID, {})
    bone_entry = next(iter(bone_entries.values()), None)
    if bone_entry:
        bone_entry.Load(False, False)
        result["bones"] = {
            "file_id": f"{bone_entry.FileID:016x}",
            "count": len(bone_entry.LoadedData.Names),
            "names": list(bone_entry.LoadedData.Names),
        }

    raw_types = {
        "physics": sdk.PhysicsID,
        "ragdoll_profile": int("1d59bd6687db6b33", 16),
        "ik_skeleton": int("57a13425279979d7", 16),
    }
    known_file_ids = {
        entry.FileID
        for entries in toc.TocDict.values()
        for entry in entries.values()
    }
    for label, type_id in raw_types.items():
        entries = toc.TocDict.get(type_id, {})
        entry = next(iter(entries.values()), None)
        if not entry:
            continue
        data = bytes(entry.TocData)
        qwords = [int.from_bytes(data[offset : offset + 8], "little") for offset in range(0, len(data) - 7, 8)]
        referenced_ids = Counter(value for value in qwords if value in known_file_ids)
        result[label] = {
            "file_id": f"{entry.FileID:016x}",
            "bytes": len(data),
            "ascii_strings": [
                value
                for value in ascii_strings(data)
                if args.verbose
                or any(
                    keyword in value.lower()
                    for keyword in ("shape", "user", "path", "instance", "skeleton", "bone", "strider")
                )
            ],
            "archive_file_id_references": [
                {"file_id": f"{file_id:016x}", "count": count}
                for file_id, count in referenced_ids.most_common()
            ],
            "transform_hash_references": [
                reference
                for reference in hash_references(data, transform_hashes)
                if args.verbose or reference["name"]
            ],
        }
        if label == "physics" and len(data) >= 0x68:
            pointer_list_offset = int.from_bytes(data[0x4C:0x50], "little")
            collider_count = int.from_bytes(data[pointer_list_offset + 4 : pointer_list_offset + 8], "little")
            transform_indices = {
                name_hash: index
                for index, name_hash in enumerate(unit.TransformInfo.NameHashes)
            } if unit_entry else {}
            colliders = []
            for index in range(collider_count):
                pointer_offset = pointer_list_offset + 8 + index * 4
                relative_offset = int.from_bytes(data[pointer_offset : pointer_offset + 4], "little")
                # Havok stores every compound-shape record offset relative to the
                # beginning of the pointer table, not relative to the individual
                # pointer field. The record begins with collider/property hashes;
                # the linked skeleton bone and flags follow eight bytes later.
                record_offset = pointer_list_offset + relative_offset
                bone_offset = record_offset + 8
                if record_offset < 0 or bone_offset + 8 > len(data):
                    continue
                collider_hash = int.from_bytes(data[record_offset : record_offset + 4], "little")
                property_hash = int.from_bytes(data[record_offset + 4 : record_offset + 8], "little")
                bone_hash = int.from_bytes(data[bone_offset : bone_offset + 4], "little")
                flags = int.from_bytes(data[bone_offset + 4 : bone_offset + 8], "little")
                colliders.append(
                    {
                        "index": index,
                        "record_offset": record_offset,
                        "collider_hash": f"{collider_hash:08x}",
                        "collider_name": thin_names.get(collider_hash),
                        "transform_index": transform_indices.get(collider_hash),
                        "property_hash": f"{property_hash:08x}",
                        "property_name": thin_names.get(property_hash),
                        "bone_hash": f"{bone_hash:08x}",
                        "bone_name": sdk.Global_BoneNames.get(bone_hash) or thin_names.get(bone_hash),
                        "flags": flags,
                    }
                )
            result[label]["collider_count"] = collider_count
            result[label]["colliders"] = colliders

    print("HD2_GATE_JSON_BEGIN")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("HD2_GATE_JSON_END")


if __name__ == "__main__":
    main()
