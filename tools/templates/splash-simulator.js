// ============ 3D SPLASH SIMULATOR (pure helpers) ============
const EXPLOSIVE_DELIVERY_PROFILES={
  "Orbital 120mm HE Barrage":{kind:"barrage",spread:27,salvos:5,shellsPerSalvo:3,shellInterval:.75,salvoInterval:2,shockwave:11},
  "Orbital 380mm HE Barrage":{kind:"barrage",spread:36,salvos:5,shellsPerSalvo:3,shellInterval:1.5,salvoInterval:3,shockwave:18},
  "Orbital Walking Barrage":{kind:"walking-barrage",spread:25,salvos:5,shellsPerSalvo:3,shellInterval:1.5,salvoInterval:3,salvoStep:25,shockwave:18},
  "Orbital Precision Strike":{kind:"single",shockwave:18},
  "B-100 Portable Hellbomb (inner blast)":{kind:"ground-timed",groundOnly:true,delay:10,radius:{inner:17,outer:25},label:"Portable Hellbomb detonation"},
  "MS-11 Solo Silo":{kind:"guided-top-attack",shockwave:35,terminalElevation:70,maxLifetime:15,preferredSpeed:200,acceleration:50,turnPriorityAngle:45,guidance:"continuous-laser"},
  "G-6 Frag":{kind:"shrapnel",fragmentCount:35},
  "G-123 Thermite":{kind:"sticky",delay:6.5},
  "TD-220 Bastion Main Cannon":{kind:"single"}
};

function splashRadius(component){
  if(component?.blastRadius)return {inner:+component.blastRadius.inner,outer:+component.blastRadius.outer};
  const match=/(\d+(?:\.\d+)?)\s*[\u2013\u2014-]\s*(\d+(?:\.\d+)?)\s*m/i.exec(component?.label||"");
  return match?{inner:+match[1],outer:+match[2]}:null;
}

function getExplosiveProfile(base,modeIndex=0){
  if(!base)return null;
  const delivery=EXPLOSIVE_DELIVERY_PROFILES[base.name]||{kind:base.sticky?"sticky":"single"};
  const barrage=/barrage/i.test(delivery.kind);
  const selected=barrage?(base.modes?.[0]||base):(base.modes?.[modeIndex]||base);
  const components=(selected.comps||base.comps||[]).map(component=>({...component,radius:splashRadius(component)||(component.explosive&&delivery.radius?{...delivery.radius}:null)}));
  const explosions=components.filter(component=>component.explosive&&component.radius);
  const shrapnel=components.filter(component=>component.shrapnel);
  const direct=components.filter(component=>!component.explosive&&!component.shrapnel&&!component.mainOnly);
  const mainOnly=components.filter(component=>component.mainOnly);
  if(!explosions.length&&!shrapnel.length&&!base.sticky)return null;
  const outer=Math.max(0,...explosions.map(component=>component.radius.outer));
  const inner=Math.max(0,...explosions.map(component=>component.radius.inner));
  return {name:base.name,base,modeIndex,components,explosions,shrapnel,direct,mainOnly,inner,outer,delivery:{...delivery},sticky:!!base.sticky,delay:base.activationDelay??base.detonationDelay??delivery.delay??0,maxShrapnel:base.maxShrapnel||delivery.fragmentCount||0};
}

const v3=(x=0,y=0,z=0)=>({x,y,z});

function normalizeImpactForDelivery(impact,profile,groundY=0){
  if(profile?.delivery?.groundOnly!==true)return {...impact,position:{...impact.position}};
  return {...impact,position:v3(impact.position.x,groundY,impact.position.z),directPoolKey:null,angleIndex:0};
}

