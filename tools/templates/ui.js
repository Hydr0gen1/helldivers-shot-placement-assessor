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
  return {...base,comps:mode?.comps||base.comps,rpm:mode?.rpm||base.rpm,mag:mode?.mag||base.mag,continuous:mode?.continuous||base.continuous,ignitionRate:mode?.ignitionRate||base.ignitionRate,base,modeIndex:index,modeName:mode?.name||null,displayName:base.name+(mode?" — "+mode.name:"")};
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

// ============ DOM APP ============
const $=id=>document.getElementById(id);
const STORAGE_KEY="hd2-shot-placement:v4",LEGACY_KEYS=["hd2-shot-placement:v3","hd2-shot-placement:v2"];
const ANGLE_SHORT=["Direct","Slight angle","Large angle","Extreme angle"],RANGE_SHORT=["Point blank","~25 m","~50 m","~75 m","100 m+"],BLAST_SHORT=["Direct impact","Inner blast","Mid blast","Blast edge"];
const FACTION_COLORS={Terminids:"#ffc000",Automatons:"#ff5f5f",Illuminate:"#ce6ff9"};
const TERM_DEFS={AP:"Armor Penetration. AP equal to AV deals partial damage; higher AP deals full damage.",AV:"Armor Value. The target armor level checked against weapon AP.",Durability:"The percentage of damage that uses a weapon's durable-damage value.",ExDR:"Explosive damage resistance applied to explosive components.",Blast:"Placement within an explosion. Splash loses damage with distance and excludes the projectile's direct-hit component.","Main HP":"The enemy's shared health pool. Depleting it kills the enemy.","Damage cap":"Limits transferred damage to the remaining health of a destructible part.",Bleedout:"A delayed death caused by destroying certain fatal parts.",Stagger:"Whether weapon stun force meets the enemy's stagger threshold.",TTK:"Estimated time to kill: firing time plus reload time when more than one magazine is needed. Bleedout kills show '+ bleedout' rather than adding its duration; rankings prefer immediate kills when times are close."};
const comboControllers={};
const orbitalRecommendationCache=new Map();
let appState={view:"recommend",intent:"aim",favoriteEnemies:[],favoriteWeapons:[],recentEnemies:[],recentWeapons:[],rankCategory:"All",showAllWeapons:false};
let currentSharePayload=null,lastAimContext="",lastWeaponContext="",activeViewIndex=0,stickyObserver=null,toastTimer=null;

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
function fillWeapons(select){const nodes=[];for(const category of ["Primary","Secondary","Support","Throwable","Stratagem"]){const classes={};WEAPONS.forEach((weapon,index)=>{if(weapon.cat===category)(classes[weaponClass(weapon)]=classes[weaponClass(weapon)]||[]).push([weapon,index]);});for(const cls of Object.keys(classes).sort()){const group=document.createElement("optgroup");group.label=category+" · "+cls;classes[cls].sort((a,b)=>a[0].name.localeCompare(b[0].name)).forEach(([weapon,index])=>{const option=new Option(weapon.name,index);option.dataset.filter=category;group.append(option);});nodes.push(group);}}select.replaceChildren(...nodes);}
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
function orbitalRadius(weapon){const radii=(weapon?.comps||[]).map(componentBlastRadius).filter(Boolean);return radii.length?{inner:Math.max(...radii.map(radius=>radius.inner)),outer:Math.max(...radii.map(radius=>radius.outer))}:{inner:0,outer:0};}
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
  const cacheKey=`${enemy.name}|${weapon.base.name}|${weapon.modeIndex}|${baseConditions.angle||0}`;if(orbitalRecommendationCache.has(cacheKey))return orbitalRecommendationCache.get(cacheKey);const radius=orbitalRadius(weapon),qualifies=result=>result.outcome==='immediate'&&result.shots!=null&&result.shots<=1;let best=null;
  enemy.parts.forEach((part,partIndex)=>{const direct=evaluatePart(enemy,part,weapon,{...baseConditions,range:0,blast:0,blastDistance:0},partIndex);let maxDistance=qualifies(direct)?0:-1,result=direct;const near=evaluatePart(enemy,part,weapon,{...baseConditions,range:0,blast:0,blastDistance:.01},partIndex);if(radius.outer>0&&qualifies(near)){let low=.01,high=radius.outer;for(let i=0;i<18;i++){const mid=(low+high)/2,candidate=evaluatePart(enemy,part,weapon,{...baseConditions,range:0,blast:0,blastDistance:mid},partIndex);if(qualifies(candidate)){low=mid;result=candidate;}else high=mid;}maxDistance=low;}if(maxDistance>=0&&(!best||maxDistance>best.maxDistance+.01))best={maxDistance,result,part,partIndex};});
  const recommendation=best?{...best,radius}:null;orbitalRecommendationCache.set(cacheKey,recommendation);return recommendation;
}

