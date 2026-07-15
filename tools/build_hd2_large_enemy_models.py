"""Regenerate verified large-enemy collision and damage-zone research assets.

The input directory is a Filediver extraction containing each configured unit's
``.unit.glb``, ``.physics.main``, and optional ``.bones.json`` files. This script
does not read or modify the live game installation.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ENEMIES = (
    (
        "hive-lord",
        "Hive Lord",
        "content/fac_bugs/cha_hive_lord/cha_hive_lord",
        True,
        True,
        None,
    ),
    (
        "vox-engine",
        "Vox Engine",
        "content/fac_cyborgs/vehicles/cyborg_siege_engine/cyborg_siege_engine",
        True,
        True,
        None,
    ),
    (
        "dropship",
        "Dropship",
        "content/fac_cyborgs/vehicles/cyborg_dropship/cyborg_dropship",
        False,
        True,
        None,
    ),
    (
        "gunship",
        "Gunship",
        "content/fac_cyborgs/vehicles/cyborg_gunship/cyborg_gunship",
        False,
        False,
        None,
    ),
    ("factory-strider", "Factory Strider", "content/fac_cyborgs/vehicles/cyborg_spawner/cyborg_spawner", True, True, None),
    ("war-strider", "War Strider", "content/fac_cyborgs/vehicles/cyborg_assault_walker/cyborg_assault_walker", True, True, None),
    ("charger", "Charger", "content/fac_bugs/cha_charger/cha_charger", False, True, None),
    ("charger-behemoth", "Charger Behemoth", "content/fac_bugs/cha_charger/cha_charger_tier2", False, True, "content/fac_bugs/cha_charger_bull/cha_charger_bull"),
    ("spore-charger", "Spore Charger", "content/fac_bugs/cha_charger_acid/cha_charger_acid", False, True, None),
    ("rupture-charger", "Rupture Charger", "content/fac_bugs/cha_charger_burrower/cha_charger_burrower", False, True, None),
    ("spore-burst-bile-titan", "Spore Burst Bile Titan", "content/fac_bugs/cha_strider/cha_strider_gloom", False, False, None),
    ("dragonroach", "Dragonroach", "content/fac_bugs/cha_dragon/cha_dragon", False, False, None),
    ("impaler", "Impaler", "content/fac_bugs/cha_impaler/cha_impaler", False, True, None),
    ("harvester", "Harvester", "content/fac_illuminate/cha_tripod/cha_tripod", True, True, None),
    ("veracitor", "Veracitor", "content/fac_illuminate/cha_exomech_melee/cha_exomech_melee", False, False, None),
    ("gatekeeper", "Gatekeeper", "content/fac_illuminate/cha_exomech_ranged/cha_exomech_ranged", False, False, None),
    ("bile-spewer", "Bile Spewer", "content/fac_bugs/cha_boomer/cha_boomer", True, True, None),
    ("fleshmob", "Fleshmob", "content/fac_illuminate/cha_meatglue/cha_meatglue", True, True, None),
    (
        "leviathan",
        "Leviathan",
        "content/fac_illuminate/vehicles/illuminate_war_machine/illuminate_war_machine",
        True,
        True,
        None,
    ),
    (
        "hulk-scorcher",
        "Hulk (Scorcher)",
        "content/fac_cyborgs/cha_lieutenant/cha_lieutenant_assault",
        False,
        True,
        "content/fac_cyborgs/cha_lieutenant_assault/cha_lieutenant_assault",
    ),
    (
        "brood-commander",
        "Brood Commander",
        "content/fac_bugs/cha_warrior_big/cha_warrior_big",
        False,
        True,
        None,
    ),
    (
        "alpha-commander",
        "Alpha Commander",
        "content/fac_bugs/cha_warrior_big/cha_warrior_big_tier2",
        False,
        True,
        None,
    ),
    (
        "devastator",
        "Devastator",
        "content/fac_cyborgs/cha_soldier/cha_soldier",
        False,
        True,
        None,
    ),
    (
        "heavy-devastator",
        "Heavy Devastator",
        "content/fac_cyborgs/cha_soldier/cha_soldier_mg",
        False,
        True,
        "content/fac_cyborgs/cha_soldier/cha_soldier_heavy_weapon",
    ),
    (
        "rocket-devastator",
        "Rocket Devastator",
        "content/fac_cyborgs/cha_soldier/cha_soldier_rpg",
        False,
        True,
        "content/fac_cyborgs/cha_soldier/cha_soldier_rocket",
    ),
    (
        "scout-strider",
        "Scout Strider",
        "content/fac_cyborgs/vehicles/cyborg_walker_scout/cyborg_walker_scout",
        False,
        True,
        None,
    ),
    (
        "berserker",
        "Berserker",
        "content/fac_cyborgs/cha_berserker/cha_berserker",
        True,
        True,
        None,
    ),
    (
        "stalker",
        "Stalker",
        "content/fac_bugs/cha_stalker/cha_stalker",
        True,
        True,
        None,
    ),
    (
        "shrieker",
        "Shrieker",
        "content/fac_bugs/cha_shrieker/cha_shrieker",
        False,
        True,
        None,
    ),
    (
        "overseer",
        "Overseer",
        "content/fac_illuminate/cha_illuminate_guy_staff/cha_illuminate_guy_staff",
        False,
        True,
        None,
    ),
    (
        "elevated-overseer",
        "Elevated Overseer",
        "content/fac_illuminate/cha_jet_champion/cha_jet_champion",
        False,
        True,
        None,
    ),
    (
        "crescent-overseer",
        "Crescent Overseer",
        "content/fac_illuminate/cha_beamer_champion/cha_beamer_champion",
        False,
        True,
        None,
    ),
    (
        "watcher",
        "Watcher",
        "content/fac_illuminate/cha_observer/cha_observer",
        False,
        True,
        None,
    ),
    (
        "stingray",
        "Stingray",
        "content/fac_illuminate/vehicles/illuminate_attack_ship/illuminate_attack_ship",
        True,
        True,
        None,
    ),
    # Small and medium enemy rollout. Each entry keeps its own HealthComponent
    # mapping even when several variants share a skeleton or base render unit.
    (
        "warrior",
        "Warrior",
        "content/fac_bugs/cha_warrior/cha_warrior_tier_2",
        True,
        True,
        "content/fac_bugs/cha_warrior/cha_warrior",
    ),
    (
        "alpha-warrior",
        "Alpha Warrior",
        "content/fac_bugs/cha_warrior/cha_warrior_tier_2_guard",
        True,
        True,
        "content/fac_bugs/cha_warrior/cha_warrior",
    ),
    ("bile-warrior", "Bile Warrior", "content/fac_bugs/cha_warrior_acid/cha_warrior_acid", True, True, None),
    ("rupture-warrior", "Rupture Warrior", "content/fac_bugs/cha_warrior_burrower/cha_warrior_burrower", True, True, None),
    (
        "spore-burst-warrior",
        "Spore Burst Warrior",
        "content/fac_bugs/cha_warrior/cha_warrior_gloom",
        True,
        True,
        "content/fac_bugs/cha_warrior/cha_warrior_gloom_tier_1",
    ),
    ("hive-guard", "Hive Guard", "content/fac_bugs/cha_warrior_plus/cha_warrior_plus", True, True, None),
    (
        "hunter",
        "Hunter",
        "content/fac_bugs/cha_hunter/cha_hunter_tier_2",
        True,
        True,
        "content/fac_bugs/cha_hunter/cha_hunter",
    ),
    ("predator-hunter", "Predator Hunter", "content/fac_bugs/cha_hunter/cha_hunter_tier_3", True, True, "content/fac_bugs/cha_hunter/cha_hunter_tier3"),
    (
        "scavenger",
        "Scavenger",
        "content/fac_bugs/cha_scavenger/cha_scavenger_tier_1",
        True,
        True,
        "content/fac_bugs/cha_scavenger/cha_scavenger",
    ),
    ("pouncer", "Pouncer", "content/fac_bugs/cha_scavenger_predator/cha_scavenger_predator", True, True, None),
    ("bile-spitter", "Bile Spitter", "content/fac_bugs/cha_scavenger_spitter/cha_scavenger_spitter", True, True, None),
    ("nursing-spewer", "Nursing Spewer", "content/fac_bugs/cha_boomer_nurser/cha_boomer_nurser", True, True, None),
    ("rupture-spewer", "Rupture Spewer", "content/fac_bugs/cha_boomer_burrower/cha_boomer_burrower", True, True, None),
    (
        "trooper",
        "Trooper",
        "content/fac_cyborgs/cha_conscript/cha_conscript_base",
        True,
        True,
        "content/fac_cyborgs/cha_conscript/cha_conscript",
    ),
    ("commissar", "Commissar", "content/fac_cyborgs/cha_conscript_commander/cha_conscript_commander", True, True, None),
    (
        "agitator",
        "Agitator",
        "content/fac_cyborgs/cha_cyborg_elite/cha_cyborg_elite",
        True,
        True,
        "content/fac_cyborgs/cha_cyborg_elite/cha_cyborg_elite_rusher",
    ),
    ("radical", "Radical", "content/fac_cyborgs/cha_cyborg_elite/cha_cyborg_elite_rusher", True, True, None),
    ("voteless-medium", "Voteless (Medium)", "content/fac_illuminate/cha_corrupted/cha_corrupted_v2", True, True, None),
    ("obtruder", "Obtruder", "0x34dfd23365472e9e", True, True, None),
)

RAGDOLL_COLLISION_ENEMIES = {
    "hive-lord",
    "dropship",
    "gunship",
    "war-strider",
    "hulk-scorcher",
    "brood-commander",
    "alpha-commander",
    "devastator",
    "heavy-devastator",
    "rocket-devastator",
    "scout-strider",
    "berserker",
    "stalker",
    "bile-spewer",
    "fleshmob",
    "shrieker",
    "overseer",
    "elevated-overseer",
    "crescent-overseer",
    "watcher",
    "stingray",
    "warrior",
    "alpha-warrior",
    "bile-warrior",
    "rupture-warrior",
    "spore-burst-warrior",
    "hive-guard",
    "hunter",
    "predator-hunter",
    "scavenger",
    "pouncer",
    "bile-spitter",
    "nursing-spewer",
    "rupture-spewer",
    "trooper",
    "commissar",
    "agitator",
    "radical",
    "voteless-medium",
    "obtruder",
}
RAGDOLL_ONLY_ENEMIES = {"dropship", "gunship", "stingray"}
LAYERED_COLLISION_ENEMIES = {
    "vox-engine",
    "hive-guard",
    "scavenger",
    "pouncer",
    "bile-spitter",
    "agitator",
    "radical",
}
BONES_SOURCE_OVERRIDES = {
    "heavy-devastator": "content/fac_cyborgs/cha_soldier/cha_soldier.bones.json",
    "rocket-devastator": "content/fac_cyborgs/cha_soldier/cha_soldier.bones.json",
    "warrior": "content/fac_bugs/cha_warrior/cha_warrior.bones.json",
    "alpha-warrior": "content/fac_bugs/cha_warrior/cha_warrior.bones.json",
    "spore-burst-warrior": "content/fac_bugs/cha_warrior/cha_warrior.bones.json",
    "hunter": "content/fac_bugs/cha_hunter/cha_hunter.bones.json",
    "predator-hunter": "content/fac_bugs/cha_hunter/cha_hunter.bones.json",
    "scavenger": "content/fac_bugs/cha_scavenger/cha_scavenger.bones.json",
    "trooper": "content/fac_cyborgs/cha_conscript/cha_conscript.bones.json",
    "commissar": "content/fac_cyborgs/cha_conscript/cha_conscript.bones.json",
    "agitator": "content/fac_cyborgs/cha_cyborg_elite/cha_cyborg_elite.bones.json",
    "radical": "content/fac_cyborgs/cha_cyborg_elite/cha_cyborg_elite.bones.json",
    "voteless-medium": "content/fac_illuminate/cha_corrupted/cha_corrupted.bones.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract-root", type=Path, required=True)
    parser.add_argument("--entities-json", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("assets/models"))
    parser.add_argument("--only", action="append", choices=[enemy[0] for enemy in ENEMIES])
    parser.add_argument(
        "--strip-textures",
        action="store_true",
        help="Build smaller neutral-gray research models instead of preserving embedded game materials.",
    )
    return parser.parse_args()


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    args = parse_args()
    tools = Path(__file__).resolve().parent
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    selected = set(args.only or ())
    for slug, display_name, entity, allow_unmatched, allow_unassigned, source_override in ENEMIES:
        if selected and slug not in selected:
            continue
        source = args.extract_root.resolve() / Path(source_override or entity)
        collision_manifest = output_root / f"{slug}-collision-research.manifest.json"
        extract_command = [
            sys.executable,
            str(tools / "extract_hd2_collision_hulls.py"),
            "--unit-glb",
            str(source.with_suffix(".unit.glb")),
            "--output",
            str(output_root / f"{slug}-collision-research.glb"),
            "--manifest",
            str(collision_manifest),
        ]
        if slug not in RAGDOLL_ONLY_ENEMIES:
            extract_command.extend(("--physics", str(source.with_suffix(".physics.main"))))
        if args.strip_textures:
            extract_command.append("--strip-textures")
        if slug in RAGDOLL_COLLISION_ENEMIES:
            ragdoll_profile = source.with_suffix(".ragdoll_profile.main")
            if not ragdoll_profile.is_file():
                raise FileNotFoundError(f"Missing articulated collision source: {ragdoll_profile}")
            extract_command.extend(("--ragdoll-profile", str(ragdoll_profile)))
        bones = (
            args.extract_root.resolve() / BONES_SOURCE_OVERRIDES[slug]
            if slug in BONES_SOURCE_OVERRIDES
            else source.with_suffix(".bones.json")
        )
        if bones.exists():
            extract_command.extend(("--bones-json", str(bones)))
        run(extract_command)

        map_command = [
            sys.executable,
            str(tools / "map_hd2_damage_zones.py"),
            "--entities-json",
            str(args.entities_json.resolve()),
            "--collision-manifest",
            str(collision_manifest),
            "--output",
            str(output_root / f"{slug}-damage-zones.manifest.json"),
            "--entity",
            entity,
            "--display-name",
            display_name,
        ]
        if allow_unmatched:
            map_command.append("--allow-unmatched-actors")
        if allow_unassigned:
            map_command.append("--allow-unassigned-colliders")
        if slug in LAYERED_COLLISION_ENEMIES:
            map_command.append("--allow-layered-colliders")
        run(map_command)
        if slug in {"berserker", "harvester", "stingray"}:
            run(
                [
                    sys.executable,
                    str(tools / "apply_hd2_damage_zone_proxies.py"),
                    "--slug",
                    slug,
                    "--collision-manifest",
                    str(collision_manifest),
                    "--damage-manifest",
                    str(output_root / f"{slug}-damage-zones.manifest.json"),
                ]
            )


if __name__ == "__main__":
    main()