// Browsers expose mouse wheels and trackpad scroll gestures through the same
// WheelEvent interface, without a reliable device-type field. Keep the
// navigation choice explicit so large trackpad deltas cannot be mistaken for
// mouse-wheel input. Pinch gestures retain native OrbitControls zoom behavior.
function classifyTargeting3dWheelGesture(event,navigationMode="trackpad"){
  if(event.ctrlKey||event.metaKey)return "zoom";
  return navigationMode==="trackpad"?"orbit":"zoom";
}

const vadd=(a,b)=>v3(a.x+b.x,a.y+b.y,a.z+b.z);
const vsub=(a,b)=>v3(a.x-b.x,a.y-b.y,a.z-b.z);
const vmul=(a,s)=>v3(a.x*s,a.y*s,a.z*s);
const vdot=(a,b)=>a.x*b.x+a.y*b.y+a.z*b.z;
const vlen2=a=>vdot(a,a);
const vlen=a=>Math.sqrt(vlen2(a));
const vcross=(a,b)=>v3(a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x);
const vnorm=a=>{const length=vlen(a)||1;return vmul(a,1/length);};

// Representative terminal segment for the Solo Silo. The decoded missile
// continuously follows the laser and does not contain a fixed terminal angle,
// so elevation is an evidence-labeled viewer policy rather than a game constant.
function guidedTopAttackDirection(heading=0,elevation=70){
  const radians=elevation*Math.PI/180,horizontal=Math.cos(radians);
  return vnorm(v3(Math.sin(heading)*horizontal,-Math.sin(radians),Math.cos(heading)*horizontal));
}

// Real-Time Collision Detection, Christer Ericson: closest point on triangle.
function closestPointOnTriangle(point,a,b,c){
  const ab=vsub(b,a),ac=vsub(c,a),ap=vsub(point,a),d1=vdot(ab,ap),d2=vdot(ac,ap);
  if(d1<=0&&d2<=0)return {...a};
  const bp=vsub(point,b),d3=vdot(ab,bp),d4=vdot(ac,bp);
  if(d3>=0&&d4<=d3)return {...b};
  const vc=d1*d4-d3*d2;if(vc<=0&&d1>=0&&d3<=0){const t=d1/(d1-d3);return vadd(a,vmul(ab,t));}
  const cp=vsub(point,c),d5=vdot(ab,cp),d6=vdot(ac,cp);
  if(d6>=0&&d5<=d6)return {...c};
  const vb=d5*d2-d1*d6;if(vb<=0&&d2>=0&&d6<=0){const t=d2/(d2-d6);return vadd(a,vmul(ac,t));}
  const va=d3*d6-d5*d4;if(va<=0&&(d4-d3)>=0&&(d5-d6)>=0){const t=(d4-d3)/((d4-d3)+(d5-d6));return vadd(b,vmul(vsub(c,b),t));}
  const denominator=1/(va+vb+vc),v=vb*denominator,w=vc*denominator;return vadd(a,vadd(vmul(ab,v),vmul(ac,w)));
}

function pointBoundsDistance(point,bounds){
  const axis=(value,min,max)=>value<min?min-value:value>max?value-max:0;
  return Math.hypot(axis(point.x,bounds.min.x,bounds.max.x),axis(point.y,bounds.min.y,bounds.max.y),axis(point.z,bounds.min.z,bounds.max.z));
}

function nearestPointOnHull(point,hull){
  let nearest=null,best=Infinity;
  for(const triangle of hull.triangles||[]){const candidate=closestPointOnTriangle(point,triangle[0],triangle[1],triangle[2]),distance=vlen2(vsub(candidate,point));if(distance<best){best=distance;nearest=candidate;}}
  if(!nearest&&hull.bounds){nearest=v3(Math.max(hull.bounds.min.x,Math.min(hull.bounds.max.x,point.x)),Math.max(hull.bounds.min.y,Math.min(hull.bounds.max.y,point.y)),Math.max(hull.bounds.min.z,Math.min(hull.bounds.max.z,point.z)));best=vlen2(vsub(nearest,point));}
  return nearest?{point:nearest,distance:Math.sqrt(best)}:null;
}

