"""Assemble Scout Strider child units on their decoded mount sockets."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from extract_hd2_collision_hulls import read_glb, sha256, strip_texture_payloads, write_glb


AXIS_ROOT_ROTATION = [-0.70710678, 0, 0, 0.70710678]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=Path("assets/models"))
    return parser.parse_args()


def prepare_hitbox(source: Path, output: Path) -> None:
    document, binary = read_glb(source)
    binary = strip_texture_payloads(document, binary)
    document.setdefault("asset", {}).setdefault("extras", {})["hd2MountedHitboxes"] = {
        "sourcePath": str(source.resolve()),
        "sourceSha256": sha256(source),
        "preparedDate": date.today().isoformat(),
    }
    write_glb(output, document, binary)


def mount(
    root: Path,
    *,
    id: str,
    label: str,
    asset_slug: str,
    attach_node: str,
    entity: str,
    axis_root: bool = False,
) -> dict:
    asset = root / f"{asset_slug}-authentic-render.glb"
    hitbox = root / f"{asset_slug}-hitboxes.glb"
    collision = root / f"{asset_slug}-collision.glb"
    prepare_hitbox(collision, hitbox)
    result = {
        "id": id,
        "label": label,
        "asset": asset.name,
        "assetSha256": sha256(asset),
        "attachNode": attach_node,
        "mountEntity": entity,
        "unitResource": entity,
        "hitboxAsset": hitbox.name,
        "hitboxAssetSha256": sha256(hitbox),
        "collisionManifest": f"{asset_slug}-collision.manifest.json",
        "damageManifest": f"{asset_slug}-damage.manifest.json",
    }
    if axis_root:
        result["axisRootRotation"] = AXIS_ROOT_ROTATION
    return result


def main() -> None:
    root = parse_args().output_root.resolve()
    body_document, _ = read_glb(root / "scout-strider-collision-research.glb")
    body_nodes = {node.get("name") for node in body_document.get("nodes", [])}
    required = {"gun_pitch", "turret", "rockets_left", "rockets_right"}
    if missing := sorted(required - body_nodes):
        raise ValueError(f"Scout Strider body is missing decoded mount sockets: {missing}")

    cannon = mount(
        root,
        id="cannon",
        label="Chin cannon",
        asset_slug="scout-strider-cannon",
        attach_node="gun_pitch",
        entity="0x2a346bf4552997e2",
        axis_root=True,
    )
    standard_driver = mount(
        root,
        id="driver",
        label="Scout Strider driver housing",
        asset_slug="scout-strider-driver",
        attach_node="turret",
        entity="0xee00bfe8ff769f70",
    )
    reinforced_driver = mount(
        root,
        id="armored-driver",
        label="Reinforced driver housing",
        asset_slug="reinforced-scout-strider-driver",
        attach_node="turret",
        entity="0xd3cd6f0ca83bb51e",
    )
    left_rockets = mount(
        root,
        id="left-rockets",
        label="Left rocket rail",
        asset_slug="reinforced-scout-strider-rockets",
        attach_node="rockets_left",
        entity="0xa8173fba5dec35c3",
    )
    left_rockets["unitResource"] = "0xe5b14182b25f7f7d"
    right_rockets = dict(left_rockets)
    right_rockets.update(
        {
            "id": "right-rockets",
            "label": "Right rocket rail",
            "attachNode": "rockets_right",
            "mountEntity": "0x397fb7e4883af100",
            "unitResource": "0xe5b14182b25f7f7d",
        }
    )

    manifests = {
        "scout-strider-mounted-units.manifest.json": ("Scout Strider", [cannon, standard_driver]),
        "reinforced-scout-strider-mounted-units.manifest.json": (
            "Reinforced Scout Strider",
            [dict(cannon), reinforced_driver, left_rockets, right_rockets],
        ),
    }
    for filename, (enemy, mounts) in manifests.items():
        payload = {
            "schemaVersion": 1,
            "extractionDate": date.today().isoformat(),
            "enemy": enemy,
            "assemblyConfidence": "verified-mount-component-join",
            "mounts": mounts,
            "authenticShaderBakes": sorted({item["asset"] for item in mounts}),
            "viewerMaterialApproximations": {item["asset"]: [] for item in mounts},
            "notes": [
                "All child paths and sockets are decoded directly from MountComponentData.",
                "The cannon, driver housing, and rocket rails use exact game Havok collision geometry and their own HealthComponents.",
                "All visible child units use intact Filediver accurate-shader bakes; no destroyed variants or targeting proxies are included.",
            ],
        }
        (root / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("Prepared exact Scout Strider and Reinforced Scout Strider assemblies")


if __name__ == "__main__":
    main()
