// ============ DERIVED RANKING (pure helpers) ============
const DATA_DATE = "{{DATA_DATE}}";
const OUTCOME_RANK = {immediate:0,bleedout:1,disable:2,blocked:3,gated:4};

// These targets do not exist as hittable zones on an intact enemy. The rule is
// deliberately separate from the preserved source dataset/calculation core: it
// describes target access, while assess() continues to describe damage once hit.
const ACCESS_RULES = {
  "Charger": {
    "Inner Flesh (exposed)": {mode:"any",parts:["Torso Armor"],note:"Break a torso armor plate to expose the inner flesh."},
    "Leg Flesh (exposed)": {mode:"any",parts:["Front Leg Armor","Rear Leg Armor"],note:"Break the armor on the same leg before shooting its exposed flesh."}
  },
  "Charger Behemoth": {
    "Inner Flesh (exposed)": {mode:"any",parts:["Torso Armor"],note:"Break a torso armor plate to expose the inner flesh."},
    "Leg Flesh (exposed)": {mode:"any",parts:["Front Leg Armor","Rear Leg Armor"],note:"Break the armor on the same leg before shooting its exposed flesh."}
  },
  "Spore Charger": {
    "Inner Flesh (exposed)": {mode:"any",parts:["Torso Armor"],note:"Break a torso armor plate to expose the inner flesh."},
    "Leg Flesh (exposed)": {mode:"any",parts:["Front Leg Armor","Rear Leg Armor"],note:"Break the armor on the same leg before shooting its exposed flesh."}
  },
  "Rupture Charger": {
    "Inner Flesh (exposed)": {mode:"any",parts:["Torso Armor"],note:"Break a torso armor plate to expose the inner flesh."},
    "Leg Flesh (exposed)": {mode:"any",parts:["Front Leg Armor","Rear Leg Armor"],note:"Break the armor on the same leg before shooting its exposed flesh."}
  },
  "Bile Titan": {
    "Inner Flesh (exposed)": {mode:"any",parts:["Torso Armor"],note:"Break a torso armor plate to expose the inner flesh."},
    "Underside (belly)": {mode:"all",parts:["Upper Bile Sac","Lower Bile Sac"],note:"Rupture both outer bile sacs to open the underlying belly health pool."},
    "Leg Flesh": {mode:"any",parts:["Leg Armor"],note:"Break the armor on that leg before shooting the flesh beneath it."}
  },
  "Impaler": {
    "Tentacle Flesh": {mode:"any",parts:["Tentacle Armor"],note:"Strip the tentacle armor before shooting the flesh beneath it."},
    "Inner Flesh (exposed)": {mode:"any",parts:["Torso Armor"],note:"Break torso armor to expose the inner flesh."},
    "Leg Flesh": {mode:"any",parts:["Leg Armor"],note:"Break the armor on that leg before shooting the flesh beneath it."}
  },
  "Hive Lord": {
    "Inner Flesh (exposed)": {mode:"any",parts:["Dorsal Plate Armor","Sterna Plate Armor","Lower Sterna Plate"],note:"Break a plate covering the section you intend to attack."}
  },
  "Overseer": {"Torso (exposed)": {mode:"any",parts:["Chest Armor"],note:"Strip the chest's ablative armor before shooting the exposed torso."}},
  "Elevated Overseer": {"Torso (exposed)": {mode:"any",parts:["Chest Armor"],note:"Strip the chest's ablative armor before shooting the exposed torso."}},
  "Crescent Overseer": {"Torso (exposed)": {mode:"any",parts:["Chest Armor"],note:"Strip the chest's ablative armor before shooting the exposed torso."}},
  "Harvester": {"Carapace Weakspot": {mode:"any",parts:["Carapace"],note:"Break the carapace first to uncover this internal weakspot."}},
  "Leviathan": {
    "Main (internals, exposed)": {mode:"any",parts:["Front Fin","Forward-Middle Fin","Rearward-Middle Fin","Rear Fin","Tail"],note:"Destroy a fin or the tail to expose the internals behind that section."}
  }
};

function accessRule(enemy,part){return ACCESS_RULES[enemy.name]?.[part.name]||null;}

function resolveWeapon(base, modeIndex=0){
  const index=base.modes?Math.max(0,Math.min(+modeIndex||0,base.modes.length-1)):0;
  const mode=base.modes?base.modes[index]:null;
  const sourceComps=mode?.comps||base.comps,referenceComps=base.comps||base.modes?.[0]?.comps||[];
  const comps=sourceComps?.map((component,componentIndex)=>{const ownRadius=componentBlastRadius(component),reference=referenceComps[componentIndex],radius=ownRadius||(reference?componentBlastRadius(reference):null);return radius&&!ownRadius?{...component,blastRadius:radius}:component;});
  return {...base,comps,rpm:mode?.rpm||base.rpm,mag:mode?.mag||base.mag,continuous:mode?.continuous||base.continuous,ignitionRate:mode?.ignitionRate||base.ignitionRate,base,modeIndex:index,modeName:mode?.name||null,displayName:base.name+(mode?" — "+mode.name:"")};
}

function isContinuous(weapon){return !!(weapon.continuous||weapon.beam);}
function firingTime(weapon,shots){
  if(!Number.isFinite(shots))return Infinity;
  if(weapon.activationDelay)return weapon.activationDelay+Math.max(0,shots-1)*(weapon.cooldown||0);
  const base=isContinuous(weapon)?shots:Math.max(0,(shots-1)/(weapon.rpm/60));
  return base+(weapon.detonationDelay||0);
}

function continuousBurnProfile(enemy,weapon){
  if(!weapon.ignitionRate)return null;
  const data=FIRE_DATA[enemy.name],threshold=data?.ig?.[1]??data?.ig?.[0];
  if(!data||threshold==null)return null;
  const mainAv=enemy.parts[0].av,penetration=penFactor(4,mainAv),dps=Math.floor(100*data.m*penetration);
  return dps>0?{dps,delay:threshold/weapon.ignitionRate,threshold,rate:weapon.ignitionRate,multiplier:data.m}:null;
}

function continuousTime(required,directDps,burn){
  if(required<=0)return 0;
  if(!burn||burn.dps<=0)return directDps>0?required/directDps:Infinity;
  const before=directDps*burn.delay;
  if(before>=required)return required/directDps;
  return burn.delay+(required-before)/(directDps+burn.dps);
}

function refineContinuousAssessment(enemy,part,weapon,raw){
  if(!isContinuous(weapon))return raw;
  const burn=continuousBurnProfile(enemy,weapon),routes=raw.routes.map(route=>{
    let seconds=route.shots;
    if(route.label.startsWith("Destroy ")&&part.hp!=="main")seconds=part.hp/raw.d.total;
    else if(route.label.startsWith("Deplete Main HP"))seconds=continuousTime(enemy.main,raw.toMainPerShot,part.hp==="main"?burn:null);
    return {...route,shots:Math.max(0,seconds)};
  });
  return {...raw,routes,continuous:{kind:weapon.continuous||"beam",streamDps:raw.d.total,burn}};
}

function compareEvaluations(a,b,includeIndex=true){
  const aa=[OUTCOME_RANK[a.outcome],a.ttk,a.shots??Infinity,a.magazines??Infinity,includeIndex?a.partIndex??a.weaponIndex??0:0];
  const bb=[OUTCOME_RANK[b.outcome],b.ttk,b.shots??Infinity,b.magazines??Infinity,includeIndex?b.partIndex??b.weaponIndex??0:0];
  for(let i=0;i<aa.length;i++)if(aa[i]!==bb[i])return aa[i]-bb[i];
  return 0;
}

function evaluateDirectPart(enemy,part,weapon,conditions={angle:0,range:0},partIndex=enemy.parts.indexOf(part)){
  const orbitalDistance=(weapon.base?.cat==="Stratagem"||weapon.cat==="Stratagem")?(conditions.blastDistance??0):null;
  const raw=refineContinuousAssessment(enemy,part,weapon,assess(enemy,part,weapon,+conditions.angle||0,+conditions.range||0,+conditions.blast||0,orbitalDistance,conditions.shrapnelHits??1));
  const lethal=raw.routes.filter(route=>route.kills).map(route=>({...route,outcome:part.fatal==="downs"&&route.label.startsWith("Destroy ")?"bleedout":"immediate"}));
  lethal.sort((a,b)=>OUTCOME_RANK[a.outcome]-OUTCOME_RANK[b.outcome]||firingTime(weapon,a.shots)-firingTime(weapon,b.shots)||a.shots-b.shots);
  const route=lethal[0]||raw.routes[0]||null;
  const outcome=lethal[0]?.outcome||(raw.d.total>0?"disable":"blocked");
  const shots=route?.shots??null;
  const ttk=outcome==="bleedout"?Infinity:firingTime(weapon,shots);
  const magazines=shots==null?null:Math.max(1,Math.ceil(shots/Math.max(1,weapon.mag)));
  const bestPen=Math.max(0,...raw.d.comps.map(component=>component.pf));
  return {enemy,part,partIndex,weapon,raw,outcome,route,shots,ttk,magazines,penetration:bestPen===1?"full":bestPen===.65?"partial":"blocked",partDamage:raw.d.total,mainDamage:raw.toMainPerShot};
}

function evaluateAccessStage(enemy,part,weapon,conditions){
  const result=evaluateDirectPart(enemy,part,weapon,conditions),route=result.raw.routes.find(candidate=>candidate.label.startsWith("Destroy "))||null,shots=route?.shots??null;
  return {...result,route,shots,ttk:firingTime(weapon,shots),magazines:shots==null?null:Math.max(1,Math.ceil(shots/Math.max(1,weapon.mag)))};
}

function evaluatePart(enemy,part,weapon,conditions={angle:0,range:0},partIndex=enemy.parts.indexOf(part)){
  const target=evaluateDirectPart(enemy,part,weapon,conditions,partIndex),rule=accessRule(enemy,part);
  if(!rule)return target;
  const candidates=rule.parts.map(name=>enemy.parts.find(candidate=>candidate.name===name)).filter(Boolean).map(candidate=>evaluateAccessStage(enemy,candidate,weapon,conditions));
  const breakable=candidates.filter(result=>result.raw.d.total>0&&Number.isFinite(result.shots));
  const stages=rule.mode==="all"?candidates:(breakable.sort((a,b)=>firingTime(weapon,a.shots)-firingTime(weapon,b.shots)||a.shots-b.shots),breakable.slice(0,1));
  const canOpen=rule.mode==="all"?candidates.length===rule.parts.length&&candidates.every(result=>result.raw.d.total>0&&Number.isFinite(result.shots)):stages.length>0;
  const access={rule,required:rule.parts,stages,canOpen,note:rule.note};
  if(!canOpen)return {...target,outcome:"gated",postBreakOutcome:target.outcome,route:null,shots:null,ttk:Infinity,magazines:null,access};
  const setupShots=stages.reduce((sum,result)=>sum+result.shots,0),targetShots=target.shots;
  if(targetShots==null)return {...target,access,setupShots,postBreakOutcome:target.outcome};
  const shots=setupShots+targetShots,ttk=target.outcome==="bleedout"?Infinity:firingTime(weapon,shots),magazines=Math.max(1,Math.ceil(shots/Math.max(1,weapon.mag)));
  const opening=stages.map(result=>result.part.name).join(rule.mode==="all"?" and ":" or ");
  return {...target,shots,ttk,magazines,access,setupShots,targetShots,route:{...target.route,label:`Break ${opening}, then ${target.route?.label?.toLowerCase()||`attack ${part.name}`}`}};
}

function rankParts(enemy,weapon,conditions){
  return enemy.parts.map((part,index)=>evaluatePart(enemy,part,weapon,conditions,index)).sort((a,b)=>compareEvaluations(a,b,true));
}

function rankWeapons(enemy,part,conditions){
  return WEAPONS.map((base,weaponIndex)=>{
    const candidates=(base.modes||[null]).map((_,modeIndex)=>({...evaluatePart(enemy,part,resolveWeapon(base,modeIndex),conditions,enemy.parts.indexOf(part)),base,weaponIndex,modeIndex}));
    candidates.sort((a,b)=>compareEvaluations(a,b,false)||a.modeIndex-b.modeIndex);
    return candidates[0];
  }).sort((a,b)=>compareEvaluations(a,b,false)||a.weaponIndex-b.weaponIndex);
}

function outcomeSummary(result){
  if(result.outcome==="gated")return "requires armor this weapon cannot break";
  if(result.outcome==="blocked")return "no damage";
  if(result.outcome==="disable")return `${result.shots??"—"} shots to disable`;
  if(result.outcome==="bleedout")return `${result.shots} shots plus bleedout`;
  return `${fmt(result.shots)} ${isContinuous(result.weapon)?"seconds":"shots"} to kill`;
}