function segmentTriangleDistance(origin,target,triangle){
  const direction=vsub(target,origin),edge1=vsub(triangle[1],triangle[0]),edge2=vsub(triangle[2],triangle[0]),p=vcross(direction,edge2),det=vdot(edge1,p);
  if(Math.abs(det)<1e-8)return null;const inv=1/det,tvec=vsub(origin,triangle[0]),u=vdot(tvec,p)*inv;if(u<0||u>1)return null;
  const q=vcross(tvec,edge1),v=vdot(direction,q)*inv;if(v<0||u+v>1)return null;const t=vdot(edge2,q)*inv;return t>1e-5&&t<.99999?t:null;
}

function rayTriangleDistance(origin,direction,triangle){
  const edge1=vsub(triangle[1],triangle[0]),edge2=vsub(triangle[2],triangle[0]),p=vcross(direction,edge2),det=vdot(edge1,p);
  if(Math.abs(det)<1e-8)return null;const inv=1/det,tvec=vsub(origin,triangle[0]),u=vdot(tvec,p)*inv;if(u<0||u>1)return null;
  const q=vcross(tvec,edge1),v=vdot(direction,q)*inv;if(v<0||u+v>1)return null;const t=vdot(edge2,q)*inv;return t>1e-5?t:null;
}

function normalizedZoneDamage(damage={}){
  const get=(camel,snake,fallback)=>damage[camel]??damage[snake]??fallback,explosive=+get("explosiveDamagePercentage","explosive_damage_percentage",1);
  return {...damage,health:+get("health","health",-1),armor:+get("armor","armor",0),durability:+get("projectileDurableResistance","projectile_durable_resistance",0),affectsMain:+get("affectsMainHealth","affects_main_health",0),redirectExplosionToMain:!!get("affectedByExplosions","affected_by_explosions",false),affectedByExplosions:!!get("affectedByExplosions","affected_by_explosions",false),explosiveMultiplier:Number.isFinite(explosive)&&explosive<100?explosive:1,verificationMode:get("explosionVerificationMode","explosion_verification_mode","ExplosionVerificationMode_All"),capMain:!!get("mainHealthAffectCappedByZoneHealth","main_health_affect_capped_by_zone_health",true),fatal:!!(get("causesDeathOnDeath","causes_death_on_death",false)||get("causesDownedOnDeath","causes_downed_on_death",false)),bleedout:!!get("causesDownedOnDeath","causes_downed_on_death",false)};
}

function humanizePhysicalPartName(value){
  const replacements={l:"Left",r:"Right",c:"Center",back:"Rear",mid:"Middle",lhs:"Left",rhs:"Right"},words=String(value||"").replace(/([a-z0-9])([A-Z])/g,"$1_$2").split(/[^a-z0-9]+/i).filter(Boolean).map(word=>replacements[word.toLowerCase()]||word.toLowerCase());
  return words.map(word=>word.length<=2&&/^(hp|ap|av)$/i.test(word)?word.toUpperCase():word[0].toUpperCase()+word.slice(1)).join(" ");
}

function damageZoneTechnicalLabel(damage={}){
  const name=damage.zoneName||damage.zoneNameRaw||"Unresolved zone";
  if(/^0x[0-9a-f]+$/i.test(name))return `Zone ${Number(damage.zoneIndex)+1} · ${name}`;
  return humanizePhysicalPartName(name);
}

