import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const html = fs.readFileSync(new URL("../index.html", import.meta.url), "utf8");
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];
const core = script.split("// ============ DERIVED RANKING", 1)[0];
const derived = script.split("// ============ DERIVED RANKING", 2)[1].split("// ============ DOM APP", 1)[0];
const context = {console};
vm.createContext(context);
vm.runInContext(`${core}\n// ============ DERIVED RANKING${derived}\nconst ANGLE_SHORT=["Direct","Slight","Large","Extreme"],RANGE_SHORT=["Point blank","25 m","50 m","75 m","100 m+"];globalThis.api={ENEMIES,WEAPONS,FALLOFF,STAGGER,RELOAD_S,blastFactor,damagePerShot,assess,resolveWeapon,firingTime,evaluatePart,rankParts,rankWeapons,compareEvaluations,buildRecoveryAdvice,ACCESS_RULES,accessRule};`, context);

const {ENEMIES, WEAPONS, STAGGER, RELOAD_S, blastFactor, damagePerShot, assess, resolveWeapon, firingTime, evaluatePart, rankParts, rankWeapons, compareEvaluations, buildRecoveryAdvice, ACCESS_RULES, accessRule} = context.api;
const enemy = name => ENEMIES.find(item => item.name === name);
const weapon = name => WEAPONS.find(item => item.name === name);
const part = (target, name) => target.parts.find(item => item.name === name);
const conditions = {angle: 0, range: 0};

const portableHellbomb = weapon("B-100 Portable Hellbomb (inner blast)");
assert.ok(portableHellbomb, "portable Hellbomb uses its current non-approximate name");
assert.deepEqual(Array.from(portableHellbomb.comps[0].ap), [10,10,10,10], "portable Hellbomb uses Anti-Tank VI penetration");
assert.equal(portableHellbomb.comps[0].std, 10000, "portable Hellbomb inner blast uses 10,000 standard damage");
assert.equal(portableHellbomb.comps[0].dur, 10000, "portable Hellbomb inner blast uses 10,000 durable damage");
assert.equal(portableHellbomb.demo, 60, "portable Hellbomb records demolition force 60");
assert.equal(STAGGER[portableHellbomb.name], 50, "portable Hellbomb uses stagger force 50");
assert.equal(firingTime(resolveWeapon(portableHellbomb), 1), 10, "portable Hellbomb TTK includes its ten-second activation countdown");
assert.equal(firingTime(resolveWeapon(portableHellbomb), 2), 310, "additional portable Hellbomb uses include the documented base cooldown");

const precisionStrike=weapon("Orbital Precision Strike");
assert.ok(precisionStrike&&precisionStrike.cat==="Stratagem","Orbital Precision Strike is available as a stratagem");
assert.deepEqual(Array.from(precisionStrike.comps[0].ap),[8,7,6,6],"OPS shell uses current Anti-Tank IV/III/II penetration");
assert.deepEqual([precisionStrike.comps[0].std,precisionStrike.comps[1].std,precisionStrike.activationDelay,precisionStrike.cooldown],[4000,1500,4.45,90],"OPS uses current shell, explosion, call-in, and cooldown values");
for(const [name,impact,explosion,delay,cooldown] of [
  ["Orbital 120mm HE Barrage",3500,1200,7.45,180],
  ["Orbital 380mm HE Barrage",4000,1500,8.45,240],
  ["Orbital Walking Barrage",4000,1500,5.45,240]
]){
  const orbital=weapon(name),one=resolveWeapon(orbital,0),three=resolveWeapon(orbital,2);
  assert.ok(orbital&&orbital.cat==="Stratagem",`${name} is available as a stratagem`);
  assert.deepEqual([one.comps[0].std,one.comps[1].std,orbital.activationDelay,orbital.cooldown],[impact,explosion,delay,cooldown],`${name} one-shell mode uses current values`);
  assert.equal(three.comps[0].std,impact*3,`${name} three-hit scenario scales impact damage explicitly`);
  assert.equal(three.comps[1].std,explosion*3,`${name} three-hit scenario scales explosion damage explicitly`);
}