function buildRecoveryAdvice(enemy,part,base,currentMode,conditions,currentEvaluation){
  if(currentEvaluation.outcome==="immediate")return [];
  const advice=[];
  if(currentEvaluation.outcome==="gated")advice.push(`${part.name} is not exposed yet. ${currentEvaluation.access.note}`);
  if(base.modes?.length>1){
    const better=base.modes.map((_,index)=>evaluatePart(enemy,part,resolveWeapon(base,index),conditions)).filter(x=>x.weapon.modeIndex!==currentMode&&compareEvaluations(x,currentEvaluation,false)<0).sort((a,b)=>compareEvaluations(a,b,false))[0];
    if(better)advice.push(`Switch to ${better.weapon.modeName}: ${outcomeSummary(better)}.`);
  }
  for(let angle=(+conditions.angle||0)-1;angle>=0;angle--){
    const better=evaluatePart(enemy,part,resolveWeapon(base,currentMode),{...conditions,angle});
    if(compareEvaluations(better,currentEvaluation,false)<0){advice.push(`Reduce the firing angle to ${ANGLE_SHORT[angle]}: ${outcomeSummary(better)}.`);break;}
  }
  for(let range=(+conditions.range||0)-1;range>=0;range--){
    const better=evaluatePart(enemy,part,resolveWeapon(base,currentMode),{...conditions,range});
    if(compareEvaluations(better,currentEvaluation,false)<0){advice.push(`Move to ${RANGE_SHORT[range]}: ${outcomeSummary(better)}.`);break;}
  }
  const alternate=rankParts(enemy,resolveWeapon(base,currentMode),conditions).find(x=>x.part!==part&&OUTCOME_RANK[x.outcome]<OUTCOME_RANK[currentEvaluation.outcome]);
  if(alternate)advice.push(`Aim for ${alternate.part.name}: ${outcomeSummary(alternate)}.`);
  const weapon=rankWeapons(enemy,part,conditions).find(x=>x.base!==base&&OUTCOME_RANK[x.outcome]<OUTCOME_RANK[currentEvaluation.outcome]);
  if(weapon)advice.push(`Try ${weapon.weapon.displayName}: ${outcomeSummary(weapon)}.`);
  return advice.slice(0,3);
}

function formatShareSummary(payload){
  if(!payload)return "Helldivers 2 Shot Placement Assessor";
  if(payload.kind==="compare")return `${payload.enemy} — ${payload.weaponA} vs ${payload.weaponB}\n${payload.summary}\n${payload.conditions}\nData: ${DATA_DATE}`;
  return `${payload.enemy} — ${payload.title}\n${payload.weapon}${payload.target?` → ${payload.target}`:""}\n${payload.metrics}\n${payload.conditions}\nData: ${DATA_DATE}`;
}

const EXPLOSION_EXPOSURE_PROFILES={"Bile Titan":{"Head":1,"Torso Armor":2,"Upper Bile Sac":1,"Lower Bile Sac":1,"Underside (belly)":1,"Leg Armor":4}};
function evaluateOrbitalExposure(enemy,weapon,baseConditions={}){
  const distance=Math.max(0,+baseConditions.blastDistance||0),profile=EXPLOSION_EXPOSURE_PROFILES[enemy.name],visibleParts=profile?Object.entries(profile).flatMap(([name,count])=>Array.from({length:count},()=>enemy.parts.find(part=>part.name===name))).filter(Boolean):enemy.parts.filter(part=>part.hp!=="main"&&!accessRule(enemy,part)),explosionWeapon={...weapon,comps:weapon.comps.filter(component=>component.explosive)},mainPart=enemy.parts.find(part=>part.hp==="main")||enemy.parts[0];let mainDamage=0,redirected=false,bestFatal=null,affected=[];
  for(const part of visibleParts){const damage=damagePerShot(explosionWeapon,part,+baseConditions.angle||0,0,0,distance),partDamage=damage.total;if(part.toMain!=null){const counted=part.cap!==0&&typeof part.hp==="number"?Math.min(partDamage,part.hp):partDamage;mainDamage+=counted*part.toMain/100;}if(part.fatal&&typeof part.hp==="number"&&partDamage>0){const shots=Math.ceil(part.hp/partDamage);if(!bestFatal||shots<bestFatal.shots)bestFatal={part,shots};}if(partDamage>0)affected.push({part,damage:partDamage});if(!redirected&&part.exdr===100){const redirectedDamage=damagePerShot(explosionWeapon,{...mainPart,exdr:0},+baseConditions.angle||0,0,0,distance).total;if(redirectedDamage>0){mainDamage+=redirectedDamage;redirected=true;}}}
  const mainShots=mainDamage>0?Math.ceil(enemy.main/mainDamage):Infinity,blastShots=Math.min(mainShots,bestFatal?.shots??Infinity);let direct=null;if(distance===0){const directWeapon={...weapon,comps:weapon.comps.filter(component=>!component.explosive)};direct=visibleParts.map((part,partIndex)=>evaluateDirectPart(enemy,part,directWeapon,{angle:+baseConditions.angle||0,range:0,blast:0},partIndex)).sort((a,b)=>compareEvaluations(a,b,true))[0]||null;}const shots=Math.min(blastShots,direct?.shots??Infinity),killed=Number.isFinite(shots),part=direct?.shots===shots?direct.part:bestFatal?.shots===shots?bestFatal.part:mainPart,route=killed?{label:shots===mainShots?`Enemy-wide explosion transfers ${fmt(mainDamage)} damage to Main HP`:`Explosion destroys ${part.name}`,shots,kills:true,tag:`${affected.length} exposed anatomy zones affected`}:null,ttk=firingTime(weapon,killed?shots:null);
  return {enemy,part,partIndex:enemy.parts.indexOf(part),weapon,raw:null,outcome:killed?"immediate":"blocked",route,shots:killed?shots:null,ttk,rankTtk:ttk,magazines:killed?Math.max(1,Math.ceil(shots/Math.max(1,weapon.mag))):null,penetration:killed?"full":"blocked",partDamage:0,mainDamage,blastExposure:{affected,redirected}};
}

// ============ DOM APP ============
const $=id=>document.getElementById(id);
const STORAGE_KEY="hd2-shot-placement:v4",LEGACY_KEYS=["hd2-shot-placement:v3","hd2-shot-placement:v2"];
const ANGLE_SHORT=["Direct","Slight angle","Large angle","Extreme angle"],RANGE_SHORT=["Point blank","~25 m","~50 m","~75 m","100 m+"],BLAST_SHORT=["Direct impact","Inner blast","Mid blast","Blast edge"];
const FACTION_COLORS={Terminids:"#ffc000",Automatons:"#ff5f5f",Illuminate:"#ce6ff9"};
const TERM_DEFS={AP:"Armor Penetration. AP equal to AV deals partial damage; higher AP deals full damage.",AV:"Armor Value. The target armor level checked against weapon AP.",Durability:"The percentage of damage that uses a weapon's durable-damage value.",ExDR:"Explosive damage resistance applied to explosive components.",Blast:"Placement within an explosion. Splash loses damage with distance and excludes the projectile's direct-hit component.","Main HP":"The enemy's shared health pool. Depleting it kills the enemy.","Damage cap":"Limits transferred damage to the remaining health of a destructible part.",Bleedout:"A delayed death caused by destroying certain fatal parts.",Stagger:"Whether weapon stun force meets the enemy's stagger threshold.",TTK:"Estimated time to kill: firing time plus reload time when more than one magazine is needed. Bleedout kills show '+ bleedout' rather than adding its duration; rankings prefer immediate kills when times are close."};
const comboControllers={};
const orbitalRecommendationCache=new Map();
const TARGETING_3D_MODELS={
  "Hive Lord":{slug:"hive-lord",cameraVector:[-1.45,.28,-.45]},
  "Vox Engine":{slug:"vox-engine",cameraVector:[-.72,.34,-1.3]},
  "Dropship":{slug:"dropship",cameraVector:[-.5,.28,-.9]},
  "Gunship":{slug:"gunship",cameraVector:[-.5,.28,-.9]},
  "Bile Titan":{slug:"bile-titan"},
  "Factory Strider":{slug:"factory-strider",renderGlb:"assets/models/factory-strider-authentic-render.glb",cameraVector:[-.45,.14,-.95],mountManifest:"assets/models/factory-strider-mounted-units.manifest.json"},
  "War Strider":{slug:"war-strider"},
  "Charger":{slug:"charger"},
  "Charger Behemoth":{slug:"charger-behemoth"},
  "Spore Charger":{slug:"spore-charger"},
  "Rupture Charger":{slug:"rupture-charger"},
  "Annihilator Tank":{slug:"annihilator-tank",assetSlug:"automaton-tank-base",renderGlb:"assets/models/automaton-tank-base-authentic-render.glb",cameraVector:[-.68,.26,-1.45],mountManifest:"assets/models/annihilator-tank-mounted-units.manifest.json"},
  "Shredder Tank":{slug:"shredder-tank",assetSlug:"automaton-tank-base",renderGlb:"assets/models/automaton-tank-base-authentic-render.glb",cameraVector:[-.68,.26,-1.45],mountManifest:"assets/models/shredder-tank-mounted-units.manifest.json"},
  "Barrager Tank":{slug:"barrager-tank",assetSlug:"automaton-tank-base",renderGlb:"assets/models/automaton-tank-base-authentic-render.glb",cameraVector:[-.68,.26,-1.45],mountManifest:"assets/models/barrager-tank-mounted-units.manifest.json"},
  "Cannon Turret":{slug:"cannon-turret",assetSlug:"automaton-heavy-cannon-turret",renderGlb:"assets/models/automaton-heavy-cannon-turret-authentic-render.glb",cameraVector:[-.62,.22,-1.45]},
  "Spore Burst Bile Titan":{slug:"spore-burst-bile-titan"},
  "Dragonroach":{slug:"dragonroach"},
  "Impaler":{slug:"impaler"},
  "Harvester":{slug:"harvester"},
  "Veracitor":{slug:"veracitor"},
  "Gatekeeper":{slug:"gatekeeper"},
  "Bile Spewer":{slug:"bile-spewer",cameraVector:[0,.05,-1.15]},
  "Fleshmob":{slug:"fleshmob"},
  "Leviathan":{slug:"leviathan",cameraVector:[-.4,.16,-.76]},
  "Hulk (Scorcher)":{slug:"hulk-scorcher",renderGlb:"assets/models/hulk-scorcher-authentic-render.glb"},
  "Devastator":{slug:"devastator",renderGlb:"assets/models/devastator-authentic-render.glb",mountManifest:"assets/models/devastator-mounted-units.manifest.json",cameraVector:[0,.04,-1.05]},
  "Heavy Devastator":{slug:"heavy-devastator",renderGlb:"assets/models/heavy-devastator-authentic-render.glb",mountManifest:"assets/models/heavy-devastator-mounted-units.manifest.json",cameraVector:[0,.04,-1.05]},
  "Rocket Devastator":{slug:"rocket-devastator",renderGlb:"assets/models/rocket-devastator-authentic-render.glb",mountManifest:"assets/models/rocket-devastator-mounted-units.manifest.json",cameraVector:[0,.04,-1.05]},
  "Scout Strider":{slug:"scout-strider",renderGlb:"assets/models/scout-strider-authentic-render.glb",mountManifest:"assets/models/scout-strider-mounted-units.manifest.json",cameraVector:[0,.08,-1.12]},
  "Reinforced Scout Strider":{slug:"reinforced-scout-strider",assetSlug:"scout-strider",renderGlb:"assets/models/scout-strider-authentic-render.glb",mountManifest:"assets/models/reinforced-scout-strider-mounted-units.manifest.json",cameraVector:[0,.08,-1.12]},
  "Stalker":{slug:"stalker",cameraVector:[0,.06,-1.1]},
  "Shrieker":{slug:"shrieker",cameraVector:[0,.08,-1.12]},
  "Overseer":{slug:"overseer",cameraVector:[0,.04,-1.06]},
  "Elevated Overseer":{slug:"elevated-overseer",cameraVector:[0,.04,-1.06]},
  "Crescent Overseer":{slug:"crescent-overseer",cameraVector:[0,.04,-1.06]},
  "Watcher":{slug:"watcher",cameraVector:[0,.06,-1.1]},
  "Stingray":{slug:"stingray",cameraVector:[0,.08,-1.12]},
  "Brood Commander":{slug:"brood-commander",cameraVector:[0,.05,-1.05]},
  "Alpha Commander":{slug:"alpha-commander",cameraVector:[0,.05,-1.05]}
};
let appState={view:"recommend",intent:"aim",favoriteEnemies:[],favoriteWeapons:[],recentEnemies:[],recentWeapons:[],rankCategory:"All",showAllWeapons:false};
let currentSharePayload=null,lastAimContext="",lastWeaponContext="",activeViewIndex=0,stickyObserver=null,toastTimer=null;
let targeting3d={bundle:null,enemy:null,initialized:false,loading:false,renderer:null,scene:null,camera:null,controls:null,model:null,hulls:[],selected:null,frame:0,resizeObserver:null,defaultCamera:null,pointerStart:null,raycastBound:false};

