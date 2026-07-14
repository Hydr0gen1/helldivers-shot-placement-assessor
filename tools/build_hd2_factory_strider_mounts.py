"""Prepare Factory Strider mounted-weapon GLBs for the local 3D viewer.

The body unit references both chin guns and the dorsal cannon as separate
mounted units. This tool preserves those game-derived meshes and materials,
applies the viewer-safe material fallback used by the collision pipeline, and
writes the exact MountComponentData attachment manifest.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from extract_hd2_collision_hulls import (
    prepare_viewer_materials,
    read_glb,
    sha256,
    strip_texture_payloads,
    write_glb,
)


MOUNTS = (
    {
        "id": "left-chin-gatling",
        "label": "Left chin gatling gun",
        "asset": "factory-strider-chin-gatling.glb",
        "attachNode": "Bone_8289f414",
        "mountEntity": "0x3aafba89b53b0f63",
        "unitResource": "0x48c91e42b9f16512",
    },
    {
        "id": "right-chin-gatling",
        "label": "Right chin gatling gun",
        "asset": "factory-strider-chin-gatling.glb",
        "attachNode": "Bone_8ca4818f",
        "mountEntity": "0x390e6b3d2f26bd70",
        "unitResource": "0x48c91e42b9f16512",
    },
    {
        "id": "dorsal-cannon",
        "label": "Dorsal cannon turret",
        "asset": "factory-strider-dorsal-cannon.glb",
        "attachNode": "attach_turret",
        "mountEntity": "content/fac_cyborgs/turrets/cyborg_big_walker_turret_cannon/cyborg_big_walker_turret_cannon",
        "unitResource": "content/fac_cyborgs/turrets/cyborg_big_walker_turret_cannon/cyborg_big_walker_turret_cannon",
    },
)


# The mounted physics resources encode broad Havok capsules.  Those volumes are
# useful for vehicle collision, but they are a poor visual proxy for the flat,
# segmented damage actors used on comparable HD2 weapons.  Keep the mined
# resources as evidence and derive conservative box proxies for targeting from
# the verified Gatekeeper gun-cover and War Strider turret collider patterns.
VIEWER_HITBOX_PROXIES = {
    "chin": {
        "mode": "comparative-box-proxy",
        "confidence": "inferred-from-game-colliders",
        "analogs": [
            {
                "enemy": "Gatekeeper",
                "parts": "left/right gun covers",
                "shape": "paired elongated convex boxes",
            },
            {
                "enemy": "War Strider",
                "parts": "turret damage actors",
                "shape": "box",
            },
        ],
        "records": {
            "0": {"label": "receiver", "boxScale": [0.55, 0.55, 0.60]},
            "1": {"label": "barrel cluster", "boxScale": [0.65, 0.85, 0.65]},
        },
    },
    "dorsal": {
        "mode": "comparative-box-proxy",
        "confidence": "inferred-from-game-colliders",
        "analogs": [
            {
                "enemy": "War Strider",
                "parts": "turret damage actors",
                "shape": "box",
            },
            {
                "enemy": "Gatekeeper",
                "parts": "weapon cover and muzzle actors",
                "shape": "elongated convex boxes",
            },
        ],
        "records": {
            "0": {
                "label": "turret housing",
                "renderNode": "g_turret_default",
                "boxScale": [0.90, 0.92, 0.90],
            },
            "1": {
                "label": "barrel assembly",
                "renderNode": "g_turret_gun",
                "boxScale": [0.45, 0.50, 0.88],
            },
            "2": {
                "label": "rotating base",
                "renderNode": "g_turret_default",
                "boxScale": [0.72, 0.24, 0.72],
                "boxOffset": [0.0, -0.52, 0.0],
            },
        },
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--factory-glb", type=Path, required=True)
    parser.add_argument("--chin-unit-glb", type=Path, required=True)
    parser.add_argument("--dorsal-cannon-unit-glb", type=Path, required=True)
    parser.add_argument(
        "--dorsal-authentic-glb",
        type=Path,
        help="Optional LUT/decal-baked cannon from bake_hd2_authentic_render.py",
    )
    parser.add_argument("--chin-collision-glb", type=Path)
    parser.add_argument("--chin-collision-manifest", type=Path)
    parser.add_argument("--chin-damage-manifest", type=Path)
    parser.add_argument("--dorsal-collision-glb", type=Path)
    parser.add_argument("--dorsal-collision-manifest", type=Path)
    parser.add_argument("--dorsal-damage-manifest", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("assets/models"))
    return parser.parse_args()


def prepare(source: Path, output: Path) -> list[int]:
    document, binary = read_glb(source)
    approximated = prepare_viewer_materials(document)
    document.setdefault("asset", {}).setdefault("extras", {})["hd2MountedUnit"] = {
        "sourcePath": str(source.resolve()),
        "sourceSha256": sha256(source),
        "preparedDate": date.today().isoformat(),
    }
    write_glb(output, document, binary)
    return approximated


def prepare_hitboxes(source: Path, output: Path) -> None:
    document, binary = read_glb(source)
    binary = strip_texture_payloads(document, binary)
    document.setdefault("asset", {}).setdefault("extras", {})["hd2MountedHitboxes"] = {
        "sourcePath": str(source.resolve()),
        "sourceSha256": sha256(source),
        "preparedDate": date.today().isoformat(),
    }
    write_glb(output, document, binary)


def prepare_json(source: Path, output: Path, asset: Path) -> None:
    document = json.loads(source.read_text(encoding="utf-8"))
    document["preparedOutput"] = {
        "path": output.name,
        "hitboxAsset": asset.name,
        "hitboxAssetSha256": sha256(asset),
    }
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    factory = args.factory_glb.resolve()
    chin = args.chin_unit_glb.resolve()
    cannon = args.dorsal_cannon_unit_glb.resolve()
    dorsal_authentic = args.dorsal_authentic_glb.resolve() if args.dorsal_authentic_glb else None
    hitbox_inputs = {
        "chin": (
            args.chin_collision_glb,
            args.chin_collision_manifest,
            args.chin_damage_manifest,
        ),
        "dorsal": (
            args.dorsal_collision_glb,
            args.dorsal_collision_manifest,
            args.dorsal_damage_manifest,
        ),
    }
    supplied_hitboxes = [value for values in hitbox_inputs.values() for value in values if value]
    if supplied_hitboxes and len(supplied_hitboxes) != 6:
        raise ValueError("Mounted hitbox export requires both collision GLBs and all four manifests")
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    factory_document, _ = read_glb(factory)
    factory_nodes = {node.get("name") for node in factory_document.get("nodes", [])}
    missing = sorted({mount["attachNode"] for mount in MOUNTS} - factory_nodes)
    if missing:
        raise ValueError(f"Factory Strider GLB is missing mount nodes: {missing}")

    chin_output = output_root / "factory-strider-chin-gatling.glb"
    cannon_output = output_root / "factory-strider-dorsal-cannon.glb"
    approximated = {chin_output.name: prepare(chin, chin_output)}
    authentic_bakes: list[str] = []
    if dorsal_authentic:
        dorsal_document, dorsal_binary = read_glb(dorsal_authentic)
        if not any(
            material.get("extras", {}).get("hd2BrowserMaterial") == "filediver-accurate-shader-bake"
            for material in dorsal_document.get("materials", [])
        ):
            raise ValueError("--dorsal-authentic-glb is not an HD2 accurate shader bake")
        write_glb(cannon_output, dorsal_document, dorsal_binary)
        approximated[cannon_output.name] = []
        authentic_bakes.append(cannon_output.name)
    else:
        approximated[cannon_output.name] = prepare(cannon, cannon_output)
    hitbox_outputs = {}
    if supplied_hitboxes:
        for key, values in hitbox_inputs.items():
            collision_source, collision_manifest_source, damage_manifest_source = (
                value.resolve() for value in values
            )
            stem = f"factory-strider-{'chin-gatling' if key == 'chin' else 'dorsal-cannon'}"
            hitbox_asset = output_root / f"{stem}-hitboxes.glb"
            collision_manifest = output_root / f"{stem}-collision.manifest.json"
            damage_manifest = output_root / f"{stem}-damage.manifest.json"
            prepare_hitboxes(collision_source, hitbox_asset)
            prepare_json(collision_manifest_source, collision_manifest, hitbox_asset)
            prepare_json(damage_manifest_source, damage_manifest, hitbox_asset)
            hitbox_outputs[key] = {
                "hitboxAsset": hitbox_asset.name,
                "hitboxAssetSha256": sha256(hitbox_asset),
                "collisionManifest": collision_manifest.name,
                "damageManifest": damage_manifest.name,
            }
    prepared_mounts = []
    for mount in MOUNTS:
        prepared = {
            **mount,
            "assetSha256": sha256(output_root / mount["asset"]),
        }
        if dorsal_authentic and mount["id"] == "dorsal-cannon":
            # Blender's Y-up armature export retains the articulated hierarchy
            # but rebases its weapon-local axes. This socket-local correction
            # restores the game's forward (-Z) barrel direction.
            prepared["axisRootRotation"] = [-0.70710678, 0, 0, 0.70710678]
        hitbox_key = "dorsal" if mount["id"] == "dorsal-cannon" else "chin"
        if hitbox_key in hitbox_outputs:
            prepared.update(hitbox_outputs[hitbox_key])
            prepared["viewerHitboxProxy"] = VIEWER_HITBOX_PROXIES[hitbox_key]
        prepared_mounts.append(prepared)

    manifest = {
        "schemaVersion": 1,
        "extractionDate": date.today().isoformat(),
        "enemy": "Factory Strider",
        "assemblyConfidence": "verified-mount-component-join",
        "sources": {
            "factoryUnitGlb": {"path": str(factory), "sha256": sha256(factory)},
            "chinGunUnitGlb": {"path": str(chin), "sha256": sha256(chin)},
            "dorsalCannonUnitGlb": {"path": str(cannon), "sha256": sha256(cannon)},
            "mountedHitboxSources": {
                key: {
                    "collisionGlb": {"path": str(values[0].resolve()), "sha256": sha256(values[0].resolve())},
                    "collisionManifest": {"path": str(values[1].resolve()), "sha256": sha256(values[1].resolve())},
                    "damageManifest": {"path": str(values[2].resolve()), "sha256": sha256(values[2].resolve())},
                }
                for key, values in hitbox_inputs.items()
                if supplied_hitboxes
            },
        },
        "mounts": prepared_mounts,
        "viewerMaterialApproximations": approximated,
        "authenticShaderBakes": authentic_bakes,
        "notes": [
            "Attachment nodes and child unit references come from decoded MountComponentData.",
            "The two chin guns are separate instances of the same unit resource.",
            "Mounted collision resources remain separate from the base-unit collision/damage manifest.",
            "Mounted targeting uses comparative box proxies derived from verified Gatekeeper gun-cover and War Strider turret collider patterns; the underlying Havok resources remain preserved.",
            "Unassigned mounted colliders use their HealthComponent default damageable zone.",
            "Pass --dorsal-authentic-glb to preserve Filediver's reconstructed LUT/decal material.",
        ],
    }
    manifest_path = output_root / "factory-strider-mounted-units.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(MOUNTS)} Factory Strider mounts in {output_root}")


if __name__ == "__main__":
    main()