function renderOrbitalRecommendation(enemy,resolved){
  const recommendation=orbitalOneShotRecommendation(enemy,resolved,conditions()),distance=+$('blastDistance').value,radius=orbitalRadius(resolved);if(recommendation)$('part').value=recommendation.partIndex;const currentPart=recommendation?.part||enemy.parts[0],current=evaluatePart(enemy,currentPart,resolved,{...conditions(),blastDistance:distance},enemy.parts.indexOf(currentPart)),within=!!recommendation&&distance<=recommendation.maxDistance+.05,title=!recommendation?'No one-shot distance':recommendation.maxDistance<.05?'Direct impact required':`Keep target within ${fmt(recommendation.maxDistance)} m`,status=!recommendation?'No one-shot route':within?'Current placement one-shots':'Move impact closer';
  currentSharePayload={kind:'result',enemy:enemy.name,title,weapon:resolved.displayName,target:'Blast placement',metrics:`Maximum one-shot distance: ${recommendation?fmt(recommendation.maxDistance)+' m':'none'}`,conditions:`Target ${fmt(distance)} m from impact`};
  $('recommendContent').innerHTML=`<article class="answer-card" id="primaryAnswer"><div class="answer-eyebrow">Orbital placement · <span class="status ${within?'immediate':'blocked'}">${esc(status)}</span></div><h2 class="answer-title">${esc(title)}</h2><p class="answer-subtitle">${esc(resolved.displayName)} · verified ${fmt(radius.inner)}–${fmt(radius.outer)} m blast profile</p><div class="metrics">${metric('Maximum one-shot',recommendation?fmt(recommendation.maxDistance)+' m':'None')}${metric('Selected distance',fmt(distance)+' m')}${metric('Call-in',fmt(resolved.activationDelay||0)+'s')}${metric('Cooldown',fmt(resolved.cooldown||0)+'s')}</div></article><section class="panel"><div class="panel-heading"><div><h2>Distance assessment</h2><p>${esc(recommendation?`The best available one-shot route remains lethal up to ${fmt(recommendation.maxDistance)} m from impact.`:'This orbital and firing mode cannot produce a one-use kill against this enemy.')}</p></div></div><div class="stat"><span>At ${fmt(distance)} m</span><span>${esc(outcomeLabel(current.outcome))} · ${esc(formatShots(current))}</span></div><div class="stat"><span>Full-damage inner radius</span><span>${fmt(radius.inner)} m</span></div><div class="stat"><span>Explosion outer radius</span><span>${fmt(radius.outer)} m</span></div><div class="note">The calculator checks every valid damage route internally, but orbital recommendations are ordered by blast tolerance rather than anatomy.</div></section>`;setupSticky(title,`${fmt(distance)} m selected · ${status}`);
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
  const recommend=appState.view==='recommend',inspect=appState.view==='inspect',compare=appState.view==='compare',aim=appState.intent==='aim';$('intentTabs').hidden=!recommend;$('partField').hidden=recommend&&aim;$('weaponField').hidden=recommend&&!aim;$('weaponBField').hidden=!compare;$('swapWeapons').hidden=!compare;$('modeRow').hidden=!(($('modeRow').dataset.available==='true')&&(inspect||compare||(recommend&&aim)));$('modeBRow').hidden=!(compare&&$('modeBRow').dataset.available==='true');$('controlsTitle').textContent='01 / '+(compare?'Compare weapons':inspect?'Inspect shot':'Build recommendation');document.querySelector('label[for="weaponSearch"]').textContent=compare?'Weapon A':'Weapon';document.querySelectorAll('.mode-tab').forEach(button=>button.setAttribute('aria-selected',button.dataset.view===appState.view?'true':'false'));document.querySelectorAll('.intent-tab').forEach(button=>button.setAttribute('aria-selected',button.dataset.intent===appState.intent?'true':'false'));for(const view of ['recommend','inspect','compare']){$(view+'Panel').hidden=appState.view!==view;$(view+'Tab').setAttribute('aria-selected',appState.view===view?'true':'false');}$('conditionsSummary').textContent=`${ANGLE_SHORT[conditions().angle]} · ${RANGE_SHORT[conditions().range]}`;updateFavoriteButtons();
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

function bindTabKeyboard(selector){const tabs=[...document.querySelectorAll(selector)];tabs.forEach((tab,index)=>tab.addEventListener('keydown',event=>{let next=null;if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index-1+tabs.length)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;if(next!==null){event.preventDefault();tabs[next].focus();tabs[next].click();}}));}

function bindEvents(){
  document.querySelectorAll('.mode-tab').forEach(button=>button.addEventListener('click',()=>{appState.view=button.dataset.view;activeViewIndex=0;render();}));document.querySelectorAll('.intent-tab').forEach(button=>button.addEventListener('click',()=>{appState.intent=button.dataset.intent;activeViewIndex=0;render();}));
  bindTabKeyboard('.mode-tab');bindTabKeyboard('.intent-tab');
  $('enemy').addEventListener('change',()=>{remember('enemy',selectedText($('enemy')));fillParts();comboControllers.enemy.sync();lastAimContext=lastWeaponContext='';activeViewIndex=0;render();});$('part').addEventListener('change',()=>{lastWeaponContext='';activeViewIndex=0;render();});
  $('weapon').addEventListener('change',()=>{remember('weapon',selectedText($('weapon')));fillMode($('mode'),$('modeRow'),$('weapon'));comboControllers.weapon.sync();lastAimContext='';render();});$('weaponB').addEventListener('change',()=>{remember('weapon',selectedText($('weaponB')));fillMode($('modeB'),$('modeBRow'),$('weaponB'));comboControllers.weaponB.sync();render();});
  [$('mode'),$('modeB'),$('angle'),$('range'),$('blast')].forEach(control=>control.addEventListener('change',()=>{lastAimContext=lastWeaponContext='';render();}));
  let blastFrame=0;$('blastDistance').addEventListener('input',()=>{$('blastDistanceValue').textContent=fmt(+$('blastDistance').value)+' m';cancelAnimationFrame(blastFrame);blastFrame=requestAnimationFrame(()=>{lastAimContext=lastWeaponContext='';render();});});
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