function esc(value){return String(value??"").replace(/[&<>'"]/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));}
function term(label){const definition=TERM_DEFS[label];return `<span class="term-wrap"><button class="term-button" type="button" data-term="${esc(label)}" aria-label="${esc(label+': '+definition)}">${esc(label)}</button><span class="term-tip" role="tooltip">${esc(definition)}</span></span>`;}
function outcomeLabel(outcome){return {immediate:"Immediate kill",bleedout:"Bleedout kill",disable:"Disables only",blocked:"No damage",gated:"Armor-gated"}[outcome];}
function outcomeText(result){return outcomeSummary(result);}
function formatTtk(result){return Number.isFinite(result.ttk)?`${fmt(result.ttk)}s${result.outcome==="bleedout"?" + bleedout":""}`:"—";}
function formatShots(result){if(result.shots==null)return "—";if(result.weapon.base?.cat==="Stratagem")return `${fmt(result.shots)} use${result.shots===1?'':'s'}`;if(result.weapon.base?.cat==="Throwable")return `${fmt(result.shots)} grenade${result.shots===1?'':'s'}`;return isContinuous(result.weapon)?`${fmt(result.shots)}s`:`${result.shots}`;}
function penetrationLabel(result){const base=result.penetration==="full"?"Full":result.penetration==="partial"?"Partial (65%)":"Blocked";return result.outcome==="gated"?`${base} once exposed`:base;}
function selectedText(select){return select.selectedOptions[0]?.textContent||"";}
function selectByText(select,text){if(!text)return false;const aliases={"B-100 Portable Hellbomb (≈)":"B-100 Portable Hellbomb (inner blast)","B-100 Portable Hellbomb":"B-100 Portable Hellbomb (inner blast)","P-35 Re-Educator (gas)":"P-35 Re-Educator (projectile; gas DoT excluded)","LAS-13 Trident (all 4 beams on target)":"LAS-13 Trident (all 6 beams on target)","FLAM-40 Flamethrower (≈ per second)":"FLAM-40 Flamethrower (sustained)","B/FLAM-80 Cremator (≈ per second)":"B/FLAM-80 Cremator (sustained)","P-72 Crisper (≈ per second)":"P-72 Crisper (sustained)"},wanted=aliases[text]||text,option=[...select.options].find(x=>x.textContent===wanted);if(!option)return false;select.value=option.value;return true;}
function fill(select,items,label){select.replaceChildren(...items.map((item,index)=>new Option(label(item),index)));}

function weaponClass(w){
  const n=w.name,X={"JAR-5 Dominator":"Special","SG-8P Punisher Plasma":"Energy-Based","CB-9 Exploding Crossbow":"Explosive","R-36 Eruptor (excl. shrapnel)":"Explosive","PLAS-15 Loyalist":"Special","P-72 Crisper (sustained)":"Special","SG-22 Bushwhacker (all pellets)":"Special","LAS-58 Talon":"Special","LAS-7 Dagger":"Special","GP-31 Grenade Pistol":"Special","P-35 Re-Educator (projectile; gas DoT excluded)":"Special","CQC-20 Breaching Hammer":"Melee"};
  if(w.cat==="Vehicle")return "Mounted Weapons";
  if(w.cat==="Throwable")return "Grenades";
  if(w.cat==="Stratagem")return "Orbital";if(X[n])return X[n];if(w.cat==="Support"){if(/^(MG|M-105|MGX)/.test(n))return "Machine Guns";if(/^(EAT|GR-8|LAS-99|MLS|RS-422|S-11|PLAS-45|MS-11|B-100)/.test(n))return "Anti-Tank";if(/^(AC-8|GL-2|B\/MD)/.test(n))return "Explosive";return "Energy / Flame / Arc";}if(w.cat==="Secondary")return "Pistols";if(/^(AR|StA-52|MA5C|BR-14)/.test(n))return "Assault Rifles";if(/^R-/.test(n))return "Marksman Rifles";if(/^(SMG|MP-98|StA-11|M7S)/.test(n))return "Submachine Guns";if(/^(SG|DBS|M90A)/.test(n))return "Shotguns";if(/^(LAS|PLAS|ARC)/.test(n))return "Energy-Based";return "Special";
}
function fillEnemies(){
  const groups={};
  ENEMIES.forEach((enemy,index)=>{const key=enemy.faction+(enemy.sub?` — ${enemy.sub}`:"");(groups[key]=groups[key]||{faction:enemy.faction,items:[]}).items.push([enemy,index]);});
  const keys=Object.keys(groups).sort((a,b)=>{const fa=groups[a].faction,fb=groups[b].faction;if(fa!==fb)return ENEMIES.findIndex(e=>e.faction===fa)-ENEMIES.findIndex(e=>e.faction===fb);return a.localeCompare(b);});
  const nodes=keys.map(key=>{const group=document.createElement("optgroup");group.label=key;groups[key].items.forEach(([enemy,index])=>{const option=new Option(enemy.name,index);option.dataset.filter=groups[key].faction;option.style.color=FACTION_COLORS[groups[key].faction]||"#fff";group.append(option);});return group;});
  $('enemy').replaceChildren(...nodes);
}
function fillWeapons(select){const nodes=[];for(const category of ["Primary","Secondary","Support","Throwable","Vehicle","Stratagem"]){const classes={};WEAPONS.forEach((weapon,index)=>{if(weapon.cat===category)(classes[weaponClass(weapon)]=classes[weaponClass(weapon)]||[]).push([weapon,index]);});for(const cls of Object.keys(classes).sort()){const group=document.createElement("optgroup");group.label=category+" · "+cls;classes[cls].sort((a,b)=>a[0].name.localeCompare(b[0].name)).forEach(([weapon,index])=>{const option=new Option(weapon.name,index);option.dataset.filter=category;group.append(option);});nodes.push(group);}}select.replaceChildren(...nodes);}
function fillParts(preferred){const enemy=ENEMIES[$('enemy').value],preferredPart=enemy.parts.find(part=>preferred===part.name||preferred?.startsWith(part.name+" (")||preferred?.startsWith(part.name+" ·"));fill($('part'),enemy.parts,part=>part.name+(accessRule(enemy,part)?" · BREAK ARMOR FIRST":"")+(part.hp==="main"?` (${enemy.main} HP — main pool, AV${part.av})`:` (${part.hp} HP, AV${part.av})`));if(preferredPart)$('part').value=enemy.parts.indexOf(preferredPart);else selectByText($('part'),preferred);}
function fillMode(modeSelect,row,weaponSelect,preferred){const base=WEAPONS[weaponSelect.value];if(base.modes){fill(modeSelect,base.modes,mode=>mode.name);selectByText(modeSelect,preferred);row.dataset.available="true";}else{modeSelect.replaceChildren();row.dataset.available="false";} }

function readStorage(){try{const current=JSON.parse(localStorage.getItem(STORAGE_KEY)||"null");if(current)return current;for(const key of LEGACY_KEYS){const legacy=JSON.parse(localStorage.getItem(key)||"null");if(legacy)return legacy;}return {};}catch{return {};}}
function readInitialState(){const stored=readStorage(),next={...appState,...stored};try{const q=new URL(location.href).searchParams;const validView=["recommend","inspect","compare"],validIntent=["aim","weapon"];if(validView.includes(q.get("view")))next.view=q.get("view");if(validIntent.includes(q.get("intent")))next.intent=q.get("intent");for(const key of ["enemy","part","weapon","mode","weaponB","modeB","angle","range","blast","blastDistance","shrapnelHits"])if(q.has(key))next[key]=q.get(key);}catch{}return next;}
function collectState(){return {...appState,enemy:selectedText($('enemy')),part:selectedText($('part')),weapon:selectedText($('weapon')),mode:selectedText($('mode')),weaponB:selectedText($('weaponB')),modeB:selectedText($('modeB')),angle:$('angle').value,range:$('range').value,blast:$('blast').value,blastDistance:$('blastDistance').value,shrapnelHits:$('shrapnelHits').value};}
function persist(){appState=collectState();try{localStorage.setItem(STORAGE_KEY,JSON.stringify(appState));}catch{}try{const url=new URL(location.href),state=collectState();for(const key of ["view","intent","enemy","part","weapon","mode","weaponB","modeB","angle","range","blast","blastDistance","shrapnelHits"]){if(state[key])url.searchParams.set(key,state[key]);else url.searchParams.delete(key);}history.replaceState(null,"",url);}catch{}}
function remember(kind,value){const key=kind==="enemy"?"recentEnemies":"recentWeapons",limit=kind==="enemy"?5:8;appState[key]=[value,...(appState[key]||[]).filter(x=>x!==value)].slice(0,limit);}

function favoriteList(kind){return kind==="enemy"?appState.favoriteEnemies:appState.favoriteWeapons;}
function enhanceSelect(select){
  const field=select.closest('.field'),label=field.querySelector('label'),combo=document.createElement('div'),input=document.createElement('input'),panel=document.createElement('div'),filters=document.createElement('div'),list=document.createElement('div'),status=document.createElement('div');
  const kind=select.id==="enemy"?"enemy":"weapon";combo.className='combo';input.className='combo-input';input.id=select.id+'Search';input.type='text';input.autocomplete='off';input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-expanded','false');panel.className='combo-panel';panel.hidden=true;filters.className='combo-filters';list.className='combo-list';list.id=select.id+'List';list.setAttribute('role','listbox');status.className='sr-only';status.setAttribute('aria-live','polite');input.setAttribute('aria-controls',list.id);label.htmlFor=input.id;panel.append(filters,list);combo.append(input,panel,status);select.after(combo);select.hidden=true;
  let items=[],active=-1,activeFilter="All",rendered=[],typedQuery="";
  const rebuild=()=>{items=[...select.options].map(option=>({value:option.value,label:option.textContent,group:option.parentElement.tagName==="OPTGROUP"?option.parentElement.label:"",filter:option.dataset.filter||"All"}));input.value=selectedText(select);drawFilters();};
  const drawFilters=()=>{const values=["All",...new Set(items.map(item=>item.filter))];filters.replaceChildren(...values.map(value=>{const button=document.createElement('button');button.type='button';button.className='filter-chip';button.textContent=value;button.setAttribute('aria-pressed',value===activeFilter?'true':'false');button.addEventListener('mousedown',event=>event.preventDefault());button.addEventListener('click',()=>{activeFilter=value;drawFilters();draw(typedQuery);});return button;}));};
  const close=()=>{panel.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');active=-1;};
  const choose=item=>{select.value=item.value;input.value=item.label;close();select.dispatchEvent(new Event('change',{bubbles:true}));};
  const draw=query=>{const q=query.trim().toLocaleLowerCase(),favorites=new Set(favoriteList(kind)),recents=new Set(kind==="enemy"?appState.recentEnemies:appState.recentWeapons);rendered=items.filter(item=>(activeFilter==="All"||item.filter===activeFilter)&&item.label.toLocaleLowerCase().includes(q)).sort((a,b)=>{const aw=favorites.has(a.label)?0:recents.has(a.label)?1:2,bw=favorites.has(b.label)?0:recents.has(b.label)?1:2;return aw-bw||a.group.localeCompare(b.group)||a.label.localeCompare(b.label);});list.replaceChildren();let previous="";rendered.forEach((item,index)=>{const group=favorites.has(item.label)?"★ Favorites":recents.has(item.label)?"Recent":item.group;if(group!==previous){const heading=document.createElement('div');heading.className='combo-group';heading.textContent=group;list.append(heading);previous=group;}const option=document.createElement('div');option.className='combo-option';option.id=select.id+'Option'+index;option.setAttribute('role','option');option.setAttribute('aria-selected',item.value===select.value?'true':'false');option.textContent=item.label;option.addEventListener('mousedown',event=>event.preventDefault());option.addEventListener('click',()=>choose(item));list.append(option);});if(!rendered.length){const empty=document.createElement('div');empty.className='combo-empty';empty.textContent='No matches in this filter';list.append(empty);}status.textContent=`${rendered.length} result${rendered.length===1?'':'s'}`;panel.hidden=false;input.setAttribute('aria-expanded','true');active=-1;};
  const setActive=next=>{const options=[...list.querySelectorAll('[role="option"]')];if(!options.length)return;active=(next+options.length)%options.length;options.forEach((option,index)=>option.classList.toggle('active',index===active));input.setAttribute('aria-activedescendant',options[active].id);options[active].scrollIntoView({block:'nearest'});};
  input.addEventListener('focus',()=>{typedQuery='';draw('');});input.addEventListener('input',()=>{typedQuery=input.value;draw(typedQuery);});input.addEventListener('blur',()=>setTimeout(()=>{close();typedQuery='';input.value=selectedText(select);},100));input.addEventListener('keydown',event=>{if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();if(panel.hidden)draw(typedQuery);setActive(active+(event.key==='ArrowDown'?1:-1));}else if(event.key==='Enter'&&active>=0){event.preventDefault();choose(rendered[active]);}else if(event.key==='Escape'){event.preventDefault();close();typedQuery='';input.value=selectedText(select);}});
  comboControllers[select.id]={sync(){rebuild();input.value=selectedText(select);},open(){draw('')}};rebuild();
}

function isOrbital(weapon){return weapon?.base?.cat==="Stratagem"||weapon?.cat==="Stratagem";}
function orbitalRadius(weapon){const radii=(weapon?.comps||[]).map(componentBlastRadius).filter(radius=>Number.isFinite(radius?.inner)&&Number.isFinite(radius?.outer)&&radius.outer>0);return radii.length?{inner:Math.max(...radii.map(radius=>radius.inner)),outer:Math.max(...radii.map(radius=>radius.outer))}:{inner:0,outer:0};}
function conditions(){const orbital=isOrbital(resolvedA())||appState.view==='compare'&&isOrbital(resolvedB());return {angle:+$('angle').value,range:orbital?0:+$('range').value,blast:orbital?0:+$('blast').value,blastDistance:orbital?+$('blastDistance').value:null,shrapnelHits:+$('shrapnelHits').value};}
function hasExplosion(weapon){return !!weapon?.comps?.some(component=>component.explosive);}
function selectedEnemy(){return ENEMIES[$('enemy').value];}
function selectedPart(){return selectedEnemy().parts[$('part').value];}
function resolvedA(){return resolveWeapon(WEAPONS[$('weapon').value],+$('mode').value||0);}
function resolvedB(){return resolveWeapon(WEAPONS[$('weaponB').value],+$('modeB').value||0);}
function favoriteActive(kind,name){return favoriteList(kind).includes(name);}
function updateFavoriteButtons(){document.querySelectorAll('.favorite-button').forEach(button=>{const target=button.dataset.favorite,kind=target==='enemy'?'enemy':'weapon',name=target==='enemy'?selectedText($('enemy')):selectedText($(target));const active=favoriteActive(kind,name);button.setAttribute('aria-pressed',active?'true':'false');button.textContent=active?'★':'☆';});}

function metric(label,value){return `<div class="metric"><span>${esc(label)}</span><b>${esc(value)}</b></div>`;}
function answerCard(result,title,eyebrow="Recommendation"){
  const status=`<span class="status ${result.outcome}">${esc(outcomeLabel(result.outcome))}</span>`;
  const access=result.access?`<div class="access-note ${result.access.canOpen?'setup':'blocked'}"><b>${result.access.canOpen?'Armor-break route':'Viable only after the armor is destroyed'}</b><span>${esc(result.access.note)}${!result.access.canOpen&&result.shots!=null?' This weapon cannot break the plate — figures below assume it is already destroyed (teammate, explosive, etc.).':''}${result.setupShots!=null?` Setup: ${fmt(result.setupShots)} ${isContinuous(result.weapon)?'seconds':'shots'}; target: ${fmt(result.targetShots)} ${isContinuous(result.weapon)?'seconds':'shots'}.`:''}</span></div>`:'';
  const continuous=isContinuous(result.weapon),capacityLabel=result.weapon.base?.cat==='Stratagem'?'Uses':result.weapon.continuous==='beam'?'Heat sinks':result.weapon.continuous==='flame'?'Canisters':'Magazines';
  return `<article class="answer-card" id="primaryAnswer"><div class="answer-eyebrow">${esc(eyebrow)} · ${status}</div><h2 class="answer-title">${esc(title)}</h2><p class="answer-subtitle">${esc(result.route?.label||result.access?.note||'This shot has no calculated lethal route.')}</p>${access}<div class="metrics">${metric(continuous?'Contact time':'Total shots',formatShots(result))}${metric('TTK',formatTtk(result))}${metric(capacityLabel,result.magazines??'—')}${metric('Penetration',penetrationLabel(result))}</div></article>`;
}
function rankPartCard(result,index,selected){return `<button class="rank-card${selected?' selected':''}" type="button" data-part-index="${result.partIndex}"><span class="rank-number">${index+1}</span><span class="rank-main"><b>${esc(result.part.name)}</b><span>${esc(outcomeLabel(result.outcome))} · ${esc(penetrationLabel(result))}${result.access?(result.access.canOpen?' · Armor break first':' · Needs armor stripped by another weapon'):''}</span></span><span class="rank-value">${esc(formatShots(result))}<small>${esc(formatTtk(result))}</small></span></button>`;}
function rankWeaponCard(result,index,selected){return `<button class="rank-card${selected?' selected':''}" type="button" data-weapon-index="${result.weaponIndex}" data-mode-index="${result.modeIndex}"><span class="rank-number">${index+1}</span><span class="rank-main"><b>${esc(result.base.name)}</b><span>${esc(result.modeName||result.base.cat)} · ${esc(outcomeLabel(result.outcome))}${result.access?' · Opens armor first':''}</span></span><span class="rank-value">${esc(formatShots(result))}<small>${esc(formatTtk(result))}</small></span></button>`;}
function adviceHTML(items){return items.length?`<div class="advice"><h3>Try this instead</h3><ul>${items.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></div>`:"";}

function imageView(file,index){const match=/ (Front|Side|Rear|Left|Right|Back)(?: \d+)?\.png$/i.exec(file.replace(/_/g,' '));return match?match[1]:`View ${index+1}`;}
function localImage(file){return 'assets/anatomy/'+encodeURIComponent(file.replace(/\.png$/i,'.webp'));}
function renderAnatomy(host,enemy,part){
  const files=part.img||[];activeViewIndex=Math.min(activeViewIndex,Math.max(0,files.length-1));host.replaceChildren();if(!files.length){host.innerHTML='<div class="empty">No anatomy image is available for this part.</div>';return;}
  const tabs=document.createElement('div');tabs.className='view-tabs';tabs.setAttribute('role','tablist');files.forEach((file,index)=>{const button=document.createElement('button');button.className='view-tab';button.type='button';button.setAttribute('role','tab');button.setAttribute('aria-selected',index===activeViewIndex?'true':'false');button.dataset.viewIndex=index;button.textContent=imageView(file,index);tabs.append(button);});
  const frame=document.createElement('div');frame.className='anatomy-frame';const img=document.createElement('img'),fallback=document.createElement('div');img.src=localImage(files[activeViewIndex]);img.width=300;img.height=190;img.alt=`${enemy.name} ${part.name} — ${imageView(files[activeViewIndex],activeViewIndex).toLowerCase()} view`;fallback.className='image-fallback';fallback.hidden=true;fallback.textContent='Anatomy image unavailable';img.addEventListener('error',()=>{img.hidden=true;fallback.hidden=false;});frame.append(img,fallback);host.append(tabs,frame);
}

function buildTechnical(enemy,part,resolved,evaluation){
  const r=evaluation.raw,base=resolved.base;const penBadge=component=>component.pf===1?`<span class="full">Full (AP${component.ap} &gt; AV${part.av})</span>`:component.pf===.65?`<span class="partial">Partial 65% (AP${component.ap} = AV${part.av})</span>`:`<span class="none">${component.explosive?'Blocked':'Ricochet'} (AP${component.ap} &lt; AV${part.av})</span>`;
  let html='<div class="technical-body">';if(evaluation.access){html+=`<div class="pen">Target access</div><div class="stat"><span>${esc(evaluation.access.note)}</span><span>${evaluation.access.canOpen?'Required':'Blocked'}</span></div>`;evaluation.access.stages.forEach(stage=>html+=`<div class="stat"><span>Break ${esc(stage.part.name)}</span><span>${fmt(stage.shots)} ${isContinuous(resolved)?'seconds':'shots'}</span></div>`);}if(r.d.comps.length===1)html+=`<div class="pen">Penetration after exposure: ${penBadge(r.d.comps[0])}</div>`;else{html+='<div class="pen">Penetration after exposure by component</div>';r.d.comps.forEach(component=>{const label=component.label||(component.explosive?'Explosion':'Direct round');html+=`<div class="stat"><span>${esc(label)}</span><span>${penBadge(component)} · ${fmt(component.dmg)} dmg</span></div>`;});}
  const force=STAGGER[base.name],required=STAGGER_REQ[enemy.name],hits=r.d.comps.some(component=>component.pf>0);let stagger;if(force==null)stagger='Weapon stagger force not documented';else if(required==null)stagger=`Force ${force}; enemy threshold not documented`;else if(!hits)stagger='No hit; no stagger';else stagger=force>=required?`Staggers (${force} ≥ ${required})`:`No flinch (${force} < ${required})`;html+=`<div class="stat"><span>${term('Stagger')}</span><span>${esc(stagger)}</span></div>`;
  const damageUnit=isContinuous(resolved)?'Damage/s':'Damage/shot';html+=`<div class="stat"><span>${damageUnit} to part</span><span>${fmt(r.d.total)}</span></div><div class="stat"><span>${damageUnit} to ${term('Main HP')}</span><span>${fmt(r.toMainPerShot)}</span></div>`;
  if(r.continuous){html+=`<div class="stat"><span>Sustained contact damage</span><span>${fmt(r.continuous.streamDps)} DPS</span></div>`;if(r.continuous.burn)html+=`<div class="stat"><span>Estimated ignition → burn</span><span>${fmt(r.continuous.burn.delay)}s → ${r.continuous.burn.dps} main DPS</span></div>`;else if(resolved.ignitionRate)html+=`<div class="note">Burn damage is excluded because this enemy's ignition threshold or fire penetration is not documented.</div>`;}if(r.routes.length){html+='<div class="pen" style="margin-top:12px">Calculated routes</div>';const best=r.routes.filter(route=>route.kills).sort((a,b)=>a.shots-b.shots)[0];r.routes.forEach(route=>html+=`<div class="route${route===best?' best':''}"><span>${esc(route.label)}<span class="tag">${esc(route.tag)}</span></span><span class="shots">${fmt(route.shots)} ${isContinuous(resolved)?'seconds':'shots'}</span></div>`);}if(base.activationDelay)html+=`<div class="stat"><span>Activation countdown</span><span>${base.activationDelay}s</span></div>`;if(base.cooldown)html+=`<div class="stat"><span>Base cooldown</span><span>${base.cooldown}s</span></div>`;if(base.demo)html+=`<div class="stat"><span>Demolition force</span><span>${base.demo}</span></div>`;if(base.note)html+=`<div class="note">${esc(base.note)}</div>`;if(r.info)html+=`<div class="note warn">${esc(r.info)}</div>`;if(enemy.note)html+=`<div class="note">${esc(enemy.note)}</div>`;return html+'</div>';
}
function detailPanel(enemy,part,resolved,evaluation,advice=[]){const access=evaluation.access?`<div class="access-note ${evaluation.access.canOpen?'setup':'blocked'}"><b>${evaluation.access.canOpen?'Requires setup':'Cannot expose with this weapon'}</b><span>${esc(evaluation.access.note)}</span></div>`:'';return `<section class="panel"><div class="panel-heading"><div><h2>Selected target</h2><p>${esc(part.name)}</p></div><span class="status ${evaluation.outcome}">${esc(outcomeLabel(evaluation.outcome))}</span></div><div class="anatomy-layout"><div id="activeAnatomy"></div><div class="detail-summary"><h3>${esc(part.name)}</h3><p>AV${part.av} · ${part.hp==='main'?enemy.main+' HP (shared main pool)':part.hp+' part HP'} · ${part.dur}% durability</p>${access}${adviceHTML(advice)}<details class="technical"><summary>Detailed damage breakdown</summary>${buildTechnical(enemy,part,resolved,evaluation)}</details></div></div></section>`;}

function recommendationContext(){return `${$('enemy').value}|${$('weapon').value}|${$('mode').value}|${$('angle').value}|${$('range').value}|${$('blast').value}`;}
function weaponContext(){return `${$('enemy').value}|${$('part').value}|${$('angle').value}|${$('range').value}|${$('blast').value}|${appState.rankCategory}`;}
function setPrimaryShare(result,title,target){const c=conditions(),blast=hasExplosion(result.weapon)?` · ${BLAST_SHORT[c.blast]}`:'';currentSharePayload={kind:'result',enemy:result.enemy.name,title,weapon:result.weapon.displayName,target,metrics:`${formatShots(result)} ${isContinuous(result.weapon)?'contact time':'shots'} · ${formatTtk(result)} TTK · ${result.magazines??'—'} magazine(s)`,conditions:`${ANGLE_SHORT[c.angle]} · ${RANGE_SHORT[c.range]}${blast}`};}

function orbitalOneShotRecommendation(enemy,weapon,baseConditions){
  const cacheKey=`${enemy.name}|${weapon.base.name}|${weapon.modeIndex}|${baseConditions.angle||0}`;if(orbitalRecommendationCache.has(cacheKey))return orbitalRecommendationCache.get(cacheKey);const radius=orbitalRadius(weapon),qualifies=result=>result.outcome==='immediate'&&result.shots!=null&&result.shots<=1,direct=evaluateOrbitalExposure(enemy,weapon,{...baseConditions,blastDistance:0});let maxDistance=qualifies(direct)?0:-1,result=direct;const near=evaluateOrbitalExposure(enemy,weapon,{...baseConditions,blastDistance:.01});if(radius.outer>0&&qualifies(near)){let low=.01,high=radius.outer;for(let i=0;i<18;i++){const mid=(low+high)/2,candidate=evaluateOrbitalExposure(enemy,weapon,{...baseConditions,blastDistance:mid});if(qualifies(candidate)){low=mid;result=candidate;}else high=mid;}maxDistance=low;}const recommendation=maxDistance>=0?{maxDistance,result,part:result.part,partIndex:result.partIndex,radius}:null;orbitalRecommendationCache.set(cacheKey,recommendation);return recommendation;
}

function renderOrbitalRecommendation(enemy,resolved){
  const recommendation=orbitalOneShotRecommendation(enemy,resolved,conditions()),distance=+$('blastDistance').value,radius=orbitalRadius(resolved),current=evaluateOrbitalExposure(enemy,resolved,{...conditions(),blastDistance:distance}),within=!!recommendation&&distance<=recommendation.maxDistance+.05,title=!recommendation?'No one-shot distance':recommendation.maxDistance<.05?'Direct impact required':`Keep target within ${fmt(recommendation.maxDistance)} m`,status=!recommendation?'No one-shot route':within?'Current placement one-shots':'Move impact closer';
  currentSharePayload={kind:'result',enemy:enemy.name,title,weapon:resolved.displayName,target:'Blast placement',metrics:`Maximum one-shot distance: ${recommendation?fmt(recommendation.maxDistance)+' m':'none'}`,conditions:`Target ${fmt(distance)} m from impact`};
  $('recommendContent').innerHTML=`<article class="answer-card" id="primaryAnswer"><div class="answer-eyebrow">Orbital placement · <span class="status ${within?'immediate':'blocked'}">${esc(status)}</span></div><h2 class="answer-title">${esc(title)}</h2><p class="answer-subtitle">${esc(resolved.displayName)} · verified ${fmt(radius.inner)}–${fmt(radius.outer)} m blast profile</p><div class="metrics">${metric('Maximum one-shot',recommendation?fmt(recommendation.maxDistance)+' m':'None')}${metric('Selected distance',fmt(distance)+' m')}${metric('Blast to Main',fmt(current.mainDamage))}${metric('Zones affected',current.blastExposure.affected.length)}</div></article><section class="panel"><div class="panel-heading"><div><h2>Distance assessment</h2><p>${esc(recommendation?`The enemy-wide blast remains lethal up to ${fmt(recommendation.maxDistance)} m from impact.`:'This orbital and firing mode cannot produce a one-use kill against this enemy.')}</p></div></div><div class="stat"><span>At ${fmt(distance)} m</span><span>${esc(outcomeLabel(current.outcome))} · ${esc(formatShots(current))}</span></div><div class="stat"><span>Full-damage inner radius</span><span>${fmt(radius.inner)} m</span></div><div class="stat"><span>Explosion outer radius</span><span>${fmt(radius.outer)} m</span></div><div class="note">Large explosions can transfer damage through several anatomy zones into Main HP. Documented repeated zones are included where a blast-exposure profile is available; other enemies use one instance of each exposed non-internal zone.</div></section>`;setupSticky(title,`${fmt(distance)} m selected · ${status}`);
}

function renderRecommendAim(){
  const enemy=selectedEnemy(),base=WEAPONS[$('weapon').value],resolved=resolvedA();if(isOrbital(resolved)){renderOrbitalRecommendation(enemy,resolved);return;}const ranked=rankParts(enemy,resolved,conditions()),context=recommendationContext();if(context!==lastAimContext){$('part').value=ranked[0].partIndex;lastAimContext=context;activeViewIndex=0;}const selected=ranked.find(result=>result.partIndex===+$('part').value)||ranked[0],advice=buildRecoveryAdvice(enemy,selected.part,base,resolved.modeIndex,conditions(),selected);setPrimaryShare(ranked[0],`Aim for ${ranked[0].part.name}`,ranked[0].part.name);
  $('recommendContent').innerHTML=answerCard(ranked[0],`Aim for ${ranked[0].part.name}`)+`<section class="panel"><div class="panel-heading"><div><h2>Ranked aim points</h2><p>Kill routes first; armor-break setup is included in total time and ammunition</p></div></div><div class="rank-grid">${ranked.map((result,index)=>rankPartCard(result,index,result.partIndex===selected.partIndex)).join('')}</div></section>`+detailPanel(enemy,selected.part,resolved,selected,advice);renderAnatomy($('activeAnatomy'),enemy,selected.part);setupSticky(`Aim for ${ranked[0].part.name}`,`${formatShots(ranked[0])} total shots · ${formatTtk(ranked[0])}`);
}

function renderRecommendWeapon(){
  // Stratagems participate in the same deterministic ranking and can also be
  // isolated when choosing an answer for a specific body part.
  const enemy=selectedEnemy(),part=selectedPart(),all=rankWeapons(enemy,part,conditions()),categories=['All','Primary','Secondary','Support','Stratagem'],filtered=appState.rankCategory==='All'?all:all.filter(result=>result.base.cat===appState.rankCategory),ranked=filtered.length?filtered:all,context=weaponContext();if(context!==lastWeaponContext){$('weapon').value=ranked[0].weaponIndex;fillMode($('mode'),$('modeRow'),$('weapon'),ranked[0].modeName);$('mode').value=ranked[0].modeIndex;comboControllers.weapon.sync();lastWeaponContext=context;}const selected=all.find(result=>result.weaponIndex===+$('weapon').value&&result.modeIndex===(+$('mode').value||0))||ranked[0],limit=appState.showAllWeapons?ranked.length:12;setPrimaryShare(ranked[0],`Use ${ranked[0].base.name}`,part.name);
  $('recommendContent').innerHTML=answerCard(ranked[0],`Use ${ranked[0].base.name}`,'Best weapon')+`<section class="panel"><div class="panel-heading"><div><h2>Ranked weapons</h2><p>Best available mode is selected per weapon</p></div></div><div class="rank-toolbar">${categories.map(category=>`<button class="filter-chip" type="button" data-rank-category="${category}" aria-pressed="${category===appState.rankCategory}">${category}</button>`).join('')}</div><div class="rank-grid">${ranked.slice(0,limit).map((result,index)=>rankWeaponCard(result,index,result.weaponIndex===selected.weaponIndex&&result.modeIndex===selected.modeIndex)).join('')}</div>${ranked.length>12?`<button class="action" type="button" id="toggleAllWeapons">${appState.showAllWeapons?'Show top 12':'Show all '+ranked.length}</button>`:''}</section>`+detailPanel(enemy,part,selected.weapon,selected);renderAnatomy($('activeAnatomy'),enemy,part);setupSticky(`Use ${ranked[0].base.name}`,`${formatShots(ranked[0])} shots · ${formatTtk(ranked[0])}`);
}

function renderInspect(){const enemy=selectedEnemy(),part=selectedPart(),base=WEAPONS[$('weapon').value],resolved=resolvedA(),evaluation=evaluatePart(enemy,part,resolved,conditions()),advice=buildRecoveryAdvice(enemy,part,base,resolved.modeIndex,conditions(),evaluation);setPrimaryShare(evaluation,`${outcomeLabel(evaluation.outcome)} through ${part.name}`,part.name);$('inspectContent').innerHTML=answerCard(evaluation,`${outcomeLabel(evaluation.outcome)} through ${part.name}`,'Shot assessment')+detailPanel(enemy,part,resolved,evaluation,advice);renderAnatomy($('activeAnatomy'),enemy,part);setupSticky(part.name,`${formatShots(evaluation)} shots · ${formatTtk(evaluation)}`);}

function comparisonResult(a,b){const comparison=compareEvaluations(a,b,false);return comparison<0?'a':comparison>0?'b':'tie';}
function compactCompareCard(result,label,winner){return `<article class="compare-weapon${winner?' winner':''}"><span class="answer-eyebrow">${esc(label)} ${winner?'· Winner':''}</span><h3>${esc(result.weapon.displayName)}</h3><p>${esc(result.part.name)} · ${esc(outcomeLabel(result.outcome))}</p><div class="metrics">${metric('Shots',formatShots(result))}${metric('TTK',formatTtk(result))}</div></article>`;}
function renderCompare(){
  const enemy=selectedEnemy(),a=resolvedA(),b=resolvedB(),rankA=rankParts(enemy,a,conditions()),rankB=rankParts(enemy,b,conditions()),overall=comparisonResult(rankA[0],rankB[0]),partIndex=+$('part').value,part=enemy.parts[partIndex],partA=evaluatePart(enemy,part,a,conditions(),partIndex),partB=evaluatePart(enemy,part,b,conditions(),partIndex),c=conditions(),blast=(hasExplosion(a)||hasExplosion(b))?` · ${BLAST_SHORT[c.blast]}`:'';currentSharePayload={kind:'compare',enemy:enemy.name,weaponA:a.displayName,weaponB:b.displayName,summary:overall==='tie'?`Tie on best routes`:overall==='a'?`${a.displayName} wins via ${rankA[0].part.name}`:`${b.displayName} wins via ${rankB[0].part.name}`,conditions:`${ANGLE_SHORT[c.angle]} · ${RANGE_SHORT[c.range]}${blast}`};
  const rows=enemy.parts.map((bodyPart,index)=>{const aa=evaluatePart(enemy,bodyPart,a,conditions(),index),bb=evaluatePart(enemy,bodyPart,b,conditions(),index),win=comparisonResult(aa,bb);return `<tr><td><button type="button" data-compare-part="${index}">${esc(bodyPart.name)}</button></td><td class="${win==='a'?'win-mark':win==='tie'?'tie-mark':''}">${esc(formatShots(aa))} · ${esc(formatTtk(aa))}${win==='a'?' · Wins':win==='tie'?' · Tie':''}</td><td class="${win==='b'?'win-mark':win==='tie'?'tie-mark':''}">${esc(formatShots(bb))} · ${esc(formatTtk(bb))}${win==='b'?' · Wins':win==='tie'?' · Tie':''}</td></tr>`;}).join('');
  $('compareContent').innerHTML=`<section class="panel" id="primaryAnswer"><div class="panel-heading"><div><h2>Enemy-wide matchup</h2><p>${esc(currentSharePayload.summary)}</p></div></div><div class="comparison-summary">${compactCompareCard(rankA[0],'Weapon A',overall==='a')}${'<div class="versus">VS</div>'}${compactCompareCard(rankB[0],'Weapon B',overall==='b')}</div></section><section class="panel"><div class="panel-heading"><div><h2>Body-part comparison</h2><p>Select a row to inspect it</p></div></div><table class="comparison-table"><thead><tr><th>Target</th><th>${esc(a.base.name)}</th><th>${esc(b.base.name)}</th></tr></thead><tbody>${rows}</tbody></table></section><section class="panel"><div class="panel-heading"><div><h2>Selected target</h2><p>${esc(part.name)}</p></div></div><div class="anatomy-layout"><div id="activeAnatomy"></div><div><div class="comparison-summary">${compactCompareCard(partA,'Weapon A',comparisonResult(partA,partB)==='a')}${'<div class="versus">VS</div>'}${compactCompareCard(partB,'Weapon B',comparisonResult(partA,partB)==='b')}</div><details class="technical"><summary>Weapon A breakdown</summary>${buildTechnical(enemy,part,a,partA)}</details><details class="technical"><summary>Weapon B breakdown</summary>${buildTechnical(enemy,part,b,partB)}</details></div></div></section>`;renderAnatomy($('activeAnatomy'),enemy,part);setupSticky(overall==='tie'?'Weapons tie':overall==='a'?`${a.base.name} wins`:`${b.base.name} wins`,`${enemy.name} matchup`);
}

function updateControls(){
  const compareMode=appState.view==='compare',shrapnelMax=Math.max(resolvedA().maxShrapnel||0,compareMode?(resolvedB().maxShrapnel||0):0);$('shrapnelField').hidden=!shrapnelMax;if(shrapnelMax){$('shrapnelHits').max=shrapnelMax;$('shrapnelHits').value=Math.min(+$('shrapnelHits').value,shrapnelMax);$('shrapnelHitsValue').textContent=`${$('shrapnelHits').value} of ${shrapnelMax}`;}
  const recommend=appState.view==='recommend',inspect=appState.view==='inspect',compare=appState.view==='compare',aim=appState.intent==='aim';$('intentTabs').hidden=!recommend;$('partField').hidden=recommend&&aim;$('weaponField').hidden=recommend&&!aim;$('weaponBField').hidden=!compare;$('swapWeapons').hidden=!compare;$('modeRow').hidden=!(($('modeRow').dataset.available==='true')&&(inspect||compare||(recommend&&aim)));$('modeBRow').hidden=!(compare&&$('modeBRow').dataset.available==='true');$('controlsTitle').textContent='01 / '+(compare?'Compare weapons':inspect?'Inspect shot':'Build recommendation');document.querySelector('label[for="weaponSearch"]').textContent=compare?'Weapon A':'Weapon';document.querySelectorAll('.mode-tab').forEach(button=>button.setAttribute('aria-selected',button.dataset.view===appState.view?'true':'false'));document.querySelectorAll('.intent-tab').forEach(button=>button.setAttribute('aria-selected',button.dataset.intent===appState.intent?'true':'false'));for(const view of ['recommend','inspect','compare']){$(view+'Panel').hidden=appState.view!==view;$(view+'Tab').setAttribute('aria-selected',appState.view===view?'true':'false');}$('conditionsSummary').textContent=`${ANGLE_SHORT[conditions().angle]} · ${RANGE_SHORT[conditions().range]}`;const modelEnemy=selectedEnemy().name,modelAvailable=!!TARGETING_3D_MODELS[modelEnemy];$('targeting3dLaunch').hidden=!modelAvailable;if(modelAvailable){$('targeting3dLaunchTitle').textContent=`${modelEnemy} damage model`;$('targeting3dLaunchDescription').textContent='Inspect game-derived collision shapes and their decoded HealthComponent damage zones.';}updateFavoriteButtons();
  const orbital=isOrbital(resolvedA())||(compare&&isOrbital(resolvedB())),explosive=hasExplosion(resolvedA())||(compare&&hasExplosion(resolvedB())),verified=resolvedA().base.blastKnown&&(!compare||!hasExplosion(resolvedB())||resolvedB().base.blastKnown);$('rangeField').hidden=orbital;$('blastField').hidden=!explosive||orbital;$('orbitalBlastField').hidden=!orbital;if(orbital){const radii=[orbitalRadius(resolvedA()),compare?orbitalRadius(resolvedB()):null].filter(radius=>radius?.outer),radius={inner:Math.max(...radii.map(item=>item.inner)),outer:Math.max(...radii.map(item=>item.outer))};$('blastDistance').max=radius.outer;$('blastDistance').value=Math.min(+$('blastDistance').value,radius.outer);$('blastDistanceValue').textContent=fmt(+$('blastDistance').value)+' m';$('blastInnerLabel').textContent='Inner '+fmt(radius.inner)+' m';$('blastOuterLabel').textContent='Edge '+fmt(radius.outer)+' m';$('conditionsSummary').textContent=`${ANGLE_SHORT[+$('angle').value]} · ${fmt(+$('blastDistance').value)} m from impact`;}else{const c=conditions();$('conditionsSummary').textContent=`${ANGLE_SHORT[c.angle]} · ${RANGE_SHORT[c.range]}${explosive?` · ${BLAST_SHORT[c.blast]}`:''}`;}$('blastHint').textContent=verified?'Verified inner and outer damage-radius profile.':'Estimated radial falloff; direct projectile damage is excluded away from impact.';$('blast').options[1].textContent=verified?'Inner blast · 100%':'Inner blast · ~85%';$('blast').options[3].textContent=verified?'Blast edge · ~1%':'Blast edge · ~15%';
}
function render(){
  updateControls();
  const activeContent=appState.view+'Content';
  for(const id of ['recommendContent','inspectContent','compareContent'])if(id!==activeContent)$(id).replaceChildren();
  if(appState.view==='recommend'){appState.intent==='aim'?renderRecommendAim():renderRecommendWeapon();}else if(appState.view==='inspect')renderInspect();else renderCompare();
  persist();
}

function setupSticky(title,meta){$('stickyTitle').textContent=title;$('stickyMeta').textContent=meta;if(stickyObserver)stickyObserver.disconnect();$('stickyResult').hidden=true;const answer=$('primaryAnswer');if(!answer||!matchMedia('(max-width:560px)').matches||!('IntersectionObserver'in window))return;stickyObserver=new IntersectionObserver(entries=>{$('stickyResult').hidden=entries[0].isIntersecting;},{threshold:.15});stickyObserver.observe(answer);}
function showToast(message){clearTimeout(toastTimer);$('toast').textContent=message;$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,2200);}
async function copyText(text){
  const area=document.createElement('textarea');area.value=text;area.setAttribute('readonly','');area.style.position='fixed';area.style.left='-9999px';document.body.append(area);area.select();area.setSelectionRange(0,area.value.length);let copied=false;
  try{copied=document.execCommand('copy');}catch{}area.remove();if(copied)return true;
  try{if(navigator.clipboard){await navigator.clipboard.writeText(text);return true;}}catch{}
  showCopyFallback(text);return false;
}
function showCopyFallback(text){const dialog=$('copyFallback'),area=$('copyFallbackText');area.value=text;if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');setTimeout(()=>{area.focus();area.select();},0);}
function downloadResultCard(){const canvas=document.createElement('canvas');canvas.width=1200;canvas.height=630;const ctx=canvas.getContext('2d'),summary=formatShareSummary(currentSharePayload).split('\n');ctx.fillStyle='#0b0d10';ctx.fillRect(0,0,1200,630);ctx.fillStyle='#ffe10a';ctx.fillRect(70,70,10,490);ctx.font='700 28px Segoe UI';ctx.fillText('HELLDIVERS 2 · SHOT PLACEMENT ASSESSOR',110,115);ctx.fillStyle='#e2e6ec';ctx.font='800 54px Segoe UI';let y=205;summary.forEach((line,index)=>{ctx.font=index===0?'800 54px Segoe UI':'600 30px Segoe UI';const words=line.split(' ');let current='';for(const word of words){const test=current?current+' '+word:word;if(ctx.measureText(test).width>960){ctx.fillText(current,110,y);y+=48;current=word;}else current=test;}ctx.fillText(current,110,y);y+=index===0?74:48;});ctx.fillStyle='#a2acbb';ctx.font='24px Segoe UI';ctx.fillText('Firing-time estimate · Reloads and movement excluded',110,560);try{const link=document.createElement('a');link.download='hd2-shot-placement.png';link.href=canvas.toDataURL('image/png');link.click();}catch{showToast('Could not create card');}}

function loadTargeting3dBundle(){
  if(targeting3d.bundle)return targeting3d.bundle;
  targeting3d.bundle=new Promise((resolve,reject)=>{if(globalThis.HD2Three){resolve(globalThis.HD2Three);return;}const script=document.createElement('script');script.src='assets/vendor/hd2-three-viewer.min.js';script.onload=()=>globalThis.HD2Three?resolve(globalThis.HD2Three):reject(new Error('Three.js bundle did not initialize'));script.onerror=()=>reject(new Error('Could not load the local Three.js bundle'));document.head.append(script);});
  return targeting3d.bundle;
}

function targeting3dArea(name){
  if(!name)return 'Unresolved attachment';
  const value=name.toLowerCase(),side=value.startsWith('l_')?'Left ':value.startsWith('r_')?'Right ':'';
  if(/head|jaw/.test(value))return 'Head / mandible neighborhood';
  if(/front_leg/.test(value))return `${side}front leg neighborhood`;
  if(/back_leg/.test(value))return `${side}rear leg neighborhood`;
  if(/arm/.test(value))return `${side}claw neighborhood`;
  if(/belly|entrail/.test(value))return 'Underside / internal neighborhood';
  if(/backplate|spine|boss/.test(value))return 'Torso / dorsal plate neighborhood';
  if(/butt|tail/.test(value))return 'Rear body / tail neighborhood';
  return 'Unresolved attachment';
}

function targeting3dZoneLabel(damage){
  const name=damage?.zoneName||damage?.zoneNameRaw||'Unresolved zone';
  if(name.startsWith('0x'))return `Zone ${Number(damage?.zoneIndex)+1} · ${name}`;
  return name.split('_').map(word=>word?word[0].toUpperCase()+word.slice(1):word).join(' ');
}

function resizeTargeting3d(){
  if(!targeting3d.renderer||!targeting3d.camera)return;const host=$('targeting3dCanvas'),width=Math.max(1,host.clientWidth),height=Math.max(1,host.clientHeight);targeting3d.renderer.setSize(width,height,false);targeting3d.camera.aspect=width/height;targeting3d.camera.updateProjectionMatrix();
}

function resetTargeting3d(){
  const saved=targeting3d.defaultCamera;if(!saved||!targeting3d.camera||!targeting3d.controls)return;targeting3d.camera.position.fromArray(saved.position);targeting3d.camera.up.set(0,1,0);targeting3d.controls.target.fromArray(saved.target);targeting3d.controls.update();
}

function applyTargeting3dHullVisibility(message=true){
  const showHulls=$('showTargeting3dHulls').checked,showGeometry=$('showTargeting3dGeometryOnly').checked;
  targeting3d.hulls.forEach(hull=>{hull.visible=showHulls&&(!hull.userData.hd2GeometryOnly||showGeometry);});
  if(targeting3d.selected&&!targeting3d.selected.visible)selectTargeting3dHull(null);
  if(!message)return;
  const damageCount=targeting3d.hulls.filter(hull=>!hull.userData.hd2GeometryOnly).length,geometryCount=targeting3d.hulls.length-damageCount;
  $('targeting3dStatus').textContent=!showHulls?'Collision hulls hidden':`${damageCount} damage hull${damageCount===1?'':'s'} visible${geometryCount?` · ${showGeometry?geometryCount+' geometry-only visible':geometryCount+' geometry-only hidden'}`:''}`;
}

function selectTargeting3dHull(mesh){
  if(targeting3d.selected)targeting3d.selected.material=targeting3d.selected.userData.hd2NormalMaterial;targeting3d.selected=mesh||null;
  if(!mesh){$('targeting3dCollider').textContent='None';$('targeting3dBone').textContent='Select a hull';$('targeting3dEvidence').textContent='Game-derived collision geometry';return;}
  mesh.material=mesh.userData.hd2SelectedMaterial;const data=mesh.userData.hd2Collision||{},damage=mesh.userData.hd2Damage,bone=data.boneName||data.parentNodeName||`Bone 0x${data.boneHash||'--------'}`,mountLabel=data.mountLabel,number=Number(data.recordIndex)+1;$('targeting3dCollider').textContent=mountLabel?`${mountLabel} · hitbox ${number}`:`Hull ${number} · 0x${data.colliderHash}`;
  if(damage){const hp=damage.mountedMainHealth?`${damage.mountedMainHealth} HP`:damage.health===-1?'Main HP':`${damage.health} HP`,durability=`${Math.round((damage.projectileDurableResistance??0)*100)}% durability`,zone=targeting3dZoneLabel(damage),analog=data.proxyMode?' · Gatekeeper / War Strider analog':'',layers=damage.zoneStack||[];
    if(layers.length>1){const summaries=layers.map(layer=>`${targeting3dZoneLabel(layer)} (${layer.health===-1?'Main HP':layer.health+' HP'}, AV${layer.armor})`);$('targeting3dBone').textContent=`Layered actor · ${summaries.join(' + ')}`;$('targeting3dEvidence').textContent=`Exact overlapping HealthComponent actor assignments · ${bone}`;$('targeting3dStatus').textContent=`Selected layered actor · hull ${number} of ${targeting3d.hulls.length}`;}
    else{$('targeting3dBone').textContent=`${zone} · ${hp} · AV${damage.armor} · ${durability}`;$('targeting3dEvidence').textContent=`${damage.evidenceLabel||'HealthComponent actor match'}${analog} · ${bone}`;$('targeting3dStatus').textContent=mountLabel?`Selected ${zone} · ${mountLabel} hitbox ${number}`:`Selected ${zone} · hull ${number} of ${targeting3d.hulls.length}`;}}
  else{$('targeting3dBone').textContent='No decoded damage-zone assignment';$('targeting3dEvidence').textContent=`Physics collider only · ${bone}`;$('targeting3dStatus').textContent=`Selected unmapped physics hull ${Number(data.recordIndex)+1}`;}
}

function bindTargeting3dRaycast(){
  if(targeting3d.raycastBound)return;targeting3d.raycastBound=true;
  const host=$('targeting3dCanvas'),{THREE}=globalThis.HD2Three,raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();
  host.addEventListener('pointerdown',event=>{targeting3d.pointerStart={x:event.clientX,y:event.clientY};});
  host.addEventListener('pointerup',event=>{const start=targeting3d.pointerStart;targeting3d.pointerStart=null;if(!start||Math.hypot(event.clientX-start.x,event.clientY-start.y)>6||!$('showTargeting3dHulls').checked)return;const rect=host.getBoundingClientRect();pointer.x=(event.clientX-rect.left)/rect.width*2-1;pointer.y=-(event.clientY-rect.top)/rect.height*2+1;raycaster.setFromCamera(pointer,targeting3d.camera);const hit=raycaster.intersectObjects(targeting3d.hulls.filter(hull=>hull.visible),false)[0];if(hit)selectTargeting3dHull(hit.object);});
}

function startTargeting3dLoop(){
  cancelAnimationFrame(targeting3d.frame);const tick=()=>{if(!$('targeting3dDialog').open)return;targeting3d.controls?.update();targeting3d.renderer?.render(targeting3d.scene,targeting3d.camera);targeting3d.frame=requestAnimationFrame(tick);};tick();
}

function loadTargeting3dGlb(GLTFLoader,path,onProgress){
  return new Promise((resolve,reject)=>new GLTFLoader().load(path,resolve,onProgress,reject));
}

function mountedDamageZone(mount,collider,manifest,mapped){
  const source=mapped||manifest.defaultDamageableZone;if(!source)return null;
  const proxy=collider.viewerProxy,area=proxy?.label?` ${proxy.label}`:collider.parentNodeName==='barrel'?' barrel':collider.parentNodeName==='pitch'?' housing':'',baseLabel=proxy?.label?.startsWith('turret ')&&mount.label.endsWith(' turret')?mount.label.slice(0,-7):mount.label;
  return {...source,zoneName:`${baseLabel}${area}`,zoneNameRaw:mapped?.zoneNameRaw||mapped?.zoneName||null,health:source.health,armor:source.armor,projectileDurableResistance:source.projectileDurableResistance??source.projectile_durable_resistance??0,affectsMainHealth:source.affectsMainHealth??source.affects_main_health??0,mountedMainHealth:manifest.mainHealth,evidenceLabel:proxy?'Comparative box proxy':mapped?'HealthComponent actor match':'HealthComponent default zone'};
}

async function attachTargeting3dMounts(entry,GLTFLoader,baseScene,status,materials){
  if(!entry.mountManifest)return {units:[],hitboxes:[]};
  const response=await fetch(entry.mountManifest,{cache:'no-store'});if(!response.ok)throw new Error('Could not load mounted-unit manifest');
  const manifest=await response.json();if(manifest.assemblyConfidence!=='verified-mount-component-join')throw new Error('Mounted-unit manifest has an unknown confidence state.');
  const mounted=[],hitboxes=[],{THREE}=globalThis.HD2Three;
  for(const mount of manifest.mounts){
    const socket=baseScene.getObjectByName(mount.attachNode);if(!socket)throw new Error(`Missing verified mount socket ${mount.attachNode}`);
    status.textContent=`Loading ${mount.label}`;
    // Repeated guns are loaded independently so each skinned mesh owns a valid skeleton.
    const assetVersion=mount.assetSha256?`?v=${mount.assetSha256.slice(0,16)}`:'',mountedGltf=await loadTargeting3dGlb(GLTFLoader,`assets/models/${mount.asset}${assetVersion}`),unit=mountedGltf.scene,axisRoot=unit.getObjectByName('StingrayEntityRoot');
    // Mounted assets retain their articulated yaw/pitch/barrel hierarchy. Raw
    // Filediver units use the socket-local identity root; Blender-authentic
    // shader bakes publish the equivalent rebased root in the manifest.
    if(axisRoot){if(mount.axisRootRotation)axisRoot.quaternion.fromArray(mount.axisRootRotation);else axisRoot.quaternion.identity();}
    unit.name=`hd2_mount_${mount.id}`;unit.userData.hd2Mount=mount;
    unit.traverse(object=>{
      if(!object.isMesh)return;
      const name=object.name.toLowerCase(),variant=object.userData?.default_hidden;
      if(variant===1||/(?:damaged|destroyed)(?:$|[_\s])/i.test(name))object.visible=false;
    });
    socket.add(unit);mounted.push(unit);
    if(mount.hitboxAsset&&mount.collisionManifest&&mount.damageManifest){
      status.textContent=`Loading ${mount.label} hitboxes`;
      const hitboxVersion=mount.hitboxAssetSha256?`?v=${mount.hitboxAssetSha256.slice(0,16)}`:'',[hitboxGltf,collisionManifest,damageManifest]=await Promise.all([
        loadTargeting3dGlb(GLTFLoader,`assets/models/${mount.hitboxAsset}${hitboxVersion}`),
        fetch(`assets/models/${mount.collisionManifest}`,{cache:'no-store'}).then(result=>{if(!result.ok)throw new Error(`Could not load ${mount.label} collision manifest`);return result.json();}),
        fetch(`assets/models/${mount.damageManifest}`,{cache:'no-store'}).then(result=>{if(!result.ok)throw new Error(`Could not load ${mount.label} damage manifest`);return result.json();})
      ]);
      if(collisionManifest.geometryConfidence!=='verified'||!['verified-complete-actor-join','partial-actor-join'].includes(damageManifest.mappingConfidence))throw new Error(`${mount.label} hitbox evidence failed validation`);
      const collisionScene=hitboxGltf.scene,collisionRoot=collisionScene.getObjectByName('StingrayEntityRoot'),damageByRecord=new Map((damageManifest.colliders||[]).map(item=>[item.recordIndex,item]));
      if(collisionRoot)collisionRoot.quaternion.identity();
      collisionScene.name=`hd2_mount_hitboxes_${mount.id}`;collisionScene.traverse(object=>{if(object.isMesh)object.visible=false;});
      const mountHitboxes=[];
      for(const collider of collisionManifest.colliders){
        const collisionObject=collisionScene.getObjectByName(collider.nodeName);if(!collisionObject?.isMesh)throw new Error(`${mount.label} is missing hitbox ${collider.nodeName}`);
        const viewerProxy=mount.viewerHitboxProxy?.records?.[String(collider.recordIndex)]||null;
        let object=collisionObject;
        if(viewerProxy){
          const renderSource=viewerProxy.renderNode?unit.getObjectByName(viewerProxy.renderNode):null;if(viewerProxy.renderNode&&!renderSource?.isMesh)throw new Error(`${mount.label} is missing proxy source ${viewerProxy.renderNode}`);
          const sourceObject=renderSource||collisionObject;sourceObject.geometry.computeBoundingBox();const bounds=sourceObject.geometry.boundingBox,center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3()),scale=viewerProxy.boxScale||[1,1,1],offset=viewerProxy.boxOffset||[0,0,0];size.multiply(new THREE.Vector3(...scale));center.add(new THREE.Vector3(...offset));
          const boxGeometry=new THREE.BoxGeometry(size.x,size.y,size.z);boxGeometry.translate(center.x,center.y,center.z);
          if(renderSource){object=new THREE.Mesh(boxGeometry);object.name=`${collider.nodeName}_proxy`;renderSource.parent.add(object);}else{const sourceGeometry=object.geometry;object.geometry=boxGeometry;sourceGeometry.dispose();}
        }
        const colliderData={...collider,viewerProxy},damage=mountedDamageZone(mount,colliderData,damageManifest,damageByRecord.get(collider.recordIndex)),normalMaterial=damage?materials.mappedMaterial:materials.unmappedMaterial,data={...colliderData,mountId:mount.id,mountLabel:mount.label,proxyMode:mount.viewerHitboxProxy?.mode||null,proxyAnalogs:mount.viewerHitboxProxy?.analogs||[]};
        object.userData.hd2Collision=data;object.userData.hd2Damage=damage;object.userData.hd2GeometryOnly=false;object.userData.hd2NormalMaterial=normalMaterial;object.userData.hd2SelectedMaterial=materials.selectedMaterial;object.material=normalMaterial;object.renderOrder=21;targeting3d.hulls.push(object);hitboxes.push(object);mountHitboxes.push(object);
      }
      if(mountHitboxes.length!==collisionManifest.hullCount)throw new Error(`${mount.label} hitbox count does not match its manifest`);
      socket.add(collisionScene);
    }
  }
  return {units:mounted,hitboxes};
}

function disposeTargeting3d(){
  cancelAnimationFrame(targeting3d.frame);targeting3d.resizeObserver?.disconnect();targeting3d.controls?.dispose?.();targeting3d.scene?.traverse(object=>{if(object.geometry)object.geometry.dispose?.();if(object.material){const materials=Array.isArray(object.material)?object.material:[object.material];materials.forEach(material=>material.dispose?.());}});targeting3d.renderer?.dispose?.();targeting3d.renderer=null;targeting3d.scene=null;targeting3d.camera=null;targeting3d.controls=null;targeting3d.model=null;targeting3d.hulls=[];targeting3d.selected=null;targeting3d.defaultCamera=null;targeting3d.initialized=false;targeting3d.enemy=null;$('targeting3dCanvas').replaceChildren();
}

async function initializeTargeting3d(enemyName=selectedEnemy().name){
  const entry=TARGETING_3D_MODELS[enemyName];if(!entry)throw new Error(`No 3D research model is available for ${enemyName}.`);if(targeting3d.initialized&&targeting3d.enemy===enemyName){resizeTargeting3d();startTargeting3dLoop();return;}if(targeting3d.loading)return;if(targeting3d.initialized)disposeTargeting3d();targeting3d.loading=true;targeting3d.enemy=enemyName;
  const loading=$('targeting3dLoading'),status=$('targeting3dStatus');loading.hidden=false;
  if(location.protocol==='file:'){loading.textContent='The 3D model is blocked by browser file security. Open the app through localhost; the 2D assessor remains available.';status.textContent='Local server required for 3D';targeting3d.loading=false;return;}
  try{
    const {THREE,GLTFLoader,OrbitControls}=await loadTargeting3dBundle(),probe=document.createElement('canvas');if(!probe.getContext('webgl2')&&!probe.getContext('webgl'))throw new Error('WebGL is unavailable; use the 2D anatomy view instead.');
    const host=$('targeting3dCanvas'),renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));renderer.setClearColor(0x111416,1);renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.35;host.replaceChildren(renderer.domElement);const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(36,1,.05,500);camera.up.set(0,1,0);const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.dampingFactor=.08;controls.screenSpacePanning=true;scene.add(new THREE.HemisphereLight(0xe0e8ea,0x51483b,3.3));const key=new THREE.DirectionalLight(0xffffff,4.2);key.position.set(-8,10,-14);scene.add(key);const fill=new THREE.DirectionalLight(0xb9d3e2,2.1);fill.position.set(10,2,-8);scene.add(fill);targeting3d.renderer=renderer;targeting3d.scene=scene;targeting3d.camera=camera;targeting3d.controls=controls;
    const base=`assets/models/${entry.assetSlug||entry.slug}`,paths={glb:`${base}-collision-research.glb`,collision:`${base}-collision-research.manifest.json`,damage:`${base}-damage-zones.manifest.json`};status.textContent=`Loading ${enemyName} model`;
    const [gltf,authenticRender,manifest,damageManifest]=await Promise.all([
      loadTargeting3dGlb(GLTFLoader,paths.glb,event=>{if(event.total)status.textContent=`Loading model · ${Math.round(event.loaded/event.total*100)}%`;}),
      entry.renderGlb?loadTargeting3dGlb(GLTFLoader,entry.renderGlb):Promise.resolve(null),
      fetch(paths.collision).then(response=>{if(!response.ok)throw new Error('Could not load collision evidence manifest');return response.json();}),
      fetch(paths.damage).then(response=>{if(!response.ok)throw new Error('Could not load damage-zone mapping manifest');return response.json();})
    ]);
    if(!['verified-exact-actor-join','verified-complete-actor-join','partial-actor-join','verified-layered-actor-join','partial-layered-actor-join'].includes(damageManifest.mappingConfidence))throw new Error('Damage-zone mapping manifest has an unknown confidence state.');
    targeting3d.model=gltf.scene;scene.add(gltf.scene);
    if(authenticRender){
      authenticRender.scene.name='hd2_authentic_render';
      const liftedFactoryMaps=new Map();
      const liftFactoryBodyMap=texture=>{
        if(!texture?.image)return texture;
        if(liftedFactoryMaps.has(texture.uuid))return liftedFactoryMaps.get(texture.uuid);
        const source=texture.image,width=source.width||source.naturalWidth||source.videoWidth,height=source.height||source.naturalHeight||source.videoHeight;
        if(!width||!height)return texture;
        try{
          const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
          const context=canvas.getContext('2d',{willReadFrequently:true});context.drawImage(source,0,0,width,height);
          const pixels=context.getImageData(0,0,width,height),data=pixels.data;
          for(let index=0;index<data.length;index+=4){
            if(!data[index+3])continue;
            const brightest=Math.max(data[index],data[index+1],data[index+2]);
            if(brightest>=70)continue;
            const lift=58-brightest;
            if(lift<=0)continue;
            data[index]=Math.min(255,data[index]+lift);data[index+1]=Math.min(255,data[index+1]+lift);data[index+2]=Math.min(255,data[index+2]+lift);
          }
          context.putImageData(pixels,0,0);
          const lifted=texture.clone();lifted.image=canvas;lifted.needsUpdate=true;liftedFactoryMaps.set(texture.uuid,lifted);return lifted;
        }catch(error){console.warn('Could not calibrate the Factory Strider body texture.',error);return texture;}
      };
      authenticRender.scene.traverse(object=>{
        if(!object.isMesh)return;
        const bodyPiece=enemyName==='Factory Strider'&&/(?:armor_(?:front|head|rear)_whole|body_static|engine_rear_whole|front_whole|head_whole|neck_whole)/.test(object.name);
        const materials=(Array.isArray(object.material)?object.material:[object.material]).map(material=>{
          if(!material?.isMeshStandardMaterial)return material;
          const bodySurface=bodyPiece||(enemyName==='Factory Strider'&&material.name.includes('0x5ab99a9d'));
          const adjusted=bodySurface?material.clone():material;
          adjusted.metalness=bodySurface ? .18 : .34;
          adjusted.metalnessMap=null;
          adjusted.roughness=bodySurface ? .64 : .62;
          adjusted.roughnessMap=null;
          if(bodySurface){adjusted.map=liftFactoryBodyMap(material.map);adjusted.color.setRGB(1.05,1.05,1.05);}
          adjusted.needsUpdate=true;
          return adjusted;
        });
        object.material=Array.isArray(object.material)?materials:materials[0];
      });
      scene.add(authenticRender.scene);
    }
    const mappedMaterial=new THREE.MeshBasicMaterial({color:0xf2d335,transparent:true,opacity:.22,wireframe:true,depthWrite:false,side:THREE.DoubleSide}),unmappedMaterial=new THREE.MeshBasicMaterial({color:0x7d8991,transparent:true,opacity:.16,wireframe:true,depthWrite:false,side:THREE.DoubleSide}),selectedMaterial=new THREE.MeshBasicMaterial({color:0xff8a4c,transparent:true,opacity:.72,depthWrite:false,side:THREE.DoubleSide}),manifestByNode=new Map(manifest.colliders.map(collider=>[collider.nodeName,collider])),damageByRecord=new Map(damageManifest.colliders.map(collider=>[collider.recordIndex,collider]));
    selectedMaterial.wireframe=true;selectedMaterial.opacity=.9;
    const renderProxies=[];
    gltf.scene.traverse(object=>{
      if(!object.isMesh)return;
      let owner=object,data=null;
      while(owner&&!data){data=owner.userData?.hd2Collision||manifestByNode.get(owner.name);owner=owner.parent;}
      if(!data&&object.material?.name!=='HD2 decoded collision hull'){
        if(authenticRender){object.visible=false;return;}
        const positions=object.geometry?.getAttribute('position')?.count||0,indices=object.geometry?.index?.count||0;
        // Filediver includes a 24-vertex unit-bounds cube in some vehicle exports.
        // It is metadata/proxy geometry, not the visible enemy mesh.
        if(!object.isSkinnedMesh&&positions===24&&indices===36){renderProxies.push(object);return;}
        // Filediver exports intact, damaged, destroyed, and internal wiring
        // variants together. The game uses default_hidden to show only the
        // intact configuration at spawn; honor that state in the static pose.
        if(object.userData?.default_hidden===1||/(?:^|[_\s])(?:damaged|destroyed)(?:$|[_\s])/i.test(object.name))object.visible=false;
        return;
      }
      if(!data)return;
      const damage=damageByRecord.get(data.recordIndex),normalMaterial=damage?mappedMaterial:unmappedMaterial;
      object.userData.hd2Collision=data;object.userData.hd2Damage=damage;object.userData.hd2GeometryOnly=!damage;object.userData.hd2NormalMaterial=normalMaterial;object.userData.hd2SelectedMaterial=selectedMaterial;object.material=normalMaterial;object.renderOrder=20;targeting3d.hulls.push(object);
    });
    renderProxies.forEach(object=>object.removeFromParent());
    if(targeting3d.hulls.length!==manifest.hullCount)throw new Error(`Expected ${manifest.hullCount} collision hulls, loaded ${targeting3d.hulls.length}.`);
    const mounted=await attachTargeting3dMounts(entry,GLTFLoader,gltf.scene,status,{mappedMaterial,unmappedMaterial,selectedMaterial});
    applyTargeting3dHullVisibility(false);
    const bounds=new THREE.Box3().setFromObject(gltf.scene),center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3()),span=Math.max(size.x,size.y,size.z),cameraVector=entry.cameraVector||[0,.08,-1.8],viewDirection=new THREE.Vector3(...cameraVector).normalize(),hostAspect=Math.max(.25,host.clientWidth/Math.max(1,host.clientHeight)),verticalHalfFov=THREE.MathUtils.degToRad(camera.fov*.5),fitExtent=Math.max(size.y,Math.max(size.x,size.z)/hostAspect),fitDistance=fitExtent/(2*Math.tan(verticalHalfFov))*1.08;camera.position.copy(center).addScaledVector(viewDirection,fitDistance);controls.target.copy(center);controls.minDistance=span*.25;controls.maxDistance=span*6;controls.update();targeting3d.defaultCamera={position:camera.position.toArray(),target:center.toArray()};targeting3d.resizeObserver=new ResizeObserver(resizeTargeting3d);targeting3d.resizeObserver.observe(host);bindTargeting3dRaycast();resizeTargeting3d();targeting3d.initialized=true;loading.hidden=true;
    const partial=damageManifest.mappingConfidence.startsWith('partial-'),layered=damageManifest.mappingConfidence.includes('layered'),mapped=damageManifest.mappedColliderCount,proxyMounts=mounted.units.filter(unit=>unit.userData.hd2Mount?.viewerHitboxProxy).length,exactMounts=mounted.units.length-proxyMounts,mountNote=mounted.units.length?(proxyMounts?`${mounted.hitboxes.length} rectangular mounted-weapon proxies cover ${proxyMounts} destroyable weapon unit${proxyMounts===1?'':'s'}. Their shapes are inferred from verified Gatekeeper gun-cover and War Strider turret colliders; mounted HP and armor remain game-derived. `:`${mounted.hitboxes.length} game-derived mounted-weapon collision hulls cover ${exactMounts} independently destroyable weapon unit${exactMounts===1?'':'s'}. No targeting proxies are substituted. `):'',layerNote=layered?`${damageManifest.layeredColliderCount} collider actor${damageManifest.layeredColliderCount===1?' is':'s are'} explicitly assigned to multiple HealthComponent pools; the viewer reports every assignment without choosing one as the gameplay winner. `:'';
    $('targeting3dTitle').textContent=`${enemyName} damage model`;$('targeting3dCanvas').setAttribute('aria-label',`Interactive ${enemyName} model with selectable collision hulls`);$('targeting3dBadge').textContent=proxyMounts?'BODY GEOMETRY VERIFIED / MOUNT PROXIES':layered?'GEOMETRY VERIFIED / LAYERED DAMAGE MAP':partial?'GEOMETRY VERIFIED / PARTIAL DAMAGE MAP':'GEOMETRY VERIFIED / DAMAGE ZONES VERIFIED';$('targeting3dSubtitle').textContent=proxyMounts?'Click a highlighted hull to inspect its damage zone. Mounted weapon boxes are comparative proxies and do not alter shot recommendations.':'Click a highlighted hull to inspect its game-derived damage zone. This preview does not yet alter shot recommendations.';$('targeting3dCaveat').textContent=partial?`${mapped} body collision hulls have verified HealthComponent assignments. ${damageManifest.unmatchedActorCount} body actor references remain unresolved; those gaps are not approximated. ${layerNote}${mountNote}Armor-break state transitions remain unmodeled.`:`Every decoded body damage actor has a verified HealthComponent assignment. ${layerNote}${damageManifest.unmappedColliderCount?`${damageManifest.unmappedColliderCount} additional non-damage physics collider${damageManifest.unmappedColliderCount===1?' is':'s are'} hidden by default; enable Show geometry-only hulls to inspect ${damageManifest.unmappedColliderCount===1?'it':'them'}. `:''}${mountNote}Armor-break state transitions remain unmodeled.`;const visibleDamage=targeting3d.hulls.filter(hull=>!hull.userData.hd2GeometryOnly).length;status.textContent=`${visibleDamage} visible damage hulls${layered?` · ${damageManifest.layeredColliderCount} layered`:''}${damageManifest.unmappedColliderCount?` · ${damageManifest.unmappedColliderCount} geometry-only hidden`:''}${mounted.units.length?` · ${mounted.units.length} mounted weapon${mounted.units.length===1?'':'s'}`:''} · click one to inspect`;startTargeting3dLoop();
  }catch(error){disposeTargeting3d();targeting3d.enemy=enemyName;loading.hidden=false;loading.textContent=error?.message||'The model could not be loaded. Use the 2D anatomy view instead.';status.textContent='3D unavailable';console.error('3D targeting preview:',error);}finally{targeting3d.loading=false;}
}