function physicalPartLabel(damage={},collisions=[]){
  const technicalLabel=damageZoneTechnicalLabel(damage),unique=values=>[...new Set(values.filter(Boolean))],mounts=unique(collisions.map(collision=>collision.mountLabel)),proxies=unique(collisions.map(collision=>collision.proxyLabel)),rawName=damage.zoneName||damage.zoneNameRaw||"",rawHash=/^0x[0-9a-f]+$/i.test(rawName),genericZone=/^(?:main|default|zone|body_main|main_body)$/i.test(rawName),bones=unique(collisions.flatMap(collision=>[collision.boneName,collision.parentNodeName]).filter(name=>name&&!/^hd2_collision_/i.test(name))),genericBone=/^(?:boss|root|unit_root|entity_root|stingrayentityroot|c_body|body|center|centre)$/i,specificBones=bones.filter(name=>!genericBone.test(name));
  if(mounts.length)return {label:mounts.map(humanizePhysicalPartName).join(" / "),technicalLabel,partEvidence:`Verified mounted unit · ${mounts.join(" / ")}`};
  if(proxies.length)return {label:proxies.map(humanizePhysicalPartName).join(" / "),technicalLabel,partEvidence:"Evidence-labeled inferred proxy"};
  if(damage.physicalLabel){const sources=damage.physicalLabelSources?.length?damage.physicalLabelSources:specificBones.length?specificBones:bones;return {label:damage.physicalLabel,technicalLabel,partEvidence:damage.physicalLabelEvidence==="decoded-damage-zone-name"?"Decoded damage-zone name":damage.physicalLabelEvidence==="verified-attachment-name"?`Verified attachment name${sources.length===1?"":"s"}${sources.length?` · ${sources.join(" / ")}`:""}`:damage.physicalLabelEvidence==="verified-root-attachment"?"Verified root attachment":damage.physicalLabelEvidence==="evidence-labeled-physical-proxy"?"Evidence-labeled physical proxy":"Physical attachment unresolved"};}
  if(!rawHash&&!genericZone&&rawName)return {label:humanizePhysicalPartName(rawName),technicalLabel,partEvidence:"Decoded damage-zone name"};
  if(specificBones.length)return {label:specificBones.map(humanizePhysicalPartName).join(" / "),technicalLabel,partEvidence:`Verified attachment bone${specificBones.length===1?"":"s"} · ${specificBones.join(" / ")}`};
  if(!rawHash&&rawName)return {label:humanizePhysicalPartName(rawName),technicalLabel,partEvidence:"Decoded damage-zone name"};
  if(bones.length)return {label:"Central Body / Chassis",technicalLabel,partEvidence:`Root-attached collision hull · ${bones.join(" / ")}`};
  return {label:"Unresolved Physical Attachment",technicalLabel,partEvidence:"No named attachment bone recovered"};
}

function buildCollisionSceneIndex(hulls,{mainHealth=0,unitsPerMeter=1}={}){
  const groups=new Map(),occluders=[];
  for(const hull of hulls||[]){
    if(!hull.damage){occluders.push({...hull,triangles:hull.triangles||[],bounds:hull.bounds,poolKey:null});continue;}
    const damage=normalizedZoneDamage(hull.damage),collision=hull.collision||{},poolKey=hull.poolKey||`${collision.mountId||"body"}:${damage.zoneIndex??damage.zoneName??collision.recordIndex}`;
    const copy={...hull,triangles:hull.triangles||[],bounds:hull.bounds,poolKey};occluders.push(copy);
    if(!groups.has(poolKey))groups.set(poolKey,{poolKey,damage,hulls:[],label:hull.label||damage.zoneName||damage.zoneNameRaw||poolKey,evidence:hull.evidence||damage.evidenceLabel||"Game-derived damage mapping"});groups.get(poolKey).hulls.push(copy);
  }
  for(const group of groups.values()){const physical=physicalPartLabel(group.damage,group.hulls.map(hull=>hull.collision||{}));group.label=physical.label;group.technicalLabel=physical.technicalLabel;group.partEvidence=physical.partEvidence;}
  return {groups:[...groups.values()],groupsByKey:groups,occluders,mainHealth:+mainHealth||0,unitsPerMeter:+unitsPerMeter||1};
}

