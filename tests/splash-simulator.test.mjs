import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(new URL("../tools/templates/splash-simulator.js", import.meta.url), "utf8");
const context = {console};
vm.createContext(context);
vm.runInContext(`${source}\nglobalThis.api={getExplosiveProfile,isPatternDelivery,normalizeImpactForDelivery,classifyTargeting3dWheelGesture,guidedTopAttackDirection,closestPointOnTriangle,pointBoundsDistance,humanizePhysicalPartName,damageZoneTechnicalLabel,physicalPartLabel,buildCollisionSceneIndex,nearestGroupPoint,blastFalloff,simulateImpact,simulateSequence,generateBarragePattern,summarizeSplashResult,explainSplashDestruction,fibonacciDirections};`, context);
const api = context.api;

assert.equal(api.classifyTargeting3dWheelGesture({ctrlKey:false,metaKey:false,deltaMode:0,deltaY:100},"trackpad"),"orbit");
assert.equal(api.classifyTargeting3dWheelGesture({ctrlKey:false,metaKey:false,deltaMode:1,deltaY:3},"trackpad"),"orbit");
assert.equal(api.classifyTargeting3dWheelGesture({ctrlKey:true,metaKey:false,deltaMode:0,deltaY:-4},"trackpad"),"zoom");
assert.equal(api.classifyTargeting3dWheelGesture({ctrlKey:false,metaKey:false,deltaMode:0,deltaY:12},"mouse"),"zoom");

assert.deepEqual(
  JSON.parse(JSON.stringify(api.physicalPartLabel({zoneIndex:12,zoneName:"0xb9d9a25d"},[{boneName:"boss"},{boneName:"r_back_tracks"}]))),
  {label:"Right Rear Tracks",technicalLabel:"Zone 13 · 0xb9d9a25d",partEvidence:"Verified attachment bone · r_back_tracks"}
);
assert.equal(api.physicalPartLabel({zoneIndex:0,zoneName:"torso"},[{boneName:"boss"}]).label,"Torso");
assert.equal(api.physicalPartLabel({zoneIndex:15,zoneName:"0xf32f319b"},[{boneName:"boss"}]).label,"Central Body / Chassis");
assert.equal(api.physicalPartLabel({zoneIndex:1,zoneName:"0x5c06dea6",physicalLabel:"Left Front Leg",physicalLabelEvidence:"verified-attachment-name",physicalLabelSources:["l_front_leg_1","l_front_leg_2"]},[{boneName:"l_front_leg_1"}]).label,"Left Front Leg");

const component = (std=100, inner=1, outer=5, ap=5) => ({std,dur:std,ap:[ap,ap,ap,ap],explosive:true,radius:{inner,outer}});
const profile = (overrides={}) => ({name:"Test explosive",direct:[],explosions:[component()],shrapnel:[],mainOnly:[],inner:1,outer:5,delivery:{kind:"single"},sticky:false,delay:0,maxShrapnel:0,...overrides});
const zone = (overrides={}) => ({zoneIndex:0,zoneName:"Target",health:500,armor:0,projectile_durable_resistance:0,affects_main_health:1,affected_by_explosions:true,explosive_damage_percentage:1,explosion_verification_mode:"ExplosionVerificationMode_All",main_health_affect_capped_by_zone_health:true,...overrides});
const plane = (x, y=0, z=0, size=1) => {
  const a={x,y:y-size,z:z-size},b={x,y:y+size,z:z-size},c={x,y:y+size,z:z+size},d={x,y:y-size,z:z+size};
  return {triangles:[[a,b,c],[a,c,d]],bounds:{min:{x,y:y-size,z:z-size},max:{x,y:y+size,z:z+size}}};
};
const hull = (poolKey,x,damage=zone(),extra={}) => ({...plane(x),poolKey,damage,collision:{recordIndex:extra.recordIndex||0},label:extra.label||poolKey,evidence:extra.evidence||"exact"});

