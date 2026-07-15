"""Add evidence-labeled viewer fallbacks for damage zones with no exact hull.

The exact actor join remains untouched. These records only make an otherwise
unrepresented damage zone selectable in the research viewer, and the emitted
manifest keeps the inferred geometry separate from verified mappings.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROXIES: dict[str, dict[str, Any]] = {
    "berserker": {
        "mode": "comparative-box-proxy",
        "confidence": "inferred-from-game-colliders",
        "evidence": (
            "Berserker uses the same named shoulderplate bones as Devastator, Heavy "
            "Devastator, and Rocket Devastator. All three verified Automaton resources "
            "use identical 0.435137 x 0.395236 x 0.377271 shoulderplate colliders."
        ),
        "analogs": ["Devastator", "Heavy Devastator", "Rocket Devastator"],
        "boxes": [
            {
                "id": "left-shoulderplate",
                "actor": "l_shoulderplate",
                "zoneIndex": 4,
                "anchorNode": "l_shoulderplate",
                "boxSize": [0.435137, 0.395236, 0.377271],
                "label": "left shoulderplate",
            },
            {
                "id": "right-shoulderplate",
                "actor": "r_shoulderplate",
                "zoneIndex": 5,
                "anchorNode": "r_shoulderplate",
                "boxSize": [0.435137, 0.395236, 0.377271],
                "label": "right shoulderplate",
            },
        ],
        "colliders": [],
    },
    "harvester": {
        "mode": "local-unassigned-collider-proxy",
        "confidence": "inferred-single-candidate-game-collider",
        "evidence": (
            "The exact Harvester physics resource has one unassigned front-sized hull and "
            "one HealthComponent zone without a hull. The actor hash itself is absent, so "
            "the association is intentionally labeled inferred."
        ),
        "analogs": [],
        "boxes": [],
        "colliders": [
            {
                "id": "front-body",
                "actor": "c_body_front",
                "zoneIndex": 1,
                "recordIndex": 24,
                "expectedColliderHash": "43a3844e",
                "label": "front body",
            }
        ],
    },
    "stingray": {
        "mode": "local-unassigned-collider-proxy",
        "confidence": "inferred-single-candidate-game-collider",
        "evidence": (
            "The Stingray ragdoll resource has one unassigned central boss hull and one "
            "HealthComponent front-body zone without a hull. The actor hash itself is "
            "absent, so the association is intentionally labeled inferred."
        ),
        "analogs": [],
        "boxes": [],
        "colliders": [
            {
                "id": "front-body",
                "actor": "front_body",
                "zoneIndex": 1,
                "recordIndex": 0,
                "expectedColliderHash": "9b115563",
                "label": "front body",
            }
        ],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", choices=sorted(PROXIES), required=True)
    parser.add_argument("--collision-manifest", type=Path, required=True)
    parser.add_argument("--damage-manifest", type=Path, required=True)
    return parser.parse_args()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    collision = load(args.collision_manifest)
    damage = load(args.damage_manifest)
    definition = PROXIES[args.slug]
    unmatched = {(item["zoneIndex"], item["actor"]) for item in damage.get("unmatchedActors", [])}
    uncovered = {item["zoneIndex"] for item in damage.get("uncoveredDamageZones", [])}
    collision_by_record = {item["recordIndex"]: item for item in collision.get("colliders", [])}
    mapped_records = {item["recordIndex"] for item in damage.get("colliders", [])}

    proxies = [*definition["boxes"], *definition["colliders"]]
    covered_zones: set[int] = set()
    for proxy in proxies:
        key = (proxy["zoneIndex"], proxy["actor"])
        if key not in unmatched or proxy["zoneIndex"] not in uncovered:
            raise AssertionError(f"{args.slug} proxy no longer covers an unresolved zone actor: {key}")
        covered_zones.add(proxy["zoneIndex"])
        if "recordIndex" not in proxy:
            if len(proxy.get("boxSize", [])) != 3 or not proxy.get("anchorNode"):
                raise AssertionError(f"{args.slug} box proxy is missing its anchor or dimensions")
            continue
        collider = collision_by_record.get(proxy["recordIndex"])
        if collider is None or collider.get("colliderHash") != proxy["expectedColliderHash"]:
            raise AssertionError(f"{args.slug} proxy collider evidence changed")
        if proxy["recordIndex"] in mapped_records:
            raise AssertionError(f"{args.slug} proxy collider gained an exact assignment")

    remaining = sorted(uncovered - covered_zones)
    if remaining:
        raise AssertionError(f"{args.slug} still has uncovered damage zones: {remaining}")
    emitted = {
        "schemaVersion": 1,
        "mode": definition["mode"],
        "confidence": definition["confidence"],
        "evidence": definition["evidence"],
        "analogs": definition["analogs"],
        "boxes": definition["boxes"],
        "colliders": definition["colliders"],
    }
    damage["viewerDamageZoneProxies"] = emitted
    damage["interactionCoverage"] = "complete-with-evidence-labeled-proxies"
    damage["proxyCoveredDamageZoneCount"] = len(covered_zones)
    damage["proxyCoveredDamageZones"] = sorted(covered_zones)
    damage["remainingUncoveredDamageZoneCount"] = 0
    damage["remainingUncoveredDamageZones"] = []
    args.damage_manifest.write_text(json.dumps(damage, indent=2) + "\n", encoding="utf-8")
    print(f"Added {len(proxies)} evidence-labeled viewer proxies for {args.slug}")


if __name__ == "__main__":
    main()
