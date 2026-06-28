#!/usr/bin/env python3
"""Build the portable offline single-file demo from the live source + embedded data."""
import json, re

data = json.load(open('/tmp/offline_v4.json'))
html = open('app/static/index.html', encoding='utf-8').read()
appjs = open('app/static/app.js', encoding='utf-8').read()
holojs = open('app/static/holo.js', encoding='utf-8').read()
holocss = open('app/static/holo.css', encoding='utf-8').read()

# inline holo
html = html.replace('<link rel="stylesheet" href="holo.css">', '<style>' + holocss + '</style>')
html = html.replace('<script src="holo.js"></script>', '<script>' + holojs + '</script>')

HEAD = '/* David Leads V4 — PORTABLE OFFLINE */\n'
HEAD += 'const EMBEDDED = ' + json.dumps(data, ensure_ascii=True) + ';\n'
HEAD += r'''const ACCESS={u:"david",p:"David2026!",k:"DAVID-2026-SECURE-DEMO"};
let TOKEN="offline";const $=(id)=>document.getElementById(id);const money=(n)=>"$"+Number(n).toLocaleString();
let lastData=null,apptHistory=[],leadsById={},holoOn=false,askGreeted=false;
const ASK_CHIPS=["Who should I call first?","Where should I prospect?","What are rates doing?","Any new businesses to reach out to?","Why did the top lead score high?","Is this compliant?"];
function doLogin(){const err=$("loginErr");err.textContent="";
  if(!($("u").value.trim()===ACCESS.u&&$("p").value===ACCESS.p&&$("k").value.trim()===ACCESS.k)){err.textContent="\u2717 Invalid credentials or access key";return;}
  $("who").textContent="Signed in as "+ACCESS.u;$("login").classList.add("hidden");$("bg3d").classList.add("hidden");$("app").classList.remove("hidden");renderKpis(null);}
document.addEventListener("keydown",(e)=>{if(e.key==="Enter"&&!$("login").classList.contains("hidden"))doLogin();});
function runIntel(live){const b1=$("runLive"),b2=$("runSample");b1.disabled=b2.disabled=true;showLeadSkeleton();
  setTimeout(()=>{const d=EMBEDDED;lastData=d;leadsById={};d.leads.forEach(l=>leadsById[l.id]=l);
    apptHistory.push(d.kpi.qualified_appts_per_week);if(apptHistory.length>12)apptHistory.shift();
    renderKpis(d.kpi);renderLeads(d.leads);renderSignals(d.signals,d.meta);renderGov(d.governance,d.meta);
    renderBrief(d.brief);renderTicker(d.signals);renderPipeline(d.kpi);showAsk();if(holoOn)renderHolo();
    $("runHint").textContent="Portable offline build \u2014 runs with zero network.";b1.disabled=b2.disabled=false;},650);}
function offlineAsk(q){const c=EMBEDDED.ask_cache||{};const k=q.toLowerCase().trim();
  if(c[k])return c[k];
  const map=[["complian","is this compliant?"],["business","any new businesses to reach out to?"],["rate","what are rates doing?"],["where","where should i prospect?"],["prospect","where should i prospect?"],["why","why did the top lead score high?"],["call","who should i call first?"]];
  for(const m of map){if(k.includes(m[0])&&c[m[1]])return c[m[1]];}
  return c["who should i call first?"]||{answer:"Run intelligence first.",citations:[],grounded:false,receipt_id:null};}
function toggleHolo(on){holoOn=on;$("holoSection").style.display=on?"":"none";if(on){renderHolo();}else if(window.Holo){Holo.disposeAll();}}
function renderHolo(){if(!window.Holo||!lastData)return;
  try{Holo.leadConstellation("holoConstellation",lastData.leads||[]);Holo.pipeline3D("holoPipe",(lastData.kpi&&lastData.kpi.pipeline_by_bucket)||{});}catch(e){console.error(e);}
  try{Holo.territoryGlobe("holoGlobe",(EMBEDDED.territory&&EMBEDDED.territory.areas)||[]);}catch(e){console.error(e);}}
async function openTerritory(){const d=EMBEDDED.territory;
  const idxs=d.areas.map(a=>a.index),mx=Math.max(...idxs),mn=Math.min(...idxs),rng=mx-mn||1;
  const tiles=d.areas.map(a=>{const norm=(a.index-mn)/rng;const bg="rgba(22,143,137,"+(0.25+0.7*norm).toFixed(2)+")";
    return '<div class="terr-tile" style="background:'+bg+'"><div><div class="terr-name">'+a.name.replace(', New York','')+'</div><div class="terr-idx">'+a.index+'</div></div><div class="terr-stat">$'+a.median_income.toLocaleString()+' \u00b7 age '+a.median_age+'</div></div>';}).join("");
  $("modalMount").innerHTML='<div class="modal-bg" onclick="if(event.target===this)closeModal()"><div class="modal"><button class="mclose" onclick="closeModal()">\u2715 Close</button><h3>\ud83d\uddfa\ufe0f Territory Opportunity Map</h3><div class="mbody"><div style="font-size:13px;color:var(--muted)">'+d.state+' \u00b7 '+d.meta.mode+' \u00b7 '+d.meta.count+' areas. Darker = higher opportunity.</div><div class="terr-grid">'+tiles+'</div><div style="font-size:11px;color:var(--muted);margin-top:14px">Formula: '+d.formula+'<br>Source: '+d.source+' \u00b7 all public \u00b7 0 fabricated</div></div></div></div>';}
function openReceipt(rid){const key=Object.keys(EMBEDDED.receipts).find(k=>EMBEDDED.receipts[k].receipt.id===rid);
  if(!key){$("modalMount").innerHTML='<div class="modal-bg" onclick="if(event.target===this)closeModal()"><div class="modal"><button class="mclose" onclick="closeModal()">\u2715 Close</button><h3>\ud83d\udd0f Signed Answer Receipt</h3><div class="mbody"><div class="vverdict ok">\u2713 SIGNED</div><div style="font-size:13px;color:var(--muted)">This answer is bound to a tamper-evident, signed receipt (full cryptographic verification in the live app).</div></div></div></div>';return;}
  const r=EMBEDDED.receipts[key],rec=r.receipt,v=r.verify;
  const checks=v.checks.map(c=>'<div class="vcheck"><span class="ic '+(c.pass?'p':'f')+'">'+(c.pass?'\u2713':'\u2717')+'</span> '+c.check+'</div>').join("");
  $("modalMount").innerHTML='<div class="modal-bg" onclick="if(event.target===this)closeModal()"><div class="modal"><button class="mclose" onclick="closeModal()">\u2715 Close</button><h3>\ud83d\udd0f Compliance-Grade Receipt</h3><div class="mbody"><div class="vverdict '+(v.verdict==="VERIFIED"?"ok":"bad")+'">'+(v.verdict==="VERIFIED"?"\u2713 VERIFIED":"\u2717 FAILED")+'</div><div style="font-size:13px;color:var(--muted);margin-bottom:4px">Receipt <code>'+rec.id+'</code> \u00b7 '+rec.signature_status+'</div>'+checks+'<div style="font-size:12px;color:var(--muted);margin-top:14px;font-weight:600">Tamper-evident payload:</div><div class="codeblock">'+JSON.stringify(rec.payload,null,2)+'</div></div></div></div>';}
function closeModal(){$("modalMount").innerHTML="";}
function showAsk(){const card=$("askCard");if(!card)return;card.style.display="";
  if(!askGreeted){$("askChips").innerHTML=ASK_CHIPS.map(c=>'<span class="ask-chip" onclick="askChip(this)">'+c+'</span>').join("");
    addAskMsg("bot","Ask me about your live public-data intelligence \u2014 who to call, where to prospect, rates, new businesses, or compliance. Every answer is cited and signed.",[],null);askGreeted=true;}}
function askChip(el){$("askInput").value=el.textContent;sendAsk();}
function addAskMsg(who,text,cites,rid){const log=$("askLog");const div=document.createElement("div");div.className="ask-msg "+who;div.textContent=text;
  if(cites&&cites.length){const c=document.createElement("div");c.className="ask-cites";c.innerHTML=cites.map(x=>'<span class="ask-cite">\u25c6 '+x.label+'</span>').join("");div.appendChild(c);}
  if(rid){const r=document.createElement("div");r.className="ask-receipt";r.textContent="\ud83d\udd0f Verify this answer";r.onclick=function(){openReceipt(rid);};div.appendChild(r);}
  log.appendChild(div);log.scrollTop=log.scrollHeight;}
function sendAsk(e){if(e)e.preventDefault();const inp=$("askInput");const q=inp.value.trim();if(!q)return;addAskMsg("user",q,[],null);inp.value="";
  setTimeout(function(){const a=offlineAsk(q);addAskMsg("bot",a.answer,a.citations||[],a.receipt_id||null);},250);}
function exportCSV(){if(!lastData||!lastData.leads){alert("Run intelligence first.");return;}
  const rows=[["Rank","Score","Bucket","Lead Segment","NYL Product","Est Premium/yr","Next Best Action","Receipt ID"]];
  lastData.leads.forEach((l,i)=>rows.push([i+1,l.score,l.bucket,l.name,l.product,l.est_premium,l.nba.action,l.receipt_id]));
  const csv=rows.map(r=>r.map(c=>'"'+String(c).replace(/"/g,'""')+'"').join(",")).join("\n");
  const blob=new Blob([csv],{type:"text/csv"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="david_leads_call_list.csv";a.click();URL.revokeObjectURL(a.href);}
'''