assert.deepEqual(JSON.parse(JSON.stringify(api.closestPointOnTriangle({x:2,y:.25,z:.25},{x:0,y:0,z:0},{x:0,y:1,z:0},{x:0,y:0,z:1}))),{x:0,y:.25,z:.25});
assert.equal(api.pointBoundsDistance({x:3,y:0,z:0},{min:{x:0,y:-1,z:-1},max:{x:1,y:1,z:1}}),2);
assert.equal(api.blastFalloff({inner:1,outer:5},3),.5);

const weapon={name:"G-12 High Explosive",comps:[{label:"Explosion 1.5-7 m",std:800,dur:800,ap:[4,4,4,4],explosive:true}],mag:5};
const normalized=api.getExplosiveProfile(weapon);
assert.deepEqual([normalized.inner,normalized.outer,normalized.explosions.length],[1.5,7,1]);

const portableHellbomb=api.getExplosiveProfile({name:"B-100 Portable Hellbomb (inner blast)",activationDelay:10,comps:[{label:"Hellbomb inner blast (10,000 damage, AP10)",std:10000,dur:10000,ap:[10,10,10,10],explosive:true}]});
assert.deepEqual([portableHellbomb.inner,portableHellbomb.outer,portableHellbomb.explosions.length,portableHellbomb.delivery.kind,portableHellbomb.delivery.groundOnly,portableHellbomb.delay],[17,25,1,"ground-timed",true,10]);
assert.deepEqual(JSON.parse(JSON.stringify(api.normalizeImpactForDelivery({position:{x:4,y:9,z:-2},directPoolKey:"head",angleIndex:3},portableHellbomb,0))),{position:{x:4,y:0,z:-2},directPoolKey:null,angleIndex:0});

const solo=api.getExplosiveProfile({name:"MS-11 Solo Silo",comps:[{label:"Impact explosion (3–6 m, AP9)",std:1500,dur:1500,ap:[9,9,9,9],explosive:true},{label:"Main explosion (10–25 m, AP7)",std:2500,dur:2500,ap:[7,7,7,7],explosive:true}]});
assert.deepEqual([solo.inner,solo.outer,solo.explosions.length,solo.delivery.kind,solo.delivery.shockwave],[10,25,2,"guided-top-attack",35]);
const soloDirection=api.guidedTopAttackDirection(0,70);
assert.ok(Math.abs(Math.hypot(soloDirection.x,soloDirection.y,soloDirection.z)-1)<1e-12);
assert.ok(Math.abs(soloDirection.y+Math.sin(70*Math.PI/180))<1e-12);
assert.ok(soloDirection.z>0&&Math.abs(soloDirection.x)<1e-12);