const currentWeaponStats = {
  "AR-23C Liberator Concussive": [60,400,75,35,[2,2,2,2]],
  "AR-23P Liberator Penetrator": [45,640,65,15,[3,3,3,0]],
  "AR-61 Tenderizer": [35,600,105,30,[2,2,2,0]],
  "AR-32 Pacifier": [40,700,55,10,[3,3,3,0]],
  "R-2 Amendment": [20,480,200,50,[2,2,2,0]],
  "R-2124 Constitution": [5,60,180,50,[3,3,3,0]],
  "SMG-37 Defender": [45,520,110,22,[2,2,2,0]],
  "SMG-72 Pummeler": [45,475,85,17,[2,2,2,0]],
  "SG-225 Breaker (all pellets)": [16,300,330,66,[2,2,2,0]],
  "SG-225IE Breaker Incendiary (all pellets)": [26,300,240,120,[2,2,2,0]],
  "MA5C Assault Rifle": [32,640,90,16,[3,3,3,0]],
  "M7S SMG": [48,872,90,18,[2,2,2,0]],
  "P-2 Peacemaker": [15,900,100,32,[2,2,2,0]],
  "P-92 Warrant (guided)": [13,450,80,20,[3,3,3,0]],
  "SG-22 Bushwhacker (all pellets)": [3,650,405,108,[2,2,2,0]],
  "LAS-58 Talon": [7,750,200,20,[3,3,3,0]],
  "APW-1 Anti-Materiel Rifle": [7,400,450,225,[4,4,4,0]],
  "MG-206 Heavy Machine Gun": [100,750,150,35,[4,4,4,0]],
  "GL-21 Grenade Launcher": [10,160,0,0,[4,4,4,0]],
  "LAS-99 Quasar Cannon": [1,10,2000,2000,[6,6,6,3]],
  "PLAS-45 Epoch (fully charged)": [3,30,800,400,[5,5,5,5]]
};
assert.deepEqual(
  [
    RELOAD_S["AR-23A Liberator Carbine"],
    RELOAD_S["MP-98 Knight"],
    RELOAD_S["SMG-37 Defender"],
    RELOAD_S["P-2 Peacemaker"],
    RELOAD_S["P-19 Redeemer"],
    RELOAD_S["P-113 Verdict"],
    RELOAD_S["P-4 Senator"],
    RELOAD_S["APW-1 Anti-Materiel Rifle"],
    RELOAD_S["AC-8 Autocannon"],
    RELOAD_S["DBS-2 Double Freedom"],
    RELOAD_S["M90A Shotgun (all pellets)"],
    RELOAD_S["R-2 Amendment"],
    RELOAD_S["LAS-58 Talon"],
    RELOAD_S["AR-2 Coyote"],
    RELOAD_S["AR-32 Pacifier"],
    RELOAD_S["SG-8P Punisher Plasma"],
    RELOAD_S["PLAS-15 Loyalist"],
    RELOAD_S["VG-70 Variable"],
    RELOAD_S["P-72 Crisper (sustained)"],
    RELOAD_S["PLAS-45 Epoch (fully charged)"],
    RELOAD_S["B/FLAM-80 Cremator (sustained)"]
  ],
  [2.5,3.0,3.0,1.5,1.8,2.2,2.8,3.0,3.0,2.0,1.5,3.6,4.6,3.1,3.0,2.7,1.8,3.6,2.3,5.1,3.9],
  "reload timings preserve directly mined values and newly decoded linked-animation defaults"
);
assert.equal(RELOAD_S["R-6 Deadeye"], 2.8, "Deadeye uses the decoded linked reload chain time to get the next shot back online");
assert.equal(RELOAD_S["FLAM-40 Flamethrower (sustained)"], 3.9, "Flamethrower reload lookup uses the current sustained weapon name");
assert.deepEqual(
  [
    RELOAD_S["SG-97 Sweeper (all flechettes)"],
    RELOAD_S["StA-52 Assault Rifle"],
    RELOAD_S["MA5C Assault Rifle"],
    RELOAD_S["AR/GL-21 One-Two"],
    RELOAD_S["SMG/FLAM-34 Stoker"],
    RELOAD_S["PLAS-39 Accelerator Rifle"],
    RELOAD_S["StA-11 SMG"],
    RELOAD_S["M7S SMG"],
    RELOAD_S["P-92 Warrant (guided)"],
    RELOAD_S["M6C/SOCOM Pistol"],
    RELOAD_S["P-35 Re-Educator (projectile; gas DoT excluded)"],
    RELOAD_S["P-69 Veto"],
    RELOAD_S["MLS-4X Commando (per rocket)"],
    RELOAD_S["ARC-12 Blitzer (per arc, fires ~3)"],
    RELOAD_S["ARC-3 Arc Thrower (per arc)"],
    RELOAD_S["GL-28 Belt-Fed Grenade Launcher"],
    RELOAD_S["B/MD C4 Pack (per charge)"]
  ],
  [1.5,4.2,3.3,3.3,3.0,3.3,3.5,3.0,2.2,1.5,2.8,3.1,0,0,0,0,0],
  "newly mapped crossover and special-case reload timings stay pinned to mined values and explicit no-reload behavior"
);
for (const [name,[mag,rpm,std,dur,ap]] of Object.entries(currentWeaponStats)) {
  const item = weapon(name);
  assert.ok(item, `audited weapon exists: ${name}`);
  assert.equal(item.mag, mag, `${name} capacity matches audited wiki data`);
  assert.equal(item.rpm, rpm, `${name} rate matches audited wiki data`);
  assert.equal(item.comps[0].std, std, `${name} standard damage matches audited wiki data`);
  assert.equal(item.comps[0].dur, dur, `${name} durable damage matches audited wiki data`);
  assert.deepEqual(Array.from(item.comps[0].ap), ap, `${name} angle penetration matches audited wiki data`);
}
const haltFlechette = weapon("SG-20 Halt").modes[0].comps[0];
assert.deepEqual([haltFlechette.std,haltFlechette.dur],[385,110],"Halt aggregates the current eleven flechettes");
assert.equal(STAGGER["GR-8 Recoilless Rifle"],50,"Recoilless Rifle stagger matches current attack data");