function nearestGroupPoint(scene,origin,group,maxDistance=Infinity){
  let best=null;for(const hull of group.hulls){if(hull.bounds&&pointBoundsDistance(origin,hull.bounds)>Math.min(maxDistance,best?.distance??Infinity))continue;const candidate=nearestPointOnHull(origin,hull);if(candidate&&(!best||candidate.distance<best.distance))best={...candidate,hull};}return best;
}

function hasLineOfSight(scene,origin,target,targetPoolKey){
  for(const hull of scene.occluders){if(hull.poolKey===targetPoolKey)continue;if(hull.bounds&&pointBoundsDistance(origin,hull.bounds)>vlen(vsub(target,origin)))continue;for(const triangle of hull.triangles||[]){if(segmentTriangleDistance(origin,target,triangle)!=null)return false;}}return true;
}

function splashPenetration(ap,armor){return ap>armor?1:(ap===armor?.65:0);}
function componentDamage(component,damage,falloff=1,explosive=false,angleIndex=0){
  const ap=component.ap?.[Math.max(0,Math.min(3,angleIndex))]??component.ap?.[0]??0,pf=splashPenetration(ap,damage.armor),dur=Math.max(0,Math.min(1,damage.durability)),base=component.std*(1-dur)+component.dur*dur,multiplier=explosive?damage.explosiveMultiplier:1;
  return {damage:Math.floor(Math.max(0,pf*base*falloff*multiplier)),ap,pf};
}

function blastFalloff(radius,distance){if(distance<=radius.inner)return 1;if(distance>=radius.outer)return 0;return (radius.outer-distance)/(radius.outer-radius.inner);}

function fibonacciDirections(count,seed=1){
  const random=mulberry32(seed),offset=random()*Math.PI*2,directions=[];for(let index=0;index<count;index++){const y=1-(index+.5)*2/count,r=Math.sqrt(Math.max(0,1-y*y)),angle=index*Math.PI*(3-Math.sqrt(5))+offset;directions.push(v3(Math.cos(angle)*r,y,Math.sin(angle)*r));}return directions;
}

function firstRayGroupHit(scene,origin,direction,maxDistance=250){
  let best=null;for(const group of scene.groups){for(const hull of group.hulls){for(const triangle of hull.triangles||[]){const distance=rayTriangleDistance(origin,direction,triangle);if(distance!=null&&distance<=maxDistance&&(!best||distance<best.distance)){const normal=vnorm(vcross(vsub(triangle[1],triangle[0]),vsub(triangle[2],triangle[0]))),incidence=Math.acos(Math.max(0,Math.min(1,Math.abs(vdot(vmul(direction,-1),normal)))))*180/Math.PI,angleIndex=incidence<=25?0:incidence<=45?1:incidence<=60?2:3;best={group,distance,point:vadd(origin,vmul(direction,distance)),normal,incidence,angleIndex};}}}}return best;
}

function freshSplashState(scene,state){
  if(state)return {mainHP:state.mainHP,zoneHP:new Map(state.zoneHP),dead:state.dead};const zoneHP=new Map();scene.groups.forEach(group=>{if(group.damage.health>=0)zoneHP.set(group.poolKey,group.damage.health);});return {mainHP:scene.mainHealth,zoneHP,dead:false};
}

function applyPoolDamage(state,group,total){
  const damage=group.damage,before=damage.health<0?Infinity:(state.zoneHP.get(group.poolKey)??damage.health),counted=damage.capMain&&Number.isFinite(before)?Math.min(total,before):total,mainDamage=damage.health<0?total:counted*damage.affectsMain;
  if(Number.isFinite(before))state.zoneHP.set(group.poolKey,Math.max(0,before-total));state.mainHP=Math.max(0,state.mainHP-mainDamage);if(state.mainHP<=0||(damage.fatal&&Number.isFinite(before)&&before>0&&before-total<=0))state.dead=true;
  return {healthBefore:before,healthAfter:Number.isFinite(before)?Math.max(0,before-total):null,mainDamage,destroyed:Number.isFinite(before)&&before>0&&before-total<=0};
}

