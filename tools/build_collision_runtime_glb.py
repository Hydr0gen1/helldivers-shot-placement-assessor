"""Build a browser-only collision GLB from a hydrated HD2 research GLB.

The research asset intentionally retains the extracted render unit, textures,
node hierarchy, and injected collision meshes. The viewer already loads a
separate authentic render GLB, so parsing the duplicate render payload wastes
bandwidth and memory. This tool preserves every node and exact collision mesh
named by the evidence manifest while compacting the binary down to only the
buffer views referenced by those meshes.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from extract_hd2_collision_hulls import aligned_append, read_glb, sha256, write_glb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def primitive_accessor_indices(primitive: dict[str, Any]) -> set[int]:
    if primitive.get("extensions"):
        raise ValueError("Compressed or extended collision primitives are not supported")
    indices = set(primitive.get("attributes", {}).values())
    if "indices" in primitive:
        indices.add(primitive["indices"])
    for target in primitive.get("targets", []):
        indices.update(target.values())
    return indices


def build_runtime_collision(
    document: dict[str, Any], binary: bytearray, collider_names: set[str], source_hash: str
) -> tuple[dict[str, Any], bytearray]:
    runtime = copy.deepcopy(document)
    nodes = runtime.get("nodes", [])
    mesh_indices: set[int] = set()
    found_names: set[str] = set()
    for node in nodes:
        name = node.get("name")
        if name in collider_names:
            found_names.add(name)
            if "mesh" not in node:
                raise ValueError(f"Collision node has no mesh: {name}")
            if "skin" in node:
                raise ValueError(f"Collision node unexpectedly uses a skin: {name}")
            mesh_indices.add(node["mesh"])
        else:
            node.pop("mesh", None)
        node.pop("skin", None)

    missing = sorted(collider_names - found_names)
    if missing:
        raise ValueError(f"Research GLB is missing collision nodes: {missing[:5]}")

    old_meshes = runtime.get("meshes", [])
    mesh_remap = {old: new for new, old in enumerate(sorted(mesh_indices))}
    kept_meshes = [copy.deepcopy(old_meshes[index]) for index in sorted(mesh_indices)]
    accessor_indices: set[int] = set()
    for mesh in kept_meshes:
        for primitive in mesh.get("primitives", []):
            primitive.pop("material", None)
            accessor_indices.update(primitive_accessor_indices(primitive))
    for node in nodes:
        if "mesh" in node:
            node["mesh"] = mesh_remap[node["mesh"]]

    old_accessors = runtime.get("accessors", [])
    accessor_remap = {old: new for new, old in enumerate(sorted(accessor_indices))}
    kept_accessors = [copy.deepcopy(old_accessors[index]) for index in sorted(accessor_indices)]
    view_indices: set[int] = set()
    for accessor in kept_accessors:
        if "bufferView" in accessor:
            view_indices.add(accessor["bufferView"])
        sparse = accessor.get("sparse", {})
        for key in ("indices", "values"):
            if "bufferView" in sparse.get(key, {}):
                view_indices.add(sparse[key]["bufferView"])
    for mesh in kept_meshes:
        for primitive in mesh.get("primitives", []):
            primitive["attributes"] = {
                key: accessor_remap[value] for key, value in primitive.get("attributes", {}).items()
            }
            if "indices" in primitive:
                primitive["indices"] = accessor_remap[primitive["indices"]]
            for target in primitive.get("targets", []):
                for key, value in list(target.items()):
                    target[key] = accessor_remap[value]

    old_views = runtime.get("bufferViews", [])
    view_remap = {old: new for new, old in enumerate(sorted(view_indices))}
    compact = bytearray()
    kept_views: list[dict[str, Any]] = []
    for index in sorted(view_indices):
        view = copy.deepcopy(old_views[index])
        if view.get("buffer", 0) != 0:
            raise ValueError("Only single-buffer GLBs are supported")
        start = view.get("byteOffset", 0)
        payload = bytes(binary[start : start + view["byteLength"]])
        offset, _ = aligned_append(compact, payload)
        view["buffer"] = 0
        view["byteOffset"] = offset
        kept_views.append(view)
    for accessor in kept_accessors:
        if "bufferView" in accessor:
            accessor["bufferView"] = view_remap[accessor["bufferView"]]
        sparse = accessor.get("sparse", {})
        for key in ("indices", "values"):
            if "bufferView" in sparse.get(key, {}):
                sparse[key]["bufferView"] = view_remap[sparse[key]["bufferView"]]

    runtime["meshes"] = kept_meshes
    runtime["accessors"] = kept_accessors
    runtime["bufferViews"] = kept_views
    runtime["buffers"] = [{"byteLength": len(compact)}]
    for key in (
        "animations",
        "images",
        "materials",
        "samplers",
        "skins",
        "textures",
        "extensions",
        "extensionsRequired",
        "extensionsUsed",
    ):
        runtime.pop(key, None)
    runtime.setdefault("asset", {}).setdefault("extras", {})["hd2RuntimeCollision"] = {
        "sourceSha256": source_hash,
        "hullCount": len(collider_names),
        "renderPayloadRemoved": True,
    }
    return runtime, compact


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    collider_names = {item["nodeName"] for item in manifest.get("colliders", [])}
    if len(collider_names) != manifest.get("hullCount"):
        raise ValueError("Collision manifest contains duplicate or missing node names")
    document, binary = read_glb(args.input)
    runtime, compact = build_runtime_collision(document, binary, collider_names, sha256(args.input))
    write_glb(args.output, runtime, compact)
    hydrated, _ = read_glb(args.output)
    runtime_meta = hydrated.get("asset", {}).get("extras", {}).get("hd2RuntimeCollision", {})
    if runtime_meta.get("hullCount") != manifest.get("hullCount"):
        raise ValueError("Runtime collision output failed its hull-count verification")
    print(f"Built {args.output}: {args.input.stat().st_size} -> {args.output.stat().st_size} bytes")


if __name__ == "__main__":
    main()
