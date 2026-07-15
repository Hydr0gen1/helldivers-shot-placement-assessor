# Enemy 3D damage mapping

The large-enemy rollout uses the same evidence chain as the Bile Titan: decoded
Havok shapes are attached to their skeleton bones, then HealthComponent actor
identifiers are joined to collider or bone hashes. Exact joins remain the
default. Three otherwise unrepresented zones use explicitly labeled viewer
fallbacks; those proxies never replace or masquerade as exact mappings.

| Enemy | Physics hulls | Damage-mapped hulls | Health actors unresolved | Status |
| --- | ---: | ---: | ---: | --- |
| Hive Lord | 91 | 56 | 10 | Every damage zone has exact hull coverage; ten redundant actor references remain unresolved |
| Vox Engine | 39 | 30 | 1 | Every damage zone has exact layered hull coverage; six colliders are assigned to two pools |
| Dropship | 18 | 6 | 0 | Complete actor coverage; 12 non-damage structural colliders |
| Gunship | 5 | 5 | 0 | Complete actor coverage |
| Bile Titan | 54 | 54 | 0 | Complete |
| Warrior | 26 | 21 | 0 | Complete actor coverage; 24 articulated ragdoll bodies |
| Alpha Warrior | 26 | 21 | 0 | Complete actor coverage; variant HealthComponent retained |
| Bile Warrior | 26 | 21 | 0 | Complete actor coverage; acid variant HealthComponent retained |
| Rupture Warrior | 27 | 21 | 0 | Complete actor coverage; three base and 24 ragdoll hulls |
| Spore Burst Warrior | 26 | 21 | 0 | Complete actor coverage; gloom variant HealthComponent retained |
| Hive Guard | 24 | 20 | 1 | Every damage zone has exact layered hull coverage; one redundant actor remains unresolved |
| Hunter | 27 | 21 | 0 | Complete actor coverage; 26 articulated ragdoll bodies |
| Predator Hunter | 27 | 21 | 0 | Complete actor coverage; predator variant HealthComponent retained |
| Predator Stalker | 48 | 46 | 1 | Every damage zone has an exact hull; verified Stalker geometry with the predator map |
| Scavenger | 25 | 7 | 0 | Complete layered actor coverage; 18 non-damage ragdoll colliders |
| Pouncer | 31 | 7 | 0 | Complete layered actor coverage; 24 non-damage ragdoll colliders |
| Bile Spitter | 25 | 7 | 0 | Complete layered actor coverage; 18 non-damage ragdoll colliders |
| Nursing Spewer | 29 | 20 | 0 | Complete actor coverage; five base and 24 ragdoll hulls |
| Rupture Spewer | 30 | 20 | 0 | Complete actor coverage; six base and 24 ragdoll hulls |
| Charger | 50 | 45 | 0 | Complete actor coverage; five non-damage physics colliders |
| Charger Behemoth | 50 | 45 | 0 | Complete actor coverage; five non-damage physics colliders |
| Spore Charger | 61 | 57 | 0 | Complete actor coverage; four non-damage physics colliders |
| Rupture Charger | 51 | 45 | 0 | Complete actor coverage; six non-damage physics colliders |
| Annihilator Tank | 10 + 9 turret | 6 + 2 turret | 0 | Complete actor coverage; exact turret attached at decoded socket |
| Shredder Tank | 10 + 7 turret | 6 + 4 turret | 0 | Complete actor coverage; exact turret attached at decoded socket |
| Barrager Tank | 10 + 6 turret | 6 + 1 turret | 0 | Complete actor coverage; exact turret attached at decoded socket |
| Cannon Turret | 9 | 2 | 0 | Complete actor coverage; seven non-damage physics colliders |
| Spore Burst Bile Titan | 54 | 54 | 0 | Complete |
| Dragonroach | 66 | 66 | 0 | Complete |
| Impaler | 47 | 46 | 0 | Complete actor coverage; one non-damage physics collider |
| Veracitor | 58 | 58 | 0 | Complete |
| Gatekeeper | 57 | 57 | 0 | Complete |
| Bile Spewer | 29 | 20 | 0 | Complete; five base hulls plus 24 articulated ragdoll bodies |
| Fleshmob | 39 | 18 | 0 | Complete actor coverage; 11 base hulls plus 28 articulated ragdoll bodies |
| Leviathan | 19 | 14 | 0 | Complete actor coverage; five non-damage physics colliders |
| Hulk (Scorcher) | 21 | 16 | 0 | Complete; 16 articulated ragdoll bodies joined by exact ITEM references |
| Brood Commander | 26 | 21 | 0 | Complete; 24 articulated ragdoll bodies plus two base colliders |
| Alpha Commander | 26 | 21 | 0 | Complete; 24 articulated ragdoll bodies plus two base colliders |
| Devastator | 23 | 22 | 0 | Complete; exact body/ragdoll join plus mounted rifle |
| Heavy Devastator | 25 + 2 shield | 23 + 1 shield | 0 | Complete; separate 800-HP AV4 shield at decoded hand socket |
| Rocket Devastator | 29 | 28 | 0 | Complete; pods, rack, and 64-bit shared mesh vertices decoded |
| Berserker | 21 + 2 proxies | 18 + 2 proxies | 2 | Complete viewer zone coverage; shoulder boxes are comparative proxies from three verified Devastator variants |
| Trooper | 22 | 21 | 0 | Complete actor coverage; exact base/ragdoll join |
| Commissar | 22 | 21 | 0 | Complete actor coverage; commander HealthComponent retained |
| Conflagration Devastator | 23 + 2 shield | 22 + 1 shield | 0 | Complete; exact right-hand rifle and independently damageable left-hand shield |
| Agitator | 39 | 27 | 0 | Complete layered actor coverage; elite-rusher geometry and exact variant HealthComponent |
| Radical | 39 | 27 | 0 | Complete layered actor coverage; exact rusher HealthComponent |
| Scout Strider | 30 + 2 child | 10 + default child zones | 0 | Complete; cannon and driver housing mounted at decoded sockets |
| Reinforced Scout Strider | 30 + 8 child instances | 10 + 6 rocket hulls | 0 | Complete; armored driver and two independently destructible rocket rails |
| Stalker | 48 | 46 | 1 | Every damage zone has an exact hull; one redundant actor reference has no collider |
| Shrieker | 37 | 25 | 0 | Complete actor coverage; 12 non-damage flight colliders |
| Overseer | 50 | 48 | 0 | Complete actor coverage |
| Elevated Overseer | 51 | 49 | 0 | Complete actor coverage |
| Crescent Overseer | 50 | 48 | 0 | Complete actor coverage |
| Watcher | 8 | 6 | 0 | Complete actor coverage |
| Stingray | 10 | 9 + 1 proxy | 1 | Complete viewer zone coverage; the sole unassigned central hull is an explicitly inferred front-body proxy |
| Voteless (Medium) | 18 | 10 | 4 | Every damage zone has exact hull coverage; four redundant distal-limb references remain unresolved |
| Obtruder | 8 | 6 | 0 | Complete actor coverage; hashed unit resource decoded directly |
| Factory Strider | 61 | 60 | 10 | Every damage zone has exact hull coverage; ten raw actor aliases remain unresolved |
| War Strider | 36 | 24 | 0 | Complete actor coverage; 15 base hulls plus 21 articulated ragdoll bodies |
| Harvester | 37 | 36 + 1 proxy | 1 | Complete viewer zone coverage; the sole unassigned front-sized hull is an explicitly inferred body-front proxy |