const eagle500=api.getExplosiveProfile({name:"Eagle 500kg Bomb",comps:[{label:"500kg bomb impact",std:2000,dur:2000,ap:[7,7,7,7]},{label:"500kg impact explosion (1-3 m)",std:100,dur:100,ap:[3,3,3,3],explosive:true},{label:"500kg delayed explosion (10-25 m)",std:1500,dur:1500,ap:[6,6,6,6],explosive:true}]});
assert.deepEqual([eagle500.delivery.kind,eagle500.delivery.detonationDelay,eagle500.inner,eagle500.outer],["eagle-500kg",.8,10,25]);
const eagleAirstrike=api.getExplosiveProfile({name:"Eagle Airstrike",modes:[{name:"One bomb hits",comps:[{label:"100kg bomb impact",std:1500,dur:1500,ap:[7,7,7,7]},{label:"100kg bomb explosion (5-10 m)",std:800,dur:800,ap:[5,5,5,5],explosive:true}]}]});
const rocketPods=api.getExplosiveProfile({name:"Eagle 110mm Rocket Pods",modes:[{name:"One rocket hits",comps:[{label:"110mm rocket impact",std:600,dur:600,ap:[7,7,7,7]},{label:"110mm rocket explosion (1.6-5 m)",std:300,dur:300,ap:[4,4,4,4],explosive:true}]}]});
const strafingRun=api.getExplosiveProfile({name:"Eagle Strafing Run",modes:[{name:"One explosive round hits",comps:[{label:"23mm projectile",std:350,dur:200,ap:[5,5,4,1]},{label:"23mm HE explosion (2.5-5 m)",std:350,dur:350,ap:[3,3,3,3],explosive:true}]}]});
const gatlingBarrage=api.getExplosiveProfile({name:"Orbital Gatling Barrage",modes:[{name:"One explosive round hits",comps:[{label:"23mm projectile",std:350,dur:200,ap:[5,5,4,1]},{label:"23mm HE explosion (1.5-4.5 m)",std:350,dur:350,ap:[3,3,3,3],explosive:true}]}]});
assert.equal(api.isPatternDelivery(eagleAirstrike.delivery),true);
assert.equal(api.isPatternDelivery(rocketPods.delivery),true);
assert.equal(api.isPatternDelivery(strafingRun.delivery),true);
assert.equal(api.isPatternDelivery(gatlingBarrage.delivery),true);
assert.equal(api.getExplosiveProfile({name:"E/AT-12 Anti-Tank Emplacement",splash3d:false,comps:[{label:"75mm APHE explosion (3-6 m)",std:150,dur:150,ap:[3,3,3,3],explosive:true}]}),null);

// Multiple hulls for one HealthComponent pool must receive one closest-point blast.
const samePoolScene=api.buildCollisionSceneIndex([hull("body:0",2),hull("body:0",4,zone(),{recordIndex:1})],{mainHealth:1000});
assert.equal(samePoolScene.groups.length,1);
const samePoolResult=api.simulateImpact(samePoolScene,{position:{x:0,y:0,z:0}},profile(),"raw");
assert.equal(samePoolResult.zones.length,1);
assert.equal(samePoolResult.zones[0].explosionDamage,75);

// Repeated limbs remain independent because they use distinct pool keys.
const limbScene=api.buildCollisionSceneIndex([hull("left-leg",2,zone({zoneIndex:1,zoneName:"Left leg"})),hull("right-leg",2,zone({zoneIndex:2,zoneName:"Right leg"}))],{mainHealth:1000});
const limbResult=api.simulateImpact(limbScene,{position:{x:0,y:0,z:0}},profile(),"raw");
assert.equal(limbResult.zones.length,2);
assert.equal(limbResult.mainDamage,150);

// Occlusion evidence policies use the same overlap pass and remain ordered.
const blockedTarget=hull("target",2,zone({explosion_verification_mode:"ExplosionVerificationMode_All"}));
const occluder={...plane(1),poolKey:null,damage:null,collision:{recordIndex:9},label:"armor obstruction"};
const blockedScene=api.buildCollisionSceneIndex([blockedTarget,occluder],{mainHealth:1000});
const conservative=api.simulateImpact(blockedScene,{position:{x:0,y:0,z:0}},profile(),"conservative");
const primary=api.simulateImpact(blockedScene,{position:{x:0,y:0,z:0}},profile(),"primary");
const raw=api.simulateImpact(blockedScene,{position:{x:0,y:0,z:0}},profile(),"raw");
assert.ok(conservative.mainDamage<=primary.mainDamage&&primary.mainDamage<=raw.mainDamage);
assert.equal(raw.mainDamage,75);
assert.equal(primary.mainDamage,0);

// affected_by_explosions is a redirect-to-Main flag, not radial immunity.
// Small enemies commonly store false plus the no-reduction float sentinel.
const smallBugScene=api.buildCollisionSceneIndex([hull("hunter",2,zone({health:175,affected_by_explosions:false,explosive_damage_percentage:3.4028235e38}))],{mainHealth:175});
const opsNearMiss=profile({inner:4,outer:12,explosions:[component(1500,4,12,6)]});
const smallBugResult=api.simulateImpact(smallBugScene,{position:{x:0,y:0,z:0}},opsNearMiss,"primary");
assert.equal(smallBugResult.zones.length,1);
assert.equal(smallBugResult.killed,true);