function simulateImpact(scene,impact,profile,policy="primary",priorState=null){
  const state=freshSplashState(scene,priorState),wasDead=state.dead,mainHPBefore=state.mainHP,origin=impact.position,zoneResults=[],directKey=impact.directPoolKey||null;
  for(const group of scene.groups){
    const nearest=nearestGroupPoint(scene,origin,group,profile.outer||0),damage=group.damage;let explosionDamage=0,directDamage=0,falloff=0,visible=true,eligible=false,distance=nearest?.distance??Infinity;
    // affected_by_explosions controls a once-per-explosion redirect to Main
    // HP; it is not blanket blast immunity. Small-enemy pools commonly store
    // false here and still take radial damage normally.
    if(nearest&&distance<=profile.outer){
      visible=hasLineOfSight(scene,origin,nearest.point,group.poolKey);const inOuter=distance>profile.inner,mode=damage.verificationMode,requires=policy==="conservative"||policy==="primary"&&(mode==="ExplosionVerificationMode_All"||mode==="ExplosionVerificationMode_OuterRadius"&&inOuter);eligible=policy==="raw"||!requires||visible;
      if(eligible)for(const component of profile.explosions){const componentFalloff=blastFalloff(component.radius,distance),value=componentDamage(component,damage,componentFalloff,true);explosionDamage+=value.damage;falloff=Math.max(falloff,componentFalloff);}
    }
    if(group.poolKey===directKey)for(const component of profile.direct)directDamage+=componentDamage(component,damage,1,false,impact.angleIndex||0).damage;
    const total=directDamage+explosionDamage;if(!total)continue;const applied=applyPoolDamage(state,group,total);zoneResults.push({poolKey:group.poolKey,label:group.label,technicalLabel:group.technicalLabel,partEvidence:group.partEvidence,evidence:group.evidence,distance,nearestPoint:nearest?.point||origin,visible,eligible,verificationMode:damage.verificationMode,falloff,directDamage,explosionDamage,shrapnelDamage:0,total,...applied,armor:damage.armor,durability:damage.durability,fatal:damage.fatal,bleedout:damage.bleedout,affectsMain:damage.affectsMain,redirectExplosionToMain:damage.redirectExplosionToMain});
  }
  if(profile.shrapnel.length){const fragment=profile.shrapnel[0],hits=new Map();for(const direction of fibonacciDirections(profile.maxShrapnel||fragment.count||1,impact.seed||1)){const hit=firstRayGroupHit(scene,origin,direction,250);if(hit){const bucket=hits.get(hit.group.poolKey)||[];bucket.push(hit);hits.set(hit.group.poolKey,bucket);}}for(const [poolKey,fragmentHits] of hits){const group=scene.groupsByKey.get(poolKey),total=fragmentHits.reduce((sum,hit)=>sum+componentDamage(fragment,group.damage,1,false,hit.angleIndex).damage,0),count=fragmentHits.length;if(!total)continue;const existing=zoneResults.find(item=>item.poolKey===poolKey),applied=applyPoolDamage(state,group,total);if(existing){existing.shrapnelDamage+=total;existing.fragmentHits=(existing.fragmentHits||0)+count;existing.total+=total;existing.mainDamage+=applied.mainDamage;existing.healthAfter=applied.healthAfter;existing.destroyed=existing.destroyed||applied.destroyed;}else zoneResults.push({poolKey,label:group.label,technicalLabel:group.technicalLabel,partEvidence:group.partEvidence,evidence:group.evidence,distance:null,visible:true,eligible:true,verificationMode:"Ballistic fragment",falloff:1,directDamage:0,explosionDamage:0,shrapnelDamage:total,fragmentHits:count,total,...applied,armor:group.damage.armor,durability:group.damage.durability,fatal:group.damage.fatal,bleedout:group.damage.bleedout,affectsMain:group.damage.affectsMain,redirectExplosionToMain:group.damage.redirectExplosionToMain});}}
  let mainOnlyDamage=0;if(directKey&&profile.mainOnly.length){const group=scene.groupsByKey.get(directKey);for(const component of profile.mainOnly)mainOnlyDamage+=componentDamage(component,group?.damage||normalizedZoneDamage(),1,false).damage;state.mainHP=Math.max(0,state.mainHP-mainOnlyDamage);if(state.mainHP<=0)state.dead=true;}
  const deathTriggers=[];if(!wasDead&&state.dead){for(const zone of zoneResults)if(zone.fatal&&zone.destroyed)deathTriggers.push({kind:zone.bleedout?"bleedout-zone":"fatal-zone",poolKey:zone.poolKey,label:zone.label,technicalLabel:zone.technicalLabel,partEvidence:zone.partEvidence,damage:zone.total,healthBefore:zone.healthBefore});if(mainHPBefore>0&&state.mainHP<=0)deathTriggers.push({kind:"main-hp",mainHPBefore,mainDamage:zoneResults.reduce((sum,item)=>sum+item.mainDamage,0)+mainOnlyDamage});}
  return {impact,policy,state,zones:zoneResults.sort((a,b)=>b.total-a.total),mainOnlyDamage,totalDamage:zoneResults.reduce((sum,item)=>sum+item.total,0)+mainOnlyDamage,mainDamage:zoneResults.reduce((sum,item)=>sum+item.mainDamage,0)+mainOnlyDamage,killed:state.dead,remainingMainHP:state.mainHP,deathTriggers};
}

