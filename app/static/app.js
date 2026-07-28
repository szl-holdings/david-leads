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
    loadBuildInfo();
  } catch (e) {
    err.textContent = "✗ " + e.message;
    btn.disabled = false; btn.innerHTML = "Access Intelligence Console";
  }
}
document.addEventListener("keydown", (e) => { if (e.key === "Enter" && !$("login").classList.contains("hidden")) doLogin(); });

async function doLogout() {
  try { if (TOKEN) await api("/api/logout", { method: "POST" }); } catch (_) {}
  TOKEN = null;
  $("p").value = ""; $("k").value = "";
  $("app").classList.add("hidden");
  $("login").classList.remove("hidden");
  $("bg3d").classList.remove("hidden");
  $("loginBtn").disabled = false;
  $("loginBtn").textContent = "Access Intelligence Console";
}

async function loadBuildInfo() {
  const stamp = $("sourceStamp"); if (!stamp) return;
  try {
    const info = await api("/api/build-info");
    const digest = String(info.bundle_sha256 || "").slice(0, 10);
    const revision = info.source_revision ? String(info.source_revision).slice(0, 8) : "revision unavailable";
    stamp.textContent = `Runtime ${digest || "digest unavailable"} · ${revision}`;
    stamp.className = "source-stamp observed";
    stamp.title = info.alignment_note || "Runtime bytes observed; parity requires external comparison.";
  } catch (_) {
    stamp.textContent = "Runtime source · unavailable";
    stamp.className = "source-stamp unverified";
  }
}

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
      <div class="label">Modeled appointment potential</div>
      <div class="val">${z(k && k.qualified_appts_per_week)}</div>
      <div class="sub">modeled from lead quality (HOT 70% · WARM 35%)</div>
    </div>
    <div class="kpi">
      <div class="label">High-match segments</div>
      <div class="val">${z(k && k.hot_count)}</div>
      <div class="sub">score ≥ 80 · contact permission not evaluated</div>
    </div>
    <div class="kpi">
      <div class="label">Modeled premium potential</div>
      <div class="val" style="font-size:27px">${k ? money(k.pipeline_premium) : "—"}</div>
      <div class="sub">illustrative — not a quoted premium</div>
    </div>
    <div class="kpi">
      <div class="label">Average match score</div>
      <div class="val">${z(k && k.avg_score)}</div>
      <div class="sub">${k ? k.total_leads + " leads scored" : "run to populate"}</div>
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
/* Contact-gate badge — public data never implies permission to contact. */
function blockedBadge(l) {
  if (!l.compliance || l.compliance.clear === true) return "";
  const reasons = (l.compliance.reasons || []).map(plainBlockReason);
  const tip = reasons.join(" · ").replace(/"/g,'&quot;');
  if (l.compliance.clear === false) {
    const why = reasons[0] || "Cannot be contacted";
    return `<span class="blocked-badge" title="${tip}">Cannot contact — ${why}</span>`;
  }
  return `<span class="contact-review" title="${tip}">Research only · contact not evaluated</span>`;
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
        <button class="verify-btn" onclick="openOperatorTrace('${l.id}')">🔎 Decision Trace</button>
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
    <thead><tr><th></th><th>Priority</th><th>Lead · Why now</th><th>Product fit</th><th>Decision · Outcome</th></tr></thead>
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
  const adv = `<div class="detail-sec"><h4>Operator context (based on public records)</h4>
    <div class="adv-box" style="margin-bottom:10px"><div class="adv-h">Wealth tier</div>${wealthLadder(wt, false)}</div>
    <div class="adv-grid">
      <div class="adv-box"><div class="adv-h">Retention signal</div><div class="adv-v">${lp.decile!=null?lp.decile+'/10':'—'}</div>
        <div class="adv-note">${lp.interpretation||''} · advisory, not a consumer report</div><ul class="adv-list">${lfac}</ul></div>
    </div>
    <div class="adv-foot">Event type: <strong>${l.event_type_label||l.event_type||'—'}</strong> · Urgency: <strong>${l.urgency||'—'}</strong> · observed ${l.hours_since!=null?l.hours_since+'h ago':'—'}</div>
  </div>`;
  const rd = l.receptivity_detail || {};
  const g = l.likely_gap || {};
  const q = l.liquidity || null;
  const p1 = `<div class="detail-sec"><h4>Readiness and coverage context</h4>
    <div class="adv-grid">
      <div class="adv-box"><div class="adv-h">Behavioral receptivity</div><div class="adv-v">${l.receptivity!=null?Math.round(l.receptivity):'—'}</div>
        <div class="adv-note">${rd.interpretation||'advisory'} · ${rd.citation ? `<a href="${rd.citation.url}" target="_blank" rel="noopener">${rd.citation.source||'RGA'}</a>` : 'RGA predictive-moments'} (advisory)</div></div>
      <div class="adv-box"><div class="adv-h">Likely coverage gap</div><div class="adv-v" style="font-size:14px">${g.label||'—'}</div>
        <div class="adv-note">${g.recommended? 'Lead with: '+g.recommended : ''}${g.basis? ' · '+g.basis : ''}</div></div>
    </div>
    ${liqWatch(q)}
  </div>`;
  return `<div class="detail-inner">
    <div class="detail-sec"><h4>Why this lead ranks here</h4>${axes}</div>
    ${adv}
    ${p1}
    <div class="detail-sec"><h4>Supporting public records</h4>${moments}</div>
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
      <span class="src">${escHtml(String(s.source||"").replace(/\[SAMPLE\]/,''))}</span>${s.live?'<span class="live">LIVE</span>':'<span class="live smp">PUBLIC</span>'}${fresh}
      <div class="txt">${escHtml(s.signal||"")}</div>
      <div class="det">${escHtml(s.detail||"")}</div>
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
      <div class="line"><span class="ok">✓</span> Evidence evaluated against ${g.signals_checked} public records</div>
      <div class="line"><span class="ok">${g.all_public?'✓':'✗'}</span> Run evidence is public-data only</div>
      <div class="line"><span class="ok">✓</span> ${g.rejected_nonpublic} non-public items rejected</div>
      <div class="line"><span class="warn">!</span> Contact permission is NOT_EVALUATED until a human records execution-time clearance</div>
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
  const ticks = sigs.map(s => `<span class="tick"><b>${escHtml(String(s.source||"").replace(/\[SAMPLE\]/,'').trim())}</b> · ${escHtml(String(s.detail||s.signal||"").slice(0,70))}</span>`);
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

/* ---------- Why leads rank (plain-English methodology) ---------- */
const AXIS_PLAIN = {
  life_event_strength: "Life event strength", income_fit: "Income fit",
  age_window_fit: "Age fit", product_propensity: "Product fit", recency: "Freshness",
};
async function openModel() {
  $("modalMount").innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()"><div class="modal">
    <button class="mclose" onclick="closeModal()">✕ Close</button>
    <h3>🔓 Why leads rank</h3>
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
        The work list ranks each lead from five operator-facing signals. It is a priority guide—not a probability, quote, underwriting decision, or permission to contact.</div>
      <div style="font-size:12px;color:var(--muted);font-weight:600;margin-top:6px">The five reasons a lead can move up or down:</div>
      ${axes}
      <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap">
        <span class="badge HOT">${(m.buckets&&m.buckets.HOT)||"Hot"}</span>
        <span class="badge WARM">${(m.buckets&&m.buckets.WARM)||"Warm"}</span>
        <span class="badge NURTURE">${(m.buckets&&m.buckets.NURTURE)||"Nurture"}</span>
      </div>
      <div style="font-size:12.5px;color:var(--navy);font-weight:600;margin-top:14px;background:#fbf7ec;border-left:3px solid var(--gold);padding:10px 12px;border-radius:6px">
        Public records only — SEC filings, U.S. Census, labor statistics, public health data, and county
        records. Nothing private is used and nothing is invented. Each lead also shows an evidence-completeness
        priority, while contact permission remains NOT_EVALUATED until a broker records clearance.</div>
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

/* ---------- operator decision trace ---------- */
async function openOperatorTrace(leadId) {
  const mount = $("modalMount");
  mount.innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()">
    <div class="modal" style="width:min(900px,96vw)">
      <button class="mclose" onclick="closeModal()">✕ Close</button>
      <h3>🔎 Decision Trace</h3>
      <div class="mbody" id="traceBody"><div class="skeleton" style="width:80%;margin:10px 0"></div><div class="skeleton" style="width:60%"></div></div>
    </div></div>`;
  try {
    const d = await api("/api/operator/trace/" + encodeURIComponent(leadId));
    const path = (d.decision_path || []).map(step => `
      <div class="trace-step">
        <div class="state">${escHtml(step.state)}</div>
        <div class="name">${escHtml(step.step)}</div>
        <div class="detail">${escHtml(step.detail)}</div>
      </div>`).join("");
    const drivers = (d.drivers || []).map(driver => `
      <div class="trace-row">
        <span class="trace-label">${escHtml(driver.label)}</span>
        <span class="trace-level">${escHtml(driver.level)}</span>
        <span class="trace-note">How much this signal supports the current work-list position.</span>
      </div>`).join("");
    const evidence = (d.evidence || []).map(item => `
      <div class="trace-row">
        <span class="trace-label">${escHtml(item.source)}</span>
        <span class="trace-level">${escHtml(item.state)}</span>
        <span class="trace-note">${escHtml(item.supports)}</span>
      </div>`).join("") || `<div class="trace-caveat">No source link was attached to this lead.</div>`;
    const caveats = (d.caveats || []).map(note => `<div class="trace-caveat">${escHtml(note)}</div>`).join("");
    const uncertainty = d.uncertainty || {};
    const range = uncertainty.range || {};
    const proof = d.proof || {};
    const proofButton = proof.receipt_id
      ? `<button class="verify-btn" onclick="openReceipt('${escHtml(proof.receipt_id)}','${escHtml(leadId)}')">Open proof record</button>`
      : `<span class="trace-level">NO PROOF RECORD</span>`;
    $("traceBody").innerHTML = `
      <div style="display:flex;gap:10px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap">
        <div><div style="font-family:'Fraunces';font-size:21px;font-weight:600">${escHtml(d.lead?.name || leadId)}</div>
          <div style="font-size:13px;color:var(--muted)">${escHtml(d.lead?.priority || "UNKNOWN")} priority · ${escHtml(d.lead?.why_now || "No reason supplied")}</div></div>
        <span class="badge ${d.run?.state==='LIVE'?'HOT':d.run?.state==='MIXED'?'WARM':'NURTURE'}">${escHtml(d.run?.state || "UNKNOWN")} RUN</span>
      </div>
      <div class="trace-grid">${path}</div>
      <h4>Why it ranks here</h4><div class="trace-list">${drivers}</div>
      <h4>Evidence attached</h4><div class="trace-list">${evidence}</div>
      <h4>What is still uncertain</h4>
      <div class="trace-row"><span class="trace-label">Confidence</span><span class="trace-level">${escHtml(uncertainty.level || "UNKNOWN")}</span><span class="trace-note">Range ${escHtml(range.low ?? "—")}–${escHtml(range.high ?? "—")} · ${escHtml(uncertainty.source_count ?? 0)} supporting source(s). ${escHtml(uncertainty.note || "")}</span></div>
      <div class="trace-row"><span class="trace-label">Conflict check</span><span class="trace-level">${escHtml(d.conflict_check?.state || "UNKNOWN")}</span><span class="trace-note">${escHtml(d.conflict_check?.note || "")}</span></div>
      ${caveats}
      <div style="display:flex;gap:12px;align-items:center;margin-top:16px;flex-wrap:wrap">
        ${proofButton}
        <span class="trace-note">Proof state: ${escHtml(proof.state || "UNKNOWN")} · Contact gate: ${escHtml(d.contact_gate?.state || "UNKNOWN")}</span>
      </div>`;
  } catch (e) {
    $("traceBody").innerHTML = `<div style="color:var(--hot)">✕ ${escHtml(e.message)}</div>`;
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
      <div class="vcheck"><span class="ic ${c.pass?'p':'f'}">${c.pass?'✓':'✗'}</span> ${escHtml(c.check)}</div>`).join("");
    const signed = v.signature_state === "VERIFIED";
    const intact = v.integrity_state === "VERIFIED";
    const verdictClass = intact ? "ok" : "bad";
    const verdictLabel = signed
      ? "Signature verified"
      : intact
      ? "Hash integrity verified · unsigned"
      : "Verification failed";
    $("rcptBody").innerHTML = `
      <div class="vverdict ${verdictClass}">${intact?'✓':'✗'} ${verdictLabel}</div>
      <div style="font-size:13px;color:var(--muted);font-weight:600;margin-bottom:8px">Integrity and provenance metadata only · not proof that a real-world claim is true</div>
      <div style="font-size:12px;color:var(--muted);margin-bottom:4px">Reference <code>${escHtml(r.id)}</code> · Sources ${escHtml((v.source_classes||[]).join(", ")||"UNCLASSIFIED")}</div>
      ${checks}
      <div style="font-size:12px;color:var(--muted);margin-top:14px;font-weight:600">The exact evidence metadata bound to this receipt:</div>
      <div class="codeblock">${escHtml(JSON.stringify(r.payload, null, 2))}</div>
    `;
  } catch (e) {
    $("rcptBody").innerHTML = `<div style="color:var(--hot)">✗ ${e.message}</div>`;
  }
}
function closeModal() { $("modalMount").innerHTML = ""; }

/* ---------- Real Prospects — public B2B business & license records (separate panel) ---------- */
const brokerDeskItems = {};
const brokerDeskViews = {};

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
  body.innerHTML = `<div style="padding:20px;color:var(--muted)">Building the governed opportunity queue…</div>`;
  try {
    const d = await api("/api/deal-desk?states=" + encodeURIComponent(states));
    const leads = d.opportunities || [];
    leads.forEach(l => {
      brokerDeskItems[l.opportunity_id] = l;
      brokerDeskViews[l.opportunity_id] = "real";
    });
    const s = d.summary || {};
    if (!leads.length) {
      body.innerHTML = `<div style="padding:20px;color:var(--muted)">No public records returned for ${escHtml(states)}. Try DE,CT.</div>`;
      $("realMeta").textContent = "";
      $("deskSummary").innerHTML = "";
      return;
    }
    $("deskSummary").innerHTML = [
      ["Official records", s.live || 0],
      ["Ready after clearance", s.call_ready || 0],
      ["Needs research", s.needs_research || 0],
      ["Examples blocked", s.examples || 0],
    ].map(([label, value]) => `<div class="desk-stat"><b>${escHtml(value)}</b><span>${escHtml(label)}</span></div>`).join("");
    const stages = ["REVIEW","RESEARCH","READY","CONTACTED","MEETING","PROPOSAL","WON","LOST","BLOCKED"];
    const cards = leads.map(l => {
      const addr = [l.address, l.city, l.state, l.zip].filter(Boolean).map(escHtml).join(", ");
      const verifyBtn = l.receipt_id
        ? `<button class="real-verify" onclick="openReceipt('${escHtml(l.receipt_id)}')">Proof</button>`
        : "";
      const cite = (l.citation && l.citation.url)
        ? `<a class="real-cite" href="${escHtml(l.citation.url)}" target="_blank" rel="noopener">${escHtml(l.citation.label || "source")} ↗</a>`
        : "";
      const gateClass = l.call_ready ? "ready" : l.truth_label === "EXAMPLE" ? "blocked" : "review";
      const options = stages.map(stage =>
        `<option value="${stage}"${stage===l.stage?" selected":""}>${stage.replace("_"," ")}</option>`).join("");
      const workflowButtons = `
        <button class="real-verify workflow" onclick="openResearchModal('${escHtml(l.opportunity_id)}','real')">Research channel</button>
        ${(l.channels||[]).length ? `<button class="real-verify workflow" onclick="openClearanceModal('${escHtml(l.opportunity_id)}','real')">Clear 24h</button>` : ""}
        ${l.call_ready ? `<button class="real-verify workflow ready" onclick="openCallSheet('${escHtml(l.opportunity_id)}')">Call sheet</button>
          <button class="real-verify workflow" onclick="openDispositionModal('${escHtml(l.opportunity_id)}','real')">Outcome</button>` : ""}`;
      return `<article class="opp-card">
        <div class="opp-head">
          <div><div class="real-name">${escHtml(l.name)}</div>
            <div class="opp-meta">${escHtml(l.credential || l.category || l.type || "Public entity")} · ${escHtml(l.state || "")} · observed ${escHtml(l.license_or_issue_date || "date unavailable")}</div></div>
          <div class="opp-priority" title="Transparent evidence-completeness priority">${escHtml(l.priority)}</div>
        </div>
        <div class="opp-source">${addr || escHtml(l.contact_quality || "No business address")}<br>${cite}</div>
        <div class="opp-angle"><strong>${escHtml(l.product_angle || "Coverage review")}</strong><br>${escHtml(l.why || "")}</div>
        <div class="opp-next"><strong>Next action</strong><br>${escHtml(l.next_action || "")}</div>
        <div class="opp-actions">
          <span class="gate ${gateClass}">${escHtml(l.contact_gate || "NOT_EVALUATED")}</span>
          <label class="real-sub" for="stage-${escHtml(l.opportunity_id)}">Stage</label>
          <select class="opp-stage" id="stage-${escHtml(l.opportunity_id)}" data-prior="${escHtml(l.stage)}" onchange="updateOpportunity('${escHtml(l.opportunity_id)}',this)">
            ${options}
          </select>
          ${verifyBtn}
          ${workflowButtons}
        </div>
      </article>`;
    }).join("");
    $("realMeta").textContent = `${s.live||0} live · ${s.call_ready||0} cleared · ${d.persistence||"IN_MEMORY"}`;
    const srcChips = (d.sources || []).map(src =>
      `<span class="real-mode ${src.mode==='LIVE'?'live':'sample'}">${escHtml(src.state)} · ${escHtml(src.source || (src.citation||{}).label || "official source")} · ${escHtml(src.mode)} (${escHtml(src.count)})</span>`).join(" ");
    $("realHint").innerHTML = srcChips;
    body.innerHTML = `<div class="opp-grid">${cards}</div>`;
  } catch (e) {
    body.innerHTML = `<div style="padding:20px;color:var(--hot)">✗ ${escHtml(e.message)}</div>`;
  }
}

function openFrontiers() {
  const card = $("frontierCard"); if (!card) return;
  card.classList.add("show");
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  loadFrontiers();
}

async function loadFrontiers() {
  const body = $("frontierBody"); if (!body) return;
  const states = ($("frontierStates") && $("frontierStates").value || "NY,NJ,PA,MD,DE,CT").trim() || "NY,NJ,PA,MD,DE,CT";
  body.innerHTML = `<div style="padding:20px;color:var(--muted)">Querying official entity-level frontiers…</div>`;
  try {
    const d = await api("/api/frontier-desk?states=" + encodeURIComponent(states));
    const leads = d.opportunities || [];
    leads.forEach(l => {
      brokerDeskItems[l.opportunity_id] = l;
      brokerDeskViews[l.opportunity_id] = "frontier";
    });
    const s = d.summary || {};
    const sources = d.sources || [];
    const liveSources = sources.filter(src => src.mode === "LIVE").length;
    $("frontierSummary").innerHTML = [
      ["Official signals", s.live || 0],
      ["Live sources", liveSources],
      ["Ready after clearance", s.call_ready || 0],
      ["Needs research", s.needs_research || 0],
    ].map(([label, value]) => `<div class="desk-stat"><b>${escHtml(value)}</b><span>${escHtml(label)}</span></div>`).join("");
    $("frontierMeta").textContent = `${s.live||0} signals · ${s.call_ready||0} cleared · ${d.persistence||"IN_MEMORY"}`;
    $("frontierHint").innerHTML = sources.map(src => {
      const unavailable = src.mode !== "LIVE";
      const suffix = unavailable ? ` · ${escHtml(src.reason || "unavailable")}` : ` · ${escHtml(src.count || 0)} records`;
      return `<a class="real-mode ${unavailable?"sample":"live"}" href="${escHtml((src.citation||{}).url||"#")}" target="_blank" rel="noopener">${escHtml(src.source||src.source_id||"official source")} · ${escHtml(src.mode)}${suffix} ↗</a>`;
    }).join(" ");
    if (!leads.length) {
      body.innerHTML = `<div style="padding:20px;color:var(--muted)">No qualifying entity-level signals were returned. Source availability is shown above; no sample records were substituted.</div>`;
      return;
    }
    const stages = ["REVIEW","RESEARCH","READY","CONTACTED","MEETING","PROPOSAL","WON","LOST","BLOCKED"];
    body.innerHTML = `<div class="opp-grid">${leads.map(l => {
      const addr = [l.address, l.city, l.state, l.zip].filter(Boolean).map(escHtml).join(", ");
      const cite = (l.citation && l.citation.url)
        ? `<a class="real-cite" href="${escHtml(l.citation.url)}" target="_blank" rel="noopener">${escHtml(l.citation.label || "official record")} ↗</a>`
        : "";
      const sourceRecord = (l.source_record && l.source_record.url)
        ? `<a class="real-cite" href="${escHtml(l.source_record.url)}" target="_blank" rel="noopener">${escHtml(l.source_record.label || "dataset")} ↗</a>`
        : "";
      const fleet = l.operational_snapshot && ("power_units" in l.operational_snapshot || "drivers" in l.operational_snapshot)
        ? `${escHtml(l.operational_snapshot.power_units||0)} power units · ${escHtml(l.operational_snapshot.drivers||0)} drivers`
        : "";
      const facility = l.source_frontier === "EPA_ECHO" && l.operational_snapshot
        ? `${escHtml(l.operational_snapshot.naics_codes||"NAICS unavailable")} NAICS · ${escHtml(l.operational_snapshot.days_since_activity||0)} days since activity`
        : "";
      const award = l.award
        ? `$${Number(l.award.amount||0).toLocaleString()} · ${escHtml(l.award.agency||"Federal agency")}`
        : "";
      const options = stages.map(stage =>
        `<option value="${stage}"${stage===l.stage?" selected":""}>${stage.replace("_"," ")}</option>`).join("");
      const gateClass = l.call_ready ? "ready" : "review";
      const verifyBtn = l.receipt_id
        ? `<button class="real-verify" onclick="openReceipt('${escHtml(l.receipt_id)}')">Proof</button>`
        : "";
      const workflowButtons = `
        <button class="real-verify workflow" onclick="openResearchModal('${escHtml(l.opportunity_id)}','frontier')">Research channel</button>
        ${(l.channels||[]).length ? `<button class="real-verify workflow" onclick="openClearanceModal('${escHtml(l.opportunity_id)}','frontier')">Clear 24h</button>` : ""}
        ${l.call_ready ? `<button class="real-verify workflow ready" onclick="openCallSheet('${escHtml(l.opportunity_id)}')">Call sheet</button>
          <button class="real-verify workflow" onclick="openDispositionModal('${escHtml(l.opportunity_id)}','frontier')">Outcome</button>` : ""}`;
      return `<article class="opp-card">
        <span class="frontier-badge">${escHtml(l.source_frontier || "OFFICIAL FRONTIER")}</span>
        <div class="opp-head">
          <div><div class="real-name">${escHtml(l.name)}</div>
            <div class="opp-meta">${escHtml(l.credential || l.category || "Official entity")} · ${escHtml(l.state || "")} · observed ${escHtml(l.trigger_date || "date unavailable")}</div></div>
          <div class="opp-priority" title="Evidence-completeness priority">${escHtml(l.priority)}</div>
        </div>
        <div class="opp-source">${addr || escHtml(l.contact_quality || "No business address")}<br>${cite}${cite&&sourceRecord?" · ":""}${sourceRecord}</div>
        <div class="frontier-signal"><strong>${escHtml(l.observed_trigger || "Official observation")}</strong><br>${escHtml(l.signal_summary || "")}${fleet?`<br>${fleet}`:""}${facility?`<br>${facility}`:""}${award?`<br>${award}`:""}</div>
        <div class="opp-angle"><strong>${escHtml(l.product_angle || "Licensed business review")}</strong><br>${escHtml(l.why || "")}</div>
        <div class="opp-next"><strong>Next action</strong><br>${escHtml(l.next_action || "")}</div>
        <div class="frontier-limit"><strong>Limit:</strong> ${escHtml((l.limitations||[]).join(" "))}</div>
        <div class="opp-actions">
          <span class="gate ${gateClass}">${escHtml(l.contact_gate || "NOT_EVALUATED")}</span>
          <label class="real-sub" for="frontier-stage-${escHtml(l.opportunity_id)}">Stage</label>
          <select class="opp-stage" id="frontier-stage-${escHtml(l.opportunity_id)}" data-prior="${escHtml(l.stage)}" onchange="updateOpportunity('${escHtml(l.opportunity_id)}',this,'frontier')">
            ${options}
          </select>
          ${verifyBtn}
          ${workflowButtons}
        </div>
      </article>`;
    }).join("")}</div>`;
  } catch (e) {
    body.innerHTML = `<div style="padding:20px;color:var(--hot)">× ${escHtml(e.message)}</div>`;
  }
}

