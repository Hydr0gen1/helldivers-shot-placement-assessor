from __future__ import annotations

import argparse
import re
from pathlib import Path


STYLE = r"""
  :root{--bg:#0d0f12;--panel:#16191f;--panel2:#1d222b;--border:#2c333f;--yellow:#ffe10a;--text:#d8dce3;--dim:#9aa3b2;--red:#ff6b63;--green:#65ff98;--white-hit:#e8e8e8;--blue:#6fc1ff;}
  *{box-sizing:border-box;margin:0;padding:0;}
  [hidden]{display:none!important;}
  body{background:var(--bg);color:var(--text);font-family:"Segoe UI",Roboto,sans-serif;padding:24px;display:flex;justify-content:center;}
  .wrap{width:100%;max-width:760px;}
  h1{font-size:20px;letter-spacing:3px;text-transform:uppercase;color:var(--yellow);border-bottom:2px solid var(--yellow);padding-bottom:8px;margin-bottom:4px;}
  .sub{color:var(--dim);font-size:12px;margin-bottom:18px;}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:6px;padding:16px;margin-bottom:16px;}
  .row{display:grid;grid-template-columns:170px minmax(0,1fr);gap:10px;align-items:center;margin-bottom:10px;}
  .row:last-child{margin-bottom:0;}
  .row label{font-size:12px;letter-spacing:1.5px;text-transform:uppercase;color:var(--dim);}
  select,.combo-input{width:100%;min-width:0;background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:8px 10px;font:inherit;font-size:14px;}
  select:focus-visible,.combo-input:focus-visible,summary:focus-visible,a:focus-visible{outline:3px solid var(--yellow);outline-offset:2px;}
  .combo{position:relative;min-width:0;}
  .combo-input{padding-right:34px;}
  .combo::after{content:"▾";position:absolute;right:11px;top:8px;color:var(--dim);pointer-events:none;}
  .combo-list{position:absolute;z-index:20;top:calc(100% + 4px);left:0;right:0;max-height:280px;overflow:auto;background:var(--panel2);border:1px solid var(--border);border-radius:4px;box-shadow:0 12px 30px #000a;}
  .combo-list[hidden]{display:none;}
  .combo-group{padding:7px 10px 4px;color:var(--dim);font-size:10px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;}
  .combo-option{padding:8px 10px;cursor:pointer;}
  .combo-option:hover,.combo-option.active,.combo-option[aria-selected="true"]{background:#303744;color:#fff;}
  .combo-empty{padding:12px;color:var(--dim);font-size:13px;}
  .native-source[hidden]{display:none;}
  .pen{font-size:15px;font-weight:600;margin-bottom:12px;}
  .pen .full{color:var(--green)}.pen .partial{color:var(--white-hit)}.pen .none{color:var(--red)}
  .stat{display:flex;justify-content:space-between;gap:16px;padding:5px 0;border-bottom:1px dashed var(--border);font-size:14px;}
  .stat>span:last-child{font-variant-numeric:tabular-nums;color:var(--yellow);text-align:right;}
  h2{font-size:13px;letter-spacing:2px;text-transform:uppercase;color:var(--dim);margin:16px 0 8px;}
  .route{display:flex;justify-content:space-between;gap:16px;padding:7px 10px;margin-bottom:6px;background:var(--panel2);border-left:3px solid var(--border);border-radius:3px;font-size:14px;}
  .route.best{border-left-color:var(--yellow)}.route .shots{font-weight:700;color:var(--yellow);font-variant-numeric:tabular-nums;white-space:nowrap;}
  .tag{font-size:11px;color:var(--dim);margin-left:8px;font-weight:400;text-transform:none;}
  .rec{margin-top:14px;padding:10px 12px;background:#22240f;border:1px solid var(--yellow);border-radius:4px;font-size:14px;}
  .rec b{color:var(--yellow)}.rec.oneshot{background:#0f2416;border-color:var(--green)}.rec.oneshot b{color:var(--green)}
  .note{color:var(--dim);font-size:12px;margin-top:10px;line-height:1.5}.warn{color:var(--red)}
  .imgs{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap;}
  .imgs:empty{display:none;}
  .imgs figure{position:relative;background:var(--panel2);border:1px solid var(--border);border-radius:4px;padding:6px;text-align:center;flex:1 1 220px;min-height:184px;overflow:hidden;}
  .imgs img{display:block;width:100%;height:150px;object-fit:contain;}
  .imgs figcaption{font-size:10px;color:var(--dim);margin-top:4px;letter-spacing:1px;text-transform:uppercase;}
  .image-fallback{display:grid;place-items:center;height:150px;padding:12px;color:var(--dim);font-size:12px;line-height:1.4;}
  .methodology{color:var(--dim);font-size:13px;line-height:1.65;margin-top:8px;}
  .methodology summary{cursor:pointer;color:var(--text);font-size:12px;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:6px;}
  .methodology p{padding-top:6px;}a{color:var(--blue)}
  .sr-status{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;}
  @media(max-width:560px){
    body{padding:12px}.card{padding:12px}.row{grid-template-columns:1fr;gap:5px;margin-bottom:14px}.row label{font-size:11px}
    select,.combo-input{min-height:44px;font-size:16px}.combo::after{top:12px}.stat,.route{align-items:flex-start;flex-wrap:wrap}.stat>span:last-child{text-align:left}
    .tag{display:block;margin:3px 0 0}.imgs figure{flex-basis:100%}h1{font-size:17px;letter-spacing:2px}.methodology{font-size:12px}
  }
"""