function openTargeting3d(){const enemyName=selectedEnemy().name,dialog=$('targeting3dDialog');$('targeting3dTitle').textContent=`${enemyName} damage model`;if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');initializeTargeting3d(enemyName);}
function closeTargeting3d(){cancelAnimationFrame(targeting3d.frame);const dialog=$('targeting3dDialog');if(typeof dialog.close==='function')dialog.close();else dialog.removeAttribute('open');}

function bindTabKeyboard(selector){const tabs=[...document.querySelectorAll(selector)];tabs.forEach((tab,index)=>tab.addEventListener('keydown',event=>{let next=null;if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index-1+tabs.length)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;if(next!==null){event.preventDefault();tabs[next].focus();tabs[next].click();}}));}

function bindEvents(){
  $('openTargeting3d').addEventListener('click',openTargeting3d);$('closeTargeting3d').addEventListener('click',closeTargeting3d);$('resetTargeting3d').addEventListener('click',resetTargeting3d);$('showTargeting3dHulls').addEventListener('change',()=>applyTargeting3dHullVisibility());$('showTargeting3dGeometryOnly').addEventListener('change',()=>applyTargeting3dHullVisibility());$('targeting3dDialog').addEventListener('close',()=>cancelAnimationFrame(targeting3d.frame));$('targeting3dDialog').addEventListener('click',event=>{if(event.target===$('targeting3dDialog'))closeTargeting3d();});
  document.querySelectorAll('.mode-tab').forEach(button=>button.addEventListener('click',()=>{appState.view=button.dataset.view;activeViewIndex=0;render();}));document.querySelectorAll('.intent-tab').forEach(button=>button.addEventListener('click',()=>{appState.intent=button.dataset.intent;activeViewIndex=0;render();}));
  bindTabKeyboard('.mode-tab');bindTabKeyboard('.intent-tab');
  $('enemy').addEventListener('change',()=>{remember('enemy',selectedText($('enemy')));fillParts();comboControllers.enemy.sync();lastAimContext=lastWeaponContext='';activeViewIndex=0;render();});$('part').addEventListener('change',()=>{lastWeaponContext='';activeViewIndex=0;render();});
  $('weapon').addEventListener('change',()=>{remember('weapon',selectedText($('weapon')));fillMode($('mode'),$('modeRow'),$('weapon'));comboControllers.weapon.sync();lastAimContext='';render();});$('weaponB').addEventListener('change',()=>{remember('weapon',selectedText($('weaponB')));fillMode($('modeB'),$('modeBRow'),$('weaponB'));comboControllers.weaponB.sync();render();});
  [$('mode'),$('modeB'),$('angle'),$('range'),$('blast')].forEach(control=>control.addEventListener('change',()=>{lastAimContext=lastWeaponContext='';render();}));
  let blastTimer=0;const renderBlastDistance=()=>{clearTimeout(blastTimer);lastAimContext=lastWeaponContext='';render();};$('blastDistance').addEventListener('input',()=>{const distance=+$('blastDistance').value;$('blastDistanceValue').textContent=fmt(distance)+' m';$('conditionsSummary').textContent=`${ANGLE_SHORT[+$('angle').value]} · ${fmt(distance)} m from impact`;clearTimeout(blastTimer);blastTimer=setTimeout(renderBlastDistance,80);});$('blastDistance').addEventListener('change',renderBlastDistance);
  let shrapnelFrame=0;$('shrapnelHits').addEventListener('input',()=>{$('shrapnelHitsValue').textContent=`${$('shrapnelHits').value} of ${$('shrapnelHits').max}`;cancelAnimationFrame(shrapnelFrame);shrapnelFrame=requestAnimationFrame(()=>{lastAimContext=lastWeaponContext='';render();});});
  document.querySelectorAll('.favorite-button').forEach(button=>button.addEventListener('click',()=>{const target=button.dataset.favorite,kind=target==='enemy'?'enemy':'weapon',name=target==='enemy'?selectedText($('enemy')):selectedText($(target)),key=kind==='enemy'?'favoriteEnemies':'favoriteWeapons',list=appState[key]||[];appState[key]=list.includes(name)?list.filter(item=>item!==name):[...list,name];comboControllers[target]?.sync();updateFavoriteButtons();persist();}));
  $('swapWeapons').addEventListener('click',()=>{const weaponA=$('weapon').value,modeA=selectedText($('mode')),weaponB=$('weaponB').value,modeB=selectedText($('modeB'));$('weapon').value=weaponB;$('weaponB').value=weaponA;fillMode($('mode'),$('modeRow'),$('weapon'),modeB);fillMode($('modeB'),$('modeBRow'),$('weaponB'),modeA);comboControllers.weapon.sync();comboControllers.weaponB.sync();render();});
  document.addEventListener('click',event=>{const partButton=event.target.closest('[data-part-index]');if(partButton){$('part').value=partButton.dataset.partIndex;activeViewIndex=0;render();return;}const weaponButton=event.target.closest('[data-weapon-index]');if(weaponButton){$('weapon').value=weaponButton.dataset.weaponIndex;fillMode($('mode'),$('modeRow'),$('weapon'));$('mode').value=weaponButton.dataset.modeIndex;comboControllers.weapon.sync();lastWeaponContext=weaponContext();render();return;}const comparePart=event.target.closest('[data-compare-part]');if(comparePart){$('part').value=comparePart.dataset.comparePart;activeViewIndex=0;render();return;}const view=event.target.closest('[data-view-index]');if(view){activeViewIndex=+view.dataset.viewIndex;render();return;}const category=event.target.closest('[data-rank-category]');if(category){appState.rankCategory=category.dataset.rankCategory;appState.showAllWeapons=false;lastWeaponContext='';render();return;}const termButton=event.target.closest('.term-button');if(termButton){termButton.closest('.term-wrap').classList.toggle('open');}});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.term-wrap.open').forEach(node=>node.classList.remove('open'));});
  $('copySummary').addEventListener('click',async()=>{if(await copyText(formatShareSummary(currentSharePayload)))showToast('Result copied');});$('copyLink').addEventListener('click',async()=>{persist();if(await copyText(location.href))showToast('Link copied');});$('downloadCard').addEventListener('click',downloadResultCard);$('closeCopyFallback').addEventListener('click',()=>$('copyFallback').close());
}