function simulateSequence(scene,impacts,profile,policy="primary"){
  let state=freshSplashState(scene),killedAt=null,totalDamage=0,totalMainDamage=0;const events=[],queue=[];for(const rawImpact of impacts){const impact=normalizeImpactForDelivery(rawImpact,profile,0);if(profile.sticky&&profile.delay>0){queue.push({impact:{...impact,phase:"attach"},profile:{...profile,explosions:[],shrapnel:[],mainOnly:[]}});queue.push({impact:{...impact,time:(impact.time||0)+profile.delay,phase:"detonation"},profile:{...profile,direct:[]}});}else if(profile.delivery?.kind==="ground-timed"){queue.push({impact:{...impact,time:(impact.time||0)+profile.delay,phase:"detonation",deliveryLabel:profile.delivery.label||"Timed explosive detonation"},profile:{...profile,direct:[]}});}else queue.push({impact,profile});}for(const entry of queue.sort((a,b)=>(a.impact.time||0)-(b.impact.time||0))){const result=simulateImpact(scene,entry.impact,entry.profile,policy,state);state=result.state;totalDamage+=result.totalDamage;totalMainDamage+=result.mainDamage;events.push(result);if(killedAt==null&&result.killed)killedAt=entry.impact.time||0;}return {policy,state,events,totalDamage,totalMainDamage,killed:state.dead,killedAt,remainingMainHP:state.mainHP};
}

function mulberry32(seed){let value=seed>>>0;return function(){value+=0x6D2B79F5;let result=value;result=Math.imul(result^result>>>15,result|1);result^=result+Math.imul(result^result>>>7,result|61);return ((result^result>>>14)>>>0)/4294967296;};}