const charger = enemy("Charger");
const coyote = resolveWeapon(weapon("AR-2 Coyote"));
assert.equal(evaluatePart(charger, part(charger, "Main (body)"), coyote, conditions).outcome, "blocked", "blocked armor ranks as blocked");
const coyoteLegFlesh = evaluatePart(charger, part(charger, "Leg Flesh (exposed)"), coyote, conditions);
assert.equal(coyoteLegFlesh.outcome, "gated", "exposed flesh is not treated as accessible when the weapon cannot break its covering plate");
assert.equal(coyoteLegFlesh.access.canOpen, false, "armor-gated results retain their failed access route");

const equalAP = {name:"Equal AP test",comps:[{std:100,dur:100,ap:[4,4,4,4]}],mag:10,rpm:600};
const equalResult = damagePerShot(equalAP, part(charger, "Head"), 0, 0);
assert.equal(equalResult.comps[0].pf, .65, "equal AP receives partial penetration");

const recoilless = resolveWeapon(weapon("GR-8 Recoilless Rifle"));
assert.equal(evaluatePart(charger, part(charger, "Head"), recoilless, conditions).outcome, "immediate", "fatal part produces immediate kill route");
assert.equal(evaluatePart(charger, part(charger, "Claw"), recoilless, conditions).outcome, "disable", "nonfatal armor can rank as disable-only");
const openedLegFlesh = evaluatePart(charger, part(charger, "Leg Flesh (exposed)"), recoilless, conditions);
assert.equal(openedLegFlesh.shots, openedLegFlesh.setupShots + openedLegFlesh.targetShots, "armor-break setup is included in total route ammunition");
assert.match(openedLegFlesh.route.label, /^Break .*Armor, then /, "conditional routes explain the plate-first sequence");
assert.match(openedLegFlesh.access.stages[0].route.label, /^Destroy /, "setup cost uses plate destruction rather than a slower main-health route");
assert.equal(accessRule(charger, part(charger, "Butt")), null, "directly accessible targets are not incorrectly armor-gated");

for (const [enemyName, rules] of Object.entries(ACCESS_RULES)) {
  const targetEnemy = enemy(enemyName);
  assert.ok(targetEnemy, `access-rule enemy exists: ${enemyName}`);
  for (const [targetName, rule] of Object.entries(rules)) {
    assert.ok(part(targetEnemy, targetName), `gated target exists: ${enemyName} / ${targetName}`);
    rule.parts.forEach(required => assert.ok(part(targetEnemy, required), `required armor exists: ${enemyName} / ${required}`));
  }
}

const warrior = enemy("Warrior");
const liberator = resolveWeapon(weapon("AR-23 Liberator"));
assert.equal(evaluatePart(warrior, part(warrior, "Head"), liberator, conditions).outcome, "bleedout", "downs parts rank below immediate kills");

const beam = {name:"Beam test",comps:[{std:100,dur:100,ap:[9,9,9,9]}],mag:10,rpm:1,beam:true};
const beamEvaluation = evaluatePart(warrior, part(warrior, "Main (body)"), beam, conditions);
assert.equal(beamEvaluation.ttk, beamEvaluation.shots, "beam TTK is expressed in contact seconds");
assert.ok(!Number.isInteger(beamEvaluation.shots), "continuous contact time retains fractional seconds instead of rounding up");