function initialize(){
  fillEnemies();fillWeapons($('weapon'));fillWeapons($('weaponB'));appState=readInitialState();selectByText($('enemy'),appState.enemy);fillParts(appState.part);selectByText($('weapon'),appState.weapon);selectByText($('weaponB'),appState.weaponB)||($('weaponB').value=$('weapon').value==='0'?'1':'0');fillMode($('mode'),$('modeRow'),$('weapon'),appState.mode);fillMode($('modeB'),$('modeBRow'),$('weaponB'),appState.modeB);if([...$('angle').options].some(option=>option.value===String(appState.angle)))$('angle').value=appState.angle;if([...$('range').options].some(option=>option.value===String(appState.range)))$('range').value=appState.range;if([...$('blast').options].some(option=>option.value===String(appState.blast)))$('blast').value=appState.blast;if(Number.isFinite(+appState.blastDistance))$('blastDistance').value=Math.max(0,+appState.blastDistance);if(Number.isFinite(+appState.shrapnelHits))$('shrapnelHits').value=Math.max(0,+appState.shrapnelHits);enhanceSelect($('enemy'));enhanceSelect($('weapon'));enhanceSelect($('weaponB'));remember('enemy',selectedText($('enemy')));remember('weapon',selectedText($('weapon')));$('glossary').innerHTML=Object.entries(TERM_DEFS).map(([name,definition])=>`<div><dt>${esc(name)}</dt><dd>${esc(definition)}</dd></div>`).join('');bindEvents();render();
}
initialize();
