from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

from PIL import Image


PNG_RE = re.compile(r'"([^"\r\n]+\.png)"', re.IGNORECASE)


def glb_json(path: Path) -> dict:
    with path.open("rb") as source:
        header = source.read(20)
        if len(header) != 20 or header[:4] != b"glTF":
            raise AssertionError(f"{path.name} is not a valid binary glTF")
        chunk_length, chunk_type = struct.unpack_from("<II", header, 12)
        if chunk_type != 0x4E4F534A:
            raise AssertionError(f"{path.name} does not start with a JSON chunk")
        payload = header[20:] + source.read(chunk_length)
    return json.loads(payload[:chunk_length].decode("utf-8").rstrip("\0 "))


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
    models = catalog.get("models", {})
    if len(models) != 39:
        raise AssertionError(f"Expected 39 large-enemy 3D models, found {len(models)}")
    complete = partial = total_hulls = total_mapped = 0
    for enemy, entry in models.items():
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
        else:
            complete += 1
            if damage.get("unmatchedActorCount", 0) != 0:
                raise AssertionError(f"{enemy} is marked complete with unresolved actors")
        total_hulls += len(colliders)
        total_mapped += len(mapped)

    expanded_enemy_expectations = {
        "Hive Lord": (91, 56, 150000, "partial-actor-join", 10),
        "Vox Engine": (39, 30, 9000, "partial-layered-actor-join", 1),
        "Dropship": (18, 6, 3500, "verified-complete-actor-join", 0),
        "Gunship": (5, 5, 950, "verified-complete-actor-join", 0),
        "Bile Spewer": (5, 4, 750, "partial-actor-join", 16),
        "Fleshmob": (11, 10, 5000, "partial-actor-join", 8),
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

    print(f"Verified {len(references)} image references and {len(actual)} WebP files")
    print(
        f"Verified {len(models)} hydrated large-enemy GLBs: {total_hulls} collision hulls, "
        f"{total_mapped} mapped damage hulls, {complete} complete and {partial} partial models"
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