BODY = r"""
<div class="wrap">
  <h1>Shot Placement Assessor</h1>
  <div class="sub">Helldivers 2 &mdash; where to aim, and how many shots it takes</div>

  <div class="card" id="controls">
    <div class="row"><label for="enemy">Select enemy</label><select id="enemy" class="native-source"></select></div>
    <div class="row"><label for="part">Select body part</label><select id="part"></select></div>
    <div class="row"><label for="weapon">Select weapon</label><select id="weapon" class="native-source"></select></div>
    <div class="row" id="modeRow" hidden><label for="mode">Firing mode</label><select id="mode"></select></div>
    <div class="row"><label for="angle">Firing angle</label><select id="angle">
      <option value="0">Direct (0&ndash;30&deg;)</option><option value="1">Slight (30&ndash;60&deg;)</option>
      <option value="2">Large (60&ndash;80&deg;)</option><option value="3">Extreme (80&deg;+)</option>
    </select></div>
    <div class="row"><label for="range">Range</label><select id="range">
      <option value="0">Point blank</option><option value="1">~25 m</option><option value="2">~50 m</option>
      <option value="3">~75 m</option><option value="4">100 m+</option>
    </select></div>
  </div>

  <div class="card" id="result">
    <div class="imgs" id="partImages" aria-label="Selected anatomy views"></div>
    <div id="calculation" aria-live="polite" aria-atomic="true"></div>
  </div>

  <details class="methodology" id="methodology">
    <summary>Methodology, sources, and assumptions</summary>
    <p>Data: <a href="https://helldivers.wiki.gg" target="_blank" rel="noopener noreferrer">helldivers.wiki.gg</a> (CC BY-NC-SA 4.0), retrieved 2026-07-06.
    Stats change with patches &mdash; edit the ENEMIES / WEAPONS objects in this file and run the image sync tool to update.
    Assumes all projectiles/pellets hit the selected part; ignores DoT effects.
    Flamethrower stream damage/ignition rate are ESTIMATES (the wiki documents 2 dmg AP4 per flame particle but not particle rate) &mdash; its real value is instant ignition + burn DoT.
    Stagger uses wiki stun-force vs enemy stagger-threshold; the Bile Titan is immune to stuns despite its listed threshold, and the Pummeler/Pacifier apply a bonus stun status not modeled here.
    Range falloff uses approximate class-based curves (the game computes it from projectile drag/velocity; exact per-weapon tables aren't published) &mdash; explosions, plasma, the Dominator, railgun and rockets don't fall off.</p>
  </details>
</div>
"""


