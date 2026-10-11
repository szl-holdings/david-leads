/* david-leads v0 UI — no build step, no external dependencies.
   Renders honest source states, the labeled synthetic demo set, and one
   receipted scoring decision at a time. */

function stateClass(state) {
  const names = { VERIFIED: "verified", UNKNOWN: "unknown", UNAVAILABLE: "unavailable", INCOMPLETE: "incomplete" };
  return Object.hasOwn(names, state) ? names[state] : "unknown";
}

function textNode(tag, text, className = "") {
  const node = document.createElement(tag);
  node.textContent = String(text ?? "UNKNOWN");
  if (className) node.className = className;
  return node;
}

async function getJSON(url, opts) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 20000);
  try {
    const r = await fetch(url, { ...opts, signal: controller.signal });
    const body = await r.json().catch(() => null);
    if (!r.ok) throw new Error((body && body.detail) || `HTTP ${r.status}`);
    return body;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("Request timed out; no result was received.");
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

async function loadSources() {
  const tbody = document.querySelector("#sources tbody");
  try {
    const data = await getJSON("v1/sources");
    if (!Array.isArray(data?.adapters)) throw new Error("Source response is incomplete.");
    const rows = data.adapters.map((a) => {
      const tr = document.createElement("tr");
      const state = document.createElement("td");
      state.append(textNode("span", a.truth_state, `chip ${stateClass(a.truth_state)}`));
      tr.append(textNode("td", a.name), textNode("td", a.kind), state, textNode("td", a.detail));
      return tr;
    });
    if (!rows.length) {
      const tr = document.createElement("tr");
      const cell = textNode("td", "Source states UNKNOWN: no adapters were reported.");
      cell.colSpan = 4;
      tr.append(cell);
      rows.push(tr);
    }
    tbody.replaceChildren(...rows);
  } catch (e) {
    const tr = document.createElement("tr");
    const cell = textNode("td", `source states UNAVAILABLE: ${e.message}`);
    cell.colSpan = 4;
    tr.append(cell);
    tbody.replaceChildren(tr);
  }
}

async function loadLeads() {
  const host = document.querySelector("#leads");
  try {
    const data = await getJSON("v1/leads");
    if (!Array.isArray(data?.leads)) throw new Error("Demonstration response is incomplete.");
    const rows = data.leads.map((lead) => {
      const div = document.createElement("div");
      div.className = "lead";
      const info = document.createElement("div");
      info.append(
        textNode("div", lead.legal_name, "lead-name"),
        textNode("div", `${lead.id} · ${lead.state || "state UNKNOWN"} · ` +
          `${Array.isArray(lead.signals) ? lead.signals.length : "UNKNOWN"} signal(s) · synthetic=${lead.synthetic}`, "meta"),
      );
      const btn = textNode("button", "Score");
      btn.type = "button";
      btn.setAttribute("aria-label", `Score ${lead.legal_name}`);
      btn.onclick = () => scoreLead(lead.id);
      div.append(info, btn);
      return div;
    });
    host.replaceChildren(...rows);
    if (!rows.length) host.textContent = "No demo records loaded. Inspect the source states above.";
  } catch (e) {
    host.textContent = `demo dataset UNAVAILABLE: ${e.message}`;
  }
}

let lastReceipt = null;
let scoreRequest = 0;
let verificationRequest = 0;

async function scoreLead(id) {
  const request = ++scoreRequest;
  ++verificationRequest;
  lastReceipt = null;
  const section = document.querySelector("#result");
  const summary = document.querySelector("#result-summary");
  const pre = document.querySelector("#receipt");
  const verifyOut = document.querySelector("#verify-out");
  const verifyButton = document.querySelector("#verify-btn");
  verifyButton.disabled = true;
  verifyOut.hidden = true;
  verifyOut.textContent = "";
  pre.textContent = "";
  summary.textContent = "Scoring the selected demonstration record…";
  section.hidden = false;
  section.setAttribute("aria-busy", "true");
  try {
    const data = await getJSON("v1/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lead_id: id }),
    });
    if (request !== scoreRequest) return;
    if (!data || !data.receipt || typeof data.receipt !== "object"
        || (data.score !== null && !Number.isFinite(data.score))
        || !Array.isArray(data.denied_signals) || !Array.isArray(data.disclaimers)) {
      throw new Error("Scoring response is incomplete; no current receipt is available.");
    }
    const score = document.createElement("div");
    if (data.score === null) score.append(textNode("span", "no score emitted"));
    else score.append(textNode("span", data.score, "big"), textNode("span", ` / 100 · bucket ${data.bucket}`));
    score.append(textNode("span", " · "), textNode("span", data.truth_state, `chip ${stateClass(data.truth_state)}`));
    summary.replaceChildren(
      textNode("div", data.legal_name, "lead-name"), score,
      textNode("div", `${data.admitted_signals} admitted signal(s), ${data.denied_signals.length} denied · ` +
        `receipt ${data.receipt.receipt_id} · ${data.receipt.signature_status}`, "meta"),
      ...data.disclaimers.map((d) => textNode("div", d, "meta")),
    );
    pre.textContent = JSON.stringify(data.receipt, null, 2);
    lastReceipt = data.receipt;
    verifyButton.disabled = false;
    section.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  } catch (e) {
    if (request !== scoreRequest) return;
    lastReceipt = null;
    summary.textContent = `scoring UNAVAILABLE: ${e.message}`;
    pre.textContent = "";
    verifyButton.disabled = true;
  } finally {
    if (request === scoreRequest) section.setAttribute("aria-busy", "false");
  }
}

async function verifyReceipt() {
  if (!lastReceipt) return;
  const receipt = lastReceipt;
  const request = ++verificationRequest;
  const out = document.querySelector("#verify-out");
  const button = document.querySelector("#verify-btn");
  button.disabled = true;
  out.textContent = "Verifying receipt integrity…";
  out.hidden = false;
  try {
    const data = await getJSON("v1/receipts/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ receipt }),
    });
    if (request !== verificationRequest || receipt !== lastReceipt) return;
    if (!data || typeof data !== "object") throw new Error("Verification response is incomplete.");
    out.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    if (request !== verificationRequest || receipt !== lastReceipt) return;
    out.textContent = `verification UNAVAILABLE: ${e.message}`;
  } finally {
    if (request === verificationRequest && receipt === lastReceipt) button.disabled = false;
  }
}

document.querySelector("#verify-btn").addEventListener("click", verifyReceipt);
loadSources();
loadLeads();
