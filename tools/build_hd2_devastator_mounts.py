"""Build exact mounted equipment for the HD2 Devastator 3D models.

The Devastator body units do not embed their hand-held equipment.  This tool
copies the game-derived weapon render units, extracts the Heavy Devastator's
separate destroyable shield collision, maps its HealthComponent, and writes
viewer manifests using the exact MountComponentData attachment sockets.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from extract_hd2_collision_hulls import (
    prepare_viewer_materials,
    read_glb,
    sha256,
    strip_texture_payloads,
    write_glb,
)


STANDARD_RIFLE = "content/fac_cyborgs/equipment/weapons/soldier_standard_rifle/soldier_standard_rifle"
MACHINEGUN = "content/fac_cyborgs/equipment/weapons/soldier_machinegun/soldier_machinegun"
SHIELD = "content/fac_cyborgs/equipment/weapons/soldier_shield/soldier_shield"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract-root", type=Path, required=True)
    parser.add_argument("--entities-json", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("assets/models"))
    return parser.parse_args()


def prepare_unit(source: Path, output: Path) -> list[int]:
    document, binary = read_glb(source)
    approximated = prepare_viewer_materials(document)
    document.setdefault("asset", {}).setdefault("extras", {})["hd2MountedUnit"] = {
        "sourcePath": str(source.resolve()),
        "sourceSha256": sha256(source),
        "preparedDate": date.today().isoformat(),
    }
    write_glb(output, document, binary)
    return approximated


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def source_path(root: Path, resource: str, suffix: str) -> Path:
    return (root / Path(resource)).with_suffix(suffix)


def main() -> None:
    args = parse_args()
    extract_root = args.extract_root.resolve()
    entities_json = args.entities_json.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    tools = Path(__file__).resolve().parent

    unit_sources = {
        "devastator-standard-rifle.glb": source_path(extract_root, STANDARD_RIFLE, ".unit.glb"),
        "heavy-devastator-machinegun.glb": source_path(extract_root, MACHINEGUN, ".unit.glb"),
        "heavy-devastator-shield.glb": source_path(extract_root, SHIELD, ".unit.glb"),
    }
    approximations = {
        name: prepare_unit(source, output_root / name)
        for name, source in unit_sources.items()
    }

    shield_collision = output_root / "heavy-devastator-shield-collision.glb"
    shield_collision_manifest = output_root / "heavy-devastator-shield-collision.manifest.json"
    shield_damage_manifest = output_root / "heavy-devastator-shield-damage.manifest.json"
    run(
        [
            sys.executable,
            str(tools / "extract_hd2_collision_hulls.py"),
            "--physics",
            str(source_path(extract_root, SHIELD, ".physics.main")),
            "--unit-glb",
            str(source_path(extract_root, SHIELD, ".unit.glb")),
            "--output",
            str(shield_collision),
            "--manifest",
            str(shield_collision_manifest),
            "--expected-hulls",
            "2",
        ]
    )
    run(
        [
            sys.executable,
            str(tools / "map_hd2_damage_zones.py"),
            "--entities-json",
            str(entities_json),
            "--collision-manifest",
            str(shield_collision_manifest),
            "--output",
            str(shield_damage_manifest),
            "--entity",
            SHIELD,
            "--display-name",
            "Heavy Devastator Shield",
            "--allow-unassigned-colliders",
        ]
    )
    hitbox_asset = output_root / "heavy-devastator-shield-hitboxes.glb"
    hitbox_document, hitbox_binary = read_glb(shield_collision)
    hitbox_binary = strip_texture_payloads(hitbox_document, hitbox_binary)
    hitbox_document.setdefault("asset", {}).setdefault("extras", {})["hd2MountedHitboxes"] = {
        "sourcePath": str(shield_collision),
        "sourceSha256": sha256(shield_collision),
        "preparedDate": date.today().isoformat(),
    }
    write_glb(hitbox_asset, hitbox_document, hitbox_binary)

    common_sources = {
        name: {"path": str(path), "sha256": sha256(path)}
        for name, path in unit_sources.items()
    }
    manifests = {
        "devastator-mounted-units.manifest.json": {
            "enemy": "Devastator",
            "mounts": [
                {
                    "id": "standard-rifle",
                    "label": "Fusion assault gun",
                    "asset": "devastator-standard-rifle.glb",
                    "assetSha256": sha256(output_root / "devastator-standard-rifle.glb"),
                    "attachNode": "attach_r_hand",
                    "mountEntity": STANDARD_RIFLE,
                    "unitResource": STANDARD_RIFLE,
                }
            ],
        },
        "heavy-devastator-mounted-units.manifest.json": {
            "enemy": "Heavy Devastator",
            "mounts": [
                {
                    "id": "machinegun",
                    "label": "Heavy machine gun",
                    "asset": "heavy-devastator-machinegun.glb",
                    "assetSha256": sha256(output_root / "heavy-devastator-machinegun.glb"),
                    "attachNode": "attach_r_hand",
                    "mountEntity": MACHINEGUN,
                    "unitResource": MACHINEGUN,
                },
                {
                    "id": "shield",
                    "label": "Ballistic shield",
                    "asset": "heavy-devastator-shield.glb",
                    "assetSha256": sha256(output_root / "heavy-devastator-shield.glb"),
                    "attachNode": "attach_l_hand",
                    "mountEntity": SHIELD,
                    "unitResource": SHIELD,
                    "hitboxAsset": hitbox_asset.name,
                    "hitboxAssetSha256": sha256(hitbox_asset),
                    "collisionManifest": shield_collision_manifest.name,
                    "damageManifest": shield_damage_manifest.name,
                },
            ],
        },
        "rocket-devastator-mounted-units.manifest.json": {
            "enemy": "Rocket Devastator",
            "mounts": [
                {
                    "id": "standard-rifle",
                    "label": "Fusion assault gun",
                    "asset": "devastator-standard-rifle.glb",
                    "assetSha256": sha256(output_root / "devastator-standard-rifle.glb"),
                    "attachNode": "attach_r_hand",
                    "mountEntity": STANDARD_RIFLE,
                    "unitResource": STANDARD_RIFLE,
                }
            ],
        },
    }
    for filename, body in manifests.items():
        payload = {
            "schemaVersion": 1,
            "extractionDate": date.today().isoformat(),
            "enemy": body["enemy"],
            "assemblyConfidence": "verified-mount-component-join",
            "sources": common_sources,
            "mounts": body["mounts"],
            "authenticShaderBakes": [],
            "viewerMaterialApproximations": approximations,
            "notes": [
                "Mounted equipment paths and sockets come directly from the enemy MountComponentData.",
                "The Heavy Devastator shield uses its separate exact Havok collision and HealthComponent; no proxy geometry is substituted.",
                "Hand-held guns have no HealthComponent and are render-only equipment, not selectable damage zones.",
            ],
        }
        (output_root / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print("Prepared three verified Devastator mounted-equipment assemblies")


if __name__ == "__main__":
    main()
