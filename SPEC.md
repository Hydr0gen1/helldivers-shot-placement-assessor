# Helldivers 2 — Shot Placement Assessor: Spec

## What It Does

Given a **weapon** and an **enemy body part**, calculate:

1. How many shots to **destroy that part** (if it has its own HP)
2. How many shots to **kill the enemy** through that part (via main HP drain or fatal part destruction)
3. Whether the weapon can even **penetrate** that part's armor at all

---

## The Damage Model (from the wiki)

### Weapon properties per shot
| Property | Description | Example (AR-23 Liberator) |
|---|---|---|
| Standard Damage | Damage to non-durable parts | 90 |
| Durable Damage | Damage to fully-durable parts | 22 |
| Armor Penetration (AP) | AP level (0–10 scale) | AP2 (Light) |
| Explosive Damage | Does it deal explosive dmg? | No |

### Enemy part properties
| Property | Description | Example (Charger Butt) |
|---|---|---|
| Part HP | Own HP pool, or "Main" (shared) | 950 |
| Armor Value (AV) | How armored the part is (0–10) | AV0 (Unarmored I) |
| Durability % | 0 = fully squishy, 100 = fully durable | 80% |
| % To Main | Fraction of part damage sent to main HP | 150% |
| Fatal | Destroying this part kills the enemy | No |
| ExDR | Explosive damage resistance (0–100%) | 0% |

### AP vs AV penetration check

```
weapon AP > part AV  →  100% of damage applies  (red hitmarker)
weapon AP = part AV  →  50% of damage applies   (white hitmarker)
weapon AP < part AV  →  0% damage, ricochet     (no damage)
```

### Effective damage to part per shot

```
penetration_factor = 1.0 | 0.5 | 0.0  (from AP check above)

effective_damage = penetration_factor ×
    [ standard_damage × (1 - durability/100)
    + durable_damage  × (durability/100)     ]
```

For explosive weapons, apply ExDR reduction on top:
```
effective_damage × (1 - ExDR/100)
```

### Damage routed to main HP per shot

```
main_hp_damage_per_shot = effective_damage × (% To Main / 100)
```

If a part is listed as "Main" (no own HP), all damage goes straight there.

---

## Kill Condition Logic

There are three ways a target dies:

1. **Fatal part destroyed** — shots to destroy part HP:
   ```
   shots = ceil(part_HP / effective_damage)
   ```
   Enemy dies instantly when this reaches 0.

2. **Main HP depleted** — shots via main HP drain:
   ```
   shots = ceil(main_HP / main_hp_damage_per_shot)
   ```

3. **Bleedout triggered** — some parts (e.g., Charger Butt) trigger bleedout on destruction, killing the enemy over ~5 seconds. The tool should flag this as a "bleedout kill" and note the timer.

The tool computes **all applicable routes** and shows the minimum shots needed.

---

## UI / Interaction Flow

```
┌─────────────────────────────────────────┐
│  SELECT ENEMY       [ Charger        ▼] │
│  SELECT BODY PART   [ Butt           ▼] │
│  SELECT WEAPON      [ AR-23 Liberator▼] │
│  Firing angle       [ Direct         ▼] │  (Direct / Slight / Large / Extreme)
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  RESULT                                 │
│                                         │
│  Penetration:  ✅ Full (AP2 > AV0)      │
│                                         │
│  Damage/shot to part:   ~45.6           │
│  Damage/shot to main:   ~68.4           │
│                                         │
│  ── Kill routes ──                      │
│  Destroy Butt (950 HP):   21 shots  ⚠️ Bleedout
│  Deplete Main (2400 HP):  36 shots      │
│                                         │
│  Recommended: Aim at Butt → 21 shots   │
│  (then bleedout finishes it)            │
└─────────────────────────────────────────┘
```

---

## Data Requirements

### Enemy data (per body part)
Pull from the wiki's anatomy tables. Each entry needs:
- `part_name`
- `part_hp` (number or "Main")
- `armor_value` (AV0–AV10)
- `durability_pct` (0–100)
- `pct_to_main` (0–300+)
- `fatal` (bool)
- `bleedout` (bool + timer if known)
- `exdr` (0–100)

### Weapon data (per attack)
- `standard_damage`
- `durable_damage`
- `ap_value` (numeric, matchable to AV scale)
- `is_explosive` (bool)
- `fire_rate` (for optional DPS view)

---

## Stretch Features

- **DPS mode** — show damage per second for sustained fire, factoring fire rate
- **Multi-part** — what if you strip armor first, then shoot flesh? (two-phase calc)
- **Mag check** — "can you kill it in one magazine?"
- **Angle selector** — swap between Direct / Slight / Large / Extreme AP tiers per weapon
- **Fire damage** — some parts have a fire damage multiplier; flagged separately
- **Visual enemy diagram** — clickable body part selector instead of dropdown

---

## Scope / Out of Scope

**In scope:**
- Primary weapons, secondary weapons, support weapons
- All three factions' enemies with documented anatomy tables
- AP vs AV check, durability formula, % To Main routing

**Out of scope (v1):**
- Stratagems / airstrikes (complex splash/radius math)
- Status effects (fire DoT, bleed, gas) beyond flagging they exist
- Cooperative damage (two players shooting simultaneously)
- Distance falloff (wiki notes damage drops with distance — too variable without range input)
