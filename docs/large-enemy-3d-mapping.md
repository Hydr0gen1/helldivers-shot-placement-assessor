# Large-enemy 3D damage mapping

The large-enemy rollout uses the same evidence chain as the Bile Titan: decoded
Havok shapes are attached to their skeleton bones, then HealthComponent actor
identifiers are joined to collider or bone hashes. No manually authored boxes
or inferred anatomy are substituted.

| Enemy | Physics hulls | Damage-mapped hulls | Health actors unresolved | Status |
| --- | ---: | ---: | ---: | --- |
| Hive Lord | 91 | 56 | 10 | Partial; 47 base hulls plus 44 articulated ragdoll bodies |
| Vox Engine | 39 | 30 | 1 | Partial layered map; six colliders are explicitly assigned to two pools |
| Dropship | 18 | 6 | 0 | Complete actor coverage; 12 non-damage structural colliders |
| Gunship | 5 | 5 | 0 | Complete actor coverage |
| Bile Titan | 54 | 54 | 0 | Complete |
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
| Bile Spewer | 5 | 4 | 16 | Partial; intact render and four exact body colliders |
| Fleshmob | 11 | 10 | 8 | Partial; one non-damage physics collider |
| Leviathan | 19 | 14 | 0 | Complete actor coverage; five non-damage physics colliders |
| Hulk (Scorcher) | 21 | 16 | 0 | Complete; 16 articulated ragdoll bodies joined by exact ITEM references |
| Brood Commander | 26 | 21 | 0 | Complete; 24 articulated ragdoll bodies plus two base colliders |
| Alpha Commander | 26 | 21 | 0 | Complete; 24 articulated ragdoll bodies plus two base colliders |
| Devastator | 23 | 22 | 0 | Complete; exact body/ragdoll join plus mounted rifle |
| Heavy Devastator | 25 + 2 shield | 23 + 1 shield | 0 | Complete; separate 800-HP AV4 shield at decoded hand socket |
| Rocket Devastator | 29 | 28 | 0 | Complete; pods, rack, and 64-bit shared mesh vertices decoded |
| Scout Strider | 30 + 2 child | 10 + default child zones | 0 | Complete; cannon and driver housing mounted at decoded sockets |
| Reinforced Scout Strider | 30 + 8 child instances | 10 + 6 rocket hulls | 0 | Complete; armored driver and two independently destructible rocket rails |
| Stalker | 48 | 46 | 1 | Partial; one HealthComponent actor has no decoded collider |
| Shrieker | 37 | 25 | 0 | Complete actor coverage; 12 non-damage flight colliders |
| Overseer | 50 | 48 | 0 | Complete actor coverage |
| Elevated Overseer | 51 | 49 | 0 | Complete actor coverage |
| Crescent Overseer | 50 | 48 | 0 | Complete actor coverage |
| Watcher | 8 | 6 | 0 | Complete actor coverage |
| Stingray | 10 | 9 | 1 | Partial ragdoll-only collision source |
| Factory Strider | 61 | 60 | 10 | Partial |
| War Strider | 15 | 15 | 12 | Partial |
| Harvester | 37 | 36 | 1 | Partial |

## Unresolved actor references

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
- Factory Strider: `0x78770d10`, `0x2372fd7e`, `0x0dd564c8`,
  `0xcbfdcaca`, `0x01362b8e`, `0x05c8b908`, `0x79883d49`,
  `0x046d20a7`, `0xe6cfad4e`, and `0xb93d83eb`.
- War Strider: `l_ankle`, `l_hip`, `l_leg_shield`, `r_leg_shield`,
  `r_ankle`, `r_hip`, `turret`, `l_hardpoint_yaw`, `r_hardpoint_yaw`,
  `yaw`, `l_rocketpod`, and `r_rocketpod`.
- Harvester: `c_body_front`.
- Bile Spewer: the base-unit physics resource does not contain the head or
  articulated leg actors referenced by its HealthComponent.
- Fleshmob: eight HealthComponent actor references are not present in the
  decoded base-unit physics resource.
- Stalker and Stingray: one actor in each HealthComponent has no matching base
  or ragdoll collider. Both remain explicitly partial.
- Berserker research recovers 21 exact hulls and 18 mapped body hulls, but its
  separately mounted chainsaw unit currently exports an armature without its
  render geometry. The incomplete assembly is withheld from the viewer.

These references are retained in the damage manifests with their zone identity.
The viewer labels the affected models as partial and does not synthesize missing
geometry. Mounted child units and entity-level collision construction are the
next research targets for closing these gaps.

## Layered damage actors

The Vox Engine is the first decoded unit in this rollout whose
`HealthComponentData` deliberately lists the same collider actor in more than
one damageable zone. The mapper requires `--allow-layered-colliders` for this
case and records a `zoneStack` on each affected hull. The viewer identifies the
overlap and displays every game-derived pool. It does not infer runtime damage
ordering or choose a single authoritative pool.

## Articulated ragdoll collision sources

Hive Lord, Hulk, Brood Commander, Alpha Commander, Devastators, Scout Strider,
Stalker, Shrieker, Watcher, and the Overseer family split their combat collision data
between the base `.physics.main` resource and `.ragdoll_profile.main`. The
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