function generateBarragePattern(profile,beacon={x:0,y:0,z:0},heading=0,seed=1,upgrades={}){
  const delivery=profile.delivery,random=mulberry32(seed),salvos=delivery.salvos+(upgrades.moreGuns?1:0),spread=delivery.spread*(upgrades.atmosphericMonitoring?.85:1),radiusScale=upgrades.highDensityExplosives?1.1:1,impacts=[];
  for(let salvo=0;salvo<salvos;salvo++){const walk=delivery.kind==="walking-barrage"?(delivery.salvoStep||0)*salvo:0,centerX=beacon.x+Math.sin(heading)*walk,centerZ=beacon.z+Math.cos(heading)*walk,phase=random()*Math.PI*2;for(let shell=0;shell<delivery.shellsPerSalvo;shell++){const radius=spread*Math.sqrt(.12+.88*random()),angle=phase+shell*Math.PI*2/delivery.shellsPerSalvo+(random()-.5)*.45,time=salvo*((delivery.shellsPerSalvo-1)*delivery.shellInterval+delivery.salvoInterval)+shell*delivery.shellInterval;impacts.push({id:`${salvo+1}.${shell+1}`,salvo:salvo+1,shell:shell+1,time,position:v3(centerX+Math.sin(angle)*radius,beacon.y,centerZ+Math.cos(angle)*radius),seed:seed*100+salvo*delivery.shellsPerSalvo+shell,radiusScale});}}
  return impacts;
}

function summarizeSplashResult(result){
  const destroyed=result.events?.flatMap(event=>event.zones.filter(zone=>zone.destroyed))||result.zones?.filter(zone=>zone.destroyed)||[],zones=result.events?.flatMap(event=>event.zones)||result.zones||[];
  return {outcome:result.killed?"Killed":"Survived",remainingMainHP:result.remainingMainHP,totalDamage:result.totalDamage,totalMainDamage:result.totalMainDamage??result.mainDamage,destroyedZones:[...new Set(destroyed.map(zone=>zone.label))],affectedZones:[...new Set(zones.map(zone=>zone.label))],killedAt:result.killedAt??null};
}

function explainSplashDestruction(result,scene){
  if(!result?.killed)return {destroyed:false,eventTime:null,reasons:[]};
  const contributors=new Map();let lethalEvent=null,cumulativeMainDamage=0;
  for(const event of result.events||[]){for(const zone of event.zones||[])if(zone.mainDamage>0){const current=contributors.get(zone.poolKey)||{poolKey:zone.poolKey,label:zone.label,damage:0};current.damage+=zone.mainDamage;contributors.set(zone.poolKey,current);}cumulativeMainDamage+=event.mainDamage||0;if(event.deathTriggers?.length){lethalEvent=event;break;}}
  const triggers=lethalEvent?.deathTriggers?.length?lethalEvent.deathTriggers:(result.remainingMainHP<=0?[{kind:"main-hp",mainHPBefore:scene?.mainHealth||0,mainDamage:result.totalMainDamage||0}]:[{kind:"unspecified"}]);
  const reasons=triggers.map(trigger=>trigger.kind==="fatal-zone"?{kind:trigger.kind,title:`${trigger.label} was destroyed`,detail:`This mapped damage zone is fatal when destroyed. It received ${trigger.damage} damage with ${trigger.healthBefore} HP remaining.`,evidence:trigger.partEvidence||trigger.technicalLabel||"Mapped fatal-zone flag"}:trigger.kind==="bleedout-zone"?{kind:trigger.kind,title:`${trigger.label} was destroyed`,detail:`This mapped damage zone causes a downed/bleedout state when destroyed. It received ${trigger.damage} damage with ${trigger.healthBefore} HP remaining.`,evidence:trigger.partEvidence||trigger.technicalLabel||"Mapped downed-zone flag"}:trigger.kind==="main-hp"?{kind:trigger.kind,title:"Main HP was depleted",detail:`Cumulative transferred damage reached ${cumulativeMainDamage||result.totalMainDamage||trigger.mainDamage} against ${scene?.mainHealth||trigger.mainHPBefore} Main HP.`,contributors:[...contributors.values()].sort((a,b)=>b.damage-a.damage)}:{kind:trigger.kind,title:"The simulation marked the target destroyed",detail:"The exact lethal trigger was not retained by this result."});
  return {destroyed:true,eventTime:lethalEvent?.impact?.time??result.killedAt??null,reasons};
}
// ============ END 3D SPLASH SIMULATOR ============
