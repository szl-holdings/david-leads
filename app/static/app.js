/* David Leads — frontend logic */
let TOKEN = null;
const $ = (id) => document.getElementById(id);
const money = (n) => "$" + Number(n).toLocaleString();

async function api(path, opts = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  if (TOKEN) headers["Authorization"] = "Bearer " + TOKEN;
  const r = await fetch(path, Object.assign({}, opts, { headers }));
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || ("HTTP " + r.status));
  return r.json();
}

/* ---------- login ---------- */
async function doLogin() {
  const btn = $("loginBtn"); const err = $("loginErr"); err.textContent = "";
  btn.disabled = true; btn.innerHTML = '<span class="loader"></span> Verifying…';
  try {
    const res = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ username: $("u").value.trim(), password: $("p").value, access_key: $("k").value.trim() }),
    });
    TOKEN = res.token;
    $("who").textContent = "Signed in as " + res.user;
    $("login").classList.add("hidden");
    $("bg3d").classList.add("hidden");
    $("app").classList.remove("hidden");
    renderKpis(null);
  } catch (e) {
    err.textContent = "✗ " + e.message;
    btn.disabled = false; btn.innerHTML = "Access Intelligence Console";
  }
}
document.addEventListener("keydown", (e) => { if (e.key === "Enter" && !$("login").classList.contains("hidden")) doLogin(); });

/* ---------- run intelligence ---------- */
let lastData = null;
let apptHistory = [];  // in-memory session trend (sandbox blocks localStorage)
let leadsById = {};
async function runIntel(live) {
  const b1 = $("runLive"), b2 = $("runSample");
  b1.disabled = b2.disabled = true;
  const active = live ? b1 : b2;
  const orig = active.innerHTML;
  active.innerHTML = '<span class="loader"></span> ' + (live ? "Gathering live public signals…" : "Loading sample…");
  showLeadSkeleton();
  try {
    const data = await api("/api/run", { method: "POST", body: JSON.stringify({ live }) });
    lastData = data;
    leadsById = {}; data.leads.forEach(l => leadsById[l.id] = l);
    apptHistory.push(data.kpi.qualified_appts_per_week); if (apptHistory.length > 12) apptHistory.shift();
    renderKpis(data.kpi);
    renderLeads(data.leads);
    renderSignals(data.signals, data.meta);
    renderGov(data.governance, data.meta);
    renderBrief(data.brief);
    renderTicker(data.signals);
    renderPipeline(data.kpi);
    if (data.learning && $("learnBadge")) {
      $("learnBadge").textContent = "🧠 learning from " + (data.learning.total_outcomes || 0) + " logged outcomes";
      $("learnBadge").style.display = data.learning.total_outcomes ? "" : "none";
    }
    showAsk();
    if (holoOn) renderHolo();
    $("runHint").textContent = data.meta.mode === "LIVE"
      ? `Live run · ${data.meta.live_count} live source(s) · ${data.meta.total_signals} signals · ${data.meta.gathered_at.slice(11,19)} UTC`
      : "Sample (offline) run — safe to demo without network.";
  } catch (e) {
    $("leadsWrap").innerHTML = `<div style="padding:30px 18px;color:var(--hot)">✗ ${e.message}</div>`;
  } finally {
    b1.disabled = b2.disabled = false; active.innerHTML = orig;
  }
}

/* ---------- KPI cards ---------- */
function renderKpis(k) {
  const z = (v) => (k ? v : "—");
  $("kpis").innerHTML = `
    <div class="kpi accent">
      <div class="label">Qualified Appts / Week</div>
      <div class="val">${z(k && k.qualified_appts_per_week)}</div>
      <div class="sub">modeled from lead quality (HOT 70% · WARM 35%)</div>
    </div>
    <div class="kpi">
      <div class="label">HOT Leads</div>
      <div class="val">${z(k && k.hot_count)}</div>
      <div class="sub">score ≥ 80 · ready to engage now</div>
    </div>
    <div class="kpi">
      <div class="label">Pipeline Premium</div>
      <div class="val" style="font-size:27px">${k ? money(k.pipeline_premium) : "—"}</div>
      <div class="sub">illustrative — not a quoted premium</div>
    </div>
    <div class="kpi">
      <div class="label">Avg Lead Score</div>
      <div class="val">${z(k && k.avg_score)}</div>
      <div class="sub">${k ? k.total_leads + " leads scored" : "run to populate"}</div>
    </div>
    <div class="kpi">
      <div class="label">Appts/Week Trend</div>
      <div class="val" style="font-size:27px">${z(k && k.qualified_appts_per_week)}</div>
      ${k && apptHistory.length > 1 ? sparkline(apptHistory) : '<div class="sub">this device · recent runs</div>'}
    </div>`;
}

