"""Join decoded HD2 health-component damage zones to extracted collision hulls.

The Filediver entity-component dumper resolves each HealthComponent damage zone
to an ``actors`` list. Actors may identify a collider directly or a skeleton
bone shared by several physics records. This script resolves both forms,
preserves partial-coverage evidence when explicitly allowed, and always refuses
cross-zone duplicate assignments unless an entity explicitly assigns one actor
to multiple pools and ``--allow-layered-colliders`` is supplied. Layered joins
remain visible in the output instead of being flattened or guessed away.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_ENTITY = "content/fac_bugs/cha_strider/cha_strider"

# These names were recovered by hashing candidate strings with Stingray's
# Murmur64A thin-hash algorithm. Uncracked hashes remain explicit raw IDs.
CRACKED_ZONE_NAMES = {
    "0xa6323908": "left_front_leg_armor",
    "0x4c967a8c": "left_front_leg_flesh",
    "0x53df0bfd": "right_front_leg_armor",
    "0xd4890690": "right_front_leg_flesh",
    "0xc10b192c": "left_back_leg_armor",
    "0x11091c35": "left_back_leg_flesh",
    "0xca9ed401": "right_back_leg_armor",
    "0x4929bf22": "right_back_leg_flesh",
}

ZONE_FIELDS = (
    "damage_multiplier",
    "damage_multiplier_dps",
    "projectile_durable_resistance",
    "armor",
    "armor_angle_check",
    "max_armor",
    "health",
    "constitution",
    "immortal",
    "causes_downed_on_downed",
    "causes_death_on_downed",
    "causes_downed_on_death",
    "causes_death_on_death",
    "affects_main_health",
    "child_zones",
    "kill_children_on_death",
    "bleedout_enabled",
    "affected_by_explosions",
    "explosive_damage_percentage",
    "explosion_verification_mode",
    "main_health_affect_capped_by_zone_health",
    "hit_effect_receiver_type",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Map HD2 HealthComponent damage-zone actors to decoded collision hulls."
    )
    parser.add_argument("--entities-json", type=Path, required=True)
    parser.add_argument("--collision-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--entity", default=DEFAULT_ENTITY)
    parser.add_argument("--display-name")
    parser.add_argument("--allow-unmatched-actors", action="store_true")
    parser.add_argument("--allow-unassigned-colliders", action="store_true")
    parser.add_argument("--allow-layered-colliders", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_json(path: Path) -> Any:
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    return json.loads(raw.decode(encoding))


def normalize_hash(value: str) -> str:
    return value.casefold().removeprefix("0x")


def murmur32(data: bytes, seed: int = 0) -> int:
    multiplier = 0xC6A4A7935BD1E995
    shift = 47
    mask = (1 << 64) - 1
    value = seed ^ ((multiplier * len(data)) & mask)
    whole = len(data) // 8 * 8
    for offset in range(0, whole, 8):
        item = int.from_bytes(data[offset : offset + 8], "little")
        item = item * multiplier & mask
        item ^= item >> shift
        item = item * multiplier & mask
        value ^= item
        value = value * multiplier & mask
    for index, byte in enumerate(data[whole:]):
        value ^= byte << (index * 8)
    if data[whole:]:
        value = value * multiplier & mask
    value ^= value >> shift
    value = value * multiplier & mask
    value ^= value >> shift
    return value >> 32


def resolved_zone_name(raw_name: str) -> tuple[str, str]:
    if raw_name in CRACKED_ZONE_NAMES:
        return CRACKED_ZONE_NAMES[raw_name], "hash-cracked"
    if raw_name.startswith("0x"):
        return raw_name, "raw-hash"
    return raw_name, "filediver-dictionary"


def zone_info_subset(info: dict[str, Any]) -> dict[str, Any]:
    return {field: info.get(field) for field in ZONE_FIELDS}


def main() -> None:
    args = parse_args()
    entities = load_json(args.entities_json)
    collision = load_json(args.collision_manifest)

    try:
        health = entities[args.entity]["components"]["HealthComponentData"]
    except KeyError as exc:
        raise AssertionError(f"Entity has no decoded HealthComponentData: {args.entity}") from exc

    colliders = collision.get("colliders", [])
    if not colliders:
        raise AssertionError("Collision manifest contains no colliders")

    direct_lookup: dict[str, list[dict[str, Any]]] = {}
    bone_lookup: dict[str, list[dict[str, Any]]] = {}
    for collider in colliders:
        direct_aliases = {
            normalize_hash(collider["colliderHash"]),
            (collider.get("nodeName") or "").casefold(),
        }
        bone_aliases = {
            normalize_hash(collider.get("boneHash") or ""),
            (collider.get("parentNodeName") or "").casefold(),
            (collider.get("boneName") or "").casefold(),
        }
        for alias in direct_aliases:
            if alias:
                direct_lookup.setdefault(alias, []).append(collider)
        for alias in bone_aliases:
            if alias:
                bone_lookup.setdefault(alias, []).append(collider)

    def actor_aliases(actor: str) -> list[str]:
        aliases = [normalize_hash(actor), actor.casefold()]
        if not actor.startswith("0x"):
            aliases.append(f"{murmur32(actor.encode('utf-8')):08x}")
        return aliases

    direct_claims: dict[int, list[int]] = {}
    for claim_zone_index, claim_zone in enumerate(health.get("damageable_zones", [])):
        for actor in claim_zone.get("actors", []):
            for alias in actor_aliases(actor):
                for collider in direct_lookup.get(alias, []):
                    record_index = collider["recordIndex"]
                    previous = direct_claims.setdefault(record_index, [])
                    if previous and claim_zone_index not in previous and not args.allow_layered_colliders:
                        raise AssertionError(
                            f"Collider record {record_index} is directly claimed by zones "
                            f"{previous[0]} and {claim_zone_index}"
                        )
                    if claim_zone_index not in previous:
                        previous.append(claim_zone_index)

    assignments: dict[int, list[int]] = {}
    zones: list[dict[str, Any]] = []
    unmatched_actors: list[dict[str, Any]] = []
    matched_actor_count = 0
    for zone_index, zone in enumerate(health.get("damageable_zones", [])):
        info = zone["info"]
        raw_name = info["zone_name"]
        name, resolution = resolved_zone_name(raw_name)
        zone_colliders = []
        matched_zone_actors: set[str] = set()
        for actor in zone.get("actors", []):
            aliases = actor_aliases(actor)
            matches_by_record: dict[int, dict[str, Any]] = {}
            for alias in aliases:
                for collider in direct_lookup.get(alias, []):
                    matches_by_record[collider["recordIndex"]] = collider
            if not matches_by_record:
                for alias in aliases:
                    for collider in bone_lookup.get(alias, []):
                        record_index = collider["recordIndex"]
                        claimed_zones = direct_claims.get(record_index)
                        if claimed_zones is None or zone_index in claimed_zones:
                            matches_by_record[record_index] = collider
            if not matches_by_record:
                unmatched_actors.append({"zoneIndex": zone_index, "zoneName": name, "actor": actor})
                continue
            matched_actor_count += 1
            matched_zone_actors.add(actor)
            for record_index, collider in sorted(matches_by_record.items()):
                assigned_zones = assignments.setdefault(record_index, [])
                if assigned_zones and zone_index not in assigned_zones and not args.allow_layered_colliders:
                    raise AssertionError(
                        f"Collider record {record_index} is assigned to zones "
                        f"{assigned_zones[0]} and {zone_index}"
                    )
                if zone_index not in assigned_zones:
                    assigned_zones.append(zone_index)
                zone_colliders.append(
                    {
                        "actor": actor,
                        "recordIndex": record_index,
                        "colliderHash": collider["colliderHash"],
                        "nodeName": collider["nodeName"],
                        "boneHash": collider.get("boneHash"),
                        "boneName": collider.get("boneName"),
                    }
                )
        zones.append(
            {
                "zoneIndex": zone_index,
                "zoneName": name,
                "zoneNameRaw": raw_name,
                "zoneNameResolution": resolution,
                "actorReferenceCount": len(zone.get("actors", [])),
                "mappedActorReferenceCount": len(matched_zone_actors),
                "unmatchedActorReferenceCount": len(zone.get("actors", [])) - len(matched_zone_actors),
                "actors": zone_colliders,
                **zone_info_subset(info),
            }
        )

    expected = {collider["recordIndex"] for collider in colliders}
    missing = sorted(expected - assignments.keys())
    if unmatched_actors and not args.allow_unmatched_actors:
        raise AssertionError(f"Damage-zone actors without decoded collision geometry: {unmatched_actors}")
    if missing and not args.allow_unassigned_colliders:
        raise AssertionError(f"Collision hulls without damage-zone assignments: {missing}")

    layered_records = sorted(record for record, assigned in assignments.items() if len(assigned) > 1)
    collider_map = []
    for collider in sorted(colliders, key=lambda item: item["recordIndex"]):
        if collider["recordIndex"] not in assignments:
            continue
        assigned_zones = [zones[index] for index in assignments[collider["recordIndex"]]]
        zone = assigned_zones[0]
        zone_stack = [
            {
                "zoneIndex": item["zoneIndex"],
                "zoneName": item["zoneName"],
                "zoneNameRaw": item["zoneNameRaw"],
                "zoneNameResolution": item["zoneNameResolution"],
                "health": item["health"],
                "armor": item["armor"],
                "projectileDurableResistance": item["projectile_durable_resistance"],
                "affectsMainHealth": item["affects_main_health"],
                "affectedByExplosions": item["affected_by_explosions"],
                "explosiveDamagePercentage": item["explosive_damage_percentage"],
                "explosionVerificationMode": item["explosion_verification_mode"],
            }
            for item in assigned_zones
        ]
        collider_map.append(
            {
                "recordIndex": collider["recordIndex"],
                "colliderHash": collider["colliderHash"],
                "nodeName": collider["nodeName"],
                "boneHash": collider.get("boneHash"),
                "boneName": collider.get("boneName"),
                "zoneIndex": zone["zoneIndex"],
                "zoneName": zone["zoneName"],
                "zoneNameRaw": zone["zoneNameRaw"],
                "zoneNameResolution": zone["zoneNameResolution"],
                "health": zone["health"],
                "armor": zone["armor"],
                "projectileDurableResistance": zone["projectile_durable_resistance"],
                "affectsMainHealth": zone["affects_main_health"],
                "affectedByExplosions": zone["affected_by_explosions"],
                "explosiveDamagePercentage": zone["explosive_damage_percentage"],
                "explosionVerificationMode": zone["explosion_verification_mode"],
                "zoneStack": zone_stack,
            }
        )

    if unmatched_actors and layered_records:
        mapping_confidence = "partial-layered-actor-join"
    elif unmatched_actors:
        mapping_confidence = "partial-actor-join"
    elif layered_records:
        mapping_confidence = "verified-layered-actor-join"
    else:
        mapping_confidence = "verified-complete-actor-join"
    uncovered_damage_zones = [
        {
            "zoneIndex": zone["zoneIndex"],
            "zoneName": zone["zoneName"],
            "zoneNameRaw": zone["zoneNameRaw"],
            "actorReferenceCount": zone["actorReferenceCount"],
        }
        for zone in zones
        if zone["actorReferenceCount"] and not zone["actors"]
    ]
    redundant_unmatched_actors = [
        actor
        for actor in unmatched_actors
        if zones[actor["zoneIndex"]]["actors"]
    ]
    interaction_coverage = (
        "verified-exact-zone-coverage"
        if not uncovered_damage_zones
        else "partial-zone-coverage"
    )
    result = {
        "schemaVersion": 1,
        "entity": args.entity,
        "displayName": args.display_name,
        "gameObjectId": entities[args.entity].get("game_object_id"),
        "mappingConfidence": mapping_confidence,
        "evidence": (
            "HealthComponentData damageableZones[].actors matched collision node names or "
            "collider hashes. Layered assignments are preserved when the game data explicitly "
            "places one collider actor in multiple damage pools."
        ),
        "source": {
            "entitiesJson": {
                "path": str(args.entities_json.resolve()),
                "sha256": sha256(args.entities_json),
            },
            "collisionManifest": {
                "path": str(args.collision_manifest.resolve()),
                "sha256": sha256(args.collision_manifest),
            },
        },
        "mainHealth": health.get("health"),
        "defaultDamageableZone": zone_info_subset(health["default_damageable_zone_info"]),
        "zoneCount": len(zones),
        "actorCount": sum(len(zone.get("actors", [])) for zone in health.get("damageable_zones", [])),
        "mappedActorCount": matched_actor_count,
        "unmatchedActorCount": len(unmatched_actors),
        "unmatchedActors": unmatched_actors,
        "redundantUnmatchedActorCount": len(redundant_unmatched_actors),
        "redundantUnmatchedActors": redundant_unmatched_actors,
        "interactionCoverage": interaction_coverage,
        "uncoveredDamageZoneCount": len(uncovered_damage_zones),
        "uncoveredDamageZones": uncovered_damage_zones,
        "mappedColliderCount": len(collider_map),
        "unmappedColliderCount": len(missing),
        "unmappedColliderRecords": missing,
        "layeredColliderCount": len(layered_records),
        "layeredColliderRecords": layered_records,
        "duplicateColliderAssignments": len(layered_records),
        "zones": zones,
        "colliders": collider_map,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"Mapped {result['mappedColliderCount']} collision hulls to "
        f"{result['zoneCount']} damage zones for {args.display_name or args.entity}; "
        f"{result['unmatchedActorCount']} actors unmatched"
    )


if __name__ == "__main__":
    main()