## Residual actor references and zone coverage

- Hive Lord: `upper_jaw`, seven third-stage jaw bones, and the second upper and
  lower crown bones exist in the skeleton and HealthComponent actor list but
  have no collider in the decoded base physics or ragdoll profile. The six
  break-off shell shards and detached limb/mandible resources are retained as
  state-transition evidence; they are not substituted for intact-body actors.
- Vox Engine: `c_head` is referenced by the armored head zone but has no
  standalone collider in the decoded physics resource. Eight named child
  actors do resolve the head geometry. Six of those child colliders are also
  explicitly present in their own vent, fog-light, or sarcophagus damage pool;
  both assignments are retained as a layered actor map rather than flattened.
  The separate sarcophagus ragdoll has no HealthComponent or exact actor join
  back to `c_head`, so it is not substituted.
- Factory Strider: `0x78770d10`, `0x2372fd7e`, `0x0dd564c8`,
  `0xcbfdcaca`, `0x01362b8e`, `0x05c8b908`, `0x79883d49`,
  `0x046d20a7`, `0xe6cfad4e`, and `0xb93d83eb`. Adding the unit's exact
  19-body ragdoll profile produces 80 total physics hulls but none of these ten
  actor identities, so the body map remains partial.
- Harvester: `c_body_front` is a skeleton node without a hash-matched collider.
  The exact ten-body ragdoll profile was also decoded and does not contain it.
  The base resource has one unassigned front-sized hull (`43a3844e`) and this is
  exposed as an inferred viewer proxy, not an exact actor join.
