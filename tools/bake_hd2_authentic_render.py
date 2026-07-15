"""Bake Filediver's HD2 shader graph into a browser-ready intact GLB.

Run this script inside Blender after importing a Filediver GLB with
``hd2_accurate_blender_importer.py``.  The importer reconstructs the game's
material LUT, ID masks, decals, weathering, and visibility groups.  This script
bakes those procedural results to ordinary glTF PBR textures, removes hidden
damage-state meshes and collision proxies, and exports only the intact render
model.

Example::

    blender --background imported.blend --python tools/bake_hd2_authentic_render.py -- \
        --output assets/models/factory-strider-authentic-render.glb
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import bpy


BAKE_OUTPUTS = (
    ("base-color", "Bake_Color", "sRGB"),
    ("metallic", "Bake_Metallic", "Non-Color"),
    ("roughness", "Bake_Roughness", "Non-Color"),
    ("normal", "Bake_Normal", "Non-Color"),
)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--texture-dir", type=Path)
    parser.add_argument("--size", type=int, default=2048)
    parser.add_argument("--samples", type=int, default=1)
    return parser.parse_args(argv)


def is_collision_proxy(obj: bpy.types.Object) -> bool:
    if obj.type != "MESH":
        return False
    names = " ".join(slot.material.name for slot in obj.material_slots if slot.material)
    return "m_collision" in names.lower() or obj.name == "0x98795381"


def visible_render_objects() -> list[bpy.types.Object]:
    return [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH"
        and not obj.hide_render
        and not is_collision_proxy(obj)
        and not any(token in obj.name.lower() for token in ("damaged", "destroyed"))
    ]


def accurate_materials(objects: list[bpy.types.Object]) -> list[bpy.types.Material]:
    materials: dict[str, bpy.types.Material] = {}
    for obj in objects:
        for slot in obj.material_slots:
            material = slot.material
            if material and material.get("needsBakeUVs"):
                materials[material.name] = material
    return [materials[name] for name in sorted(materials)]


def find_shader_group(material: bpy.types.Material) -> bpy.types.ShaderNodeGroup:
    for node in material.node_tree.nodes:
        if node.type == "GROUP" and node.name == "HD2 Shader Template":
            return node
    raise RuntimeError(f"{material.name} has no HD2 Shader Template node")


def ensure_bake_uvs(objects: list[bpy.types.Object]) -> None:
    for obj in objects:
        if not obj.data.uv_layers:
            raise RuntimeError(f"{obj.name} has no UV map")
        layer = obj.data.uv_layers.get("UVs for Baking") or obj.data.uv_layers[0]
        obj.data.uv_layers.active = layer
        layer.active_render = True


def select_objects(objects: list[bpy.types.Object]) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]


def bake_material_output(
    material: bpy.types.Material,
    objects: list[bpy.types.Object],
    output_name: str,
    socket_name: str,
    color_space: str,
    texture_dir: Path,
    size: int,
) -> bpy.types.Image:
    image_name = f"{material.name} {output_name}"
    image = bpy.data.images.new(image_name, width=size, height=size, alpha=False)
    image.colorspace_settings.name = color_space
    image.file_format = "PNG"
    image.filepath_raw = str(texture_dir / f"{material.name.replace(' ', '-')}-{output_name}.png")

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    group = find_shader_group(material)
    output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
    if output is None:
        raise RuntimeError(f"{material.name} has no material output")

    image_node = nodes.new("ShaderNodeTexImage")
    image_node.name = f"HD2 Bake Target {output_name}"
    image_node.image = image
    nodes.active = image_node
    image_node.select = True

    # Blender validates the active bake target for every material slot on a
    # selected mesh, even though only the faces assigned to ``material`` write
    # into this image.  HD2 vehicle meshes commonly contain several armor
    # materials in one object.  Without harmless targets in the other slots,
    # Cycles clears the requested image and leaves it completely black.  This
    # went unnoticed on simpler single-material units and on whichever
    # material happened to bake last.
    dummy_image = bpy.data.images.new(
        f"{material.name} {output_name} unused-slot target",
        width=1,
        height=1,
        alpha=False,
    )
    dummy_nodes: list[tuple[bpy.types.Material, bpy.types.Node, bpy.types.Node | None]] = []

    emission = nodes.new("ShaderNodeEmission")
    emission.name = f"HD2 Bake Emission {output_name}"
    links.new(group.outputs[socket_name], emission.inputs["Color"])
    original_surface = output.inputs["Surface"].links[0].from_socket if output.inputs["Surface"].links else None
    links.new(emission.outputs["Emission"], output.inputs["Surface"])

    target_objects = [
        obj
        for obj in objects
        if any(slot.material == material for slot in obj.material_slots)
    ]
    for obj in target_objects:
        for slot in obj.material_slots:
            other = slot.material
            if other is None or other == material or not other.use_nodes:
                continue
            other_nodes = other.node_tree.nodes
            previous_active = other_nodes.active
            dummy_node = other_nodes.new("ShaderNodeTexImage")
            dummy_node.name = f"HD2 Unused Bake Target {material.name} {output_name}"
            dummy_node.image = dummy_image
            dummy_node.select = True
            other_nodes.active = dummy_node
            dummy_nodes.append((other, dummy_node, previous_active))
    ensure_bake_uvs(target_objects)
    select_objects(target_objects)
    try:
        bpy.ops.object.bake(type="EMIT", use_clear=True, margin=12)
        image.save()
        image.pack()
    finally:
        for other, dummy_node, previous_active in dummy_nodes:
            other_nodes = other.node_tree.nodes
            other_nodes.remove(dummy_node)
            if previous_active is not None and previous_active.name in other_nodes:
                other_nodes.active = previous_active
        bpy.data.images.remove(dummy_image)

    if original_surface:
        links.new(original_surface, output.inputs["Surface"])
    nodes.remove(emission)
    return image


def convert_to_pbr(
    material: bpy.types.Material,
    baked: dict[str, bpy.types.Image],
) -> None:
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    material.node_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    base = nodes.new("ShaderNodeTexImage")
    base.name = "Authentic HD2 Base Color"
    base.image = baked["base-color"]
    material.node_tree.links.new(base.outputs["Color"], principled.inputs["Base Color"])

    metallic = nodes.new("ShaderNodeTexImage")
    metallic.name = "Authentic HD2 Metallic"
    metallic.image = baked["metallic"]
    material.node_tree.links.new(metallic.outputs["Color"], principled.inputs["Metallic"])

    roughness = nodes.new("ShaderNodeTexImage")
    roughness.name = "Authentic HD2 Roughness"
    roughness.image = baked["roughness"]
    material.node_tree.links.new(roughness.outputs["Color"], principled.inputs["Roughness"])

    normal_texture = nodes.new("ShaderNodeTexImage")
    normal_texture.name = "Authentic HD2 Normal"
    normal_texture.image = baked["normal"]
    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.name = "Authentic HD2 Normal Map"
    normal_map.inputs["Strength"].default_value = 1.0
    material.node_tree.links.new(normal_texture.outputs["Color"], normal_map.inputs["Color"])
    material.node_tree.links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])

    material["hd2BrowserMaterial"] = "filediver-accurate-shader-bake"


def delete_non_intact_meshes(keep: list[bpy.types.Object]) -> int:
    keep_set = set(keep)
    removed = 0
    for obj in list(bpy.data.objects):
        if obj.type == "MESH" and obj not in keep_set:
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    return removed


def retain_browser_uvs(objects: list[bpy.types.Object]) -> None:
    """Make the bake UV the primary glTF TEXCOORD_0 channel.

    Filediver models can carry five UV sets. Blender's glTF exporter otherwise
    writes the baked material against TEXCOORD_4, which is outside the texture
    channel range supported consistently by browser renderers.
    """
    seen_meshes: set[int] = set()
    for obj in objects:
        mesh_pointer = obj.data.as_pointer()
        if mesh_pointer in seen_meshes:
            continue
        seen_meshes.add(mesh_pointer)
        layers = obj.data.uv_layers
        bake_layer = layers.get("UVs for Baking") or layers.active or layers[0]
        bake_layer_name = bake_layer.name
        # Removing one UV layer invalidates Blender's Python wrappers for the
        # remaining collection. Re-resolve each layer by name instead of
        # retaining stale UVLoopLayer objects from a list copy.
        for layer_name in [layer.name for layer in layers if layer.name != bake_layer_name]:
            layer = layers.get(layer_name)
            if layer is not None:
                layers.remove(layer)
        bake_layer = layers.get(bake_layer_name)
        if bake_layer is None:
            raise RuntimeError(f"{obj.name} lost its bake UV while pruning texture channels")
        bake_layer.name = "UVMap"
        layers.active = bake_layer
        bake_layer.active_render = True


def export_glb(output: Path, objects: list[bpy.types.Object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    armatures = {
        armature
        for obj in objects
        if (armature := obj.find_armature()) is not None
    }
    select_objects(objects + sorted(armatures, key=lambda obj: obj.name))
    # Selection-only glTF export does not automatically retain a mesh's
    # armature dependency. Select the armature explicitly so mounted units keep
    # their yaw/pitch/barrel hierarchy instead of being flattened into a static
    # mesh during the shader bake.
    bpy.ops.export_scene.gltf(
        filepath=str(output),
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_apply=False,
        export_animations=False,
        export_materials="EXPORT",
        export_image_format="AUTO",
        export_extras=True,
    )


def rebase_exported_uvs(output: Path) -> int:
    """Rewrite the exported bake UV accessor as TEXCOORD_0.

    Blender can retain anonymous corner attributes after named UV maps are
    removed, so the glTF exporter may still number the sole material UV as
    TEXCOORD_2. Repointing the accessor in the JSON chunk is lossless and keeps
    the generated binary vertex data untouched.
    """
    raw = output.read_bytes()
    magic, version, _ = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF" or version != 2:
        raise RuntimeError(f"{output} is not a glTF 2.0 binary")
    json_length, json_type = struct.unpack_from("<I4s", raw, 12)
    if json_type != b"JSON":
        raise RuntimeError(f"{output} has no leading JSON chunk")
    document = json.loads(raw[20 : 20 + json_length].decode("utf-8").rstrip(" \0"))

    # Some HD2 units keep intact and destroyed visibility groups as separate
    # primitives in one skinned mesh. Blender therefore cannot exclude the
    # alternate state by object visibility alone. Preserve the game-authored
    # intact primitives and remove only primitives whose own material is
    # explicitly named as a damaged/destroyed state.
    alternate_materials = {
        index
        for index, material in enumerate(document.get("materials", []))
        if any(token in material.get("name", "").lower() for token in ("damaged", "destroyed"))
    }
    removed_primitives = 0
    if alternate_materials:
        for mesh in document.get("meshes", []):
            primitives = mesh.get("primitives", [])
            retained = [
                primitive
                for primitive in primitives
                if primitive.get("material") not in alternate_materials
            ]
            removed_primitives += len(primitives) - len(retained)
            if not retained:
                raise RuntimeError(f"{mesh.get('name', 'mesh')} contains only alternate-state primitives")
            mesh["primitives"] = retained

    baked_channels: set[int] = set()
    for material in document.get("materials", []):
        if material.get("extras", {}).get("hd2BrowserMaterial") != "filediver-accurate-shader-bake":
            continue
        pbr = material.get("pbrMetallicRoughness", {})
        for key in ("baseColorTexture", "metallicRoughnessTexture"):
            texture = pbr.get(key)
            if texture:
                baked_channels.add(int(texture.get("texCoord", 0)))
                texture["texCoord"] = 0
        normal_texture = material.get("normalTexture")
        if normal_texture:
            baked_channels.add(int(normal_texture.get("texCoord", 0)))
            normal_texture["texCoord"] = 0
    if len(baked_channels) != 1:
        raise RuntimeError(f"Expected one exported bake UV channel, found {sorted(baked_channels)}")
    source_channel = baked_channels.pop()

    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            attributes = primitive.get("attributes", {})
            source = f"TEXCOORD_{source_channel}"
            if source not in attributes:
                raise RuntimeError(f"{mesh.get('name', 'mesh')} is missing {source}")
            attributes["TEXCOORD_0"] = attributes[source]
            for name in list(attributes):
                if name.startswith("TEXCOORD_") and name != "TEXCOORD_0":
                    del attributes[name]

    json_bytes = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_bytes += b" " * ((-len(json_bytes)) % 4)
    remainder = raw[20 + json_length :]
    total_length = 12 + 8 + len(json_bytes) + len(remainder)
    rebuilt = struct.pack("<4sII", b"glTF", 2, total_length)
    rebuilt += struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes + remainder
    output.write_bytes(rebuilt)
    return removed_primitives


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    texture_dir = (args.texture_dir or output.with_suffix("").with_name(output.stem + "-textures")).resolve()
    texture_dir.mkdir(parents=True, exist_ok=True)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    # Blender's bake operator requires Cycles, but one sample is enough because
    # these are deterministic shader outputs rather than lit beauty renders.
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = False
    scene.render.bake.use_clear = True
    scene.render.bake.margin = 12

    objects = visible_render_objects()
    materials = accurate_materials(objects)
    if not objects or not materials:
        raise RuntimeError("No visible Filediver HD2 render materials were found")

    report = {
        "output": str(output),
        "textureSize": args.size,
        "visibleMeshCount": len(objects),
        "materials": {},
    }
    for material in materials:
        baked: dict[str, bpy.types.Image] = {}
        for output_name, socket_name, color_space in BAKE_OUTPUTS:
            print(f"Baking {material.name}: {output_name}")
            baked[output_name] = bake_material_output(
                material,
                objects,
                output_name,
                socket_name,
                color_space,
                texture_dir,
                args.size,
            )
        convert_to_pbr(material, baked)
        report["materials"][material.name] = {
            name: str(Path(image.filepath_raw).resolve()) for name, image in baked.items()
        }

    report["removedMeshCount"] = delete_non_intact_meshes(objects)
    retain_browser_uvs(objects)
    export_glb(output, objects)
    report["removedAlternatePrimitiveCount"] = rebase_exported_uvs(output)
    report_path = output.with_suffix(".bake.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Exported authentic intact render: {output}")


if __name__ == "__main__":
    main()
