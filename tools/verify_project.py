from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import struct
from pathlib import Path

from PIL import Image


PNG_RE = re.compile(r'"([^"\r\n]+\.png)"', re.IGNORECASE)


def glb_chunks(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise AssertionError(f"{path.name} is not a valid binary glTF")
    offset = 12
    document = None
    binary = b""
    while offset + 8 <= len(raw):
        chunk_length, chunk_type = struct.unpack_from("<II", raw, offset)
        payload = raw[offset + 8 : offset + 8 + chunk_length]
        if chunk_type == 0x4E4F534A:
            document = json.loads(payload.decode("utf-8").rstrip("\0 "))
        elif chunk_type == 0x004E4942:
            binary = payload
        offset += 8 + chunk_length
    if document is None:
        raise AssertionError(f"{path.name} does not contain a JSON chunk")
    return document, binary


def glb_json(path: Path) -> dict:
    return glb_chunks(path)[0]


def assert_nonblank_base_color(path: Path) -> None:
    document, binary = glb_chunks(path)
    for material in document.get("materials", []):
        if material.get("extras", {}).get("hd2BrowserMaterial") != "filediver-accurate-shader-bake":
            continue
        texture_info = material.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        if not texture_info:
            raise AssertionError(f"{path.name} material {material.get('name')} has no baked base color")
        texture = document["textures"][texture_info["index"]]
        image_info = document["images"][texture["source"]]
        view = document["bufferViews"][image_info["bufferView"]]
        start = view.get("byteOffset", 0)
        payload = binary[start : start + view["byteLength"]]
        with Image.open(io.BytesIO(payload)) as image:
            extrema = image.convert("RGB").getextrema()
        if not any(channel_max > 0 for _, channel_max in extrema):
            raise AssertionError(
                f"{path.name} material {material.get('name')} has an all-black failed base-color bake"
            )


def calculation_core(html: str) -> str:
    script = html.split("<script>", 1)[1]
    for marker in ("// ============ DERIVED RANKING", "// ============ UI ============"):
        if marker in script:
            return script.split(marker, 1)[0].rstrip()
    raise AssertionError("Could not locate the preserved calculation core")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the deployable assessor and its local image bundle.")
    parser.add_argument("html", type=Path, nargs="?", default=Path("shot-placement-assessor.html"))
    parser.add_argument("--original", type=Path)
    parser.add_argument("--assets", type=Path, default=Path("assets/anatomy"))
    args = parser.parse_args()

    html = args.html.read_text(encoding="utf-8")
    references = sorted(set(PNG_RE.findall(html)), key=str.casefold)
    expected = {re.sub(r"\.png$", ".webp", name, flags=re.IGNORECASE) for name in references}
    actual = {path.name for path in args.assets.glob("*.webp")}
    missing = sorted(expected - actual, key=str.casefold)
    if missing:
        raise AssertionError(f"Missing {len(missing)} local images; first: {missing[:5]}")

    invalid = []
    for path in args.assets.glob("*.webp"):
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if image.format != "WEBP" or image.width > 300 or image.height > 300:
                    invalid.append(f"{path.name}: {image.format} {image.size}")
        except Exception as exc:  # noqa: BLE001 - aggregate verification failures
            invalid.append(f"{path.name}: {exc}")
    if invalid:
        raise AssertionError(f"Invalid assets: {invalid[:5]}")

    required = [
        'role="tablist"',
        "function rankParts",
        "function rankWeapons",
        "function renderCompare",
        "function formatShareSummary",
        "hd2-shot-placement:v3",
        'rel="noopener noreferrer"',
        'assets/favicon.svg',
        "localStorage.setItem",
        'id="showTargeting3dGeometryOnly"',
        'id="targeting3dSimulateMode"',
        'id="targeting3dTimeline"',
        'id="targeting3dGridOpacity"',
        'id="targeting3dNavigationMode"',
        "THREE.TOUCH.DOLLY_ROTATE",
        "touches.ONE=THREE.TOUCH.PAN",
        "mouseButtons.LEFT=THREE.MOUSE.PAN",
        "screenSpacePanning=false",
        "function classifyTargeting3dWheelGesture",
        "hd2-3d-navigation-mode",
        "orbitTargeting3dFromTrackpad",
        "@media(any-pointer:fine)",
        "function getExplosiveProfile",
        '"MS-11 Solo Silo":{kind:"guided-top-attack"',
        "function guidedTopAttackDirection",
        "function resolveGuidedTopAttackImpact",
        "representative 70° terminal descent",
        "function physicalPartLabel",
        "damage.physicalLabel",
        "redirectExplosionToMain",
        "function buildCollisionSceneIndex",
        "function simulateImpact",
        "function simulateSequence",
        "function normalizeImpactForDelivery",
        '"B-100 Portable Hellbomb (inner blast)":{kind:"ground-timed",groundOnly:true',
        "Ground placement only",
        "function generateBarragePattern",
        "const showRadii=barrage||visibleImpacts.length<=3",
        "function summarizeSplashResult",
        "function explainSplashDestruction",
        "function makeGroundClippedBlastSphere",
        "renderer.localClippingEnabled=true",
        "Why the target was destroyed",
    ]
    absent = [marker for marker in required if marker not in html]
    if absent:
        raise AssertionError(f"Missing expected implementation markers: {absent}")

    if args.original:
        original = args.original.read_text(encoding="utf-8")
        if calculation_core(original) != calculation_core(html):
            raise AssertionError("Data/calculation core differs from the original")

    project_root = args.html.resolve().parent
    models_root = project_root / "assets/models"
    catalog_path = models_root / "enemy-3d-models.json"
    viewer_bundle = project_root / "assets/vendor/hd2-three-viewer.min.js"
    if not viewer_bundle.is_file() or viewer_bundle.stat().st_size < 100_000:
        raise AssertionError("Local Three.js viewer bundle is missing or unexpectedly small")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    default_units = catalog.get("defaultUnitsPerMeter")
    if not isinstance(default_units, (int, float)) or default_units <= 0:
        raise AssertionError("3D model catalog is missing a positive defaultUnitsPerMeter")
    models = catalog.get("models", {})
    if len(models) != 61:
        raise AssertionError(f"Expected 61 enemy 3D models, found {len(models)}")
    complete = partial = exact_zone_covered = proxy_zone_covered = incomplete_zone_coverage = total_hulls = total_mapped = 0
    for enemy, entry in models.items():
        units_per_meter = entry.get("unitsPerMeter", default_units)
        if not isinstance(units_per_meter, (int, float)) or units_per_meter <= 0:
            raise AssertionError(f"{enemy} has an invalid unitsPerMeter value")
        model_path = project_root / entry["glb"]
        manifest_path = project_root / entry["collisionManifest"]
        damage_manifest_path = project_root / entry["damageManifest"]
        render_path = project_root / entry["renderGlb"] if entry.get("renderGlb") else None
        if not model_path.is_file() or model_path.stat().st_size < 1_000_000:
            raise AssertionError(f"{enemy} research GLB is missing or unexpectedly small")
        if model_path.read_bytes()[:4] != b"glTF":
            raise AssertionError(f"{enemy} research asset is not a hydrated binary GLB")
        if render_path and (
            not render_path.is_file()
            or render_path.stat().st_size < 1_000_000
            or render_path.read_bytes()[:4] != b"glTF"
        ):
            raise AssertionError(f"{enemy} authentic render asset is missing or invalid")
        model_document = glb_json(model_path)
        if not model_document.get("images") or not model_document.get("textures"):
            raise AssertionError(f"{enemy} research GLB does not retain embedded color textures")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        colliders = manifest.get("colliders", [])
        records = [collider.get("recordIndex") for collider in colliders]
        if manifest.get("geometryConfidence") != "verified" or len(colliders) != manifest.get("hullCount"):
            raise AssertionError(f"{enemy} collision manifest failed its geometry gate")
        if len(records) != len(set(records)):
            raise AssertionError(f"{enemy} collision manifest contains duplicate records")
        damage = json.loads(damage_manifest_path.read_text(encoding="utf-8"))
        if damage.get("physicalLabeling", {}).get("version") != 1:
            raise AssertionError(f"{enemy} damage manifest has stale physical labels")
        for zone in damage.get("zones", []):
            missing_explosion_fields = {
                "affected_by_explosions",
                "explosive_damage_percentage",
                "explosion_verification_mode",
            } - zone.keys()
            if missing_explosion_fields:
                raise AssertionError(
                    f"{enemy} damage zone {zone.get('zoneIndex')} is missing explosion metadata: "
                    f"{sorted(missing_explosion_fields)}"
                )
            physical_label = zone.get("physicalLabel", "")
            if not physical_label or re.fullmatch(r"(?:Zone\s+\d+\s*[·-]\s*)?0x[0-9a-f]+", physical_label, re.I):
                raise AssertionError(
                    f"{enemy} zone {zone.get('zoneIndex')} lacks a physical user-facing label"
                )
        if manifest.get("source", {}).get("ragdollProfile"):
            if not str(manifest.get("ragdollMappingEvidence", "")).startswith("Exact "):
                raise AssertionError(f"{enemy} articulated hulls are not tied to exact ragdoll records")
            for collider in colliders:
                if collider.get("geometryConfidence") != "verified":
                    raise AssertionError(f"{enemy} contains a non-verified articulated collider")
                if enemy in {
                    "Hunter", "Stalker", "Scavenger", "Pouncer", "Warrior",
                    "Devastator", "Heavy Devastator", "Rocket Devastator",
                } and "hknpCapsuleShape" in collider.get("shapeTypes", []):
                    size = sorted(collider.get("localSize", []))
                    if len(size) != 3 or size[1] <= 0.02:
                        raise AssertionError(
                            f"{enemy} capsule collider {collider.get('recordIndex')} has a collapsed radius"
                        )
            if enemy in {"Stalker", "Predator Stalker"}:
                transformed = [
                    collider for collider in colliders if collider.get("ragdollBodyTransform")
                ]
                nodes_by_name = {
                    node.get("name"): node for node in model_document.get("nodes", [])
                }
                if (
                    manifest.get("decodedRagdollBodyTransformCount") != 41
                    or len(transformed) != 41
                    or any(
                        collider["ragdollBodyTransform"].get("bonePositionError", 1) > 0.01
                        or not str(
                            collider["ragdollBodyTransform"].get("coordinateConversion", "")
                        ).startswith("Havok body orientation")
                        or "matrix" not in nodes_by_name.get(collider.get("nodeName"), {})
                        for collider in transformed
                    )
                ):
                    raise AssertionError(f"{enemy} lost its decoded ragdoll body poses")
                articulated_limbs = [
                    collider
                    for collider in transformed
                    if any(token in collider.get("boneName", "") for token in ("leg", "claw"))
                    and "boneAxisAlignment" in collider["ragdollBodyTransform"]
                ]
                if not articulated_limbs or any(
                    collider["ragdollBodyTransform"]["boneAxisAlignment"] < 0.75
                    for collider in articulated_limbs
                ):
                    raise AssertionError(f"{enemy} limb hulls are not aligned to their skeleton bones")
        expected_capsules = {
            "Hunter": 20,
            "Stalker": 30,
            "Scavenger": 20,
            "Pouncer": 20,
            "Warrior": 10,
        }
        if enemy in expected_capsules:
            capsules = sum(
                "hknpCapsuleShape" in collider.get("shapeTypes", [])
                for collider in colliders
            )
            if capsules < expected_capsules[enemy]:
                raise AssertionError(
                    f"{enemy} lost exact game capsule records ({capsules} found)"
                )
        if enemy in {"Devastator", "Heavy Devastator", "Rocket Devastator"}:
            arms = {collider.get("boneName"): collider for collider in colliders}
            for bone_name in ("l_shoulder", "r_shoulder"):
                if "hknpBoxShape" not in arms.get(bone_name, {}).get("shapeTypes", []):
                    raise AssertionError(f"{enemy} {bone_name} lost its exact game box collider")
            for bone_name in ("l_elbow", "r_elbow"):
                arm = arms.get(bone_name, {})
                if not set(arm.get("shapeTypes", [])) & {"hknpCapsuleShape", "hknpConvexShape"}:
                    raise AssertionError(f"{enemy} {bone_name} lost its exact game articulated collider")
        confidence = damage.get("mappingConfidence")
        if confidence not in {
            "verified-exact-actor-join",
            "verified-complete-actor-join",
            "partial-actor-join",
            "verified-layered-actor-join",
            "partial-layered-actor-join",
        }:
            raise AssertionError(f"{enemy} damage manifest has invalid confidence: {confidence}")
        mapped = [collider.get("recordIndex") for collider in damage.get("colliders", [])]
        if len(mapped) != damage.get("mappedColliderCount") or not set(mapped).issubset(records):
            raise AssertionError(f"{enemy} damage manifest references invalid collision records")
        layered = "layered" in confidence
        if layered:
            layered_records = damage.get("layeredColliderRecords", [])
            if (
                damage.get("layeredColliderCount") != len(layered_records)
                or damage.get("duplicateColliderAssignments") != len(layered_records)
                or not layered_records
                or any(
                    len(collider.get("zoneStack", [])) < 2
                    for collider in damage.get("colliders", [])
                    if collider.get("recordIndex") in layered_records
                )
            ):
                raise AssertionError(f"{enemy} layered damage assignments lost their evidence")
        elif damage.get("duplicateColliderAssignments") != 0:
            raise AssertionError(f"{enemy} damage manifest contains unexpected duplicate assignments")
        if confidence.startswith("partial-"):
            partial += 1
            if damage.get("unmatchedActorCount", 0) < 1:
                raise AssertionError(f"{enemy} is marked partial without an unresolved actor")
            interaction = damage.get("interactionCoverage")
            if interaction == "verified-exact-zone-coverage":
                exact_zone_covered += 1
                if damage.get("uncoveredDamageZoneCount") != 0:
                    raise AssertionError(f"{enemy} claims exact zone coverage with an uncovered zone")
            elif interaction == "complete-with-evidence-labeled-proxies":
                proxy_zone_covered += 1
                proxies = damage.get("viewerDamageZoneProxies", {})
                proxy_count = len(proxies.get("boxes", [])) + len(proxies.get("colliders", []))
                if (
                    proxies.get("confidence") not in {
                        "inferred-from-game-colliders",
                        "inferred-single-candidate-game-collider",
                    }
                    or proxy_count < 1
                    or damage.get("proxyCoveredDamageZoneCount", 0) < 1
                    or damage.get("remainingUncoveredDamageZoneCount") != 0
                ):
                    raise AssertionError(f"{enemy} damage-zone proxy evidence is incomplete")
            else:
                incomplete_zone_coverage += 1
        else:
            complete += 1
            if damage.get("unmatchedActorCount", 0) != 0:
                raise AssertionError(f"{enemy} is marked complete with unresolved actors")
        total_hulls += len(colliders)
        total_mapped += len(mapped)

    automaton_authentic_renders = {
        "Vox Engine": "vox-engine-authentic-render.glb",
        "War Strider": "war-strider-authentic-render.glb",
        "Dropship": "dropship-authentic-render.glb",
        "Gunship": "gunship-authentic-render.glb",
        "Trooper": "trooper-authentic-render.glb",
        "Commissar": "commissar-authentic-render.glb",
        "Agitator": "agitator-authentic-render.glb",
        "Radical": "agitator-authentic-render.glb",
    }
    for enemy, filename in automaton_authentic_renders.items():
        if models[enemy].get("renderGlb") != f"assets/models/{filename}":
            raise AssertionError(f"{enemy} is not wired to its authentic Automaton render")
        render = glb_json(models_root / filename)
        baked = [
            material
            for material in render.get("materials", [])
            if material.get("extras", {}).get("hd2BrowserMaterial") == "filediver-accurate-shader-bake"
        ]
        alternate_meshes = [
            node.get("name", "")
            for node in render.get("nodes", [])
            if "mesh" in node
            and any(token in node.get("name", "").lower() for token in ("damaged", "destroyed"))
        ]
        if not baked or len(render.get("images", [])) < 3 or alternate_meshes:
            raise AssertionError(f"{enemy} lost its intact authentic shader bake: {alternate_meshes}")
        if enemy in {"Vox Engine", "War Strider"}:
            assert_nonblank_base_color(models_root / filename)

    predator_render_path = models_root / "predator-stalker-authentic-render.glb"
    predator_render_manifest_path = models_root / "predator-stalker-render.manifest.json"
    if models["Predator Stalker"].get("renderGlb") != (
        "assets/models/predator-stalker-authentic-render.glb"
    ):
        raise AssertionError("Predator Stalker is not wired to its verified variant render")
    predator_render = glb_json(predator_render_path)
    predator_evidence = json.loads(predator_render_manifest_path.read_text(encoding="utf-8"))
    expected_variant_materials = {"0x04233981fa5eac49", "0xc3296e9a9f06a5a6"}
    expected_variant_images = {
        "0x032bceb39b083398",
        "0x5b7926860c55c911",
        "0xcd80f2f90e95e977",
    }
    render_hash = hashlib.sha256(predator_render_path.read_bytes()).hexdigest().upper()
    if (
        predator_evidence.get("variantEvidence") != "verified-material-swap-component"
        or predator_evidence.get("entity") != "0xd1e990baf22d5a52"
        or len(predator_evidence.get("swaps", [])) != 2
        or predator_evidence.get("output", {}).get("sha256") != render_hash
        or not expected_variant_materials.issubset(
            {material.get("name") for material in predator_render.get("materials", [])}
        )
        or not expected_variant_images.issubset(
            {image.get("name") for image in predator_render.get("images", [])}
        )
    ):
        raise AssertionError("Predator Stalker lost its verified material-swap render evidence")

    automaton_vehicle_mounts = {
        "Vox Engine": {
            "manifest": "vox-engine-mounted-units.manifest.json",
            "sockets": {"l_gattling_socket1", "r_gattling_socket1", "l_cannon_socket", "r_cannon_socket"},
            "healthArmor": {(300, 3), (3500, 4)},
            "hullCount": 10,
        },
        "War Strider": {
            "manifest": "war-strider-mounted-units.manifest.json",
            "sockets": {"attach_left_gun", "attach_right_gun"},
            "healthArmor": {(500, 4)},
            "hullCount": 2,
        },
    }
    for enemy, expected in automaton_vehicle_mounts.items():
        if models[enemy].get("mountManifest") != f"assets/models/{expected['manifest']}":
            raise AssertionError(f"{enemy} mounted-unit catalog wiring is missing")
        assembly = json.loads((models_root / expected["manifest"]).read_text(encoding="utf-8"))
        mounts = assembly.get("mounts", [])
        if (
            assembly.get("assemblyConfidence") != "verified-mount-component-join"
            or {mount.get("attachNode") for mount in mounts} != expected["sockets"]
        ):
            raise AssertionError(f"{enemy} mounted-unit sockets changed unexpectedly")
        hull_count = 0
        observed_health_armor = set()
        for mount in mounts:
            render_path = models_root / mount["asset"]
            hitbox_path = models_root / mount["hitboxAsset"]
            if hashlib.sha256(render_path.read_bytes()).hexdigest() != mount.get("assetSha256", "").lower():
                raise AssertionError(f"{enemy} mounted render revision is stale: {mount.get('id')}")
            if hashlib.sha256(hitbox_path.read_bytes()).hexdigest() != mount.get("hitboxAssetSha256", "").lower():
                raise AssertionError(f"{enemy} mounted hitbox revision is stale: {mount.get('id')}")
            collision = json.loads((models_root / mount["collisionManifest"]).read_text(encoding="utf-8"))
            damage = json.loads((models_root / mount["damageManifest"]).read_text(encoding="utf-8"))
            if collision.get("geometryConfidence") != "verified" or mount.get("viewerHitboxProxy"):
                raise AssertionError(f"{enemy} must use exact mounted collision geometry: {mount.get('id')}")
            if damage.get("interactionCoverage") != "verified-exact-zone-coverage":
                raise AssertionError(f"{enemy} mounted damage coverage is incomplete: {mount.get('id')}")
            hull_count += collision.get("hullCount", 0)
            observed_health_armor.add((damage.get("mainHealth"), damage.get("defaultDamageableZone", {}).get("armor")))
        if hull_count != expected["hullCount"] or observed_health_armor != expected["healthArmor"]:
            raise AssertionError(f"{enemy} mounted weapon evidence changed unexpectedly")

    expanded_enemy_expectations = {
        "Hive Lord": (91, 56, 150000, "partial-actor-join", 10),
        "Vox Engine": (39, 30, 9000, "partial-layered-actor-join", 1),
        "War Strider": (36, 24, 3500, "verified-complete-actor-join", 0),
        "Dropship": (18, 6, 3500, "verified-complete-actor-join", 0),
        "Gunship": (5, 5, 950, "verified-complete-actor-join", 0),
        "Bile Spewer": (29, 20, 750, "verified-complete-actor-join", 0),
        "Fleshmob": (39, 18, 5000, "verified-complete-actor-join", 0),
        "Leviathan": (19, 14, 15000, "verified-complete-actor-join", 0),
        "Hulk (Scorcher)": (21, 16, 1800, "verified-complete-actor-join", 0),
        "Brood Commander": (26, 21, 800, "verified-complete-actor-join", 0),
        "Alpha Commander": (26, 21, 1000, "verified-complete-actor-join", 0),
        "Devastator": (23, 22, 750, "verified-complete-actor-join", 0),
        "Heavy Devastator": (25, 23, 750, "verified-complete-actor-join", 0),
        "Rocket Devastator": (29, 28, 750, "verified-complete-actor-join", 0),
        "Scout Strider": (30, 10, 500, "verified-complete-actor-join", 0),
        "Reinforced Scout Strider": (30, 10, 500, "verified-complete-actor-join", 0),
        "Stalker": (48, 46, 800, "partial-actor-join", 1),
        "Shrieker": (37, 25, 80, "verified-complete-actor-join", 0),
        "Overseer": (50, 48, 600, "verified-complete-actor-join", 0),
        "Elevated Overseer": (51, 49, 450, "verified-complete-actor-join", 0),
        "Crescent Overseer": (50, 48, 600, "verified-complete-actor-join", 0),
        "Watcher": (8, 6, 600, "verified-complete-actor-join", 0),
        "Stingray": (10, 9, 800, "partial-actor-join", 1),
        "Warrior": (26, 21, 325, "verified-complete-actor-join", 0),
        "Alpha Warrior": (26, 21, 325, "verified-complete-actor-join", 0),
        "Bile Warrior": (26, 21, 325, "verified-complete-actor-join", 0),
        "Rupture Warrior": (27, 21, 250, "verified-complete-actor-join", 0),
        "Spore Burst Warrior": (26, 21, 325, "verified-complete-actor-join", 0),
        "Hive Guard": (24, 20, 500, "partial-layered-actor-join", 1),
        "Hunter": (27, 21, 160, "verified-complete-actor-join", 0),
        "Predator Hunter": (27, 21, 175, "verified-complete-actor-join", 0),
        "Predator Stalker": (48, 46, 650, "partial-actor-join", 1),
        "Scavenger": (25, 7, 60, "verified-layered-actor-join", 0),
        "Pouncer": (31, 7, 60, "verified-layered-actor-join", 0),
        "Bile Spitter": (25, 7, 60, "verified-layered-actor-join", 0),
        "Nursing Spewer": (29, 20, 750, "verified-complete-actor-join", 0),
        "Rupture Spewer": (30, 20, 750, "verified-complete-actor-join", 0),
        "Berserker": (21, 18, 750, "partial-actor-join", 2),
        "Trooper": (22, 21, 125, "verified-complete-actor-join", 0),
        "Commissar": (22, 21, 125, "verified-complete-actor-join", 0),
        "Conflagration Devastator": (23, 22, 750, "verified-complete-actor-join", 0),
        "Agitator": (39, 27, 750, "verified-layered-actor-join", 0),
        "Radical": (39, 27, 750, "verified-layered-actor-join", 0),
        "Voteless (Medium)": (18, 10, 130, "partial-actor-join", 4),
        "Obtruder": (8, 6, 400, "verified-complete-actor-join", 0),
    }
    ragdoll_expectations = {
        "Hive Lord": (47, 44),
        "Dropship": (0, 18),
        "Gunship": (0, 5),
        "Hulk (Scorcher)": (5, 16),
        "Brood Commander": (2, 24),
        "Alpha Commander": (2, 24),
        "Devastator": (1, 22),
        "Heavy Devastator": (2, 23),
        "Rocket Devastator": (7, 22),
        "Scout Strider": (11, 19),
        "Reinforced Scout Strider": (11, 19),
        "Stalker": (7, 41),
        "Shrieker": (1, 36),
        "Overseer": (29, 21),
        "Elevated Overseer": (30, 21),
        "Crescent Overseer": (29, 21),
        "Watcher": (6, 2),
        "Stingray": (0, 10),
        "Bile Spewer": (5, 24),
        "Fleshmob": (11, 28),
        "War Strider": (15, 21),
        "Warrior": (2, 24),
        "Alpha Warrior": (2, 24),
        "Bile Warrior": (2, 24),
        "Rupture Warrior": (3, 24),
        "Spore Burst Warrior": (2, 24),
        "Hive Guard": (2, 22),
        "Hunter": (1, 26),
        "Predator Hunter": (1, 26),
        "Predator Stalker": (7, 41),
        "Scavenger": (1, 24),
        "Pouncer": (1, 30),
        "Bile Spitter": (1, 24),
        "Nursing Spewer": (5, 24),
        "Rupture Spewer": (6, 24),
        "Berserker": (1, 20),
        "Trooper": (1, 21),
        "Commissar": (1, 21),
        "Conflagration Devastator": (1, 22),
        "Agitator": (20, 19),
        "Radical": (20, 19),
        "Voteless (Medium)": (2, 16),
        "Obtruder": (6, 2),
    }
    partial_zone_coverage_expectations = {
        "Hive Lord": "verified-exact-zone-coverage",
        "Vox Engine": "verified-exact-zone-coverage",
        "Factory Strider": "verified-exact-zone-coverage",
        "Harvester": "complete-with-evidence-labeled-proxies",
        "Stalker": "verified-exact-zone-coverage",
        "Stingray": "complete-with-evidence-labeled-proxies",
        "Hive Guard": "verified-exact-zone-coverage",
        "Predator Stalker": "verified-exact-zone-coverage",
        "Berserker": "complete-with-evidence-labeled-proxies",
        "Voteless (Medium)": "verified-exact-zone-coverage",
    }
    for enemy, (hulls, mapped, main_health, confidence, unmatched) in expanded_enemy_expectations.items():
        entry = models[enemy]
        collision = json.loads((project_root / entry["collisionManifest"]).read_text(encoding="utf-8"))
        damage = json.loads((project_root / entry["damageManifest"]).read_text(encoding="utf-8"))
        if (
            collision.get("hullCount") != hulls
            or damage.get("mappedColliderCount") != mapped
            or damage.get("mainHealth") != main_health
            or damage.get("mappingConfidence") != confidence
            or damage.get("unmatchedActorCount") != unmatched
        ):
            raise AssertionError(f"{enemy} expanded-model evidence changed unexpectedly")
        expected_coverage = partial_zone_coverage_expectations.get(enemy)
        if expected_coverage and damage.get("interactionCoverage") != expected_coverage:
            raise AssertionError(f"{enemy} damage-zone interaction coverage regressed")
        document = glb_json(project_root / entry["glb"])
        visible_alternates = [
            node.get("name", "")
            for node in document.get("nodes", [])
            if "mesh" in node
            and any(token in node.get("name", "").lower() for token in ("gib", "damaged", "destroyed"))
            and node.get("extras", {}).get("default_hidden") != 1
        ]
        if visible_alternates:
            raise AssertionError(f"{enemy} exposes damaged render variants by default: {visible_alternates}")
        if enemy in ragdoll_expectations:
            base_hulls, ragdoll_hulls = ragdoll_expectations[enemy]
            ragdoll_source = collision.get("source", {}).get("ragdollProfile")
            if (
                collision.get("basePhysicsHullCount") != base_hulls
                or collision.get("ragdollHullCount") != ragdoll_hulls
                or not collision.get("ragdollMappingEvidence", "").startswith(
                    "Exact hknpPhysicsSystemData::bodyCinfoWithAttachment"
                )
                or not ragdoll_source
                or len(ragdoll_source.get("sha256", "")) != 64
            ):
                raise AssertionError(f"{enemy} lost its exact ragdoll body-to-shape evidence")

    for enemy, expected_coverage in partial_zone_coverage_expectations.items():
        entry = models[enemy]
        damage = json.loads((project_root / entry["damageManifest"]).read_text(encoding="utf-8"))
        if damage.get("interactionCoverage") != expected_coverage:
            raise AssertionError(f"{enemy} damage-zone interaction coverage regressed")
    berserker_proxies = json.loads(
        (models_root / "berserker-damage-zones.manifest.json").read_text(encoding="utf-8")
    )["viewerDamageZoneProxies"]
    if (
        berserker_proxies.get("mode") != "comparative-box-proxy"
        or len(berserker_proxies.get("boxes", [])) != 2
        or set(berserker_proxies.get("analogs", []))
        != {"Devastator", "Heavy Devastator", "Rocket Devastator"}
        or any(proxy.get("boxSize") != [0.435137, 0.395236, 0.377271] for proxy in berserker_proxies["boxes"])
    ):
        raise AssertionError("Berserker shoulderplate proxy evidence changed")
    for slug, expected_record, expected_hash in (
        ("harvester", 24, "43a3844e"),
        ("stingray", 0, "9b115563"),
    ):
        proxy = json.loads((models_root / f"{slug}-damage-zones.manifest.json").read_text(encoding="utf-8"))[
            "viewerDamageZoneProxies"
        ]
        records = proxy.get("colliders", [])
        if (
            proxy.get("mode") != "local-unassigned-collider-proxy"
            or len(records) != 1
            or records[0].get("recordIndex") != expected_record
            or records[0].get("expectedColliderHash") != expected_hash
        ):
            raise AssertionError(f"{slug} local collider proxy evidence changed")

    hulk_render_path = models_root / "hulk-scorcher-authentic-render.glb"
    hulk_render = glb_json(hulk_render_path)
    hulk_mesh_nodes = [node for node in hulk_render.get("nodes", []) if "mesh" in node]
    hulk_baked = [
        material
        for material in hulk_render.get("materials", [])
        if material.get("extras", {}).get("hd2BrowserMaterial") == "filediver-accurate-shader-bake"
    ]
    if (
        len(hulk_mesh_nodes) != 11
        or len(hulk_render.get("images", [])) < 6
        or len(hulk_baked) != 1
        or any(
            any(token in node.get("name", "").lower() for token in ("damaged", "destroyed"))
            for node in hulk_mesh_nodes
        )
        or "hulk-scorcher-authentic-render.glb" not in html
    ):
        raise AssertionError("Hulk (Scorcher) lost its intact authentic shader bake")

    for enemy, slug, minimum_baked in (
        ("Devastator", "devastator", 2),
        ("Heavy Devastator", "heavy-devastator", 3),
        ("Rocket Devastator", "rocket-devastator", 4),
    ):
        render = glb_json(models_root / f"{slug}-authentic-render.glb")
        baked = [
            material
            for material in render.get("materials", [])
            if material.get("extras", {}).get("hd2BrowserMaterial") == "filediver-accurate-shader-bake"
        ]
        used_materials = {
            primitive.get("material")
            for mesh in render.get("meshes", [])
            for primitive in mesh.get("primitives", [])
            if "material" in primitive
        }
        alternate_materials = [
            render["materials"][index].get("name", "")
            for index in used_materials
            if any(
                token in render["materials"][index].get("name", "").lower()
                for token in ("damaged", "destroyed")
            )
        ]
        if len(baked) < minimum_baked or not render.get("images") or alternate_materials:
            raise AssertionError(f"{enemy} lost its intact authentic material bake: {alternate_materials}")
        if f'"{enemy}":{{slug:"{slug}"' not in html:
            raise AssertionError(f"{enemy} is not connected to the 3D viewer")

    devastator_mount_expectations = {
        "Devastator": ("devastator-mounted-units.manifest.json", 1),
        "Heavy Devastator": ("heavy-devastator-mounted-units.manifest.json", 2),
        "Rocket Devastator": ("rocket-devastator-mounted-units.manifest.json", 1),
        "Conflagration Devastator": ("conflagration-devastator-mounted-units.manifest.json", 2),
    }
    for enemy, (filename, mount_count) in devastator_mount_expectations.items():
        assembly = json.loads((models_root / filename).read_text(encoding="utf-8"))
        if assembly.get("assemblyConfidence") != "verified-mount-component-join":
            raise AssertionError(f"{enemy} mounted-equipment evidence failed its assembly gate")
        mounts = assembly.get("mounts", [])
        if len(mounts) != mount_count:
            raise AssertionError(f"{enemy} mounted-equipment count changed unexpectedly")
        for mount in mounts:
            asset = models_root / mount["asset"]
            if not asset.is_file() or hashlib.sha256(asset.read_bytes()).hexdigest().upper() != mount["assetSha256"]:
                raise AssertionError(f"{enemy} mounted asset is missing or stale: {mount.get('id')}")
    heavy_mounts = json.loads(
        (models_root / "heavy-devastator-mounted-units.manifest.json").read_text(encoding="utf-8")
    )
    shield = next((mount for mount in heavy_mounts["mounts"] if mount["id"] == "shield"), None)
    if not shield:
        raise AssertionError("Heavy Devastator lost its separate destroyable shield")
    shield_collision = json.loads((models_root / shield["collisionManifest"]).read_text(encoding="utf-8"))
    shield_damage = json.loads((models_root / shield["damageManifest"]).read_text(encoding="utf-8"))
    shield_zone = shield_damage.get("zones", [{}])[0]
    if (
        shield_collision.get("hullCount") != 2
        or shield_damage.get("mappedColliderCount") != 1
        or shield_damage.get("mainHealth") != 800
        or shield_zone.get("armor") != 4
        or shield_zone.get("projectile_durable_resistance") != 0.7
    ):
        raise AssertionError("Heavy Devastator shield collision or HealthComponent data changed unexpectedly")

    conflagration_mounts = json.loads(
        (models_root / "conflagration-devastator-mounted-units.manifest.json").read_text(encoding="utf-8")
    )
    conflagration_shield = next(
        (mount for mount in conflagration_mounts["mounts"] if mount["id"] == "shield"), None
    )
    conflagration_gun = next(
        (mount for mount in conflagration_mounts["mounts"] if mount["id"] == "incendiary-rifle"), None
    )
    if (
        not conflagration_shield
        or not conflagration_gun
        or conflagration_shield.get("attachNode") != "attach_l_hand"
        or conflagration_gun.get("attachNode") != "attach_r_hand"
    ):
        raise AssertionError("Conflagration Devastator lost its exact hand-socket equipment assembly")
    conflagration_shield_collision = json.loads(
        (models_root / conflagration_shield["collisionManifest"]).read_text(encoding="utf-8")
    )
    conflagration_shield_damage = json.loads(
        (models_root / conflagration_shield["damageManifest"]).read_text(encoding="utf-8")
    )
    conflagration_shield_zone = conflagration_shield_damage.get("zones", [{}])[0]
    if (
        conflagration_shield_collision.get("hullCount") != 2
        or conflagration_shield_damage.get("mappedColliderCount") != 1
        or conflagration_shield_damage.get("mainHealth") != 800
        or conflagration_shield_zone.get("armor") != 4
        or conflagration_shield_zone.get("projectile_durable_resistance") != 0.7
    ):
        raise AssertionError("Conflagration Devastator shield evidence changed unexpectedly")

    scout_mount_expectations = {
        "Scout Strider": ("scout-strider-mounted-units.manifest.json", 2),
        "Reinforced Scout Strider": ("reinforced-scout-strider-mounted-units.manifest.json", 4),
    }
    for enemy, (filename, expected_count) in scout_mount_expectations.items():
        assembly = json.loads((models_root / filename).read_text(encoding="utf-8"))
        mounts = assembly.get("mounts", [])
        authentic = set(assembly.get("authenticShaderBakes", []))
        if assembly.get("assemblyConfidence") != "verified-mount-component-join" or len(mounts) != expected_count:
            raise AssertionError(f"{enemy} mounted child-unit assembly changed unexpectedly")
        for mount in mounts:
            asset = models_root / mount["asset"]
            hitbox = models_root / mount["hitboxAsset"]
            if (
                mount["asset"] not in authentic
                or hashlib.sha256(asset.read_bytes()).hexdigest().upper() != mount["assetSha256"]
                or hashlib.sha256(hitbox.read_bytes()).hexdigest().upper() != mount["hitboxAssetSha256"]
            ):
                raise AssertionError(f"{enemy} mounted child asset is stale: {mount.get('id')}")
            render = glb_json(asset)
            if not any(
                material.get("extras", {}).get("hd2BrowserMaterial") == "filediver-accurate-shader-bake"
                for material in render.get("materials", [])
            ):
                raise AssertionError(f"{enemy} mounted child lost its authentic shader bake: {mount.get('id')}")
            collision = json.loads((models_root / mount["collisionManifest"]).read_text(encoding="utf-8"))
            damage = json.loads((models_root / mount["damageManifest"]).read_text(encoding="utf-8"))
            if collision.get("geometryConfidence") != "verified" or damage.get("unmatchedActorCount") != 0:
                raise AssertionError(f"{enemy} mounted child failed its exact damage gate: {mount.get('id')}")

    factory_mounts = json.loads((models_root / "factory-strider-mounted-units.manifest.json").read_text(encoding="utf-8"))
    if factory_mounts.get("assemblyConfidence") != "verified-mount-component-join":
        raise AssertionError("Factory Strider mounted-unit manifest failed its evidence gate")
    mounts = factory_mounts.get("mounts", [])
    authentic_mounts = set(factory_mounts.get("authenticShaderBakes", []))
    mounted_hitbox_count = 0
    if len(mounts) != 3 or len({mount.get("attachNode") for mount in mounts}) != 3:
        raise AssertionError("Factory Strider must have two chin guns and one dorsal cannon on distinct sockets")
    for mount in mounts:
        asset = mount.get("asset")
        mounted_path = models_root / asset
        if not mounted_path.is_file() or mounted_path.stat().st_size < 1_000_000 or mounted_path.read_bytes()[:4] != b"glTF":
            raise AssertionError(f"Factory Strider mounted asset is missing or invalid: {asset}")
        expected_hash = mount.get("assetSha256", "").lower()
        actual_hash = hashlib.sha256(mounted_path.read_bytes()).hexdigest()
        if expected_hash != actual_hash:
            raise AssertionError(f"Factory Strider mounted asset revision is stale: {asset}")
        mounted_document = glb_json(mounted_path)
        if not mounted_document.get("meshes") or not mounted_document.get("materials"):
            raise AssertionError(f"Factory Strider mounted asset has no render geometry: {asset}")
        if asset == "factory-strider-dorsal-cannon.glb":
            node_names = {node.get("name") for node in mounted_document.get("nodes", [])}
            if not {"StingrayEntityRoot", "pitch", "barrel", "muzzle"}.issubset(node_names):
                raise AssertionError("Factory Strider dorsal cannon lost its articulated barrel hierarchy")
            if len(mounted_document.get("images", [])) < 3 or asset not in authentic_mounts:
                raise AssertionError("Factory Strider dorsal cannon lost its authentic baked textures")
            baked = [
                material
                for material in mounted_document.get("materials", [])
                if material.get("extras", {}).get("hd2BrowserMaterial") == "filediver-accurate-shader-bake"
            ]
            if len(baked) != 1 or "normalTexture" not in baked[0]:
                raise AssertionError("Factory Strider dorsal cannon material is not a complete authentic bake")
            rotation = mount.get("axisRootRotation")
            if rotation != [-0.70710678, 0, 0, 0.70710678]:
                raise AssertionError("Factory Strider authentic dorsal cannon has an invalid socket-local axis correction")
        hitbox_asset = mount.get("hitboxAsset")
        collision_manifest_name = mount.get("collisionManifest")
        damage_manifest_name = mount.get("damageManifest")
        if not all((hitbox_asset, collision_manifest_name, damage_manifest_name)):
            raise AssertionError(f"Factory Strider mounted weapon is missing hitbox evidence: {mount.get('id')}")
        hitbox_path = models_root / hitbox_asset
        hitbox_bytes = hitbox_path.read_bytes() if hitbox_path.is_file() else b""
        if len(hitbox_bytes) < 100_000 or hitbox_bytes[:4] != b"glTF":
            raise AssertionError(f"Factory Strider mounted hitbox asset is missing or invalid: {hitbox_asset}")
        if hashlib.sha256(hitbox_bytes).hexdigest() != mount.get("hitboxAssetSha256", "").lower():
            raise AssertionError(f"Factory Strider mounted hitbox revision is stale: {hitbox_asset}")
        collision_manifest = json.loads((models_root / collision_manifest_name).read_text(encoding="utf-8"))
        damage_manifest = json.loads((models_root / damage_manifest_name).read_text(encoding="utf-8"))
        colliders = collision_manifest.get("colliders", [])
        hitbox_nodes = {node.get("name") for node in glb_json(hitbox_path).get("nodes", [])}
        if collision_manifest.get("geometryConfidence") != "verified" or len(colliders) != collision_manifest.get("hullCount"):
            raise AssertionError(f"Factory Strider mounted collision manifest failed its geometry gate: {mount.get('id')}")
        for collider in colliders:
            if "hknpCapsuleShape" in collider.get("shapeTypes", []):
                size = sorted(collider.get("localSize", []))
                if len(size) != 3 or size[1] <= 0.1:
                    raise AssertionError(
                        f"Factory Strider mounted capsule radius collapsed during extraction: {mount.get('id')}"
                    )
        if not {collider.get("nodeName") for collider in colliders}.issubset(hitbox_nodes):
            raise AssertionError(f"Factory Strider mounted hitbox GLB is missing manifest nodes: {mount.get('id')}")
        if not damage_manifest.get("mainHealth") or not damage_manifest.get("defaultDamageableZone"):
            raise AssertionError(f"Factory Strider mounted weapon has no destroyable HealthComponent: {mount.get('id')}")
        proxy = mount.get("viewerHitboxProxy", {})
        proxy_records = proxy.get("records", {})
        analog_enemies = {item.get("enemy") for item in proxy.get("analogs", [])}
        if (
            proxy.get("mode") != "comparative-box-proxy"
            or proxy.get("confidence") != "inferred-from-game-colliders"
            or len(proxy_records) != len(colliders)
            or not {"Gatekeeper", "War Strider"}.issubset(analog_enemies)
            or any(len(item.get("boxScale", [])) != 3 for item in proxy_records.values())
        ):
            raise AssertionError(f"Factory Strider mounted box-proxy evidence is incomplete: {mount.get('id')}")
        if mount.get("id") == "dorsal-cannon":
            if (
                proxy_records.get("0", {}).get("renderNode") != "g_turret_default"
                or proxy_records.get("1", {}).get("renderNode") != "g_turret_gun"
                or proxy_records.get("2", {}).get("renderNode") != "g_turret_default"
                or proxy_records.get("0", {}).get("label") != "turret housing"
            ):
                raise AssertionError("Factory Strider dorsal cannon proxies are not fitted to its render meshes")
        expected = (900, 5) if mount.get("id") == "dorsal-cannon" else (300, 3)
        default_zone = damage_manifest["defaultDamageableZone"]
        if (damage_manifest["mainHealth"], default_zone.get("armor")) != expected:
            raise AssertionError(f"Factory Strider mounted weapon health/armor changed unexpectedly: {mount.get('id')}")
        mounted_hitbox_count += len(colliders)
    if (
        "assetSha256.slice(0,16)" not in html
        or "axisRoot.quaternion.fromArray(mount.axisRootRotation)" not in html
        or "axisRoot.quaternion.identity()" not in html
        or "mountedDamageZone" not in html
        or "hitboxAssetSha256.slice(0,16)" not in html
        or "new THREE.BoxGeometry" not in html
        or "renderSource.parent.add(object)" not in html
        or "Gatekeeper / War Strider analog" not in html
    ):
        raise AssertionError("Factory Strider mounts are missing cache-safe socket-local axis handling")
    if mounted_hitbox_count != 7:
        raise AssertionError(f"Expected 7 mounted-weapon hitboxes, found {mounted_hitbox_count}")

    tank_mount_specs = {
        "Annihilator Tank": ("annihilator-tank-mounted-units.manifest.json", 9),
        "Shredder Tank": ("shredder-tank-mounted-units.manifest.json", 7),
        "Barrager Tank": ("barrager-tank-mounted-units.manifest.json", 6),
    }
    tank_hitbox_count = 0
    for enemy, (manifest_name, expected_hulls) in tank_mount_specs.items():
        assembly = json.loads((models_root / manifest_name).read_text(encoding="utf-8"))
        mounts = assembly.get("mounts", [])
        if assembly.get("enemy") != enemy or assembly.get("assemblyConfidence") != "verified-mount-component-join":
            raise AssertionError(f"{enemy} mounted turret failed its evidence gate")
        if len(mounts) != 1 or mounts[0].get("attachNode") != "attach_turret":
            raise AssertionError(f"{enemy} must have one turret on the decoded attach_turret socket")
        mount = mounts[0]
        if mount.get("asset") not in set(assembly.get("authenticShaderBakes", [])):
            raise AssertionError(f"{enemy} mounted turret is not marked as an authentic shader bake")
        if mount.get("viewerHitboxProxy"):
            raise AssertionError(f"{enemy} unexpectedly substitutes a hand-authored turret hitbox")
        if mount.get("axisRootRotation") != [-0.70710678, 0, 0, 0.70710678]:
            raise AssertionError(f"{enemy} authentic turret lost its socket-local axis correction")
        render_path = models_root / mount["asset"]
        hitbox_path = models_root / mount["hitboxAsset"]
        if hashlib.sha256(render_path.read_bytes()).hexdigest() != mount.get("assetSha256", "").lower():
            raise AssertionError(f"{enemy} mounted turret render revision is stale")
        if hashlib.sha256(hitbox_path.read_bytes()).hexdigest() != mount.get("hitboxAssetSha256", "").lower():
            raise AssertionError(f"{enemy} mounted turret collision revision is stale")
        render_document = glb_json(render_path)
        mesh_nodes = [node for node in render_document.get("nodes", []) if "mesh" in node]
        alternate_meshes = [
            node.get("name", "")
            for node in mesh_nodes
            if any(token in node.get("name", "").lower() for token in ("damaged", "destroyed"))
        ]
        baked = [
            material
            for material in render_document.get("materials", [])
            if material.get("extras", {}).get("hd2BrowserMaterial") == "filediver-accurate-shader-bake"
        ]
        if not baked or len(render_document.get("images", [])) < 3 or alternate_meshes:
            raise AssertionError(f"{enemy} mounted turret lost its intact authentic textures: {alternate_meshes}")
        collision = json.loads((models_root / mount["collisionManifest"]).read_text(encoding="utf-8"))
        damage = json.loads((models_root / mount["damageManifest"]).read_text(encoding="utf-8"))
        if collision.get("geometryConfidence") != "verified" or collision.get("hullCount") != expected_hulls:
            raise AssertionError(f"{enemy} mounted turret collision geometry changed unexpectedly")
        if damage.get("mappingConfidence") != "verified-complete-actor-join" or damage.get("mainHealth") != 2100:
            raise AssertionError(f"{enemy} mounted turret HealthComponent mapping changed unexpectedly")
        tank_hitbox_count += expected_hulls
    if tank_hitbox_count != 22:
        raise AssertionError(f"Expected 22 exact tank-turret collision hulls, found {tank_hitbox_count}")
    tank_body = json.loads((models_root / "automaton-tank-base-damage-zones.manifest.json").read_text(encoding="utf-8"))
    if tank_body.get("mainHealth") != 4000 or tank_body.get("mappedColliderCount") != 6:
        raise AssertionError("Automaton tank hull HealthComponent mapping changed unexpectedly")
    tank_render_path = models_root / "automaton-tank-base-authentic-render.glb"
    tank_render = glb_json(tank_render_path)
    tank_mesh_nodes = [node for node in tank_render.get("nodes", []) if "mesh" in node]
    tank_baked = [
        material
        for material in tank_render.get("materials", [])
        if material.get("extras", {}).get("hd2BrowserMaterial") == "filediver-accurate-shader-bake"
    ]
    if (
        len(tank_mesh_nodes) != 7
        or not tank_baked
        or len(tank_render.get("images", [])) < 6
        or any(
            any(token in node.get("name", "").lower() for token in ("damaged", "destroyed"))
            for node in tank_mesh_nodes
        )
    ):
        raise AssertionError("Automaton tank body lost its intact authentic Filediver shader bake")
    for enemy in (
        "Hive Lord",
        "Vox Engine",
        "Dropship",
        "Gunship",
        "Charger Behemoth",
        "Spore Charger",
        "Rupture Charger",
        "Annihilator Tank",
        "Shredder Tank",
        "Barrager Tank",
        "Cannon Turret",
        "Bile Spewer",
        "Fleshmob",
        "Leviathan",
        "Hulk (Scorcher)",
        "Brood Commander",
        "Alpha Commander",
    ):
        if f'"{enemy}":' not in html:
            raise AssertionError(f"{enemy} is not connected to the 3D viewer")
    if (
        "entry.assetSlug||entry.slug" not in html
        or "No targeting proxies are substituted" not in html
        or "automaton-tank-base-authentic-render.glb" not in html
        or "automaton-heavy-cannon-turret-authentic-render.glb" not in html
        or "object.userData.hd2GeometryOnly=!damage" not in html
        or "hull.visible=showHulls&&(!hull.userData.hd2GeometryOnly||showGeometry)" not in html
        or "viewerDamageZoneProxies" not in html
        or "bodyProxyDamage" not in html
        or "DAMAGE ZONES VERIFIED / ACTOR REFERENCES PARTIAL" not in html
    ):
        raise AssertionError("Shared tank geometry or exact mounted-turret evidence is not connected to the viewer")

    factory_document = glb_json(models_root / "factory-strider-collision-research.glb")
    hidden_variants = [node for node in factory_document.get("nodes", []) if node.get("extras", {}).get("default_hidden") == 1]
    if len(hidden_variants) < 10 or "object.userData?.default_hidden===1" not in html:
        raise AssertionError("Factory Strider damaged/hidden render variants are not being suppressed")

    authentic_path = models_root / "factory-strider-authentic-render.glb"
    if not authentic_path.is_file() or authentic_path.stat().st_size < 2_000_000 or authentic_path.read_bytes()[:4] != b"glTF":
        raise AssertionError("Factory Strider authentic render GLB is missing or invalid")
    authentic = glb_json(authentic_path)
    if len(authentic.get("meshes", [])) != 24 or len(authentic.get("images", [])) < 6:
        raise AssertionError("Factory Strider authentic render is missing intact geometry or baked textures")
    bad_names = [
        node.get("name", "")
        for node in authentic.get("nodes", [])
        if node.get("extras", {}).get("default_hidden") == 1
        or any(token in node.get("name", "").lower() for token in ("damaged", "destroyed"))
    ]
    if bad_names:
        raise AssertionError(f"Factory Strider authentic render contains alternate damage meshes: {bad_names}")
    baked_materials = [
        material
        for material in authentic.get("materials", [])
        if material.get("extras", {}).get("hd2BrowserMaterial") == "filediver-accurate-shader-bake"
    ]
    if len(baked_materials) != 2:
        raise AssertionError("Factory Strider authentic LUT materials were not baked")
    for material in baked_materials:
        pbr = material.get("pbrMetallicRoughness", {})
        if pbr.get("baseColorTexture", {}).get("texCoord", 0) != 0:
            raise AssertionError("Factory Strider authentic texture does not use browser-safe TEXCOORD_0")
        if material.get("normalTexture", {}).get("texCoord", 0) != 0:
            raise AssertionError("Factory Strider authentic normal detail does not use browser-safe TEXCOORD_0")
        if "normalTexture" not in material:
            raise AssertionError("Factory Strider authentic material is missing its game-derived normal/detail bake")
    if "factory-strider-authentic-render.glb" not in html or "if(authenticRender)" not in html:
        raise AssertionError("Factory Strider authentic render is not connected to the viewer")

    if incomplete_zone_coverage or exact_zone_covered + proxy_zone_covered != partial:
        raise AssertionError("At least one actor-partial model still has incomplete damage-zone interaction coverage")
    print(f"Verified {len(references)} image references and {len(actual)} WebP files")
    print(
        f"Verified {len(models)} hydrated large-enemy GLBs: {total_hulls} collision hulls, "
        f"{total_mapped} exact mapped damage hulls, {complete} actor-complete models, "
        f"{exact_zone_covered} exact-zone-covered models with redundant unresolved actor references, "
        f"and {proxy_zone_covered} proxy-zone-covered models; 0 models have incomplete zone interaction coverage"
    )
    print("Verified 3 Factory Strider mounted weapon instances on decoded attachment sockets")
    print("Verified 7 selectable Factory Strider mounted-weapon box proxies with destroyable HealthComponents")
    print("Verified 3 Automaton tank turret assemblies with 22 exact collision hulls and destroyable HealthComponents")
    print("Verified intact authentic Automaton tank, mounted turret, and Cannon Turret shader bakes")
    print("Verified Factory Strider 24-piece intact render with game-derived shader bake")
    print("Data/calculation core unchanged" if args.original else "Core comparison skipped")
    print("Project verification passed")


if __name__ == "__main__":
    main()
