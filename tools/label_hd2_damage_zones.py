"""Attach stable, human-readable physical labels to HD2 damage-zone manifests.

The decoded HealthComponent data often exposes only a thin hash for a damage
pool. Its actor join still gives us named collision/bone attachments. This
tool turns those verified names into a conservative physical label without
discarding the original zone ID or claiming knowledge that was not recovered.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


RAW_HASH = re.compile(r"^0x[0-9a-f]+$", re.IGNORECASE)
GENERIC_NAMES = {
    "boss", "root", "unit_root", "entity_root", "stingrayentityroot",
    "c_body", "g_body", "body", "body_main", "main_body", "main",
    "default", "zone",
}
WORD_REPLACEMENTS = {
    "l": "Left", "r": "Right", "lhs": "Left", "rhs": "Right",
    "c": "Center", "fore": "Front", "front": "Front", "hind": "Rear",
    "rear": "Rear", "back": "Rear", "mid": "Middle", "centre": "Center",
}


def _split_words(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value or "")
    return [word.casefold() for word in re.split(r"[^a-z0-9]+", value) if word]


def humanize(value: str) -> str:
    words = _split_words(value)
    while words and words[-1].isdigit():
        words.pop()
    rendered = []
    for word in words:
        if word in WORD_REPLACEMENTS:
            rendered.append(WORD_REPLACEMENTS[word])
        elif word in {"hp", "ap", "av"}:
            rendered.append(word.upper())
        else:
            rendered.append(word.capitalize())
    if len(rendered) > 1 and rendered[-1] in {"Left", "Right", "Center"}:
        rendered.insert(0, rendered.pop())
    return " ".join(rendered)


def _canonical_attachment(value: str) -> str | None:
    if not value or RAW_HASH.fullmatch(value) or value.casefold() in GENERIC_NAMES:
        return None
    label = humanize(value)
    label = re.sub(r"\bFore Leg\b", "Front Leg", label)
    label = re.sub(r"\bHind Leg\b", "Rear Leg", label)
    label = re.sub(r"\bBack Leg\b", "Rear Leg", label)
    label = re.sub(r"\bFront Tracks\b", "Front Track", label)
    label = re.sub(r"\bRear Tracks\b", "Rear Track", label)
    return label or None


def _unique(values: Iterable[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def physical_label_for_zone(zone: dict[str, Any]) -> tuple[str, str, list[str]]:
    raw_name = str(zone.get("zoneName") or zone.get("zoneNameRaw") or "")
    if raw_name and not RAW_HASH.fullmatch(raw_name) and raw_name.casefold() not in GENERIC_NAMES:
        return humanize(raw_name), "decoded-damage-zone-name", [raw_name]

    actor_names: list[str] = []
    for actor in zone.get("actors", []):
        actor_names.extend(
            str(value)
            for value in (actor.get("boneName"), actor.get("actor"))
            if value
        )
    labels = _unique(_canonical_attachment(name) for name in actor_names)
    if labels:
        return " / ".join(labels), "verified-attachment-name", _unique(actor_names)
    if actor_names:
        return "Central Body / Chassis", "verified-root-attachment", _unique(actor_names)
    return "Unresolved Body Area", "unresolved-physical-attachment", []


def annotate_manifest(document: dict[str, Any]) -> dict[str, Any]:
    proxy_labels = {
        int(proxy["zoneIndex"]): humanize(proxy.get("label") or proxy.get("id") or "")
        for proxy in (
            document.get("viewerDamageZoneProxies", {}).get("boxes", [])
            + document.get("viewerDamageZoneProxies", {}).get("colliders", [])
        )
        if "zoneIndex" in proxy
    }
    labels_by_zone: dict[int, tuple[str, str, list[str]]] = {}
    for zone in document.get("zones", []):
        label, evidence, sources = physical_label_for_zone(zone)
        if evidence == "unresolved-physical-attachment" and int(zone["zoneIndex"]) in proxy_labels:
            label = proxy_labels[int(zone["zoneIndex"])]
            evidence = "evidence-labeled-physical-proxy"
            sources = ["viewerDamageZoneProxies"]
        zone["physicalLabel"] = label
        zone["physicalLabelEvidence"] = evidence
        zone.pop("physicalLabelSources", None)
        labels_by_zone[int(zone["zoneIndex"])] = (label, evidence, sources)

    for collider in document.get("colliders", []):
        collider.pop("physicalLabel", None)
        collider.pop("physicalLabelEvidence", None)
        collider.pop("physicalLabelSources", None)
        for layer in collider.get("zoneStack", []):
            layer.pop("physicalLabel", None)
            layer.pop("physicalLabelEvidence", None)
            layer.pop("physicalLabelSources", None)
    document["physicalLabeling"] = {
        "version": 1,
        "policy": "decoded zone name, otherwise verified actor/bone attachment",
        "technicalIdsPreserved": True,
    }
    return document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs="*")
    parser.add_argument("--models-root", type=Path, default=Path("assets/models"))
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = args.paths or sorted(args.models_root.glob("*-damage-zones.manifest.json"))
    changed = 0
    unresolved = 0
    for path in paths:
        original = path.read_text(encoding="utf-8")
        document = annotate_manifest(json.loads(original))
        rendered = json.dumps(document, indent=2) + "\n"
        unresolved += sum(
            zone.get("physicalLabelEvidence") == "unresolved-physical-attachment"
            for zone in document.get("zones", [])
        )
        if rendered != original:
            changed += 1
            if not args.check:
                path.write_text(rendered, encoding="utf-8")
    if args.check and changed:
        raise SystemExit(f"{changed} damage-zone manifests need physical-label synchronization")
    print(f"Labeled {len(paths)} damage-zone manifests; {unresolved} zones remain physically unresolved")


if __name__ == "__main__":
    main()
