# Bile Titan 3D extraction gate

**Gate status:** Passed for collision-hull-to-damage-zone mapping.

**Research date:** 2026-07-13

The Bile Titan's 54 decoded Havok convex hulls are actor shapes assigned directly to HealthComponent damage zones. The original archive-only search missed the generated entity-component data; decoding `generated_entities.dl_bin` supplied the missing semantic link.

## Source record

| Item | Value |
| --- | --- |
| Game | Helldivers 2 `release/01.006.301` |
| Build | 18653; commit `2777dec0d45d243a11770`; 2026-07-02 21:18:08 |
| Enemy entity | `content/fac_bugs/cha_strider/cha_strider` |
| Main HP | 6,500 |
| Physics resource | SHA-256 `2012F5CAA1A22623159BCE5B31C6DC2C7F9C8EC072FA047BC5F6A6BB459C28AC` |
| Generated entities data | SHA-256 `EFBF19C1B8F80C4C7E24FD0A77A2092E39DEA685FF42C8ED46E5763BD232421C` |
| Filediver source | commit `6f713e744a40d71f00fa55d33120e63aaf8115d7` |

The extraction and mapping are read-only. Nothing was written to the game installation and no gameplay patch or anti-cheat bypass was used.

## Mapping proof

The decoded `HealthComponentData` contains 26 populated `damageable_zones`. Each zone has an `actors` list whose values are either a friendly collider node name or a thin-hash identifier.

- All 54 actor entries resolve to a collider `nodeName` or `colliderHash` in the Havok manifest.
- Every one of the 54 hulls is assigned exactly once.
- There are zero unknown actor references, zero unmapped hulls, and zero duplicate assignments.
- Actor-to-zone links supply the zone's HP, armor, durability, Main-health transfer, fatal/downed behavior, explosion participation, explosive-damage percentage, and explosion verification mode.
- This is a direct game-data join, not a spatial or anatomy-based guess.

The machine-readable result is `assets/models/bile-titan-damage-zones.manifest.json`.

## Recovered named zones

| Zone | Hulls | HP | AV | Durability | Main transfer | Explosion damage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Head | 2 | 1,500 | 4 | 95% | 100% | 50% |
| Left torso | 1 | 1,500 | 4 | 100% | 100% | 50% |
| Right torso | 1 | 1,500 | 4 | 100% | 100% | 50% |
| Lower butt | 3 | 3,500 | 4 | 100% | 100% | 50% |
| Left arm | 3 | 1,000 | 4 | 0% | 100% | 50% |
| Right arm | 3 | 1,000 | 4 | 0% | 100% | 50% |
| Inner body | 4 | 4,000 | 2 | 80% | 60% | 100% |
| Inner torso | 1 | Main HP | 0 | 70% | 100% | 50% |

Destroying the head or inner body has `causes_death_on_death` enabled. `inner_torso` is a direct Main-HP zone and caps Main-health contribution at its zone health.

Eight previously unresolved limb hashes were cracked and verified by re-hashing their recovered names:

- `left_front_leg_armor`, `left_front_leg_flesh`
- `right_front_leg_armor`, `right_front_leg_flesh`
- `left_back_leg_armor`, `left_back_leg_flesh`
- `right_back_leg_armor`, `right_back_leg_flesh`

Each leg also has two individually mapped AV4/1,000-HP distal zones whose source labels remain raw hashes. Two AV0/750-HP torso zones also retain raw labels; their actor placement and values are consistent with the two bile sacs, but the manifest does not substitute inferred names for source identifiers.

## What remains unresolved

- Ten zone-name strings have not been recovered, although their unique zone IDs, hull assignments, and gameplay values are verified.
- The HealthComponent identifies armor and zone actors but not the behavioral state transition that swaps armor plates for exposed actors.
- The component provides explosion participation and ray-verification mode, but the engine's runtime explosion overlap, occlusion, and once-per-explosion aggregation algorithm still requires separate validation.
- The 3D view remains informational and does not yet replace the assessor's 2D targeting or explosion calculations.

## Reproduce the mapping

Decode the current `generated_entities.dl_bin` with Filediver's entity-component settings dumper, then run:

```powershell
python tools\map_hd2_damage_zones.py `
  --entities-json C:\path\to\hd2-entity-components.json `
  --collision-manifest assets\models\bile-titan-collision-research.manifest.json `
  --output assets\models\bile-titan-damage-zones.manifest.json
```

The mapper fails if any actor is unknown, any hull is missing, or any hull is assigned more than once.