const continuousStats = {
  "LAS-5 Scythe": [350,70,8,"beam"],
  "LAS-7 Dagger": [250,50,6.67,"beam"],
  "LAS-98 Laser Cannon": [350,200,12.5,"beam"],
  "FLAM-40 Flamethrower (sustained)": [150,150,15,"flame"],
  "P-72 Crisper (sustained)": [150,150,8,"flame"],
  "B/FLAM-80 Cremator (sustained)": [225,225,12,"flame"]
};
for (const [name,[std,dur,capacity,kind]] of Object.entries(continuousStats)) {
  const item=weapon(name);
  assert.ok(item, `continuous weapon exists: ${name}`);
  assert.deepEqual([item.comps[0].std,item.comps[0].dur,item.mag,item.continuous],[std,dur,capacity,kind],`${name} uses documented sustained DPS and contact capacity`);
}
const trident=weapon("LAS-13 Trident (all 6 beams on target)");
assert.deepEqual([trident.comps[0].std,trident.comps[0].dur,trident.mag,trident.rpm,trident.continuous],[360,36,10,300,undefined],"Trident is modeled as its current six-beam discrete burst");
const flameEvaluation=evaluatePart(warrior,part(warrior,"Main (body)"),resolveWeapon(weapon("FLAM-40 Flamethrower (sustained)")),conditions);
assert.ok(flameEvaluation.raw.continuous.burn?.dps>0,"documented ignition thresholds add a separate burn phase to sustained flame TTK");
assert.ok(flameEvaluation.shots < warrior.main/flameEvaluation.raw.d.total,"burn damage reduces main-health contact time after ignition");

const explosivePart = {...part(charger, "Head"), exdr:50};
const explosiveWeapon = {name:"Explosion test",comps:[{std:100,dur:100,ap:[9,9,9,9],explosive:true}],mag:1,rpm:60};
assert.equal(damagePerShot(explosiveWeapon, explosivePart, 0, 0).total, 50, "explosive resistance is retained");
assert.equal(damagePerShot(explosiveWeapon, explosivePart, 0, 0, 2).total, 25, "mid-blast placement applies radial falloff before ExDR");
const mixedBlastWeapon={name:"Mixed blast",comps:[{std:100,dur:100,ap:[9,9,9,9]},{std:100,dur:100,ap:[9,9,9,9],explosive:true}],mag:1,rpm:60};
assert.equal(damagePerShot(mixedBlastWeapon, explosivePart, 0, 0, 1).comps[0].dmg,0,"splash does not include direct projectile damage");
assert.equal(damagePerShot(mixedBlastWeapon, explosivePart, 0, 0, 1).comps[1].dmg,42,"inner splash combines estimated falloff and ExDR with game rounding");
const hellbombComponent={std:10000,dur:10000,ap:[10,10,10,10],explosive:true,label:"Hellbomb inner blast"};
assert.equal(blastFactor(hellbombComponent,1),1,"Hellbomb retains full damage through its verified inner radius");
assert.equal(blastFactor(hellbombComponent,2),0.5,"Hellbomb uses its verified outer-zone falloff profile");

const falloffWeapon = {name:"Falloff test",comps:[{std:100,dur:100,ap:[9,9,9,9],fo:"medium"}],mag:10,rpm:600};
assert.ok(damagePerShot(falloffWeapon, part(warrior, "Main (body)"), 0, 4).total < damagePerShot(falloffWeapon, part(warrior, "Main (body)"), 0, 0).total, "range falloff reduces damage");

const stalker = enemy("Stalker");
assert.match(assess(stalker, part(stalker, "Wings"), liberator, 0, 0).info, /can't be fully drained/, "damage-cap route retains explanatory failure");

const ranked = rankParts(charger, recoilless, conditions);
for (const item of ranked) {
  const direct = assess(charger, item.part, recoilless, 0, 0);
  assert.equal(item.partDamage, direct.d.total, "ranking delegates part damage to assess()");
  assert.equal(item.mainDamage, direct.toMainPerShot, "ranking delegates main damage to assess()");
}
assert.ok(ranked.every((item, index) => !index || compareEvaluations(ranked[index - 1], item, true) <= 0), "part ranking is deterministic");

const modeWeapon = WEAPONS.find(item => item.modes?.length > 1);
assert.ok(modeWeapon, "dataset contains a multi-mode weapon");
const modeRanking = rankWeapons(warrior, part(warrior, "Main (body)"), conditions).find(item => item.base === modeWeapon);
const candidates = modeWeapon.modes.map((_, index) => evaluatePart(warrior, part(warrior, "Main (body)"), resolveWeapon(modeWeapon, index), conditions));
assert.ok(candidates.every(candidate => compareEvaluations(modeRanking, candidate, false) <= 0), "best-weapon ranking retains the best firing mode");

const titan = enemy("Bile Titan");
const titanMain = part(titan, "Main (body)");
const blockedTitan = evaluatePart(titan, titanMain, liberator, conditions);
const recovery = buildRecoveryAdvice(titan, titanMain, weapon("AR-23 Liberator"), 0, conditions, blockedTitan);
assert.ok(recovery.length > 0 && recovery.every(item => !item.includes("undefined")), "recovery advice names valid alternatives");

console.log("Ranking tests passed");