async function updateOpportunity(opportunityId, select, view) {
  const stage = select.value;
  const prior = select.dataset.prior || "REVIEW";
  if (stage === "READY") {
    select.value = prior;
    openClearanceModal(opportunityId, view);
    return;
  }
  select.disabled = true;
  try {
    await api("/api/deal-desk/" + encodeURIComponent(opportunityId), {
      method: "POST",
      body: JSON.stringify({
        stage,
        actor: "David",
        next_action: stage === "RESEARCH"
          ? "Verify the source and find the official business contact channel"
          : "",
      }),
    });
    select.dataset.prior = stage;
    if (view === "frontier") await loadFrontiers();
    else await loadRealLeads();
  } catch (e) {
    select.value = prior;
    window.alert(e.message);
  } finally {
    select.disabled = false;
  }
}

function reloadBrokerDesk(view) {
  closeModal();
  return view === "frontier" ? loadFrontiers() : loadRealLeads();
}

function modalField(id, label, type="text", value="", hint="") {
  return `<label class="workflow-field">${escHtml(label)}
    <input id="${escHtml(id)}" type="${escHtml(type)}" value="${escHtml(value)}" autocomplete="off">
    ${hint ? `<small>${escHtml(hint)}</small>` : ""}
  </label>`;
}

function openResearchModal(opportunityId, view) {
  const item = brokerDeskItems[opportunityId] || {};
  $("modalMount").innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()">
    <div class="modal workflow-modal">
      <button class="mclose" onclick="closeModal()">Close</button>
      <h3>Record business-published channel</h3>
      <div class="mbody">
        <div class="workflow-guard">This records evidence, not contact permission. Use only the business's own HTTPS website. Social profiles, personal mobile numbers, and free-mail addresses are rejected.</div>
        <div class="workflow-form">
          ${modalField("researchActor","Researcher","text","David")}
          <label class="workflow-field">Channel type
            <select id="researchType"><option>BUSINESS_PHONE</option><option>BUSINESS_EMAIL</option><option>WEBSITE_FORM</option><option>WEBSITE</option></select>
          </label>
          ${modalField("researchValue","Business channel","text","","Main business phone, role mailbox, or HTTPS contact URL")}
          ${modalField("researchSource","First-party source URL","url","","Exact HTTPS company page where the channel appears")}
          ${modalField("researchNote","Research note","text",`Verified for ${item.name||"business"}`)}
        </div>
        <div class="workflow-actions"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn primary" id="researchSave" onclick="saveResearch('${escHtml(opportunityId)}','${escHtml(view||"real")}')">Save evidence</button></div>
        <div class="workflow-result" id="researchResult"></div>
      </div>
    </div></div>`;
}

async function saveResearch(opportunityId, view) {
  const button = $("researchSave"); button.disabled = true;
  try {
    await api(`/api/deal-desk/${encodeURIComponent(opportunityId)}/research`, {
      method: "POST",
      body: JSON.stringify({
        actor: $("researchActor").value,
        channel_type: $("researchType").value,
        channel_value: $("researchValue").value,
        source_url: $("researchSource").value,
        publisher_class: "FIRST_PARTY_BUSINESS_WEBSITE",
        note: $("researchNote").value,
      }),
    });
    await reloadBrokerDesk(view);
  } catch (e) {
    $("researchResult").textContent = e.message; button.disabled = false;
  }
}

function openClearanceModal(opportunityId, view) {
  const item = brokerDeskItems[opportunityId] || {};
  const channels = item.channels || [];
  if (!channels.length) {
    openResearchModal(opportunityId, view);
    return;
  }
  const options = channels.map(channel =>
    `<option value="${escHtml(channel.channel_id)}">${escHtml(channel.type)} · ${escHtml(channel.value)} · ${escHtml(channel.source_host)}</option>`
  ).join("");
  $("modalMount").innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()">
    <div class="modal workflow-modal">
      <button class="mclose" onclick="closeModal()">Close</button>
      <h3>Issue time-limited outreach clearance</h3>
      <div class="mbody">
        <div class="workflow-guard">Every box is an execution-time assertion by the operator. Clearance expires in 24 hours and is revoked by suppression, research, block, or loss transitions.</div>
        <div class="workflow-form">
          ${modalField("clearActor","Licensed operator","text","David")}
          <label class="workflow-field wide">Verified channel<select id="clearChannel">${options}</select></label>
          ${modalField("clearPurpose","Truthful business purpose","text","Licensed business coverage and continuity review")}
          ${modalField("clearTalk","Talk-track version","text","DL-B2B-MANUAL-v1")}
          ${modalField("clearState","Broker jurisdiction","text",item.state||"")}
          ${modalField("clearScope","License / appointment scope","text","","Record the applicable line, state, and carrier/agency authority")}
        </div>
        <div class="workflow-checks">
          <label><input type="checkbox" id="checkFederal"> Federal/company suppression checked</label>
          <label><input type="checkbox" id="checkState"> Applicable state suppression checked</label>
          <label><input type="checkbox" id="checkOptout"> No prior opt-out or do-not-contact request</label>
          <label><input type="checkbox" id="checkRules"> Licensing and channel rules reviewed now</label>
        </div>
        <div class="workflow-actions"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn primary" id="clearSave" onclick="saveClearance('${escHtml(opportunityId)}','${escHtml(view||"real")}')">Issue 24-hour clearance</button></div>
        <div class="workflow-result" id="clearResult"></div>
      </div>
    </div></div>`;
}