UI = r"""
// ============ UI ============
const $ = id => document.getElementById(id);
const STORAGE_KEY = "hd2-shot-placement:v2";
const FACTION_COLORS = {Terminids:"#ffc000", Automatons:"#ff5f5f", Illuminate:"#ce6ff9"};
const comboControllers = {};

function fill(sel, items, labelFn){
  sel.replaceChildren(...items.map((it,i)=>new Option(labelFn(it), i)));
}
function fillEnemies(){
  const sel=$("enemy"), groups={};
  ENEMIES.forEach((e,i)=>{(groups[e.faction]=groups[e.faction]||[]).push([e,i]);});
  const nodes=[];
  for(const f in groups){
    const og=document.createElement("optgroup"); og.label=f;
    groups[f].forEach(([e,i])=>{const o=new Option(e.name,i);o.dataset.group=f;o.style.color=FACTION_COLORS[f]||"#fff";og.append(o);});
    nodes.push(og);
  }
  sel.replaceChildren(...nodes);
}
function weaponClass(w){
  const n=w.name;
  const X={"JAR-5 Dominator":"Special","FLAM-66 Torcher":"Special","SG-8P Punisher Plasma":"Energy-Based","CB-9 Exploding Crossbow":"Explosive","R-36 Eruptor (excl. shrapnel)":"Explosive","PLAS-15 Loyalist":"Special","P-72 Crisper (≈ per second)":"Special","SG-22 Bushwhacker (all pellets)":"Special","LAS-58 Talon":"Special","LAS-7 Dagger":"Special","GP-31 Grenade Pistol":"Special","P-33 Missile Pistol (≈)":"Special","P-35 Re-Educator (gas)":"Special","CQC-20 Breaching Hammer":"Melee"};
  if(X[n])return X[n];
  if(w.cat==="Support"){if(/^(MG|M-105|MGX)/.test(n))return "Machine Guns";if(/^(EAT|GR-8|LAS-99|MLS|RS-422|S-11|PLAS-45|MS-11|B-100)/.test(n))return "Anti-Tank";if(/^(AC-8|GL-2|B\/MD)/.test(n))return "Explosive";return "Energy / Flame / Arc";}
  if(w.cat==="Secondary")return "Pistols";if(/^(AR|StA-52|MA5C|BR-14)/.test(n))return "Assault Rifles";if(/^R-/.test(n))return "Marksman Rifles";
  if(/^(SMG|MP-98|StA-11|M7S)/.test(n))return "Submachine Guns";if(/^(SG|DBS|M90A)/.test(n))return "Shotguns";if(/^(LAS|PLAS|ARC)/.test(n))return "Energy-Based";return "Special";
}
function fillWeapons(){
  const sel=$("weapon"),nodes=[];
  for(const cat of ["Primary","Secondary","Support"]){
    const byClass={};WEAPONS.forEach((w,i)=>{if(w.cat===cat){const c=weaponClass(w);(byClass[c]=byClass[c]||[]).push([w,i]);}});
    for(const cls of Object.keys(byClass).sort()){
      const og=document.createElement("optgroup");og.label=cat+" · "+cls;
      byClass[cls].sort((a,b)=>a[0].name.localeCompare(b[0].name)).forEach(([w,i])=>{const o=new Option(w.name,i);o.dataset.group=og.label;og.append(o);});nodes.push(og);
    }
  }
  sel.replaceChildren(...nodes);
}
function fillParts(preferred){
  const e=ENEMIES[$("enemy").value];
  fill($("part"),e.parts,p=>p.name+(p.hp==="main"?"  (Main HP)":"  ("+p.hp+" HP, AV"+p.av+")"));
  selectByText($("part"),preferred);
}
function fillModes(preferred){
  const w=WEAPONS[$("weapon").value],row=$("modeRow");
  if(w.modes){fill($("mode"),w.modes,m=>m.name);selectByText($("mode"),preferred);row.hidden=false;}else{row.hidden=true;$("mode").replaceChildren();}
}
function selectByText(select,text){if(!text)return false;const o=[...select.options].find(x=>x.textContent===text);if(o){select.value=o.value;return true;}return false;}
function safeState(){try{return JSON.parse(localStorage.getItem(STORAGE_KEY)||"{}")||{};}catch{return {};}}
function saveState(){
  const state={enemy:$("enemy").selectedOptions[0]?.textContent,part:$("part").selectedOptions[0]?.textContent,weapon:$("weapon").selectedOptions[0]?.textContent,mode:$("mode").selectedOptions[0]?.textContent,angle:$("angle").value,range:$("range").value};
  try{localStorage.setItem(STORAGE_KEY,JSON.stringify(state));}catch{}
}

function enhanceSelect(select){
  const row=select.closest(".row"),label=row.querySelector("label"),combo=document.createElement("div"),input=document.createElement("input"),list=document.createElement("div"),status=document.createElement("div");
  combo.className="combo";input.className="combo-input";input.id=select.id+"Search";input.type="text";input.autocomplete="off";input.setAttribute("role","combobox");input.setAttribute("aria-autocomplete","list");input.setAttribute("aria-expanded","false");
  list.className="combo-list";list.id=select.id+"List";list.setAttribute("role","listbox");list.hidden=true;input.setAttribute("aria-controls",list.id);status.className="sr-status";status.setAttribute("aria-live","polite");
  label.htmlFor=input.id;combo.append(input,list,status);select.after(combo);select.hidden=true;
  let items=[],active=-1;
  const rebuildItems=()=>{items=[...select.options].map(o=>({value:o.value,label:o.textContent,group:o.parentElement.tagName==="OPTGROUP"?o.parentElement.label:""}));input.value=select.selectedOptions[0]?.textContent||"";};
  const close=()=>{list.hidden=true;input.setAttribute("aria-expanded","false");input.removeAttribute("aria-activedescendant");active=-1;};
  const choose=item=>{select.value=item.value;input.value=item.label;close();select.dispatchEvent(new Event("change",{bubbles:true}));};
  const draw=query=>{
    const q=query.trim().toLocaleLowerCase(),matches=items.filter(x=>x.label.toLocaleLowerCase().includes(q));list.replaceChildren();let lastGroup="";
    matches.forEach((item,i)=>{if(item.group!==lastGroup){const g=document.createElement("div");g.className="combo-group";g.textContent=item.group;list.append(g);lastGroup=item.group;}const el=document.createElement("div");el.className="combo-option";el.id=select.id+"Option"+i;el.setAttribute("role","option");el.setAttribute("aria-selected",item.value===select.value?"true":"false");el.textContent=item.label;el.addEventListener("mousedown",e=>e.preventDefault());el.addEventListener("click",()=>choose(item));el.dataset.value=item.value;list.append(el);});
    if(!matches.length){const empty=document.createElement("div");empty.className="combo-empty";empty.textContent="No matches";list.append(empty);}status.textContent=matches.length+" result"+(matches.length===1?"":"s");list.hidden=false;input.setAttribute("aria-expanded","true");active=-1;return matches;
  };
  const setActive=(matches,next)=>{const opts=[...list.querySelectorAll('[role="option"]')];if(!opts.length)return;active=(next+opts.length)%opts.length;opts.forEach((o,i)=>o.classList.toggle("active",i===active));input.setAttribute("aria-activedescendant",opts[active].id);opts[active].scrollIntoView({block:"nearest"});};
  input.addEventListener("focus",()=>draw(""));input.addEventListener("input",()=>draw(input.value));input.addEventListener("blur",()=>{setTimeout(()=>{close();input.value=select.selectedOptions[0]?.textContent||"";},100);});
  input.addEventListener("keydown",e=>{const matches=items.filter(x=>x.label.toLocaleLowerCase().includes(input.value.trim().toLocaleLowerCase()));if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();if(list.hidden)draw(input.value);setActive(matches,active+(e.key==="ArrowDown"?1:-1));}else if(e.key==="Enter"&&active>=0){e.preventDefault();choose(matches[active]);}else if(e.key==="Escape"){e.preventDefault();close();input.value=select.selectedOptions[0]?.textContent||"";}});
  const controller={sync(){rebuildItems();},input};comboControllers[select.id]=controller;rebuildItems();
}

function imageView(file){const m=/ (Front|Side|Rear|Left|Right)\.png$/i.exec(file.replace(/_/g," "));return m?m[1]:"Anatomy";}
function localImage(file){return "assets/anatomy/"+encodeURIComponent(file.replace(/\.png$/i,".webp"));}
function renderImages(){
  const enemy=ENEMIES[$("enemy").value],part=enemy.parts[$("part").value],host=$("partImages");host.replaceChildren();
  (part.img||[]).forEach((file,index)=>{const figure=document.createElement("figure"),img=document.createElement("img"),cap=document.createElement("figcaption"),fallback=document.createElement("div"),view=imageView(file);
    img.src=localImage(file);img.width=300;img.height=150;img.loading=index===0?"eager":"lazy";img.decoding="async";img.alt=enemy.name+" "+part.name+" — "+view.toLowerCase()+" view";
    cap.textContent=view;fallback.className="image-fallback";fallback.hidden=true;fallback.textContent="Anatomy image unavailable: "+view.toLowerCase()+" view";
    img.addEventListener("error",()=>{img.hidden=true;fallback.hidden=false;});figure.append(img,fallback,cap);host.append(figure);
  });
}

function renderCalculation(){
  const enemy=ENEMIES[$("enemy").value],part=enemy.parts[$("part").value],base=WEAPONS[$("weapon").value];
  const m=base.modes?base.modes[+$("mode").value||0]:null;
  const weapon=m?{...base,comps:m.comps||base.comps,rpm:m.rpm||base.rpm,mag:m.mag||base.mag}:base;
  const r=assess(enemy,part,weapon,+$("angle").value,+$("range").value);let html="";
  const penBadge=c=>c.pf===1?'<span class="full">✅ Full penetration (AP'+c.ap+' &gt; AV'+part.av+')</span>':c.pf===.65?'<span class="partial">⚪ Partial penetration, 65% (AP'+c.ap+' = AV'+part.av+')</span>':'<span class="none">❌ '+(c.explosive?'Blocked':'Ricochet')+' (AP'+c.ap+' &lt; AV'+part.av+')</span>';
  if(r.d.comps.length===1)html+='<div class="pen">Penetration: '+penBadge(r.d.comps[0])+'</div>';else{html+='<div class="pen">Penetration by component:</div>';r.d.comps.forEach(c=>{const label=c.label||(c.explosive?"Explosion"+(c.pf>0&&part.exdr?" (after "+part.exdr+"% ExDR)":""):"Direct round");html+='<div class="stat"><span>'+label+'</span><span>'+penBadge(c)+' &nbsp;'+fmt(c.dmg)+' dmg</span></div>';});}
  const force=STAGGER[base.name],req=STAGGER_REQ[enemy.name],hits=r.d.comps.some(c=>c.pf>0);let stTxt;
  if(force==null||req==null)stTxt='<span class="tag">force '+(force==null?'?':force)+' vs threshold '+(req==null?'n/a':req)+' — not documented</span>';else if(!hits)stTxt='<span class="none">No hit; no stagger</span>';else if(force>=req)stTxt='<span class="full">⚡ Staggers (force '+force+' ≥ threshold '+req+')</span>';else stTxt='<span class="partial">No flinch (force '+force+' &lt; threshold '+req+')</span>';html+='<div class="pen">Stagger: '+stTxt+'</div>';
  const fph=FIRE_PER_HIT[base.name];if(fph){const fd=FIRE_DATA[enemy.name];if(!fd)html+='<div class="pen">Incendiary: <span class="tag">fire data for this enemy not documented</span></div>';else{const mainAv=enemy.parts[0].av,burnPf=penFactor(4,mainAv),burn=Math.floor(100*fd.m*burnPf);let igTxt;if(fd.ig){const lo=Math.ceil(fd.ig[0]/fph),hi=fd.ig[1]?Math.ceil(fd.ig[1]/fph):null;igTxt=hi?(lo===hi?lo+" hits to ignite":"chance from "+lo+" hits, guaranteed at "+hi):"chance from "+lo+" hits";}else igTxt="threshold not documented";html+='<div class="pen">Incendiary: <span class="'+(burn>0?'full':'none')+'">🔥 '+(hits?igTxt:'needs a connecting hit')+(burn>0?' → ~'+burn+' burn dmg/s to main ('+fd.m+'× fire mult'+(burnPf<1?', reduced by AV'+mainAv:'')+')':' → burn blocked by AV'+mainAv+' main armor')+'</span></div>';}}
  html+='<div class="stat"><span><b>Damage/shot to part (total)</b></span><span>'+fmt(r.d.total)+'</span></div><div class="stat"><span>Damage/shot to main HP'+(part.hp!=="main"&&part.toMain?(part.cap!==0?' <span class="tag">(capped at part HP)</span>':' <span class="tag">(overkill overflows)</span>'):'')+'</span><span>'+fmt(r.toMainPerShot)+'</span></div>';if(r.info)html+='<div class="note warn">'+r.info+'</div>';
  if(!r.routes.length)html+='<h2>Kill routes</h2><div class="note warn">This weapon cannot damage this part at this angle. Aim elsewhere or bring a bigger gun.</div>';else{const killRoutes=r.routes.filter(x=>x.kills),best=killRoutes.length?killRoutes.reduce((a,b)=>a.shots<=b.shots?a:b):null;html+='<h2>Kill routes</h2>';const unit=base.beam?(n=>n+'s beam'):(n=>n+' shots');for(const rt of r.routes)html+='<div class="route'+(rt===best?' best':'')+'"><span>'+rt.label+'<span class="tag">'+rt.tag.replace("dmg/shot","dmg/"+(base.beam?"s":"shot"))+'</span></span><span class="shots">'+unit(rt.shots)+'</span></div>';if(best){const mags=best.shots/weapon.mag,ttk=base.beam?best.shots:(best.shots-1)/(weapon.rpm/60);html+='<div class="rec'+(best.shots===1?' oneshot':'')+'">Recommended: <b>'+best.label+'</b> → <b>'+unit(best.shots)+'</b>'+(best.tag.includes("BLEEDOUT")?' <span class="warn">⚠ bleedout kill — target dies over a few seconds</span>':'')+'<div class="note">≈ '+(base.beam?(mags<=1?'one heatsink ('+weapon.mag+'s of beam)':fmt(Math.ceil(mags*10)/10)+' heatsinks ('+weapon.mag+'s each)'):(mags<=1?'fits in one mag ('+weapon.mag+' rounds)':fmt(Math.ceil(mags*10)/10)+' magazines')+' · ~'+fmt(Math.max(ttk,0))+'s sustained fire at '+weapon.rpm+' rpm')+'</div></div>';}else html+='<div class="note warn">No lethal route through this part — destroying it only cripples. Check the main-HP route via another part.</div>';}
  if(enemy.note)html+='<div class="note">'+enemy.note+'</div>';$("calculation").innerHTML=html;
}

fillEnemies();fillWeapons();
const restored=safeState();selectByText($("enemy"),restored.enemy);selectByText($("weapon"),restored.weapon);fillParts(restored.part);fillModes(restored.mode);
if([...$("angle").options].some(o=>o.value===restored.angle))$("angle").value=restored.angle;if([...$("range").options].some(o=>o.value===restored.range))$("range").value=restored.range;
enhanceSelect($("enemy"));enhanceSelect($("weapon"));
$("enemy").addEventListener("change",()=>{fillParts();comboControllers.enemy.sync();renderImages();renderCalculation();saveState();});
$("weapon").addEventListener("change",()=>{fillModes();comboControllers.weapon.sync();renderCalculation();saveState();});
$("part").addEventListener("change",()=>{renderImages();renderCalculation();saveState();});
[$("mode"),$("angle"),$("range")].forEach(el=>el.addEventListener("change",()=>{renderCalculation();saveState();}));
$("methodology").open=matchMedia("(min-width: 700px)").matches;
renderImages();renderCalculation();saveState();
"""

