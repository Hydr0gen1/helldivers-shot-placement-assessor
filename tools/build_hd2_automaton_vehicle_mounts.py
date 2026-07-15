"""Assemble verified Vox Engine and War Strider mounted weapons.

The parent units keep their child weapons in MountComponentData.  Filediver
exports those children separately, so the browser viewer must join them back to
the decoded socket without baking or guessing a world-space transform.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from extract_hd2_collision_hulls import read_glb, sha256, strip_texture_payloads, write_glb


VOX_MOUNTS = (
    ("left-minigun", "Left minigun", "l_gattling_socket1", "0xf2881f5807348116", "0x48c91e42b9f16512", "left-gatling"),
    ("right-minigun", "Right minigun", "r_gattling_socket1", "0x356de4a7808ef3e3", "0x48c91e42b9f16512", "right-gatling"),
    ("left-side-cannon", "Left side cannon", "l_cannon_socket", "0x611ba777783b08a2", "content/fac_cyborgs/turrets/cyborg_big_walker_turret_cannon/cyborg_big_walker_turret_cannon", "heavy-cannon"),
    ("right-side-cannon", "Right side cannon", "r_cannon_socket", "0x611ba777783b08a2", "content/fac_cyborgs/turrets/cyborg_big_walker_turret_cannon/cyborg_big_walker_turret_cannon", "heavy-cannon"),
)

WAR_MOUNTS = (
    ("left-cannon", "Left cannon", "attach_left_gun", "0x8372619b2702d743", "0x8372619b2702d743", "left-cannon"),
    ("right-cannon", "Right cannon", "attach_right_gun", "0x9ab036439f74c115", "0x9ab036439f74c115", "right-cannon"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vox-unit-glb", type=Path, required=True)
    parser.add_argument("--war-unit-glb", type=Path, required=True)
    parser.add_argument("--gatling-render-glb", type=Path, required=True)
    parser.add_argument("--gatling-collision-glb", type=Path, required=True)
    parser.add_argument("--gatling-collision-manifest", type=Path, required=True)
    parser.add_argument("--vox-left-gatling-damage-manifest", type=Path, required=True)
    parser.add_argument("--vox-right-gatling-damage-manifest", type=Path, required=True)
    parser.add_argument("--heavy-cannon-render-glb", type=Path, required=True)
    parser.add_argument("--heavy-cannon-collision-glb", type=Path, required=True)
    parser.add_argument("--heavy-cannon-collision-manifest", type=Path, required=True)
    parser.add_argument("--vox-heavy-cannon-damage-manifest", type=Path, required=True)
    parser.add_argument("--war-left-render-glb", type=Path, required=True)
    parser.add_argument("--war-left-collision-glb", type=Path, required=True)
    parser.add_argument("--war-left-collision-manifest", type=Path, required=True)
    parser.add_argument("--war-left-damage-manifest", type=Path, required=True)
    parser.add_argument("--war-right-render-glb", type=Path, required=True)
    parser.add_argument("--war-right-collision-glb", type=Path, required=True)
    parser.add_argument("--war-right-collision-manifest", type=Path, required=True)
    parser.add_argument("--war-right-damage-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("assets/models"))
    return parser.parse_args()


def glb_nodes(path: Path) -> set[str]:
    document, _ = read_glb(path)
    return {node.get("name", "") for node in document.get("nodes", [])}


def install_glb(source: Path, output: Path, *, hitbox: bool = False) -> None:
    document, binary = read_glb(source)
    if hitbox:
        binary = strip_texture_payloads(document, binary)
    document.setdefault("asset", {}).setdefault("extras", {})[
        "hd2MountedHitboxes" if hitbox else "hd2MountedUnit"
    ] = {
        "sourcePath": str(source.resolve()),
        "sourceSha256": sha256(source),
        "preparedDate": date.today().isoformat(),
    }
    write_glb(output, document, binary)


def install_manifest(source: Path, output: Path, hitbox_asset: Path) -> None:
    data = json.loads(source.read_text(encoding="utf-8"))
    data["preparedOutput"] = {
        "path": output.name,
        "hitboxAsset": hitbox_asset.name,
        "hitboxAssetSha256": sha256(hitbox_asset),
    }
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def authentic(path: Path) -> bool:
    document, _ = read_glb(path)
    return any(
        material.get("extras", {}).get("hd2BrowserMaterial") == "filediver-accurate-shader-bake"
        for material in document.get("materials", [])
    )


def main() -> None:
    args = parse_args()
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    vox_unit = args.vox_unit_glb.resolve()
    war_unit = args.war_unit_glb.resolve()

    for unit, mounts in ((vox_unit, VOX_MOUNTS), (war_unit, WAR_MOUNTS)):
        missing = sorted({mount[2] for mount in mounts} - glb_nodes(unit))
        if missing:
            raise ValueError(f"{unit.name} is missing decoded mount sockets: {missing}")

    render_inputs = {
        # The hashed minigun unit uses Filediver's ordinary embedded PBR
        # materials and has no reconstructable HD2 LUT shader to bake.
        "vox-engine-minigun.glb": (args.gatling_render_glb.resolve(), False),
        "vox-engine-side-cannon.glb": (args.heavy_cannon_render_glb.resolve(), True),
        "war-strider-left-cannon.glb": (args.war_left_render_glb.resolve(), True),
        "war-strider-right-cannon.glb": (args.war_right_render_glb.resolve(), True),
    }
    authentic_assets = []
    for name, (source, requires_bake) in render_inputs.items():
        if requires_bake and not authentic(source):
            raise ValueError(f"Mounted render is not an authentic shader bake: {source}")
        install_glb(source, output / name)
        if requires_bake:
            authentic_assets.append(name)

    evidence = {
        "gatling": (args.gatling_collision_glb, args.gatling_collision_manifest),
        "heavy-cannon": (args.heavy_cannon_collision_glb, args.heavy_cannon_collision_manifest),
        "left-cannon": (args.war_left_collision_glb, args.war_left_collision_manifest),
        "right-cannon": (args.war_right_collision_glb, args.war_right_collision_manifest),
    }
    for key, (glb_source, manifest_source) in evidence.items():
        hitbox = output / f"{'vox-engine-' if key in {'gatling', 'heavy-cannon'} else 'war-strider-'}{key}-hitboxes.glb"
        collision = output / hitbox.name.replace("-hitboxes.glb", "-collision.manifest.json")
        install_glb(glb_source.resolve(), hitbox, hitbox=True)
        install_manifest(manifest_source.resolve(), collision, hitbox)

    damage_sources = {
        "vox-engine-left-gatling-damage.manifest.json": args.vox_left_gatling_damage_manifest,
        "vox-engine-right-gatling-damage.manifest.json": args.vox_right_gatling_damage_manifest,
        "vox-engine-heavy-cannon-damage.manifest.json": args.vox_heavy_cannon_damage_manifest,
        "war-strider-left-cannon-damage.manifest.json": args.war_left_damage_manifest,
        "war-strider-right-cannon-damage.manifest.json": args.war_right_damage_manifest,
    }
    for name, source in damage_sources.items():
        key = (
            "gatling" if "gatling" in name else
            "heavy-cannon" if "heavy" in name else
            "left-cannon" if "left" in name else "right-cannon"
        )
        hitbox = output / f"{'vox-engine-' if name.startswith('vox') else 'war-strider-'}{key}-hitboxes.glb"
        install_manifest(source.resolve(), output / name, hitbox)

    vox_assets = {
        "left-gatling": ("vox-engine-minigun.glb", "vox-engine-gatling-hitboxes.glb", "vox-engine-gatling-collision.manifest.json", "vox-engine-left-gatling-damage.manifest.json", False),
        "right-gatling": ("vox-engine-minigun.glb", "vox-engine-gatling-hitboxes.glb", "vox-engine-gatling-collision.manifest.json", "vox-engine-right-gatling-damage.manifest.json", False),
        "heavy-cannon": ("vox-engine-side-cannon.glb", "vox-engine-heavy-cannon-hitboxes.glb", "vox-engine-heavy-cannon-collision.manifest.json", "vox-engine-heavy-cannon-damage.manifest.json", True),
    }
    war_assets = {
        "left-cannon": ("war-strider-left-cannon.glb", "war-strider-left-cannon-hitboxes.glb", "war-strider-left-cannon-collision.manifest.json", "war-strider-left-cannon-damage.manifest.json", True),
        "right-cannon": ("war-strider-right-cannon.glb", "war-strider-right-cannon-hitboxes.glb", "war-strider-right-cannon-collision.manifest.json", "war-strider-right-cannon-damage.manifest.json", True),
    }

    def make_mounts(rows, assets):
        result = []
        for mount_id, label, socket, entity, resource, key in rows:
            asset, hitbox, collision, damage, rebased = assets[key]
            item = {
                "id": mount_id, "label": label, "asset": asset,
                "assetSha256": sha256(output / asset), "attachNode": socket,
                "mountEntity": entity, "unitResource": resource,
                "hitboxAsset": hitbox, "hitboxAssetSha256": sha256(output / hitbox),
                "collisionManifest": collision, "damageManifest": damage,
            }
            if rebased:
                item["axisRootRotation"] = [-0.70710678, 0, 0, 0.70710678]
            result.append(item)
        return result

    common_notes = [
        "Attachment sockets, child entities, and unit resources come from decoded MountComponentData.",
        "Mounted hitboxes are exact decoded Havok collision geometry; no targeting proxy is substituted.",
        "Visible mounted units are intact Filediver accurate-shader bakes.",
        "Unassigned colliders use the mounted HealthComponent default damageable zone.",
    ]
    manifests = (
        ("vox-engine-mounted-units.manifest.json", "Vox Engine", vox_unit, make_mounts(VOX_MOUNTS, vox_assets)),
        ("war-strider-mounted-units.manifest.json", "War Strider", war_unit, make_mounts(WAR_MOUNTS, war_assets)),
    )
    for filename, enemy, parent, mounts in manifests:
        manifest = {
            "schemaVersion": 1, "extractionDate": date.today().isoformat(), "enemy": enemy,
            "assemblyConfidence": "verified-mount-component-join",
            "sources": {"parentUnitGlb": {"path": str(parent), "sha256": sha256(parent)}},
            "mounts": mounts,
            "authenticShaderBakes": sorted({mount["asset"] for mount in mounts if mount["asset"] in authentic_assets}),
            "filediverEmbeddedMaterials": sorted({mount["asset"] for mount in mounts if mount["asset"] not in authentic_assets}),
            "viewerMaterialApproximations": {}, "notes": common_notes,
        }
        (output / filename).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Prepared {len(mounts)} verified mounts for {enemy}")


if __name__ == "__main__":
    main()