const outerOnlyScene=api.buildCollisionSceneIndex([hull("target",2,zone({explosion_verification_mode:"ExplosionVerificationMode_OuterRadius"})),occluder],{mainHealth:1000});
const wideInner=profile({inner:3,explosions:[component(100,3,5)]});
assert.equal(api.simulateImpact(outerOnlyScene,{position:{x:0,y:0,z:0}},wideInner,"primary").mainDamage,100);
assert.equal(api.simulateImpact(outerOnlyScene,{position:{x:0,y:0,z:0}},wideInner,"conservative").mainDamage,0);

// Direct and blast components combine on a direct surface impact.
const directProfile=profile({direct:[{std:200,dur:200,ap:[5,5,5,5]}]});
const directScene=api.buildCollisionSceneIndex([hull("target",0)],{mainHealth:1000});
const directResult=api.simulateImpact(directScene,{position:{x:0,y:0,z:0},directPoolKey:"target"},directProfile,"raw");
assert.deepEqual([directResult.zones[0].directDamage,directResult.zones[0].explosionDamage],[200,100]);

const eagle500Result=api.simulateSequence(directScene,[{position:{x:0,y:0,z:0},directPoolKey:"target",time:0}],eagle500,"raw");
assert.deepEqual(Array.from(eagle500Result.events,event=>[event.impact.deliveryLabel,event.impact.time]),[["500kg bomb impact",0],["500kg delayed detonation",.8]]);
assert.equal(eagle500Result.events[0].zones[0].directDamage,2000);
assert.equal(eagle500Result.events[0].zones[0].explosionDamage,100);

// Thermite attachment and delayed detonation are separate chronological events.
const stickyProfile=profile({sticky:true,delay:6.5,mainOnly:[{std:50,dur:50,ap:[5,5,5,5],mainOnly:true}]});
const sticky=api.simulateSequence(directScene,[{position:{x:0,y:0,z:0},directPoolKey:"target",time:0}],stickyProfile,"raw");
assert.deepEqual(Array.from(sticky.events,event=>[event.impact.phase,event.impact.time]),[["attach",0],["detonation",6.5]]);

// Portable Hellbombs detonate after activation and can never retain a direct-hit target.
const groundTimed=api.simulateSequence(directScene,[{position:{x:0,y:0,z:0},directPoolKey:"target",time:0}],portableHellbomb,"raw");
assert.deepEqual(Array.from(groundTimed.events,event=>[event.impact.phase,event.impact.time,event.impact.directPoolKey,event.impact.deliveryLabel]),[["detonation",10,null,"Portable Hellbomb detonation"]]);
assert.equal(groundTimed.events[0].zones[0].directDamage,0);

// Fragment directions and outcomes are reproducible for a fixed seed.
assert.deepEqual(api.fibonacciDirections(35,17),api.fibonacciDirections(35,17));

const barrageProfile=profile({delivery:{kind:"barrage",spread:27,salvos:5,shellsPerSalvo:3,shellInterval:.75,salvoInterval:2}});
const barrageA=api.generateBarragePattern(barrageProfile,{x:0,y:0,z:0},0,42,{});
const barrageB=api.generateBarragePattern(barrageProfile,{x:0,y:0,z:0},0,42,{});
assert.deepEqual(barrageA,barrageB);
assert.equal(barrageA.length,15);
assert.ok(barrageA.every(impact=>Math.hypot(impact.position.x,impact.position.z)<=27));
assert.equal(api.generateBarragePattern(barrageProfile,{x:0,y:0,z:0},0,42,{moreGuns:true}).length,18);