# The expanded result-first UI lives in readable templates. The legacy inline
# constants above remain only to make older diffs/builds reproducible.
TEMPLATE_DIR = Path(__file__).parent / "templates"
STYLE = (TEMPLATE_DIR / "style.css").read_text(encoding="utf-8")
BODY = (TEMPLATE_DIR / "body.html").read_text(encoding="utf-8")
UI = (TEMPLATE_DIR / "ui.js").read_text(encoding="utf-8")


def build(source: Path, destination: Path) -> None:
    text = source.read_text(encoding="utf-8")
    script_start = text.index("<script>") + len("<script>")
    ui_start = text.index("// ============ UI ============", script_start)
    preserved = text[script_start:ui_start].rstrip()
    date_match = re.search(r"DATA \(helldivers\.wiki\.gg, (\d{4}-\d{2}-\d{2})\)", text)
    data_date = date_match.group(1) if date_match else "unknown"
    body = BODY.replace("{{DATA_DATE}}", data_date)
    ui = UI.replace("{{DATA_DATE}}", data_date)
    output = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0d0f12">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<title>HD2 Shot Placement Assessor</title>
<style>{STYLE}</style>
</head>
<body>
{body}
<script>{preserved}

{ui}
</script>
</body>
</html>
'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(output, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the improved assessor while preserving its data and calculation core.")
    parser.add_argument("source", type=Path, help="Path to the source assessor HTML")
    parser.add_argument("--output", type=Path, default=Path("index.html"))
    args = parser.parse_args()
    build(args.source.resolve(), args.output.resolve())
    print(f"Built {args.output.resolve()}")


if __name__ == "__main__":
    main()