function sparkline(values, w = 130, h = 26) {
  if (!values.length) return "";
  const mn = Math.min(...values), mx = Math.max(...values), rng = mx - mn || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1 || 1)) * (w - 4) + 2;
    const y = h - 2 - ((v - mn) / rng) * (h - 6);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `<svg class="spark" width="${w}" height="${h}"><polyline points="${pts}" fill="none" stroke="#168f89" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

/* ---------- leads table ---------- */
function showLeadSkeleton() {
  let rows = "";
  for (let i = 0; i < 5; i++) rows += `<tr><td colspan="5"><div class="skeleton" style="width:${60+i*7}%"></div></td></tr>`;
  $("leadsWrap").innerHTML = `<table><tbody>${rows}</tbody></table>`;
}
function urgencyChip(u) {
  if (!u) return "";
  const map = { ACT_NOW: ["⏱ ACT NOW", "act-now"], WARM: ["WARM", "warm"], COLD: ["COLD", "cold"] };
  const m = map[u] || [u, "cold"];
  return `<span class="urg-chip ${m[1]}">${m[0]}</span>`;
}
function eventTag(l) {
  const lab = l.event_type_label || l.event_type;
  return lab ? `<span class="evt-tag">${lab}</span>` : "";
}
function wealthTag(l) {
  const w = l.wealth_tier && l.wealth_tier.tier;
  return w ? `<span class="wealth-tag t-${w.replace(/[^a-z]/gi,'').toLowerCase()}" title="based on public records">${w}</span>` : "";
}
function lapseBadge(l) {
  if (!l.lapse || l.lapse.decile == null) return "";
  const d = l.lapse.decile;
  const cls = d <= 3 ? "low" : d <= 6 ? "mid" : "high";
  return `<span class="lapse-badge ${cls}" title="${(l.lapse.note||'').replace(/"/g,'&quot;')}">Lapse ${d}/10</span>`;
}
/* V8.2 P1-D behavioral receptivity meter */
function receptMeter(l) {
  if (l.receptivity == null) return "";
  const v = Math.round(l.receptivity);
  const tip = ((l.receptivity_detail||{}).interpretation || "behavioral receptivity (advisory)").replace(/"/g,'&quot;');
  return `<span class="recept-meter" title="${tip}"><span class="recept-lbl">Receptivity</span>` +
    `<span class="recept-track"><span class="recept-fill" style="width:${Math.max(0,Math.min(100,v))}%"></span></span>` +
    `<span class="recept-val">${v}</span></span>`;
}
/* V8.2 P1-E likely coverage-gap chip */
function gapChip(l) {
  const g = l.likely_gap; if (!g || !g.label) return "";
  const covered = g.has_gap === false;
  return `<span class="gap-chip ${covered?'covered':''}" title="${(g.recommended||'').replace(/"/g,'&quot;')}">${covered?'✓ ':'◆ '}${g.label}</span>`;
}
/* V8.2 P1-A SEC Form 4 insider-sell liquidity flag */
function liqFlag(l) {
  const q = l.liquidity; if (!q) return "";
  if (q.mode === "LIVE" && q.recent_sells) {
    return `<span class="liq-flag live" title="${(q.note||'').replace(/"/g,'&quot;')}">💧 Liquidity: ${q.recent_sells} Form-4 sell(s)</span>`;
  }
  return `<span class="liq-flag" title="${(q.note||'Public SEC filing — example').replace(/"/g,'&quot;')}">💧 Liquidity ${q.mode==='SAMPLE'?'(example)':'watch'}</span>`;
}
/* V8.3 P2-3 wealth ladder (4 segments, lead's tier highlighted) */
function wealthLadder(wt, compact) {
  if (!wt || !wt.tier) return "";
  const ladder = wt.ladder && wt.ladder.length ? wt.ladder : ["Mass","Mass-Affluent","Affluent","HNW"];
  const idx = (wt.ladder_index != null) ? wt.ladder_index : ladder.indexOf(wt.tier);
  const segs = ladder.map((t, i) =>
    `<span class="wseg ${i===idx?'on':''}" title="${t}${i===idx?' — '+(wt.basis||'based on public records'):''}">${t}</span>`).join("");
  if (compact) return `<div class="wladder compact" title="Wealth tier: ${wt.tier} (based on public records)">${segs}</div>`;
  const chips = (wt.signals||[]).map(s =>
    `<span class="proxy-chip">${s} <span class="est">· based on public records</span></span>`).join("");
  return `<div class="wladder-wrap"><div class="wladder-cap">Wealth ladder · <strong>${wt.tier}</strong>${wt.score!=null?` · score ${wt.score}/100`:''}</div>` +
    `<div class="wladder">${segs}</div>${chips?`<div class="proxy-chips">${chips}</div>`:''}</div>`;
}
/* V8.3 P2-2 Liquidity Watch subsection (SEC Form 4) */
function liqWatch(q) {
  if (!q) return "";
  const mode = q.mode === "LIVE" ? "live" : q.mode === "SAMPLE" ? "sample" : "";
  const emp = q.employer ? `${q.employer}${q.employer_illustrative?' <span class="est" style="color:var(--gold);font-weight:700">[illustrative public employer]</span>':''}` : "—";
  return `<div class="liqwatch">
    <div class="lw-h">💧 Liquidity Watch — SEC Form 4 insider sells
      <span class="lw-mode ${mode}">${q.mode||'—'}</span></div>
    <div class="lw-grid">
      <div>Employer<b>${emp}</b></div>
      <div>Recent sells<b>${q.recent_sells!=null?q.recent_sells:'—'}</b></div>
      <div>Latest filing<b>${q.latest_date||'—'}</b></div>
      ${q.citation_url?`<div>SEC citation<b style="font-size:12px"><a href="${q.citation_url}" target="_blank" rel="noopener">EDGAR Form 4 ↗</a></b></div>`:''}
    </div>
    <div class="lw-foot">${q.note||'Employer-level public signal, not an individual assertion. [SAMPLE] if SEC unreachable.'}</div>
  </div>`;
}
/* Momentum chip — how interest is trending across public signals */
function trendChip(l) {
  const t = l.track; if (!t || !t.trend || t.trend === "none") return "";
  const pct = Math.round((t.intensity != null ? t.intensity : 0) * 100);
  const map = { heating: ["↑ Heating up", "heating"], cooling: ["↓ Cooling off", "cooling"], steady: ["→ Steady", "steady"] };
  const m = map[t.trend] || ["→ Steady", "steady"];
  const tip = ("Momentum — how this prospect's interest is trending across recent public signals.").replace(/"/g,'&quot;');
  return `<span class="trend-chip ${m[1]}" title="${tip}">${m[0]} · ${pct}% interest</span>`;
}
/* Plain-English match + confidence line (no jargon; honesty carried in words) */
function confidenceLine(l) {
  const c = l.confidence; if (!c) return "";
  const n = c.n_sources || 1;
  const word = c.level || "Building";
  const src = "confirmed across " + n + " public record" + (n === 1 ? "" : "s");
  const range = (c.lo != null && c.hi != null) ? ` <span class="conf-range">(range ${c.lo}–${c.hi})</span>` : "";
  return `<div class="conf-line" title="Confidence reflects how many public records confirm this lead — more records, higher confidence.">` +
    `Match ${c.point} · Confidence: ${word} · ${src}${range}</div>`;
}
/* Cannot-contact badge — compliance removed this lead from outreach */
function blockedBadge(l) {
  if (!l.compliance || l.compliance.clear !== false) return "";
  const reasons = (l.compliance.reasons || []).map(plainBlockReason);
  const tip = reasons.join(" · ").replace(/"/g,'&quot;');
  const why = reasons[0] || "Cannot be contacted";
  return `<span class="blocked-badge" title="${tip}">🚫 Cannot contact — ${why}</span>`;
}
/* Map raw compliance reason codes/text to plain English */
function plainBlockReason(r) {
  const s = String(r || "").toLowerCase();
  if (s.includes("dnc") || s.includes("do-not-call") || s.includes("do not call")) return "On the Do-Not-Call list";
  if (s.includes("decea") || s.includes("death")) return "Records show deceased";
  if (s.includes("opt") || s.includes("unsub") || s.includes("request")) return "Asked not to be contacted";
  return "Cannot be contacted";
}
function renderLeads(leads) {
  $("leadMeta").textContent = leads.length + " scored";
  let rows = leads.map(l => {
    const blocked = l.compliance && l.compliance.clear === false;
    const scoreCell = blocked
      ? `<span class="score-pill blocked"><s>${l.score_pre_gate!=null?l.score_pre_gate:''}</s> 0</span><br><span class="badge BLOCKED">Removed</span>`
      : `<span class="score-pill" style="color:${l.bucket==='HOT'?'var(--hot)':l.bucket==='WARM'?'#9a6c14':'var(--nurture)'}">${l.score}</span><br><span class="badge ${l.bucket}">${l.bucket}</span>`;
    return `
    <tr class="lead-row${blocked?' blocked-row':''}" id="row-${l.id}">
      <td><span class="expander" onclick="toggleLeadDetail('${l.id}')">▸</span></td>
      <td>${scoreCell}</td>
      <td>
        <div class="lead-name" onclick="toggleLeadDetail('${l.id}')" style="cursor:pointer">${l.name}${l.fresh?' <span class="fresh-tag">⚡ FRESH</span>':''}</div>
        <div class="lead-chips">${blockedBadge(l)}${trendChip(l)}${urgencyChip(l.urgency)}${eventTag(l)}${wealthTag(l)}${lapseBadge(l)}${gapChip(l)}${liqFlag(l)}</div>
        ${confidenceLine(l)}
        ${l.demo_note?`<div class="demo-note">${l.demo_note}</div>`:''}
        ${wealthLadder(l.wealth_tier, true)}
        ${receptMeter(l)}
        <div class="lead-why">${l.why}</div>
      </td>
      <td><div class="prod">${l.product}</div><div class="prem" title="Illustrative — not a quoted premium">~${money(l.est_premium)}/yr (illustrative)</div></td>
      <td>
        <button class="verify-btn" onclick="openReceipt('${l.receipt_id}','${l.id}')">🔒 Proof &amp; Sources</button>
        <button class="verify-btn" style="margin-top:6px" onclick="openBrief('${l.id}')">📜 Call Brief</button>
        <div class="outcome-row">
          <button class="oc-btn sold" onclick="logOutcome('${l.id}','sold',this)">Sold</button>
          <button class="oc-btn meet" onclick="logOutcome('${l.id}','meeting',this)">Meeting</button>
          <button class="oc-btn no" onclick="logOutcome('${l.id}','no',this)">No</button>
        </div>
      </td>
    </tr>
    <tr class="detail-row" id="detail-${l.id}" style="display:none"><td colspan="5"></td></tr>`;
  }).join("");
  $("leadsWrap").innerHTML = `<table>
    <thead><tr><th></th><th>Match</th><th>Lead Segment · Why</th><th>NYL Product Match</th><th>Proof · Outcome</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

/* ---------- P0-6 adaptive conversion loop ---------- */
async function logOutcome(leadId, outcome, btn) {
  const row = btn ? btn.parentElement : null;
  if (row) row.querySelectorAll("button").forEach(b => b.disabled = true);
  try {
    const r = await api("/api/outcome", { method: "POST", body: JSON.stringify({ lead_id: leadId, outcome }) });
    if (btn) { btn.classList.add("logged"); btn.textContent = "✓ " + btn.textContent.replace("✓ ", ""); }
    $("learnBadge").textContent = "🧠 " + r.message;
    $("learnBadge").style.display = "";
  } catch (e) {
    if (row) row.querySelectorAll("button").forEach(b => b.disabled = false);
    $("learnBadge").textContent = "✗ " + e.message;
    $("learnBadge").style.display = "";
  }
}

function toggleLeadDetail(id, forceOpen) {
  const row = $("row-" + id), det = $("detail-" + id);
  if (!row || !det) return;
  const open = det.style.display !== "none";
  if (open && !forceOpen) { det.style.display = "none"; row.classList.remove("open"); return; }
  det.querySelector("td").innerHTML = renderLeadDetail(leadsById[id]);
  det.style.display = ""; row.classList.add("open");
}

function renderLeadDetail(l) {
  const axisLabels = {life_event_strength:"Life-event strength", income_fit:"Income fit",
    age_window_fit:"Age-window fit", product_propensity:"Product propensity", recency:"Recency"};
  const axes = Object.keys(axisLabels).map(k => {
    const v = Math.round((l.axes[k]||0)*100);
    return `<div class="axis-row"><span class="axis-lbl">${axisLabels[k]}</span><div class="axis-track"><div class="axis-fill" style="width:${v}%"></div></div><span class="axis-val">${v}</span></div>`;
  }).join("");
  const moments = (l.moments||[]).map(m =>
    `<div class="moment"><span class="mdot"></span><div><span class="msrc">${m.source}</span> — ${m.label}</div></div>`).join("");
  const wt = l.wealth_tier || {}, lp = l.lapse || {};
  const lfac = (lp.factors||[]).map(s => `<li>${s}</li>`).join("");
  const adv = `<div class="detail-sec"><h4>Advisory tiers (based on public records)</h4>
    <div class="adv-box" style="margin-bottom:10px"><div class="adv-h">Wealth tier</div>${wealthLadder(wt, false)}</div>
    <div class="adv-grid">
      <div class="adv-box"><div class="adv-h">Lapse decile</div><div class="adv-v">${lp.decile!=null?lp.decile+'/10':'—'}</div>
        <div class="adv-note">${lp.interpretation||''} · advisory, NOT FCRA</div><ul class="adv-list">${lfac}</ul></div>
    </div>
    <div class="adv-foot">Event type: <strong>${l.event_type_label||l.event_type||'—'}</strong> · Urgency: <strong>${l.urgency||'—'}</strong> · observed ${l.hours_since!=null?l.hours_since+'h ago':'—'}</div>
  </div>`;
  const rd = l.receptivity_detail || {};
  const g = l.likely_gap || {};
  const q = l.liquidity || null;
  const p1 = `<div class="detail-sec"><h4>P1 advisory signals (public-data, honest)</h4>
    <div class="adv-grid">
      <div class="adv-box"><div class="adv-h">Behavioral receptivity</div><div class="adv-v">${l.receptivity!=null?Math.round(l.receptivity):'—'}</div>
        <div class="adv-note">${rd.interpretation||'advisory'} · ${rd.citation ? `<a href="${rd.citation.url}" target="_blank" rel="noopener">${rd.citation.source||'RGA'}</a>` : 'RGA predictive-moments'} (advisory)</div></div>
      <div class="adv-box"><div class="adv-h">Likely coverage gap</div><div class="adv-v" style="font-size:14px">${g.label||'—'}</div>
        <div class="adv-note">${g.recommended? 'Lead with: '+g.recommended : ''}${g.basis? ' · '+g.basis : ''}</div></div>
    </div>
    ${liqWatch(q)}
  </div>`;
  return `<div class="detail-inner">
    <div class="detail-sec"><h4>Why this lead (transparent score)</h4>${axes}</div>
    ${adv}
    ${p1}
    <div class="detail-sec"><h4>Predictive moments · public sources</h4>${moments}</div>
    <div class="nba-box"><div class="act">▶ Next best action: ${l.nba.action}</div><div class="tt">“${l.nba.talk_track}”</div></div>
  </div>`;
}

/* ---------- signals ---------- */
function renderSignals(sigs, meta) {
  $("sigMeta").textContent = (meta.fresh_daily ? meta.fresh_daily + " daily · " : "") + meta.mode;
  // freshest first: daily/real-time signals float to the top
  const rank = { "real-time": 0, "updated daily": 1, "updated weekly": 2, "updated monthly": 3, "updated annually": 4 };
  const sorted = [...sigs].sort((a, b) => (rank[a.freshness] ?? 9) - (rank[b.freshness] ?? 9));
  $("signals").innerHTML = sorted.map(s => {
    const fresh = s.freshness ? `<span class="fresh-badge ${s.freshness === 'updated daily' || s.freshness === 'real-time' ? 'hot' : ''}">${s.freshness}</span>` : "";
    return `
    <div class="sig">
      <span class="src">${s.source.replace(/\[SAMPLE\]/,'')}</span>${s.live?'<span class="live">LIVE</span>':'<span class="live smp">PUBLIC</span>'}${fresh}
      <div class="txt">${s.signal}</div>
      <div class="det">${s.detail||''}</div>
    </div>`; }).join("");
}

/* ---------- governance ---------- */
function renderGov(g, meta) {
  let checksWord = "";
  if (g.consensus) {
    const m = String(g.consensus).match(/(\d+)/);
    if (m) checksWord = `Independently double-checked — ${m[1]} separate verifications agree`;
  }
  $("gov").innerHTML = `
    <div class="gov-inner">
      <div class="line"><span class="ok">✓</span> Every lead checked against ${g.signals_checked} public records</div>
      <div class="line"><span class="ok">${g.all_public?'✓':'✗'}</span> 100% public data — nothing private, nothing invented</div>
      <div class="line"><span class="ok">✓</span> ${g.rejected_nonpublic} non-public items rejected</div>
      ${checksWord ? `<div class="line"><span class="ok">✓</span> <strong style="margin-left:0">${checksWord}</strong></div>` : ''}
      <div class="verdict">🛡️ ${g.verdict}</div>
    </div>`;
}

/* ---------- Ask the Territory ---------- */
const ASK_CHIPS = [
  "Who should I call first?", "Show me the affluent / estate prospects", "Expand to other East Coast states",
  "Any new graduates to target?", "Any fresh home buyers today?", "Is this compliant?"
];
let askGreeted = false;
function showAsk() {
  const card = $("askCard"); if (!card) return;
  card.style.display = "";
  if (!askGreeted) {
    $("askChips").innerHTML = ASK_CHIPS.map(c => `<span class="ask-chip" onclick="askChip(this)">${c}</span>`).join("");
    addAskMsg("bot", "Ask me anything about your live public-data intelligence — who to call, where to prospect, rates, new businesses, or compliance. Every answer is cited and signed.", [], null);
    askGreeted = true;
  }
}
function askChip(el) { $("askInput").value = el.textContent; sendAsk(); }
function addAskMsg(who, text, cites, receiptId) {
  const log = $("askLog");
  const div = document.createElement("div");
  div.className = "ask-msg " + who;
  div.textContent = text;
  if (cites && cites.length) {
    const c = document.createElement("div"); c.className = "ask-cites";
    c.innerHTML = cites.map(x => `<span class="ask-cite">\u25c6 ${x.label}</span>`).join("");
    div.appendChild(c);
  }
  if (receiptId) {
    const r = document.createElement("div"); r.className = "ask-receipt";
    r.textContent = "\ud83d\udd0f Verify this answer";
    r.onclick = () => openReceipt(receiptId);
    div.appendChild(r);
  }
  log.appendChild(div); log.scrollTop = log.scrollHeight;
}
async function sendAsk(e) {
  if (e) e.preventDefault();
  const inp = $("askInput"); const q = inp.value.trim(); if (!q) return;
  addAskMsg("user", q, [], null); inp.value = "";
  const btn = $("askSend"); btn.disabled = true; btn.innerHTML = '<span class="loader"></span>';
  try {
    const r = await api("/api/ask", { method: "POST", body: JSON.stringify({ question: q }) });
    addAskMsg("bot", r.answer, r.citations, r.receipt_id);
  } catch (err) {
    addAskMsg("bot", "\u2717 " + err.message, [], null);
  } finally {
    btn.disabled = false; btn.textContent = "Ask";
  }
}

/* ---------- holographic mode ---------- */
let holoOn = false;
function toggleHolo(on) {
  holoOn = on;
  document.getElementById("holoSection").style.display = on ? "" : "none";
  if (on) {
    renderHolo();
  } else if (window.Holo) {
    Holo.disposeAll();
  }
}
function renderHolo() {
  if (!window.Holo || !lastData) return;
  try {
    Holo.leadConstellation("holoConstellation", lastData.leads || []);
    Holo.pipeline3D("holoPipe", (lastData.kpi && lastData.kpi.pipeline_by_bucket) || {});
  } catch (e) { console.error("holo lead/pipe", e); }
  // territory needs its own fetch (areas live in /api/territory)
  api("/api/territory").then(d => {
    try { Holo.territoryGlobe("holoGlobe", d.areas || []); } catch (e) { console.error("holo globe", e); }
  }).catch(() => {});
}

/* ---------- morning brief ---------- */
function renderBrief(brief) {
  if (!brief || !brief.items || !brief.items.length) return;
  const cards = brief.items.map((it, i) => `
    <div class="brief-card" onclick="focusLead('${it.id}')">
      <span class="brief-score">${it.score}</span>
      <div class="brief-rank">#${i+1} · ${it.bucket}</div>
      <div class="brief-name">${it.name}</div>
      <div class="brief-act">${it.action}</div>
    </div>`).join("");
  $("briefBar").innerHTML = `
    <div class="brief-head"><span class="pulse"></span> Morning Brief — ${brief.headline}</div>
    <div class="brief-items">${cards}</div>`;
  $("briefBar").classList.add("show");
}
function focusLead(id) {
  const row = $("row-" + id);
  if (row) { row.scrollIntoView({ behavior: "smooth", block: "center" }); toggleLeadDetail(id, true); }
}

/* ---------- intelligence ticker ---------- */
function renderTicker(sigs) {
  if (!sigs || !sigs.length) return;
  const ticks = sigs.map(s => `<span class="tick"><b>${s.source.replace(/\[SAMPLE\]/,'').trim()}</b> · ${(s.detail||s.signal).slice(0,70)}</span>`);
  const track = ticks.join('<span class="tick-sep">◆</span>');
  $("tickerBar").innerHTML = `<div class="ticker-track">${track}<span class="tick-sep">◆</span>${track}</div>`;
  $("tickerBar").classList.add("show");
}

/* ---------- premium pipeline ---------- */
function renderPipeline(kpi) {
  if (!kpi || !kpi.pipeline_by_bucket) return;
  const bb = kpi.pipeline_by_bucket, total = kpi.pipeline_premium || 1;
  $("pipeTotal").textContent = money(total) + " total";
  $("pipeBody").innerHTML = ["HOT","WARM","NURTURE"].map(b => {
    const v = bb[b]||0, pct = Math.round(v/total*100);
    return `<div class="pipe-row"><span class="pipe-lbl">${b}</span><div class="pipe-track"><div class="pipe-fill ${b}" style="width:${pct}%"></div></div><span class="pipe-val">${money(v)}</span></div>`;
  }).join("");
  $("pipelineCard").style.display = "";
}

/* ---------- How scoring works (plain-English methodology) ---------- */
const AXIS_PLAIN = {
  life_event_strength: "Life event strength", income_fit: "Income fit",
  age_window_fit: "Age fit", product_propensity: "Product fit", recency: "Freshness",
};
async function openModel() {
  $("modalMount").innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()"><div class="modal">
    <button class="mclose" onclick="closeModal()">✕ Close</button>
    <h3>🔓 How scoring works</h3>
    <div class="mbody" id="modelBody"><div class="skeleton" style="width:80%;margin:10px 0"></div><div class="skeleton" style="width:60%"></div></div></div></div>`;
  try {
    const m = await api("/api/model");
    const axes = (m.axes || []).map(a => `
      <div style="padding:10px 0;border-top:1px solid var(--line)">
        <strong style="color:var(--navy)">${AXIS_PLAIN[a.key] || a.key.replace(/_/g,' ')}</strong>
        <div style="font-size:13px;color:var(--ink);margin-top:3px">${a.meaning}</div>
        <div style="font-size:11.5px;color:var(--muted);margin-top:2px">Built from: ${a.sources}</div>
      </div>`).join("");
    $("modelBody").innerHTML = `
      <div style="background:#e6f7f6;border:1px solid #bfeae8;border-radius:10px;padding:12px 14px;font-size:13px;color:#0b5957;margin-bottom:14px">
        Every lead is rated on five plain factors. A lead only scores high when it does well across
        all five — one weak factor holds the whole score back, so the strongest leads rise to the top.</div>
      <div style="font-size:12px;color:var(--muted);font-weight:600;margin-top:6px">The five factors — and the public records behind each:</div>
      ${axes}
      <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap">
        <span class="badge HOT">${(m.buckets&&m.buckets.HOT)||"Hot"}</span>
        <span class="badge WARM">${(m.buckets&&m.buckets.WARM)||"Warm"}</span>
        <span class="badge NURTURE">${(m.buckets&&m.buckets.NURTURE)||"Nurture"}</span>
      </div>
      <div style="font-size:12.5px;color:var(--navy);font-weight:600;margin-top:14px;background:#fbf7ec;border-left:3px solid var(--gold);padding:10px 12px;border-radius:6px">
        Public records only — SEC filings, U.S. Census, labor statistics, public health data, and county
        records. Nothing private is used and nothing is invented. Each lead also shows a confidence level
        based on how many public records confirm it, and anyone who can't be contacted is removed.</div>
      <div style="font-size:11px;color:var(--muted);margin-top:10px;text-align:center">Honest by design · open methodology · every lead carries a proof trail you can open and check.</div>`;
  } catch (e) {
    $("modelBody").innerHTML = `<div style="color:var(--hot)">✗ ${e.message}</div>`;
  }
}

/* ---------- territory map ---------- */
async function openTerritory() {
  $("modalMount").innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()"><div class="modal">
    <button class="mclose" onclick="closeModal()">✕ Close</button>
    <h3>🗺️ Territory Opportunity Map</h3>
    <div class="mbody" id="terrBody"><div class="skeleton" style="width:80%;margin:10px 0"></div><div class="skeleton" style="width:60%"></div></div></div></div>`;
  try {
    const d = await api("/api/territory");
    const idxs = d.areas.map(a => a.index), mx = Math.max(...idxs), mn = Math.min(...idxs), rng = mx-mn||1;
    const tiles = d.areas.map(a => {
      const norm = (a.index - mn) / rng;
      const bg = `rgba(22,143,137,${(0.25 + 0.7*norm).toFixed(2)})`;
      return `<div class="terr-tile" style="background:${bg}">
        <div><div class="terr-name">${a.name.replace(', New York','')}</div><div class="terr-idx">${a.index}</div></div>
        <div class="terr-stat">$${a.median_income.toLocaleString()} · age ${a.median_age}</div></div>`;
    }).join("");
    $("terrBody").innerHTML = `
      <div style="font-size:13px;color:var(--muted)">${d.state} · ${d.meta.mode} · ${d.meta.count} areas. Darker = higher opportunity.</div>
      <div class="terr-grid">${tiles}</div>
      <div style="font-size:11px;color:var(--muted);margin-top:14px">Ranked by opportunity from income and age in each area.<br>Source: ${d.source} · all public · nothing invented</div>`;
  } catch (e) {
    $("terrBody").innerHTML = `<div style="color:var(--hot)">✗ ${e.message}</div>`;
  }
}

/* ---------- export call list (CSV from the signed backend endpoint) ---------- */
async function exportCSV() {
  if (!lastData || !lastData.leads) { alert("Run intelligence first."); return; }
  const btn = $("btnCsv"); const orig = btn ? btn.innerHTML : "";
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="loader"></span> Exporting…'; }
  try {
    const r = await fetch("/api/export.csv", { headers: { "Authorization": "Bearer " + TOKEN } });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const csv = await r.text();
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "david-leads-export.csv"; a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) {
    alert("Export failed: " + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = orig; }
  }
}

/* ---------- V8.2 P1-F Producer Benchmark (conversion funnel) ---------- */
async function openBenchmark() {
  const card = $("benchCard"); if (!card) return;
  card.classList.add("show");
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  $("benchBody").innerHTML = `<div style="padding:20px;color:var(--muted)">Loading funnel…</div>`;
  try {
    const d = await api("/api/benchmark");
    const s = d.summary || {};
    $("benchMeta").textContent = `${s.outcomes_logged||0} outcomes · ${s.durable_outcome_receipts||0} durable receipt(s)`;
    const stat = (h, v) => `<div class="bench-stat"><div class="bh">${h}</div><div class="bv">${v}</div></div>`;
    const summary = `<div class="bench-summary">
      ${stat("Leads surfaced", s.leads_surfaced ?? 0)}
      ${stat("Outcomes logged", s.outcomes_logged ?? 0)}
      ${stat("Meetings", s.meeting ?? 0)}
      ${stat("Sold", s.sold ?? 0)}
      ${stat("Conversion", (s.overall_conversion_rate_pct ?? 0) + "%")}
    </div>`;
    const rows = (d.by_event_type || []).map(e => {
      const pct = e.conversion_rate_pct || 0;
      return `<tr><td>${e.event_type}</td><td>${e.surfaced}</td><td>${e.meeting}</td><td>${e.sold}</td><td>${e.no}</td>
        <td><div style="display:flex;align-items:center;gap:8px"><div class="bench-bar"><i style="width:${Math.min(100,pct)}%"></i></div><span style="font-weight:600">${pct}%</span></div></td></tr>`;
    }).join("") || `<tr><td colspan="6" style="color:var(--muted)">No outcomes logged yet — log Sold/Meeting/No on leads to build the funnel.</td></tr>`;
    $("benchBody").innerHTML = summary +
      `<table class="bench-table"><thead><tr><th>Event type</th><th>Surfaced</th><th>Meeting</th><th>Sold</th><th>No</th><th>Conversion</th></tr></thead><tbody>${rows}</tbody></table>` +
      `<div class="bench-note">${d.honest_note || ''}</div>`;
  } catch (e) {
    $("benchBody").innerHTML = `<div style="padding:20px;color:var(--hot)">✗ ${e.message}</div>`;
  }
}

/* ---------- V8.3 P2-1 Lead Routing (best-fit advisor) ---------- */
async function openRouting() {
  const card = $("routingCard"); if (!card) return;
  card.classList.add("show");
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  $("routingBody").innerHTML = `<div style="padding:20px;color:var(--muted)">Loading routing table…</div>`;
  try {
    const d = await api("/api/routing");
    const roster = (d.roster || []).map(a =>
      `<span class="route-agent ${a.real?'real':''}">${a.name}${a.real?' <span style="color:#0b5957">✓ real</span>':` <span class="illus">${a.label||'[illustrative roster]'}</span>`}${(a.states&&a.states.length)?` · ${a.states.join('/')}`:''}</span>`).join("");
    const rows = (d.routing || []).map(r => {
      const tag = r.recommended_is_real ? `<span class="realtag">✓ real</span>` : `<span class="illus">[illustrative]</span>`;
      const alts = (r.alternatives||[]).slice(0,2).map(a => `${a.agent} (${a.score})`).join(" · ");
      return `<tr>
        <td><div style="font-weight:600;color:var(--navy)">${r.lead_name||r.lead_id||''}</div>
          <div class="route-basis">${r.event_type||''} · ${r.state||''}</div></td>
        <td><span class="route-rec">${r.recommended_agent}</span>${tag}
          <div class="route-basis">${r.basis||''}</div>
          ${alts?`<div class="route-basis">alt: ${alts}</div>`:''}</td>
        <td><span class="route-score">${r.score}</span></td>
      </tr>`;
    }).join("") || `<tr><td colspan="3" style="color:var(--muted)">No leads to route — run intelligence first.</td></tr>`;
    const f = d.factors || {};
    $("routingMeta").textContent = (d.routing||[]).length + " leads routed";
    $("routingBody").innerHTML =
      `<div class="route-roster">${roster}</div>` +
      `<table class="route-table"><thead><tr><th>Lead</th><th>Recommended advisor · basis</th><th>Fit</th></tr></thead><tbody>${rows}</tbody></table>` +
      `<div class="route-note">Factors — specialty ${Math.round((f.specialty||0)*100)}% · territory ${Math.round((f.territory||0)*100)}% · history ${Math.round((f.history||0)*100)}%. ${d.honest_note||''}</div>`;
  } catch (e) {
    $("routingBody").innerHTML = `<div style="padding:20px;color:var(--hot)">✗ ${e.message}</div>`;
  }
}

/* ---------- V8.2 P1-G Push to CRM (webhook test) ---------- */
async function pushToCRM() {
  if (!lastData || !lastData.leads) { alert("Run intelligence first."); return; }
  const url = (prompt("CRM webhook URL (leave blank to preview the would-send payload):", "") || "").trim();
  $("modalMount").innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()"><div class="modal">
    <button class="mclose" onclick="closeModal()">✕ Close</button>
    <h3>🔗 Push to CRM — Webhook Test</h3>
    <div class="mbody" id="crmBody"><div class="skeleton" style="width:80%;margin:10px 0"></div><div class="skeleton" style="width:60%"></div></div></div></div>`;
  try {
    const r = await api("/api/webhook/test", { method: "POST", body: JSON.stringify(url ? { url } : {}) });
    const head = r.sent
      ? `<div class="vverdict ok">✓ SENT · HTTP ${r.status}</div><div style="font-size:13px;color:var(--muted)">Delivered ${r.count} lead(s) to <code>${r.url}</code></div>`
      : `<div class="vverdict ${url?'bad':'ok'}">${url ? '✗ NOT SENT' : '◆ PREVIEW (no URL)'}</div><div style="font-size:13px;color:var(--muted)">${r.reason||''}. Honest: showing the exact would-send payload — never a faked send.</div>`;
    const payload = r.would_send || { sent: true, status: r.status, response_snippet: r.response_snippet };
    $("crmBody").innerHTML = head +
      `<div style="font-size:12px;color:var(--muted);margin-top:12px;font-weight:600">Payload:</div>` +
      `<div class="codeblock">${JSON.stringify(payload, null, 2)}</div>`;
  } catch (e) {
    $("crmBody").innerHTML = `<div style="color:var(--hot)">✗ ${e.message}</div>`;
  }
}

/* ---------- V8 Territory Pulse (seaboard coverage map) ---------- */
let pulseRegion = "ALL";
function openPulse() {
  $("pulseCard").classList.add("show");
  $("pulseCard").scrollIntoView({ behavior: "smooth", block: "start" });
  loadPulse();
}
function selRegion(r) {
  pulseRegion = r;
  document.querySelectorAll("#regionSeg button").forEach(b =>
    b.classList.toggle("active", b.dataset.region === r));
  loadPulse();
}
async function loadPulse() {
  const live = $("pulseLive").checked;
  const grid = $("pulseGrid");
  grid.innerHTML = `<div style="padding:20px;color:var(--muted)">${live ? "Probing each portal LIVE…" : "Loading seaboard…"}</div>`;
  $("pulseHint").textContent = live ? "Live: real recent counts where a portal answers; failed probes shown [SAMPLE]." : "Static richness ranking · tick Live to probe each portal.";
  try {
    const q = new URLSearchParams();
    if (pulseRegion !== "ALL") q.set("region", pulseRegion);
    if (live) q.set("live", "true");
    const d = await api("/api/pulse?" + q.toString());
    const tiles = d.seaboard.map(s => {
      const badges = [];
      if (s.confirmed) badges.push(`<span class="pt-badge">VERIFIED</span>`);
      if (s.mode === "LIVE") badges.push(`<span class="pt-badge live">LIVE</span>`);
      else if (s.mode === "SAMPLE") badges.push(`<span class="pt-badge sample">[SAMPLE]</span>`);
      badges.push(`<span class="pt-badge">${s.cadence}</span>`);
      const count = (s.coverage_count != null)
        ? `<div class="pt-count">${Number(s.coverage_count).toLocaleString()} recent</div>`
        : (s.gap ? `<div class="pt-count">no verified API</div>` : "");
      return `<div class="pulse-tile ${s.bucket}" title="${(s.headline||'').replace(/"/g,'&quot;')}">
        <div class="pt-top">
          <div><div class="pt-state">${s.state}</div><div class="pt-name">${s.name}</div></div>
          <div style="text-align:right"><div class="pt-pulse">${s.pulse}</div><span class="pt-bucket">${s.bucket}</span></div>
        </div>
        <div><div class="pt-badges">${badges.join("")}</div>${count}</div>
      </div>`;
    }).join("");
    grid.innerHTML = tiles;
    const sm = d.summary;
    $("pulseMeta").textContent = `${sm.state_count} states · ${sm.surging.length} surging · ${sm.gaps.length} gaps${d.summary.live ? " · LIVE" : ""}`;
  } catch (e) {
    grid.innerHTML = `<div style="padding:20px;color:var(--hot)">✗ ${e.message}</div>`;
  }
}

/* ---------- Call Brief (grounded + independently double-checked) ---------- */
let BRIEF_ANGLES = {};
function copyAngle(key, btn) {
  const text = BRIEF_ANGLES[key] || "";
  const done = () => { if (btn) { const o = btn.textContent; btn.textContent = "✓ copied"; btn.classList.add("copied"); setTimeout(() => { btn.textContent = o; btn.classList.remove("copied"); }, 1400); } };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => { fallbackCopy(text); done(); });
  } else { fallbackCopy(text); done(); }
}
function fallbackCopy(text) {
  const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (e) {} document.body.removeChild(ta);
}
async function openBrief(leadId) {
  $("modalMount").innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()"><div class="modal">
    <button class="mclose" onclick="closeModal()">✕ Close</button>
    <h3>📜 Call Brief</h3>
    <div class="mbody" id="briefBody"><div class="skeleton" style="width:80%;margin:10px 0"></div><div class="skeleton" style="width:60%"></div></div></div></div>`;
  try {
    const b = await api("/api/brief/" + leadId);
    BRIEF_ANGLES = {};
    const parts = (b.parts || []).map(p => {
      const v = p.formula_verdict || {};
      const allow = v.allow;
      let angleHtml = "";
      if (p.key === "OPENING_LINE" && p.angles && p.angles.length) {
        angleHtml = `<div class="angles">` + p.angles.map((a, i) => {
          const key = leadId + "_" + i; BRIEF_ANGLES[key] = a.line;
          return `<div class="angle">
            <div class="angle-head"><span class="angle-rank">#${a.rank}</span><span class="angle-label">${a.label}</span>
              <button class="copy-btn" onclick="copyAngle('${key}',this)">⧉ copy</button></div>
            <div class="angle-line">${a.line}</div></div>`;
        }).join("") + `</div>`;
      }
      return `<div class="bp">
        <div class="bp-title">${p.title}
          <span class="vchip ${allow ? 'allow' : 'deny'}">${allow ? '✓ checked' : '✗ review'}</span></div>
        <div class="bp-body">${(p.key === "OPENING_LINE" && angleHtml) ? '3 ranked angles — keyed to ' + (b.event_type_label||b.event_type||'event') : (p.body || '')}</div>
        ${angleHtml}
      </div>`;
    }).join("");
    const wt = b.wealth_tier || {}, lp = b.lapse || {};
    const tiers = `<div class="brief-tiers">
      ${b.urgency ? `<span class="urg-chip ${b.urgency==='ACT_NOW'?'act-now':b.urgency==='WARM'?'warm':'cold'}">${b.urgency.replace('_',' ')}</span>` : ''}
      ${wt.tier ? `<span class="wealth-tag" title="based on public records">${wt.tier}</span>` : ''}
      ${lp.decile!=null ? `<span class="lapse-badge ${lp.decile<=3?'low':lp.decile<=6?'mid':'high'}" title="advisory, NOT FCRA">Lapse ${lp.decile}/10</span>` : ''}
    </div>${wealthLadder(wt, false)}`;
    const c = b.consensus || {};
    let checksLine = "";
    const cc = (c.consensus_count != null) ? c.consensus_count : null;
    if (cc) checksLine = `Independently double-checked — ${cc} separate verifications agree`;
    const consensus = checksLine ? `<div class="consensus-bar"><span>✓ ${checksLine}</span></div>` : "";
    const lc = (leadsById[leadId] || {}).confidence || {};
    const confLine = lc.n_sources
      ? `<div style="font-size:12px;color:#0d6b34;font-weight:600;margin-bottom:6px">Confirmed across ${lc.n_sources} public record${lc.n_sources===1?'':'s'} · Confidence: ${lc.level||'Building'}</div>`
      : "";
    $("briefBody").innerHTML = `
      <div style="font-size:13px;color:var(--muted);margin-bottom:6px">${b.lead_name || ''} · Match ${b.score} · ${b.bucket}</div>
      ${confLine}
      ${tiers}
      ${parts}
      ${consensus}
      ${b.receipt_id ? `<div class="ask-receipt" style="color:var(--navy)" onclick="openReceipt('${b.receipt_id}')">🔒 Proof &amp; Sources (${b.receipt_id})</div>` : ''}`;
  } catch (e) {
    $("briefBody").innerHTML = `<div style="color:var(--hot)">✗ ${e.message}</div>`;
  }
}

/* ---------- receipt modal ---------- */
async function openReceipt(rid, leadId) {
  const mount = $("modalMount");
  mount.innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()">
    <div class="modal">
      <button class="mclose" onclick="closeModal()">✕ Close</button>
      <h3>🔒 Proof &amp; Sources</h3>
      <div class="mbody" id="rcptBody"><div class="skeleton" style="width:80%;margin:10px 0"></div><div class="skeleton" style="width:60%"></div></div>
    </div></div>`;
  try {
    const r = await api("/api/receipt/" + rid);
    const v = await api("/api/verify/" + rid);
    const checks = v.checks.map(c => `
      <div class="vcheck"><span class="ic ${c.pass?'p':'f'}">${c.pass?'✓':'✗'}</span> ${c.check}</div>`).join("");
    $("rcptBody").innerHTML = `
      <div class="vverdict ${v.verdict==='VERIFIED'?'ok':'bad'}">${v.verdict==='VERIFIED'?'✓ Verified':'✗ Needs review'}</div>
      <div style="font-size:13px;color:#0b5957;font-weight:600;margin-bottom:8px">Verified · 100% public data · sources listed below · nothing invented</div>
      <div style="font-size:12px;color:var(--muted);margin-bottom:4px">Reference <code>${r.id}</code></div>
      ${checks}
      <div style="font-size:12px;color:var(--muted);margin-top:14px;font-weight:600">The exact public data behind this lead:</div>
      <div class="codeblock">${JSON.stringify(r.payload, null, 2)}</div>
    `;
  } catch (e) {
    $("rcptBody").innerHTML = `<div style="color:var(--hot)">✗ ${e.message}</div>`;
  }
}
function closeModal() { $("modalMount").innerHTML = ""; }

/* ---------- Real Prospects — public B2B business & license records (separate panel) ---------- */
function escHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function openRealLeads() {
  const card = $("realCard"); if (!card) return;
  card.classList.add("show");
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  loadRealLeads();
}
async function loadRealLeads() {
  const body = $("realBody"); if (!body) return;
  const states = ($("realStates") && $("realStates").value || "DE,CT").trim() || "DE,CT";
  body.innerHTML = `<div style="padding:20px;color:var(--muted)">Fetching real public records (live)…</div>`;
  try {
    const d = await api("/api/real-leads?states=" + encodeURIComponent(states));
    const leads = d.leads || [];
    const s = d.summary || {};
    if (!leads.length) {
      body.innerHTML = `<div style="padding:20px;color:var(--muted)">No public records returned for ${escHtml(states)}. Try DE,CT.</div>`;
      $("realMeta").textContent = "";
      return;
    }
    const rows = leads.map(l => {
      const addr = [l.address, l.city, l.state, l.zip].filter(Boolean).map(escHtml).join(", ");
      const cqClass = l.contact_quality === "business address (public)" ? "addr"
        : (l.contact_quality === "[SAMPLE]" ? "sample" : "entity");
      const catOrCred = escHtml(l.credential || l.category || "—");
      const verifyBtn = l.receipt_id
        ? `<button class="real-verify" onclick="openReceipt('${escHtml(l.receipt_id)}')">🔏 Verify</button>`
        : `<span class="real-sub">no receipt</span>`;
      const cite = (l.citation && l.citation.url)
        ? `<a class="real-cite" href="${escHtml(l.citation.url)}" target="_blank" rel="noopener">${escHtml(l.citation.label || "source")} ↗</a>`
        : "";
      return `<tr>
        <td><div class="real-name">${escHtml(l.name)}</div>
          <div class="real-sub">${escHtml((l.type||"").toUpperCase())}${l.status?" · "+escHtml(l.status):""}</div></td>
        <td>${catOrCred}</td>
        <td>${addr ? addr : `<span class="real-cq ${cqClass}">${escHtml(l.contact_quality)}</span>`}</td>
        <td class="real-sub">${escHtml(l.license_or_issue_date || "date withheld")}</td>
        <td><div class="real-angle">${escHtml(l.product_angle || "")}</div>
          <div class="real-why">${escHtml(l.why || "")}</div></td>
        <td>${verifyBtn}<div style="margin-top:6px">${cite}</div></td>
      </tr>`;
    }).join("");
    $("realMeta").textContent = `${s.live_count||0} live · ${s.sample_count||0} sample · ${leads.length} total`;
    const srcChips = (d.sources || []).map(src =>
      `<span class="real-mode ${src.mode==='LIVE'?'live':'sample'}">${escHtml(src.state)} ${escHtml(src.mode)} (${src.count})</span>`).join(" ");
    $("realHint").innerHTML = srcChips;
    body.innerHTML =
      `<div class="real-wrap"><table class="real-table">
        <thead><tr><th>Business / Name</th><th>Category / Credential</th><th>Public Address</th>
          <th>Record date</th><th>Suggested NYL angle</th><th>Receipt · Source</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`;
  } catch (e) {
    body.innerHTML = `<div style="padding:20px;color:var(--hot)">✗ ${escHtml(e.message)}</div>`;
  }
}

/* ---------- Where Need Is Rising (plain-English surge readout) ---------- */
function openSurge() {
  const card = $("surgeCard"); if (!card) return;
  card.classList.add("show");
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  loadSurge();
}
async function loadSurge() {
  const body = $("surgeBody"); if (!body) return;
  const states = ($("surgeStates") && $("surgeStates").value || "NY,NJ,PA,MD,DE,CT").trim() || "NY,NJ,PA,MD,DE,CT";
  body.innerHTML = `<div style="padding:20px;color:var(--muted)">Finding where need is rising…</div>`;
  try {
    const d = await api("/api/surge?states=" + encodeURIComponent(states));
    const areas = d.areas || [];
    if (!areas.length) {
      body.innerHTML = `<div style="padding:20px;color:var(--muted)">No rising areas right now — check back after the next update.</div>`;
      $("surgeMeta").textContent = "";
      return;
    }
    const nRising = areas.filter(a => a.status === "Rising").length;
    $("surgeMeta").textContent = nRising ? `${nRising} area${nRising===1?'':'s'} rising` : "All steady";
    const rows = areas.map(a => {
      const cls = (a.status || "Steady").toLowerCase();
      const cite = (a.source && a.source.url)
        ? `<a class="real-cite" href="${escHtml(a.source.url)}" target="_blank" rel="noopener">${escHtml(a.source.label||"Public records")} ↗</a>`
        : `<span class="src">${escHtml((a.source||{}).label || "Public records")}</span>`;
      const ex = a.source_status === "live" ? "" : ` <span class="src">(example)</span>`;
      return `<div class="surge-row">
        <span class="surge-pill ${cls}">${escHtml(a.status||"Steady")}</span>
        <span class="area">${escHtml(a.area||a.state||"—")}</span>
        <span class="note">${escHtml(a.note||"")}${ex}</span>
        <span class="src">${cite}</span>
      </div>`;
    }).join("");
    body.innerHTML = rows;
  } catch (e) {
    body.innerHTML = `<div style="padding:20px;color:var(--hot)">✗ ${escHtml(e.message)}</div>`;
  }
}

/* ---------- Layoff Alerts — public state labor records (coverage-cliff trigger) ---------- */
function openWarn() {
  const card = $("warnCard"); if (!card) return;
  card.classList.add("show");
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  loadWarn();
}
async function loadWarn() {
  const body = $("warnBody"); if (!body) return;
  const states = ($("warnStates") && $("warnStates").value || "NY,NJ,PA,MD,DE,CT").trim() || "NY,NJ,PA,MD,DE,CT";
  body.innerHTML = `<div style="padding:20px;color:var(--muted)">Finding layoff notices…</div>`;
  try {
    const d = await api("/api/warn-leads?states=" + encodeURIComponent(states));
    const leads = d.leads || [];
    if (!leads.length) {
      body.innerHTML = `<div style="padding:20px;color:var(--muted)">No layoff notices returned for ${escHtml(states)}.</div>`;
      $("warnMeta").textContent = "";
      return;
    }
    const rows = leads.map(l => {
      const c = l.confidence || {};
      const n = c.n_sources || 1;
      const conf = c.point != null
        ? `Match ${c.point} · Confidence: ${escHtml(c.level||"Building")} · confirmed across ${n} public record${n===1?'':'s'}`
        : "";
      const modeCls = l.source_status === "live" ? "live" : "sample";
      const modeLabel = l.source_status === "live" ? "Live" : "Example";
      const cite = (l.source && l.source.url)
        ? `<a class="real-cite" href="${escHtml(l.source.url)}" target="_blank" rel="noopener">${escHtml(l.source.label||"State labor source")} ↗</a>`
        : escHtml((l.source||{}).label || "");
      const loc = [l.city, l.county ? l.county + " Co." : "", l.state].filter(Boolean).map(escHtml).join(", ");
      return `<tr>
        <td><div class="real-name">${escHtml(l.employer||"—")}</div>
          <div class="real-sub"><span class="real-mode ${modeCls}">${modeLabel}</span></div></td>
        <td>${loc}</td>
        <td style="text-align:center"><b>${escHtml(String(l.affected_count!=null?l.affected_count:"—"))}</b></td>
        <td class="real-sub">${escHtml(l.coverage_loss_date||"—")}<div class="real-sub">notice ${escHtml(l.notice_date||"—")}</div></td>
        <td><div class="real-angle">${escHtml(l.product||"")}</div>
          <div class="real-why">${escHtml(l.angle||"")}</div>
          <div class="conf-line">${conf}</div></td>
        <td>${cite}</td>
      </tr>`;
    }).join("");
    const ns = (d.sample_states||[]).length, nl = (d.live_states||[]).length;
    $("warnMeta").textContent = `${d.count||leads.length} notices · ${nl} live state(s) · ${ns} sample state(s)`;
    body.innerHTML =
      `<div class="real-wrap"><table class="real-table">
        <thead><tr><th>Employer</th><th>Location</th><th>Affected</th>
          <th>Coverage-loss date</th><th>Product angle · confidence</th><th>Source</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`;
  } catch (e) {
    body.innerHTML = `<div style="padding:20px;color:var(--hot)">✗ ${escHtml(e.message)}</div>`;
  }
}

/* ---------- Tax Territories — aggregate IRS public statistics (territory, not individuals) ---------- */
function openTax() {
  const card = $("taxCard"); if (!card) return;
  card.classList.add("show");
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  loadTax();
}
async function loadTax() {
  const body = $("taxBody"); if (!body) return;
  const states = ($("taxStates") && $("taxStates").value || "NY,NJ,CT").trim() || "NY,NJ,CT";
  body.innerHTML = `<div style="padding:20px;color:var(--muted)">Fetching IRS SOI tax-territory data (live)…</div>`;
  try {
    const d = await api("/api/tax-territories?states=" + encodeURIComponent(states));
    const zips = d.affluent_zips || [];
    const counties = d.money_in_motion || [];
    const sum = d.summary || {};
    const verifyBtn = d.receipt_id
      ? `<button class="real-verify" onclick="openReceipt('${escHtml(d.receipt_id)}')">🔒 Proof &amp; Sources</button>`
      : `<span class="real-sub">no receipt</span>`;
    const srcChips = (d.sources || []).map(src =>
      `<a class="real-mode ${src.mode==='LIVE'?'live':'sample'}" href="${escHtml(src.url||'#')}" target="_blank" rel="noopener">${escHtml(src.mode)} · ${escHtml(src.label||'IRS SOI')} ↗</a>`).join(" ");
    $("taxHint").innerHTML = srcChips;
    $("taxMeta").textContent = `${zips.length} affluent ZIPs · ${counties.length} money-in-motion counties`;

    const zipRows = zips.map(z => `<tr>
      <td><span class="real-zip">${escHtml(z.zip)}</span> <span class="real-sub">${escHtml(z.state)}</span></td>
      <td class="real-num">${Number(z.high_income_returns||0).toLocaleString()}</td>
      <td class="real-num">${escHtml(z.affluent_share)}%</td>
      <td class="real-num">$${Number(z.high_income_agi_000||0).toLocaleString()}k</td>
      <td><div class="real-angle">${escHtml(z.angle||"")}</div></td>
    </tr>`).join("");
    const cRows = counties.map(c => `<tr>
      <td><div class="real-name">${escHtml(c.county)}</div><div class="real-sub">${escHtml(c.state)}</div></td>
      <td class="real-num">${Number(c.returns_inflow||0).toLocaleString()}</td>
      <td class="real-num">$${Number(c.agi_inflow_000||0).toLocaleString()}k</td>
      <td class="real-num">$${Number(c.avg_agi_per_return_000||0).toLocaleString()}k</td>
      <td><div class="real-angle">${escHtml(c.angle||"")}</div></td>
    </tr>`).join("");

    body.innerHTML = `
      <div class="tax-sub-h">🏘️ Affluent ZIPs <span class="real-sub">— $200k+ AGI return density (IRS SOI by ZIP, mode: ${escHtml(sum.zip_mode||"?")})</span></div>
      <div class="real-wrap"><table class="real-table">
        <thead><tr><th>ZIP</th><th>$200k+ returns</th><th>Affluent share</th><th>$200k+ AGI</th><th>Suggested NYL angle</th></tr></thead>
        <tbody>${zipRows || `<tr><td colspan="5" class="real-sub">No ZIPs for ${escHtml(states)}</td></tr>`}</tbody></table></div>
      <div class="tax-sub-h" style="margin-top:18px">💸 Money-in-Motion counties <span class="real-sub">— AGI carried in by movers (IRS county migration inflow, mode: ${escHtml(sum.migration_mode||"?")})</span></div>
      <div class="real-wrap"><table class="real-table">
        <thead><tr><th>County</th><th>Returns in</th><th>AGI in</th><th>Avg AGI / return</th><th>Suggested NYL angle</th></tr></thead>
        <tbody>${cRows || `<tr><td colspan="5" class="real-sub">No counties for ${escHtml(states)}</td></tr>`}</tbody></table></div>
      <div style="margin-top:14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        ${verifyBtn}<span class="real-sub">${escHtml(d.label||"")}</span></div>`;
  } catch (e) {
    body.innerHTML = `<div style="padding:20px;color:var(--hot)">✗ ${escHtml(e.message)}</div>`;
  }
}

/* ---------- Opt-In — express-consent capture (only place personal contact is accepted) ---------- */
function openOptin() {
  const card = $("optinCard"); if (!card) return;
  card.classList.add("show");
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  loadOptinLeads();
}
async function submitOptin(ev) {
  if (ev) ev.preventDefault();
  const res = $("optResult"); const btn = $("optSubmit");
  const consent = $("optConsent").checked;
  res.className = "optin-result";
  if (!consent) {
    res.classList.add("err");
    res.textContent = "✗ Consent is required — please check the box to be contacted.";
    return false;
  }
  const payload = {
    name: ($("optName").value || "").trim(),
    email: ($("optEmail").value || "").trim() || null,
    phone: ($("optPhone").value || "").trim() || null,
    zip: ($("optZip").value || "").trim() || null,
    interest: ($("optInterest").value || "").trim() || null,
    consent: true,
  };
  btn.disabled = true; const orig = btn.innerHTML; btn.innerHTML = '<span class="loader"></span> Submitting…';
  try {
    const d = await api("/api/optin", { method: "POST", body: JSON.stringify(payload) });
    res.classList.add("ok");
    res.innerHTML = `✓ ${escHtml(d.message || "Submitted")} — consent receipt
      <button class="real-verify" onclick="openReceipt('${escHtml(d.receipt_id)}')">🔏 ${escHtml(d.receipt_id)}</button>`;
    $("optinForm").reset();
    loadOptinLeads();
  } catch (e) {
    res.classList.add("err");
    res.textContent = "✗ " + e.message;
  } finally {
    btn.disabled = false; btn.innerHTML = orig;
  }
  return false;
}
async function loadOptinLeads() {
  const body = $("optinBody"); if (!body) return;
  body.innerHTML = `<div style="padding:14px;color:var(--muted)">Loading consented leads…</div>`;
  try {
    const d = await api("/api/optin/leads");
    const leads = d.leads || [];
    $("optinMeta").textContent = `${leads.length} consented`;
    if (!leads.length) {
      body.innerHTML = `<div style="padding:14px;color:var(--muted)">No consented leads yet.</div>`;
      return;
    }
    body.innerHTML = leads.map(l => {
      const contact = [l.email, l.phone].filter(Boolean).map(escHtml).join(" · ");
      const verify = l.receipt_id
        ? `<button class="real-verify" onclick="openReceipt('${escHtml(l.receipt_id)}')">🔏 Verify</button>` : "";
      return `<div class="optin-lead">
        <div class="real-name">${escHtml(l.name)} <span class="optin-consent-badge">${escHtml(l.consent_basis || "express consent (opt-in)")}</span></div>
        <div class="real-sub">${contact || "no contact provided"}${l.zip?" · ZIP "+escHtml(l.zip):""}${l.interest?" · "+escHtml(l.interest):""}</div>
        <div class="real-sub">${escHtml(l.submitted_at || "")}</div>
        <div style="margin-top:6px">${verify}</div>
      </div>`;
    }).join("");
  } catch (e) {
    body.innerHTML = `<div style="padding:14px;color:var(--hot)">✗ ${escHtml(e.message)}</div>`;
  }
}

/* ---------- 3D login backdrop (governed-AI constellation) ---------- */
(function () {
  if (!window.THREE) return;
  const cv = $("bg3d"); if (!cv) return;
  const renderer = new THREE.WebGLRenderer({ canvas: cv, antialias: true, alpha: true });
  renderer.setSize(innerWidth, innerHeight); renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.1, 100); cam.position.z = 9;
  // node constellation = leads being scored & linked by signed receipts
  const N = 70, geo = new THREE.SphereGeometry(0.06, 10, 10);
  const matGold = new THREE.MeshBasicMaterial({ color: 0xd7b96b });
  const matTeal = new THREE.MeshBasicMaterial({ color: 0x5cc4bf });
  const nodes = [];
  for (let i = 0; i < N; i++) {
    const m = new THREE.Mesh(geo, Math.random() > 0.7 ? matGold : matTeal);
    m.position.set((Math.random()-.5)*14, (Math.random()-.5)*9, (Math.random()-.5)*8);
    m.userData.s = 0.2 + Math.random() * 0.6; scene.add(m); nodes.push(m);
  }
  const lgeo = new THREE.BufferGeometry(); const pts = [];
  for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
    if (nodes[i].position.distanceTo(nodes[j].position) < 2.4) {
      pts.push(nodes[i].position.x, nodes[i].position.y, nodes[i].position.z,
               nodes[j].position.x, nodes[j].position.y, nodes[j].position.z);
    }
  }
  lgeo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
  const lines = new THREE.LineSegments(lgeo, new THREE.LineBasicMaterial({ color: 0x2f6e8f, transparent: true, opacity: 0.25 }));
  scene.add(lines);
  let t = 0;
  (function loop() {
    t += 0.0035; scene.rotation.y = t; scene.rotation.x = Math.sin(t * 0.6) * 0.1;
    nodes.forEach((n, i) => n.scale.setScalar(n.userData.s * (1 + 0.3 * Math.sin(t * 3 + i))));
    renderer.render(scene, cam); requestAnimationFrame(loop);
  })();
  addEventListener("resize", () => {
    if (cv.classList.contains("hidden")) return;
    renderer.setSize(innerWidth, innerHeight); cam.aspect = innerWidth / innerHeight; cam.updateProjectionMatrix();
  });
})();
