"""Build a browser-ready render GLB from verified HD2 material swaps.

The source unit geometry is kept byte-for-byte.  Only named material slots are
replaced with materials extracted from the variant entity's
``MaterialSwapComponentData`` references.  Embedded images are deduplicated and
unused base-variant texture payloads are removed from the output.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from extract_hd2_collision_hulls import aligned_append, read_glb, sha256, write_glb


TEXTURE_KEYS = (
    "baseColorTexture",
    "metallicRoughnessTexture",
    "normalTexture",
    "occlusionTexture",
    "emissiveTexture",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit-glb", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--variant-name", required=True)
    parser.add_argument("--entity", required=True)
    parser.add_argument(
        "--swap",
        action="append",
        required=True,
        metavar="SLOT=MATERIAL_GLB",
        help="Exact source material slot prefix and extracted replacement material GLB",
    )
    return parser.parse_args()


def buffer_view_bytes(document: dict, binary: bytearray, index: int) -> bytes:
    view = document["bufferViews"][index]
    start = int(view.get("byteOffset", 0))
    return bytes(binary[start : start + int(view["byteLength"])])


def texture_info_nodes(material: dict):
    pbr = material.get("pbrMetallicRoughness", {})
    for key in ("baseColorTexture", "metallicRoughnessTexture"):
        if key in pbr:
            yield pbr[key]
    for key in ("normalTexture", "occlusionTexture", "emissiveTexture"):
        if key in material:
            yield material[key]


def import_material(
    target: dict,
    target_binary: bytearray,
    source_path: Path,
) -> tuple[dict, dict]:
    source, source_binary = read_glb(source_path)
    if len(source.get("materials", [])) != 1:
        raise ValueError(f"{source_path} must contain exactly one material")

    target.setdefault("bufferViews", [])
    target.setdefault("images", [])
    target.setdefault("samplers", [])
    target.setdefault("textures", [])
    image_by_name = {
        image.get("name"): index
        for index, image in enumerate(target["images"])
        if image.get("name")
    }
    image_map: dict[int, int] = {}
    imported_images: list[str] = []
    for source_index, source_image in enumerate(source.get("images", [])):
        name = source_image.get("name")
        if name and name in image_by_name:
            image_map[source_index] = image_by_name[name]
            continue
        image = copy.deepcopy(source_image)
        if "bufferView" not in image:
            raise ValueError(f"{source_path} contains a non-embedded image")
        payload = buffer_view_bytes(source, source_binary, image["bufferView"])
        byte_offset, byte_length = aligned_append(target_binary, payload)
        image["bufferView"] = len(target["bufferViews"])
        target["bufferViews"].append({
            "buffer": 0,
            "byteOffset": byte_offset,
            "byteLength": byte_length,
        })
        image_map[source_index] = len(target["images"])
        target["images"].append(image)
        if name:
            image_by_name[name] = image_map[source_index]
            imported_images.append(name)

    sampler_map: dict[int, int] = {}
    for source_index, source_sampler in enumerate(source.get("samplers", [])):
        sampler = copy.deepcopy(source_sampler)
        try:
            target_index = target["samplers"].index(sampler)
        except ValueError:
            target_index = len(target["samplers"])
            target["samplers"].append(sampler)
        sampler_map[source_index] = target_index

    texture_map: dict[int, int] = {}
    for source_index, source_texture in enumerate(source.get("textures", [])):
        texture = copy.deepcopy(source_texture)
        if "source" in texture:
            texture["source"] = image_map[texture["source"]]
        if "sampler" in texture:
            texture["sampler"] = sampler_map[texture["sampler"]]
        try:
            target_index = target["textures"].index(texture)
        except ValueError:
            target_index = len(target["textures"])
            target["textures"].append(texture)
        texture_map[source_index] = target_index

    material = copy.deepcopy(source["materials"][0])
    for texture_info in texture_info_nodes(material):
        texture_info["index"] = texture_map[texture_info["index"]]
    return material, {
        "path": str(source_path.resolve()),
        "sha256": sha256(source_path),
        "material": material.get("name"),
        "importedImages": imported_images,
    }


def compact_embedded_resources(document: dict, binary: bytearray) -> bytearray:
    used_textures = {
        int(texture_info["index"])
        for material in document.get("materials", [])
        for texture_info in texture_info_nodes(material)
    }
    texture_map = {old: new for new, old in enumerate(sorted(used_textures))}
    textures = [document["textures"][old] for old in sorted(used_textures)]
    for material in document.get("materials", []):
        for texture_info in texture_info_nodes(material):
            texture_info["index"] = texture_map[int(texture_info["index"])]

    used_images = sorted({int(texture["source"]) for texture in textures if "source" in texture})
    image_map = {old: new for new, old in enumerate(used_images)}
    images = [document["images"][old] for old in used_images]
    for texture in textures:
        if "source" in texture:
            texture["source"] = image_map[int(texture["source"])]

    used_samplers = sorted({int(texture["sampler"]) for texture in textures if "sampler" in texture})
    sampler_map = {old: new for new, old in enumerate(used_samplers)}
    samplers = [document["samplers"][old] for old in used_samplers]
    for texture in textures:
        if "sampler" in texture:
            texture["sampler"] = sampler_map[int(texture["sampler"])]

    document["textures"] = textures
    document["images"] = images
    document["samplers"] = samplers

    used_views = {
        int(accessor["bufferView"])
        for accessor in document.get("accessors", [])
        if "bufferView" in accessor
    }
    used_views.update(int(image["bufferView"]) for image in images if "bufferView" in image)
    view_map = {old: new for new, old in enumerate(sorted(used_views))}
    rebuilt = bytearray()
    views = []
    for old in sorted(used_views):
        view = copy.deepcopy(document["bufferViews"][old])
        payload = buffer_view_bytes(document, binary, old)
        byte_offset, byte_length = aligned_append(rebuilt, payload)
        view["byteOffset"] = byte_offset
        view["byteLength"] = byte_length
        view["buffer"] = 0
        views.append(view)
    for accessor in document.get("accessors", []):
        if "bufferView" in accessor:
            accessor["bufferView"] = view_map[int(accessor["bufferView"])]
    for image in images:
        if "bufferView" in image:
            image["bufferView"] = view_map[int(image["bufferView"])]
    document["bufferViews"] = views
    document["buffers"] = [{"byteLength": len(rebuilt)}]
    return rebuilt


def main() -> None:
    args = parse_args()
    unit_path = args.unit_glb.resolve()
    output = args.output.resolve()
    document, binary = read_glb(unit_path)
    swaps = []
    replaced_indices: set[int] = set()

    for value in args.swap:
        if "=" not in value:
            raise ValueError(f"Invalid --swap {value!r}; expected SLOT=MATERIAL_GLB")
        slot, source_value = value.split("=", 1)
        source_path = Path(source_value).resolve()
        matches = [
            index
            for index, material in enumerate(document.get("materials", []))
            if material.get("name", "").split(" ", 1)[0] == slot
        ]
        if len(matches) != 1:
            raise ValueError(f"Material slot {slot!r} matched {len(matches)} source materials")
        material, evidence = import_material(document, binary, source_path)
        material_index = matches[0]
        document["materials"][material_index] = material
        replaced_indices.add(material_index)
        swaps.append({"slot": slot, "materialIndex": material_index, **evidence})

    primitive_materials = {
        int(primitive["material"])
        for mesh in document.get("meshes", [])
        for primitive in mesh.get("primitives", [])
        if "material" in primitive
    }
    if not replaced_indices.issubset(primitive_materials):
        raise ValueError("One or more swapped material slots are not used by the render mesh")

    binary = compact_embedded_resources(document, binary)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_glb(output, document, binary)
    manifest = {
        "schemaVersion": 1,
        "variant": args.variant_name,
        "entity": args.entity,
        "variantEvidence": "verified-material-swap-component",
        "sourceUnit": {"path": str(unit_path), "sha256": sha256(unit_path)},
        "swaps": swaps,
        "output": {"path": str(output), "sha256": sha256(output)},
        "materialCount": len(document.get("materials", [])),
        "textureCount": len(document.get("textures", [])),
        "embeddedImages": [image.get("name") for image in document.get("images", [])],
    }
    args.manifest.resolve().write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Built {args.variant_name} render with {len(swaps)} verified material swaps: {output}")


if __name__ == "__main__":
    main()
