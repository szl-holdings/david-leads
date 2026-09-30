/* david-leads v0 minimal UI — no build step, no external dependencies.
   Renders honest source states, the labeled synthetic demo set, and one
   receipted scoring decision at a time. */

const stateClass = (s) =>
  ({ VERIFIED: "verified", UNKNOWN: "unknown", UNAVAILABLE: "unavailable", INCOMPLETE: "incomplete" }[s] || "unknown");

async function getJSON(url, opts) {
  const r = await fetch(url, opts);
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error((body && body.detail) || `HTTP ${r.status}`);
  return body;
}

async function loadSources() {
  const tbody = document.querySelector("#sources tbody");
  try {
    const data = await getJSON("/v1/sources");
    tbody.innerHTML = "";
    for (const a of data.adapters) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${a.name}</td><td>${a.kind}</td>` +
        `<td><span class="chip ${stateClass(a.truth_state)}">${a.truth_state}</span></td>` +
        `<td>${a.detail}</td>`;
      tbody.appendChild(tr);
    }
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4">source states UNAVAILABLE: ${e.message}</td></tr>`;
  }
}

async function loadLeads() {
  const host = document.querySelector("#leads");
  try {
    const data = await getJSON("/v1/leads");
    host.innerHTML = "";
    for (const lead of data.leads) {
      const div = document.createElement("div");
      div.className = "lead";
      const info = document.createElement("div");
      info.innerHTML =
        `<div>${lead.legal_name}</div>` +
        `<div class="meta">${lead.id} · ${lead.state || "state UNKNOWN"} · ` +
        `${lead.signals.length} signal(s) · synthetic=${lead.synthetic}</div>`;
      const btn = document.createElement("button");
      btn.textContent = "Score";
      btn.onclick = () => scoreLead(lead.id);
      div.append(info, btn);
      host.appendChild(div);
    }
    if (!data.leads.length) host.textContent = "No demo records loaded; see /v1/leads for the adapter state.";
  } catch (e) {
    host.textContent = `demo dataset UNAVAILABLE: ${e.message}`;
  }
}

let lastReceipt = null;

async function scoreLead(id) {
  const section = document.querySelector("#result");
  const summary = document.querySelector("#result-summary");
  const pre = document.querySelector("#receipt");
  const verifyOut = document.querySelector("#verify-out");
  verifyOut.hidden = true;
  try {
    const data = await getJSON("/v1/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lead_id: id }),
    });
    lastReceipt = data.receipt;
    const scoreText =
      data.score === null
        ? "no score emitted"
        : `<span class="big">${data.score}</span> / 100 · bucket ${data.bucket}`;
    summary.innerHTML =
      `<div>${data.legal_name}</div>` +
      `<div>${scoreText} · <span class="chip ${stateClass(data.truth_state)}">${data.truth_state}</span></div>` +
      `<div class="meta" style="color:var(--muted);font-size:0.78rem">` +
      `${data.admitted_signals} admitted signal(s), ${data.denied_signals.length} denied · ` +
      `receipt ${data.receipt.receipt_id} · ${data.receipt.signature_status}</div>` +
      data.disclaimers.map((d) => `<div class="meta" style="color:var(--muted);font-size:0.78rem">${d}</div>`).join("");
    pre.textContent = JSON.stringify(data.receipt, null, 2);
    section.hidden = false;
    section.scrollIntoView({ behavior: "smooth" });
  } catch (e) {
    summary.textContent = `scoring UNAVAILABLE: ${e.message}`;
    pre.textContent = "";
    section.hidden = false;
  }
}

async function verifyReceipt() {
  const out = document.querySelector("#verify-out");
  if (!lastReceipt) return;
  try {
    const data = await getJSON("/v1/receipts/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ receipt: lastReceipt }),
    });
    out.textContent = JSON.stringify(data, null, 2);
    out.hidden = false;
  } catch (e) {
    out.textContent = `verification UNAVAILABLE: ${e.message}`;
    out.hidden = false;
  }
}

document.querySelector("#verify-btn").addEventListener("click", verifyReceipt);
loadSources();
loadLeads();