async function saveClearance(opportunityId, view) {
  const button = $("clearSave"); button.disabled = true;
  try {
    await api(`/api/deal-desk/${encodeURIComponent(opportunityId)}/clearance`, {
      method: "POST",
      body: JSON.stringify({
        actor: $("clearActor").value,
        channel_id: $("clearChannel").value,
        business_purpose: $("clearPurpose").value,
        talk_track_version: $("clearTalk").value,
        broker_jurisdiction: $("clearState").value,
        license_scope: $("clearScope").value,
        federal_dnc_checked: $("checkFederal").checked,
        state_dnc_checked: $("checkState").checked,
        opt_out_checked: $("checkOptout").checked,
        rules_reviewed: $("checkRules").checked,
        expires_hours: 24,
      }),
    });
    await reloadBrokerDesk(view);
  } catch (e) {
    $("clearResult").textContent = e.message; button.disabled = false;
  }
}

async function openCallSheet(opportunityId) {
  $("modalMount").innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()"><div class="modal workflow-modal">
    <button class="mclose" onclick="closeModal()">Close</button><h3>Governed broker call sheet</h3>
    <div class="mbody" id="callSheetBody"><div class="skeleton"></div></div></div></div>`;
  try {
    const sheet = await api(`/api/deal-desk/${encodeURIComponent(opportunityId)}/call-sheet`);
    const b = sheet.business || {}, c = sheet.business_channel || {}, t = sheet.talk_track || {};
    $("callSheetBody").innerHTML = `
      <div class="call-sheet-head"><span>CALL READY</span><b>Expires ${escHtml(sheet.clearance_expires_at)}</b></div>
      <h4>${escHtml(b.name)}</h4>
      <div class="call-sheet-grid"><div><small>Verified channel</small><strong>${escHtml(c.type)} · ${escHtml(c.value)}</strong><a href="${escHtml(c.source_url)}" target="_blank" rel="noopener">First-party source ↗</a></div>
      <div><small>Clearance receipt</small><strong>${escHtml(sheet.clearance_receipt)}</strong><span>${escHtml(sheet.jurisdiction)} · ${escHtml(sheet.license_scope)}</span></div></div>
      <div class="workflow-guard">${escHtml(b.official_signal||"Official signal")}<br><strong>Limits:</strong> ${escHtml((b.limitations||[]).join(" "))}</div>
      <h4>Manual opening</h4><div class="call-script">${escHtml(t.opening)}</div>
      <h4>Discovery</h4><ol>${(t.discovery_questions||[]).map(q=>`<li>${escHtml(q)}</li>`).join("")}</ol>
      <h4>Do not say or do</h4><ul>${(t.prohibited_claims||[]).map(q=>`<li>${escHtml(q)}</li>`).join("")}</ul>`;
  } catch (e) {
    $("callSheetBody").innerHTML = `<div class="workflow-result">${escHtml(e.message)}</div>`;
  }
}

function openDispositionModal(opportunityId, view) {
  const options = ["NO_ANSWER","LEFT_VOICEMAIL","CONNECTED","MEETING_BOOKED","NOT_INTERESTED","FOLLOW_UP","DO_NOT_CALL","WRONG_BUSINESS"];
  $("modalMount").innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()"><div class="modal workflow-modal">
    <button class="mclose" onclick="closeModal()">Close</button><h3>Record observed outcome</h3><div class="mbody">
      <div class="workflow-form">${modalField("dispActor","Operator","text","David")}
      <label class="workflow-field">Disposition<select id="dispValue">${options.map(v=>`<option>${v}</option>`).join("")}</select></label>
      ${modalField("dispNote","Factual note","text","")}${modalField("dispFollow","Follow-up date/time","datetime-local","")}</div>
      <div class="workflow-actions"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn primary" id="dispSave" onclick="saveDisposition('${escHtml(opportunityId)}','${escHtml(view||"real")}')">Record outcome</button></div>
      <div class="workflow-result" id="dispResult"></div>
    </div></div></div>`;
}

