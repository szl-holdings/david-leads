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
      <div class="sub">est. annualized across all leads</div>
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
function renderLeads(leads) {
  $("leadMeta").textContent = leads.length + " scored";
  let rows = leads.map(l => `
    <tr class="lead-row" id="row-${l.id}">
      <td><span class="expander" onclick="toggleLeadDetail('${l.id}')">▸</span></td>
      <td><span class="score-pill" style="color:${l.bucket==='HOT'?'var(--hot)':l.bucket==='WARM'?'#9a6c14':'var(--nurture)'}">${l.score}</span><br><span class="badge ${l.bucket}">${l.bucket}</span></td>
      <td><div class="lead-name" onclick="toggleLeadDetail('${l.id}')" style="cursor:pointer">${l.name}</div><div class="lead-why">${l.why}</div></td>
      <td><div class="prod">${l.product}</div><div class="prem">~${money(l.est_premium)}/yr est.</div></td>
      <td><button class="verify-btn" onclick="openReceipt('${l.receipt_id}','${l.id}')">🔏 Verify Receipt</button></td>
    </tr>
    <tr class="detail-row" id="detail-${l.id}" style="display:none"><td colspan="5"></td></tr>`).join("");
  $("leadsWrap").innerHTML = `<table>
    <thead><tr><th></th><th>Score</th><th>Lead Segment · Why</th><th>NYL Product Match</th><th>Provenance</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
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
  return `<div class="detail-inner">
    <div class="detail-sec"><h4>Why this lead (transparent score)</h4>${axes}</div>
    <div class="detail-sec"><h4>Predictive moments · public sources</h4>${moments}</div>
    <div class="nba-box"><div class="act">▶ Next best action: ${l.nba.action}</div><div class="tt">“${l.nba.talk_track}”</div></div>
  </div>`;
}

/* ---------- signals ---------- */
function renderSignals(sigs, meta) {
  $("sigMeta").textContent = meta.mode;
  $("signals").innerHTML = sigs.map(s => `
    <div class="sig">
      <span class="src">${s.source.replace(/\[SAMPLE\]/,'')}</span>${s.live?'<span class="live">LIVE</span>':'<span class="live smp">PUBLIC</span>'}
      <div class="txt">${s.signal}</div>
      <div class="det">${s.detail||''}</div>
    </div>`).join("");
}

/* ---------- governance ---------- */
function renderGov(g, meta) {
  $("gov").innerHTML = `
    <div class="gov-inner">
      <div class="line"><span class="ok">✓</span> ${g.signals_checked} signals checked</div>
      <div class="line"><span class="ok">${g.all_public?'✓':'✗'}</span> All signals are public data ${g.all_public?'':'(violation!)'}</div>
      <div class="line"><span class="ok">✓</span> ${g.fabricated} fabricated signals (honest by design)</div>
      <div class="line"><span class="ok">✓</span> ${g.rejected_nonpublic} non-public signals rejected</div>
      <div class="verdict">🛡️ ${g.verdict}</div>
    </div>`;
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
      <div style="font-size:11px;color:var(--muted);margin-top:14px">Formula: ${d.formula}<br>Source: ${d.source} · all public · 0 fabricated</div>`;
  } catch (e) {
    $("terrBody").innerHTML = `<div style="color:var(--hot)">✗ ${e.message}</div>`;
  }
}

/* ---------- export call list (CSV) ---------- */
function exportCSV() {
  if (!lastData || !lastData.leads) { alert("Run intelligence first."); return; }
  const rows = [["Rank","Score","Bucket","Lead Segment","NYL Product","Est Premium/yr","Next Best Action","Receipt ID"]];
  lastData.leads.forEach((l, i) => rows.push([i+1, l.score, l.bucket, l.name, l.product, l.est_premium, l.nba.action, l.receipt_id]));
  const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g,'""')}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "david_leads_call_list.csv"; a.click();
  URL.revokeObjectURL(a.href);
}

/* ---------- receipt modal ---------- */
async function openReceipt(rid, leadId) {
  const mount = $("modalMount");
  mount.innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()">
    <div class="modal">
      <button class="mclose" onclick="closeModal()">✕ Close</button>
      <h3>🔏 Compliance-Grade Lead Receipt</h3>
      <div class="mbody" id="rcptBody"><div class="skeleton" style="width:80%;margin:10px 0"></div><div class="skeleton" style="width:60%"></div></div>
    </div></div>`;
  try {
    const r = await api("/api/receipt/" + rid);
    const v = await api("/api/verify/" + rid);
    const checks = v.checks.map(c => `
      <div class="vcheck"><span class="ic ${c.pass?'p':'f'}">${c.pass?'✓':'✗'}</span> ${c.check}</div>`).join("");
    $("rcptBody").innerHTML = `
      <div class="vverdict ${v.verdict==='VERIFIED'?'ok':'bad'}">${v.verdict==='VERIFIED'?'✓ VERIFIED':'✗ FAILED'}</div>
      <div style="font-size:13px;color:var(--muted);margin-bottom:4px">Receipt <code>${r.id}</code> · ${r.signature_status}</div>
      ${checks}
      <div style="font-size:12px;color:var(--muted);margin-top:14px;font-weight:600">Tamper-evident payload (re-derivable hash):</div>
      <div class="codeblock">${JSON.stringify(r.payload, null, 2)}</div>
      <div style="font-size:12px;color:var(--muted);margin-top:10px">payload SHA-256: <code>${r.payload_sha256}</code></div>
    `;
  } catch (e) {
    $("rcptBody").innerHTML = `<div style="color:var(--hot)">✗ ${e.message}</div>`;
  }
}
function closeModal() { $("modalMount").innerHTML = ""; }

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