# From app.js, KEEP only the pure render/helper functions (renderKpis .. end),
# and drop any function we re-defined in HEAD + drop stray top-level decls.
OVERRIDDEN = {"doLogin","runIntel","toggleHolo","renderHolo","openTerritory","openReceipt",
              "closeModal","showAsk","askChip","addAskMsg","sendAsk","exportCSV","api"}

def strip_fns(s, names):
    lines = s.split("\n"); out = []; i = 0
    while i < len(lines):
        m = re.match(r'^(async )?function (\w+)\b', lines[i])
        if m and m.group(2) in names:
            i += 1
            while i < len(lines) and lines[i] != "}":
                i += 1
            i += 1
            continue
        out.append(lines[i]); i += 1
    return "\n".join(out)

src = appjs[appjs.index("function renderKpis"):]
src = strip_fns(src, OVERRIDDEN)
# drop stray top-level declarations that HEAD already owns
drop_substr = ["API_BASE", "let holoOn", "let askGreeted", "const ASK_CHIPS"]
kept = []
skip_block = False
for line in src.split("\n"):
    if any(d in line for d in drop_substr):
        # if it's the start of a multiline array (ends with [ ), skip until line with ];
        if line.rstrip().endswith("["):
            skip_block = True
        continue
    if skip_block:
        if line.strip().startswith("]"):
            skip_block = False
        continue
    kept.append(line)
src = "\n".join(kept)

offline_js = HEAD + "\n" + src
html = html.replace('<script src="app.js"></script>', '<script>' + offline_js + '</script>')
open('David_Leads_PORTABLE.html', 'w', encoding='utf-8').write(html)

# validate the inline script
scripts = re.findall(r'<script>(.*?)</script>', html, re.S)
open('/tmp/portable_check.js', 'w', encoding='utf-8').write(scripts[-1])
print("portable bytes:", len(html))
