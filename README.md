# HD2 Shot Placement Assessor

A framework-free Helldivers 2 shot-placement assistant with locally bundled anatomy images.

The interface includes three task-focused modes:

- **Recommend** ranks aim points or weapons using practical lethality.
- **Inspect** explains one exact enemy/body-part/weapon interaction.
- **Compare** evaluates two weapons across every body part.

Selections, favorites, and recent items stay on the device. The current result can also be copied, linked, or exported as a PNG card.

## Run locally

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

Then open `http://127.0.0.1:8765/index.html`.

## Refresh from the original assessor

The builder preserves the original data/calculation section and replaces its UI shell:

```powershell
python tools/build_assessor.py "C:\path\to\source-assessor.html" --output index.html
python tools/sync_images.py
python tools/verify_project.py
node tests/ranking.test.mjs
```

The image sync requires Pillow and downloads each unique wiki anatomy image, resizes it to at most 300 px, and stores it as WebP under `assets/anatomy/`.

## 3D damage models

The optional viewer now covers 39 enemies. In addition to the large units, it includes the standard, Heavy, and Rocket Devastators; both Scout Striders; Stalker; Shrieker; all three Overseers; Watcher; and Stingray. Each model lazy-loads only when opened. The extraction pipeline decodes Havok convex, box, capsule, sphere, compound, compressed-mesh (including 64-bit shared vertices), and articulated ragdoll collision shapes and joins them to HealthComponent actors, including HP, armor, durability, Main-health transfer, and explosion settings.

Thirty models have complete actor coverage. Stalker and Stingray join the existing seven partial models because one HealthComponent actor is absent from each decoded collision source; those gaps are not approximated. Articulated Stalker collision now applies the ragdoll body's decoded shape-to-world orientation as well as its position, with elongated leg and claw hulls checked against their next skeleton bone before export. Predator Stalker uses its own two game-derived material swaps instead of inheriting the base Stalker appearance. The Devastators combine body physics with exact ragdoll limbs, use intact shader bakes, and attach their game-mounted weapons at decoded hand sockets. The Heavy shield is a separate selectable 800-HP AV4 child. Both Scout Striders share the exact 500-HP walker body and attach their cannon, driver housing, and Reinforced rocket rails as independently destructible child units. All Overseer-family actors and all Watcher actors resolve exactly. The viewer remains informational until armor-break transitions, layered-pool runtime ordering, and runtime explosion aggregation are modeled. Direct `file://` use retains the 2D assessor but requires the local server above for 3D assets.

Regenerate the collision research asset from Filediver output with:

```powershell
python tools/extract_hd2_collision_hulls.py `
  --physics path\to\cha_strider.physics.main `
  --unit-glb path\to\cha_strider.unit.glb `
  --bones-json path\to\cha_strider.bones.json `
  --output assets\models\bile-titan-collision-research.glb `
  --manifest assets\models\bile-titan-collision-research.manifest.json
```

Then join Filediver's decoded entity-component data to the hull manifest:

```powershell
python tools\map_hd2_damage_zones.py `
  --entities-json C:\path\to\hd2-entity-components.json `
  --collision-manifest assets\models\bile-titan-collision-research.manifest.json `
  --output assets\models\bile-titan-damage-zones.manifest.json
```

Regenerate the additional large-enemy models from a Filediver extraction with:

```powershell
python tools\build_hd2_large_enemy_models.py `
  --extract-root C:\path\to\filediver-extract `
  --entities-json C:\path\to\hd2-entity-components.json
```

For articulated humanoids, creatures, and aircraft, the builder also requires the extracted
`.ragdoll_profile.main` beside the base physics resource. It follows the
profile's exact body-name and shape ITEM references to recover articulated
limbs that are absent from `.physics.main`.

Embedded game materials and textures are preserved by default so the browser
viewer can render the enemy colors. Factory Strider, Hulk (Scorcher), the
Automaton tank hull, tank turrets, Devastators, and Scout Strider assemblies use a Stingray-only material-LUT/decal shader. They now use Filediver's
accurate Blender shader reconstruction to combine the original material LUT,
ID masks, decals, weathering, and base data into ordinary browser-ready PBR
textures. Each render-only GLB contains only the default-visible intact meshes;
alternate damaged/destroyed meshes and collision proxies are excluded. The collision
research GLB remains separate and supplies the selectable hitboxes and mount
sockets. Pass `--strip-textures` only when intentionally producing smaller
neutral-gray research models.

After running `hd2_accurate_blender_importer.py` on the Factory Strider unit,
bake the reconstructed shader and export the intact browser render with:

```powershell
blender --background C:\path\to\factory-strider-accurate.blend `
  --python tools\bake_hd2_authentic_render.py -- `
  --output assets\models\factory-strider-authentic-render.glb `
  --size 1024
```

The bake tool makes its generated UV map `TEXCOORD_0`, which avoids the
five-channel Filediver source layout exceeding browser texture-channel support.
It also removes alternate damaged/destroyed objects and material primitives
from mixed intact-state units.

Regenerate the verified Devastator and Scout Strider mounted-unit manifests with:

```powershell
python tools\build_hd2_devastator_mounts.py --extract-root C:\path\to\extract --entities-json C:\path\to\hd2-entity-components.json
python tools\build_hd2_scout_strider_mounts.py
```

The Factory Strider body export does not contain its weapon meshes. Its two
chin gatlings and dorsal cannon are separate units referenced by
`MountComponentData`. Regenerate those viewer assets and their exact socket
manifest with:

```powershell
python tools\build_hd2_factory_strider_mounts.py `
  --factory-glb C:\path\to\cyborg_spawner.unit.glb `
  --chin-unit-glb C:\path\to\0x48c91e42b9f16512.unit.glb `
  --dorsal-cannon-unit-glb C:\path\to\cyborg_big_walker_turret_cannon.unit.glb `
  --dorsal-authentic-glb C:\path\to\factory-dorsal-authentic.glb
```

The Annihilator, Shredder, and Barrager tanks use the shared base unit plus
separate turret units. After extracting those resources and building their
collision/damage manifests, regenerate the socket assemblies with:

```powershell
python tools\build_hd2_tank_models.py `
  --extract-root C:\path\to\filediver-extract `
  --tank-glb C:\path\to\cyborg_tank.unit.glb `
  --authentic-root assets\models
```

`--authentic-root` must contain the intact Filediver shader bakes named
`automaton-heavy-cannon-turret-authentic-render.glb`,
`automaton-shredder-turret-authentic-render.glb`, and
`automaton-barrager-turret-authentic-render.glb`. The builder refuses to fall
back to the former gray material approximation. Non-damage physics volumes are
retained as evidence but hidden by default behind **Show geometry-only hulls**.

See the [model catalog](assets/models/enemy-3d-models.json), [Bile Titan gate evidence report](docs/3d-extraction-gate.md), and [machine-readable gate manifest](docs/3d-gate-manifest.json). Three.js is bundled locally under its MIT license in `assets/vendor/three-LICENSE.txt`. GLB files are tracked through Git LFS.