async function saveDisposition(opportunityId, view) {
  const button = $("dispSave"); button.disabled = true;
  try {
    await api(`/api/deal-desk/${encodeURIComponent(opportunityId)}/disposition`, {
      method: "POST",
      body: JSON.stringify({
        actor: $("dispActor").value,
        disposition: $("dispValue").value,
        note: $("dispNote").value,
        follow_up_at: $("dispFollow").value || null,
      }),
    });
    await reloadBrokerDesk(view);
  } catch (e) {
    $("dispResult").textContent = e.message; button.disabled = false;
  }
}

async function exportBrokerDesk() {
  try {
    const response = await fetch("/api/deal-desk-export.csv", {headers:{Authorization:"Bearer "+token}});
    if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
    const blob = await response.blob(), link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "david-leads-opportunities.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  } catch (e) {
    window.alert(e.message);
  }
}

function openDataPolicy() {
  const card = $("policyCard"); if (!card) return;
  card.style.display = "block";
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  loadDataPolicy();
}

async function loadDataPolicy() {
  const body = $("policyBody"); if (!body) return;
  try {
    const policy = await api("/api/data-policy");
    $("policyMeta").textContent = `v${policy.version} · ${policy.legal_status}`;
    body.innerHTML = `<div class="policy-grid">${(policy.source_classes||[]).map(item => `
      <div class="policy-item">
        <h4>${escHtml(item.label)} · ${escHtml(item.ingestion)}</h4>
        <p>${escHtml((item.controls||[]).join(" "))}</p>
      </div>`).join("")}</div>
      <div class="tax-sub-h">Implemented frontiers</div>
      <div class="policy-grid">${(policy.implemented_frontiers||[]).map(item => `
        <div class="policy-item">
          <h4>${escHtml(item.id)} · ${escHtml(item.status)}</h4>
          <p>${escHtml(item.purpose || "")}</p>
        </div>`).join("")}</div>
      <div class="tax-sub-h">Deferred or blocked</div>
      <div class="policy-grid">${(policy.deferred_frontiers||[]).map(item => `
        <div class="policy-item">
          <h4>${escHtml(item.id)} · ${escHtml(item.status)}</h4>
          <p>${escHtml(item.reason || "")}</p>
        </div>`).join("")}</div>
      <div class="real-banner">Purpose: ${escHtml(policy.purpose)} Counsel review is required before automated outreach, social ingestion, purchased personal data, consumer profiling, or cross-state campaigns.</div>`;
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