- Stalker and Stingray: one actor in each HealthComponent has no matching base
  or ragdoll collider. Stalker's missing `spine_lower_2` and Stingray's missing
  `front_body` both exist as skeleton nodes only; Stingray has no separate base
  physics resource. Stalker's zone already has seven exact mapped hulls.
  Stingray's sole unassigned central `boss` hull (`9b115563`) is exposed as an
  inferred viewer proxy for its otherwise uncovered front-body zone.
- Hive Guard: `neck` exists in the ragdoll skeleton but has no body-info shape.
  Overlapping verified assignments remain layered instead of being flattened.
- Predator Stalker: its entity resolves to the verified Stalker unit geometry,
  but one actor in the predator-specific HealthComponent has no matching hull.
  Its distinct appearance is no longer inherited from the base Stalker render:
  the two exact `MaterialSwapComponentData` resources (`m_stalker1` and the
  wing slot `0x1b07df56`) are embedded in a dedicated browser GLB, with their
  source hashes recorded in `predator-stalker-render.manifest.json`.
- Voteless (Medium): four HealthComponent actors do not resolve to a collider
  in the decoded base physics or ragdoll resources. `l_hand`, `r_hand`,
  `l_foot`, and `r_foot` are skeleton nodes, but the exact V2 ragdoll body list
  stops at the elbows and knees; the V3 variant has the same limitation.
- Berserker research recovers 21 exact hulls and 18 mapped body hulls, but its
  two shoulder actors remain unresolved. The viewer adds rectangular proxies
  at the exact shoulderplate bones using the identical collider dimensions
  found on Devastator, Heavy Devastator, and Rocket Devastator; these remain
  comparative rather than exact. Its separately mounted chainsaw unit
  currently exports an armature without its render geometry, so that incomplete
  child assembly is withheld from the viewer. The Iron Fleet variant's exact
  physics and ragdoll resources were also tested and likewise contain no
  `l_shoulderplate` or `r_shoulderplate` body shapes.

These references are retained in the damage manifests with their zone identity.
Seven models already had exact hull coverage for every damage zone despite the
extra unresolved references. Berserker, Harvester, and Stingray now have
complete viewer interaction coverage through evidence-labeled fallbacks. The
viewer and verifier keep exact actor coverage, exact zone coverage, and proxy
zone coverage as separate claims.

## Resolved actor references

The 2026-07-14 archive re-audit recovered three exact ragdoll profiles that had
not been included in the earlier batch build:

- Bile Spewer: 24 articulated bodies resolve the head and all 15 leg actors,
  eliminating 16 unmatched HealthComponent references.
- Fleshmob: 28 articulated bodies resolve all eight elbow and hand actors.
- War Strider: 21 articulated bodies resolve both legs, both shields, the
  turret hierarchy, and both rocket pods.

These joins use serialized `bodyCinfoWithAttachment` shape and `ragdoll_*` bone
references from each enemy's own unit. No render-mesh or comparative proxies
were used.

## Layered damage actors

Vox Engine, Hive Guard, Scavenger, Pouncer, Bile Spitter, Agitator, and Radical
contain `HealthComponentData` that deliberately lists the same collider actor
in more than one damageable zone. The mapper requires
`--allow-layered-colliders` for these cases and records a `zoneStack` on each
affected hull. The viewer identifies the overlap and displays every game-derived
pool. It does not infer runtime damage ordering or choose a single authoritative
pool.

## Articulated ragdoll collision sources

Hive Lord, Hulk, Brood Commander, Alpha Commander, Warriors, Hive Guard,
Hunters, Stalkers, Scavengers, Spewers, Fleshmob, Berserker, Troopers,
Devastators, War Strider, Scout Strider, Shrieker, Watcher, Voteless, Obtruder,
and the Overseer family
split their combat collision data between the base `.physics.main` resource and
`.ragdoll_profile.main`. The
ragdoll decoder follows each serialized
`hknpPhysicsSystemData::bodyCinfoWithAttachment` shape ITEM reference and its
paired `ragdoll_*` name ITEM reference. Those names resolve directly to unit
skeleton nodes and HealthComponent actors; no render meshes or hand-authored
limb shapes are used.

Dropship and Gunship have no separate base `.physics.main` resource. Their
ragdoll profiles are the authoritative collision source, so the extractor also
supports verified ragdoll-only builds. The aircraft compressed-mesh hulls are
decoded through their exact `hknpCompressedMeshShapeData` ITEM references; the
render meshes are not substituted as hitboxes.
