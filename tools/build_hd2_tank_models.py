"""Prepare Automaton tank turret assemblies for the local 3D viewer.

The three combat tanks share the same game-derived hull unit and mount a
different destroyable turret at the decoded ``attach_turret`` socket.  This
tool keeps the render units, collision hulls, and HealthComponent mappings as
separate evidence files while producing cache-safe assembly manifests.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

from extract_hd2_collision_hulls import read_glb, sha256


TURRETS = (
    {
        "enemy": "Annihilator Tank",
        "slug": "annihilator-tank",
        "id": "heavy-cannon-turret",
        "label": "Heavy cannon turret",
        "source": "content/fac_cyborgs/turrets/cyborg_tank_turret_cannon/cyborg_tank_turret_cannon.unit.glb",
        "asset": "automaton-heavy-cannon-turret.glb",
        "authenticAsset": "automaton-heavy-cannon-turret-authentic-render.glb",
        "hitboxAsset": "automaton-heavy-cannon-turret-collision-research.glb",
        "collisionManifest": "automaton-heavy-cannon-turret-collision-research.manifest.json",
        "damageManifest": "automaton-heavy-cannon-turret-damage-zones.manifest.json",
        "mountEntity": "content/fac_cyborgs/turrets/cyborg_tank_turret_cannon/cyborg_tank_turret_heavycannon",
    },
    {
        "enemy": "Shredder Tank",
        "slug": "shredder-tank",
        "id": "quad-autocannon-turret",
        "label": "Quad autocannon turret",
        "source": "content/fac_cyborgs/turrets/cyborg_tank_turret_autocannons/cyborg_tank_turret_autocannons.unit.glb",
        "asset": "automaton-shredder-turret.glb",
        "authenticAsset": "automaton-shredder-turret-authentic-render.glb",
        "hitboxAsset": "automaton-shredder-turret-collision-research.glb",
        "collisionManifest": "automaton-shredder-turret-collision-research.manifest.json",
        "damageManifest": "automaton-shredder-turret-damage-zones.manifest.json",
        "mountEntity": "content/fac_cyborgs/turrets/cyborg_tank_turret_autocannons/cyborg_tank_turret_autocannons",
    },
    {
        "enemy": "Barrager Tank",
        "slug": "barrager-tank",
        "id": "rocket-launcher-turret",
        "label": "Rocket launcher turret",
        "source": "content/fac_cyborgs/turrets/cyborg_tank_turret_rocketlauncher/cyborg_tank_turret_rocketlauncher.unit.glb",
        "asset": "automaton-barrager-turret.glb",
        "authenticAsset": "automaton-barrager-turret-authentic-render.glb",
        "hitboxAsset": "automaton-barrager-turret-collision-research.glb",
        "collisionManifest": "automaton-barrager-turret-collision-research.manifest.json",
        "damageManifest": "automaton-barrager-turret-damage-zones.manifest.json",
        "mountEntity": "content/fac_cyborgs/turrets/cyborg_tank_turret_rocketlauncher/cyborg_tank_turret_rocketlauncher",
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract-root", type=Path, required=True)
    parser.add_argument("--tank-glb", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("assets/models"))
    parser.add_argument(
        "--authentic-root",
        type=Path,
        help="Directory containing Filediver shader-baked intact turret GLBs",
    )
    return parser.parse_args()


def install_authentic_render(source: Path, output: Path) -> None:
    document, _ = read_glb(source)
    baked = [
        material
        for material in document.get("materials", [])
        if material.get("extras", {}).get("hd2BrowserMaterial") == "filediver-accurate-shader-bake"
    ]
    mesh_nodes = [node for node in document.get("nodes", []) if "mesh" in node]
    alternate_meshes = [
        node.get("name", "")
        for node in mesh_nodes
        if any(token in node.get("name", "").lower() for token in ("damaged", "destroyed"))
    ]
    if not baked or not document.get("images") or alternate_meshes:
        raise ValueError(f"Authentic turret render failed its intact shader-bake gate: {source}")
    shutil.copyfile(source, output)


def main() -> None:
    args = parse_args()
    extract_root = args.extract_root.resolve()
    tank_glb = args.tank_glb.resolve()
    output_root = args.output_root.resolve()
    authentic_root = args.authentic_root.resolve() if args.authentic_root else None
    output_root.mkdir(parents=True, exist_ok=True)

    tank_document, _ = read_glb(tank_glb)
    tank_nodes = {node.get("name") for node in tank_document.get("nodes", [])}
    if "attach_turret" not in tank_nodes:
        raise ValueError("Automaton tank GLB is missing the decoded attach_turret socket")

    for turret in TURRETS:
        source = extract_root / Path(turret["source"])
        asset = output_root / turret["asset"]
        authentic = authentic_root / turret["authenticAsset"] if authentic_root else None
        if authentic and authentic.is_file():
            install_authentic_render(authentic, asset)
            approximated = []
        else:
            raise FileNotFoundError(
                f"Authentic Filediver shader bake required for {turret['enemy']}: "
                f"{authentic or turret['authenticAsset']}"
            )
        hitbox_asset = output_root / turret["hitboxAsset"]
        collision_manifest = output_root / turret["collisionManifest"]
        damage_manifest = output_root / turret["damageManifest"]
        for required in (hitbox_asset, collision_manifest, damage_manifest):
            if not required.is_file():
                raise FileNotFoundError(f"Missing prepared tank evidence: {required}")

        mount = {
            "id": turret["id"],
            "label": turret["label"],
            "asset": turret["asset"],
            "assetSha256": sha256(asset),
            "attachNode": "attach_turret",
            "mountEntity": turret["mountEntity"],
            "unitResource": turret["source"].removesuffix(".unit.glb"),
            "hitboxAsset": turret["hitboxAsset"],
            "hitboxAssetSha256": sha256(hitbox_asset),
            "collisionManifest": turret["collisionManifest"],
            "damageManifest": turret["damageManifest"],
            # Blender's glTF exporter rebases the skinned Filediver unit from
            # Stingray Z-up into glTF Y-up. Undo that rebase inside the decoded
            # attach_turret socket, matching the verified Factory cannon path.
            "axisRootRotation": [-0.70710678, 0, 0, 0.70710678],
        }
        manifest = {
            "schemaVersion": 1,
            "extractionDate": date.today().isoformat(),
            "enemy": turret["enemy"],
            "assemblyConfidence": "verified-mount-component-join",
            "sources": {
                "tankUnitGlb": {"path": str(tank_glb), "sha256": sha256(tank_glb)},
                "turretUnitGlb": {"path": str(source), "sha256": sha256(source)},
                "authenticTurretGlb": {"path": str(authentic), "sha256": sha256(authentic)},
            },
            "mounts": [mount],
            "authenticShaderBakes": [asset.name],
            "viewerMaterialApproximations": {asset.name: approximated},
            "notes": [
                "The tank hull and turret resource are joined at the decoded attach_turret socket.",
                "The mounted turret uses its exact decoded Havok collision geometry; no hand-authored hitbox proxy is used.",
                "Health, armor, durability, and damage-zone assignments come from the mounted turret HealthComponent.",
                "The visible turret is an intact Filediver accurate-shader bake; damaged and destroyed render variants are excluded.",
                "Unassigned physics colliders remain visible as geometry but use the turret default damage zone only when selected as a mounted component.",
            ],
        }
        target = output_root / f"{turret['slug']}-mounted-units.manifest.json"
        target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Prepared {turret['enemy']} turret assembly in {target}")


if __name__ == "__main__":
    main()