const airstrikePattern=api.generateBarragePattern(eagleAirstrike,{x:0,y:0,z:0},0,1,{});
assert.equal(airstrikePattern.length,6);
assert.deepEqual(Array.from(airstrikePattern,impact=>impact.time),[0,.2,.4,.6000000000000001,.8,1]);
assert.ok(airstrikePattern.every(impact=>impact.deliveryLabel.startsWith("Eagle Airstrike bomb")));
const rocketPattern=api.generateBarragePattern(rocketPods,{x:0,y:0,z:0},0,1,{});
assert.equal(rocketPattern.length,6);
assert.deepEqual(Array.from(rocketPattern,impact=>impact.salvo),[1,1,2,2,3,3]);
assert.ok(rocketPattern.every(impact=>Math.hypot(impact.position.x,impact.position.z)<2));
const strafePattern=api.generateBarragePattern(strafingRun,{x:0,y:0,z:0},0,5,{});
assert.equal(strafePattern.length,100);
assert.equal(strafePattern.filter(impact=>!impact.suppressExplosion).length,25);
assert.equal(strafePattern.at(-1).time,1.4849999999999999);
assert.ok(strafePattern.every(impact=>impact.position.z>=0&&impact.position.z<=50));
const gatlingPattern=api.generateBarragePattern(gatlingBarrage,{x:0,y:0,z:0},0,7,{});
assert.equal(gatlingPattern.length,240);
assert.equal(gatlingPattern.filter(impact=>!impact.suppressExplosion).length,60);
assert.equal(gatlingPattern.at(-1).time,10.754999999999999);
assert.ok(gatlingPattern.every(impact=>Math.hypot(impact.position.x,impact.position.z)<=20));
assert.equal(api.generateBarragePattern(gatlingBarrage,{x:0,y:0,z:0},0,7,{moreGuns:true}).length,300);
const suppressedBlast=api.simulateImpact(directScene,{position:{x:0,y:0,z:0},directPoolKey:"target",suppressExplosion:true},gatlingBarrage,"raw");
assert.deepEqual([suppressedBlast.zones[0].directDamage,suppressedBlast.zones[0].explosionDamage],[350,0]);

const walkingProfile=profile({delivery:{kind:"walking-barrage",spread:25,salvos:5,shellsPerSalvo:3,shellInterval:1.5,salvoInterval:3,salvoStep:25}});
const walking=api.generateBarragePattern(walkingProfile,{x:0,y:0,z:0},0,9,{});
for(const impact of walking)assert.ok(Math.hypot(impact.position.x,impact.position.z-(impact.salvo-1)*25)<=25.000001);

const summary=api.summarizeSplashResult(api.simulateSequence(limbScene,[{position:{x:0,y:0,z:0},time:0}],profile(),"raw"));
assert.equal(summary.affectedZones.length,2);

const fatalScene=api.buildCollisionSceneIndex([hull("head",0,zone({zoneName:"Head",health:50,affects_main_health:0,causes_death_on_death:true}))],{mainHealth:1000});
const fatalResult=api.simulateSequence(fatalScene,[{position:{x:0,y:0,z:0},time:0}],profile(),"raw");
const fatalExplanation=api.explainSplashDestruction(fatalResult,fatalScene);
assert.equal(fatalExplanation.reasons[0].kind,"fatal-zone");
assert.equal(fatalExplanation.reasons[0].title,"Head was destroyed");

const mainKillScene=api.buildCollisionSceneIndex([hull("torso",0,zone({zoneName:"Torso",health:500,affects_main_health:1}))],{mainHealth:50});
const mainKillResult=api.simulateSequence(mainKillScene,[{position:{x:0,y:0,z:0},time:0}],profile(),"raw");
const mainExplanation=api.explainSplashDestruction(mainKillResult,mainKillScene);
assert.equal(mainExplanation.reasons[0].kind,"main-hp");
assert.equal(mainExplanation.reasons[0].contributors[0].label,"Torso");
assert.equal(api.explainSplashDestruction(api.simulateSequence(limbScene,[{position:{x:20,y:0,z:0},time:0}],profile(),"raw"),limbScene).destroyed,false);

console.log("Splash simulator tests passed");
