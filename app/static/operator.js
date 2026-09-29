"use strict";

// No protected fetch runs during public bootstrap. Tokens and evidence live only
// in this closure and are cleared on sign-out, expiry, and page lifecycle exit.
function createOperatorWorkspace(env) {
  const { document, fetch, crypto, setTimeout, clearTimeout } = env;
  const byId = (id) => document.getElementById(id);
  const forms = () => [...document.querySelectorAll("[data-operator-action]")];
  const nodeSelects = () => [...document.querySelectorAll("[data-node-kind]")];
  const sourceKinds = new Set(["source", "observation"]);
  const factsAllowed = new Set(["organization_name", "legal_name", "state", "city", "postal", "participant_count", "plan_name", "plan_year", "form_year", "filing_date", "plan_begin_date", "plan_end_date", "reported_life_benefit", "source_url", "event_type", "observed_change", "industry", "plan_year_begin", "plan_year_end", "amended_filing"]);
  let token = "", user = "", scope = "", workspace = null, pending = false;
  let generation = 0, sessionTimer = null, taskRetry = null;
  let selected = new Set();

  function text(tag, value, className) {
    const element = document.createElement(tag);
    element.textContent = String(value ?? "");
    if (className) element.className = className;
    return element;
  }
  function label(value) { return String(value || "Unknown").replaceAll("_", " ").toLowerCase(); }
  function status(message, kind = "info") {
    byId("operatorStatus").textContent = message;
    byId("operatorStatus").dataset.state = kind;
  }
  function updateControls() {
    byId("operatorWorkspace").setAttribute("aria-busy", String(pending));
    byId("operatorReload").disabled = pending || !scope || !token;
    for (const form of forms()) {
      const permitted = workspace?.available_actions?.includes(form.dataset.operatorAction);
      for (const control of form.querySelectorAll("button, input, select")) {
        control.disabled = pending || !workspace || !permitted;
      }
      form.dataset.permission = permitted ? "available" : "unavailable";
      let note = form.querySelector(".operator-permission-note");
      if (!note) { note = text("p", "", "operator-permission-note"); form.append(note); }
      note.textContent = workspace && !permitted ? "This action is not included in your current operator policy." : "";
    }
    for (const element of byId("operatorScopeForm").querySelectorAll("input, button")) {
      if (element.id !== "operatorReload") element.disabled = pending;
    }
  }
  function clearEvidence() {
    workspace = null;
    selected.clear();
    for (const id of ["operatorEvidenceList", "operatorHistory", "operatorBriefPreview", "operatorActionResult", "operatorDiffResult", "operatorSourceHealth"]) byId(id).replaceChildren();
    for (const select of nodeSelects()) select.replaceChildren();
    byId("operatorScopeLabel").textContent = "";
    byId("operatorEpoch").textContent = "—";
    byId("operatorNodeCount").textContent = "—";
    byId("operatorLoadedAt").textContent = "—";
    byId("operatorWorkspace").hidden = true;
    updateSelection();
  }
  function reset(message = "Signed out. Protected research has been cleared.") {
    generation += 1;
    clearTimeout(sessionTimer);
    sessionTimer = null;
    token = ""; user = ""; scope = ""; pending = false; taskRetry = null;
    clearEvidence();
    byId("operatorLogin").reset();
    byId("operatorLogin").querySelector("button").disabled = false;
    byId("operatorScopeForm").reset();
    for (const form of forms()) form.reset();
    byId("operatorSessionLabel").textContent = "";
    byId("operatorSession").hidden = true;
    byId("operatorLogin").hidden = false;
    updateControls();
    status(message);
  }
  async function request(path, body, authToken = token) {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      cache: "no-store", credentials: "omit", redirect: "error",
      headers: { Accept: "application/json", ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}), ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload?.detail;
      const code = typeof detail === "object" && detail !== null ? detail.code : null;
      const error = new Error(typeof code === "string" && /^[A-Z0-9_]{1,100}$/.test(code) ? code : `REQUEST_FAILED_${response.status}`);
      error.status = response.status;
      throw error;
    }
    if (!payload || typeof payload !== "object") throw new Error("INVALID_SERVER_RESPONSE");
    return payload;
  }
  function path(suffix = "") { return `/api/v1/operator/workspaces/${encodeURIComponent(scope)}${suffix}`; }
  function errorMessage(error) {
    if (error.status === 401) return "Your session is no longer valid. Sign in again.";
    if (error.status === 403) return `Access held: ${label(error.message)}. Current policy and source rights must be admitted by the operator administrator.`;
    if (error.status === 409) return `Decision held: ${label(error.message)}. Review the reloaded evidence before trying again.`;
    if (error.status === 503) return `Research is unavailable: ${label(error.message)}. No success was recorded by this interface.`;
    return `Request could not be confirmed: ${label(error.message)}. Reload before making another decision.`;
  }
  async function signIn(event) {
    event.preventDefault();
    if (pending) return;
    pending = true;
    const serial = ++generation;
    const button = byId("operatorLogin").querySelector("button");
    button.disabled = true;
    status("Checking operator credentials…", "pending");
    const credentials = { username: byId("operatorUsername").value.trim(), password: byId("operatorPassword").value, access_key: byId("operatorAccessKey").value };
    byId("operatorPassword").value = "";
    byId("operatorAccessKey").value = "";
    try {
      const result = await request("/api/login", credentials, "");
      if (generation !== serial) return;
      if (typeof result.token !== "string" || !result.token || typeof result.user !== "string" || !Number.isFinite(result.expires_in) || result.expires_in <= 0) throw new Error("INVALID_SESSION_RESPONSE");
      token = result.token; user = result.user;
      byId("operatorLogin").reset();
      byId("operatorLogin").hidden = true;
      byId("operatorSession").hidden = false;
      byId("operatorSessionLabel").textContent = `Signed in as ${user}. Research permissions are checked for every request.`;
      sessionTimer = setTimeout(() => reset("Session expired. Protected research has been cleared. Sign in again."), Math.min(result.expires_in * 1000, 2147483647));
      status("Signed in. Open your assigned research workspace to check access.");
      byId("operatorScope").focus();
    } catch (error) {
      if (generation === serial) status(errorMessage(error), "error");
    } finally {
      if (generation === serial) { pending = false; button.disabled = false; updateControls(); }
    }
  }
  async function signOut() {
    const previousToken = token;
    reset();
    const serial = generation;
    if (!previousToken) return;
    try { await request("/api/logout", {}, previousToken); }
    catch (_) { if (serial === generation) status("Local research was cleared. Server sign-out could not be confirmed; the server session will expire.", "error"); }
  }
  function admitWorkspace(payload) {
    if (payload.schema !== "szl.david.workspace/v2" || payload.scope_id !== scope || !Number.isSafeInteger(payload.decision_epoch) || payload.decision_epoch < 0 || !Array.isArray(payload.nodes) || !Array.isArray(payload.available_actions) || payload.contact_permission !== "NOT_GRANTED") throw new Error("WORKSPACE_CONTRACT_INVALID");
    for (const node of payload.nodes) {
      if (!node || !/^[0-9a-f]{64}$/.test(node.id) || typeof node.kind !== "string" || typeof node.state !== "string" || node.scope_id !== scope) throw new Error("EVIDENCE_CONTRACT_INVALID");
    }
    workspace = payload;
    selected = new Set([...selected].filter((id) => payload.nodes.some((node) => node.id === id && node.state === "VALID" && sourceKinds.has(node.kind))));
    render();
  }
  async function loadWorkspace(silent = false, serial = generation) {
    const result = await request(path());
    if (serial !== generation || !token) return false;
    admitWorkspace(result);
    if (!silent) status(result.nodes.length ? "Evidence loaded. Review the current records before making a decision." : "This workspace has no admitted evidence. Admit an approved source reference to begin.");
    return true;
  }
  async function openWorkspace(event) {
    event?.preventDefault();
    if (pending || !token) return;
    const requested = byId("operatorScope").value.trim();
    if (!/^[A-Za-z0-9_.:-]{1,128}$/.test(requested)) { status("Enter a workspace ID using letters, numbers, periods, colons, hyphens, or underscores.", "error"); return; }
    const serial = ++generation;
    if (scope !== requested) { taskRetry = null; clearEvidence(); }
    scope = requested;
    pending = true; workspace = null; updateControls();
    status("Loading current evidence and operator permissions…", "pending");
    try { await loadWorkspace(false, serial); }
    catch (error) {
      if (serial !== generation) return;
      clearEvidence();
      if (error.status === 401) reset(errorMessage(error));
      else status(errorMessage(error), "error");
    } finally { if (serial === generation) { pending = false; updateControls(); } }
  }
  function updateSelection() { byId("operatorSelectionCount").textContent = `${selected.size} source record${selected.size === 1 ? "" : "s"} selected`; }
  function sourceIds() {
    if (!selected.size) throw new Error("SELECT_SOURCE_RECORDS_FIRST");
    return [...selected];
  }
  function reference(id) {
    const value = byId(id).value;
    if (!/^[0-9a-f]{64}$/.test(value)) throw new Error("SELECT_A_CURRENT_EVIDENCE_RECORD");
    return value;
  }
  function appendFacts(parent, facts) {
    if (!facts || typeof facts !== "object" || Array.isArray(facts)) return;
    const list = document.createElement("dl");
    list.className = "operator-facts";
    for (const [name, value] of Object.entries(facts)) {
      if (!factsAllowed.has(name) || (value !== null && !["string", "number", "boolean"].includes(typeof value))) continue;
      list.append(text("dt", label(name)));
      const item = text("dd", value === null ? "Unknown" : value);
      if (name === "source_url" && typeof value === "string") {
        try {
          const url = new URL(value);
          if (url.protocol === "https:") {
            const link = text("a", "Open original source ↗");
            link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
            item.replaceChildren(link);
          }
        } catch (_) { item.textContent = "Source link unavailable"; }
      }
      list.append(item);
    }
    parent.append(list);
  }
  function appendDetail(parent, detail) {
    if (!detail || typeof detail !== "object") return;
    for (const name of ["summary", "decision", "reason", "task_type", "outcome", "next_verification"]) {
      if (typeof detail[name] === "string") parent.append(text("p", `${label(name)}: ${detail[name]}`));
    }
    if (Array.isArray(detail.limitations)) {
      const list = document.createElement("ul");
      for (const item of detail.limitations) if (typeof item === "string") list.append(text("li", item));
      parent.append(list);
    }
    if (Array.isArray(detail.facts)) for (const row of detail.facts) {
      if (!row || typeof row !== "object") continue;
      parent.append(text("p", `Source ${typeof row.source_node_id === "string" ? row.source_node_id.slice(0, 12) : "unavailable"} · Published ${typeof row.published_at === "string" ? row.published_at : "unknown"} · Observed ${typeof row.observed_at === "string" ? row.observed_at : "unknown"}`, "operator-fineprint"));
      if (typeof row.snapshot_published_at === "string") parent.append(text("p", `Snapshot published ${row.snapshot_published_at}. Original filing publication time is unknown.`, "operator-fineprint"));
      appendFacts(parent, row.fields);
    }
  }
  function nodeCard(node, selectable = false) {
    const card = document.createElement("details"); card.className = "operator-node";
    const summary = document.createElement("summary");
    const title = node.state === "VALID" ? node.facts?.organization_name || node.facts?.legal_name : null;
    summary.append(text("span", title || label(node.kind)), text("span", node.state, "operator-node-state"));
    card.append(summary);
    const body = document.createElement("div"); body.className = "operator-node-body";
    body.append(text("code", node.id), text("p", `Expires ${node.expires_at || "unknown"}`, "operator-fineprint"));
    if (node.state === "VALID") { appendFacts(body, node.facts); appendDetail(body, node.detail); }
    else body.append(text("p", "Facts are withheld because this record is not currently valid."));
    if (Array.isArray(node.parents) && node.parents.length) {
      body.append(text("p", "Dependency references", "operator-fineprint"));
      for (const id of node.parents) if (typeof id === "string" && /^[0-9a-f]{64}$/.test(id)) body.append(text("code", id, "operator-parent"));
    }
    if (selectable && node.state === "VALID") {
      const choice = document.createElement("label"); choice.className = "operator-check";
      const input = document.createElement("input"); input.type = "checkbox"; input.checked = selected.has(node.id); input.dataset.sourceNodeId = node.id;
      input.addEventListener("change", () => { if (input.checked) selected.add(node.id); else selected.delete(node.id); updateSelection(); });
      choice.append(input, text("span", "Use this source in the next review")); body.append(choice);
    }
    card.append(body); return card;
  }
  function renderBriefPreview() {
    const container = byId("operatorBriefPreview"); container.replaceChildren();
    const selectedBrief = workspace?.nodes.find((node) => node.id === byId("operatorBriefRef").value && node.kind === "brief" && node.state === "VALID");
    if (selectedBrief) { container.append(text("h4", "Selected brief")); appendDetail(container, selectedBrief.detail); }
  }
  function renderSourceHealth() {
    const container = byId("operatorSourceHealth"); container.replaceChildren();
    const health = workspace?.source_health;
    if (!health || typeof health !== "object") { container.append(text("p", "Source health has not been evaluated. No successful observation is claimed.", "operator-empty")); return; }
    const list = document.createElement("dl"); list.className = "operator-facts";
    const fields = { status: "Overall state", configured_enabled: "Configured", policy_state: "Policy", credential_state: "Credentials", transport_state: "Transport", schema_state: "Schema", integrity_state: "Integrity", completeness_state: "Completeness", freshness_state: "Freshness", last_attempt_at: "Last attempt", last_success_at: "Last success", snapshot_revision: "Snapshot revision" };
    for (const [key, title] of Object.entries(fields)) {
      const value = health[key];
      const display = key === "configured_enabled" ? value === true ? "Enabled; checks still required" : value === false ? "Disabled" : "Unknown" : typeof value === "string" && value ? value : "Not observed";
      list.append(text("dt", title), text("dd", display));
    }
    container.append(list);
    for (const [key, title] of [["blocking_reasons", "Blocking reasons"], ["eligible_operations", "Eligible operations"]]) {
      const values = Array.isArray(health[key]) ? health[key].filter((value) => typeof value === "string") : [];
      container.append(text("p", `${title}: ${values.length ? values.map(label).join(", ") : "None reported"}`, "operator-fineprint"));
    }
  }
  function render() {
    byId("operatorBriefDecision").value = "REJECTED";
    byId("operatorIdentityDecision").value = "NEEDS_REVIEW";
    byId("operatorSuppressConfirm").checked = false;
    byId("operatorWorkspace").hidden = false;
    byId("operatorScopeLabel").textContent = scope;
    byId("operatorEpoch").textContent = String(workspace.decision_epoch);
    byId("operatorNodeCount").textContent = String(workspace.nodes.length);
    byId("operatorLoadedAt").textContent = new Date().toLocaleTimeString();
    for (const [id, nodes] of [["operatorEvidenceList", workspace.nodes.filter((node) => sourceKinds.has(node.kind))], ["operatorHistory", workspace.nodes.filter((node) => !sourceKinds.has(node.kind))]]) {
      const container = byId(id); container.replaceChildren();
      if (!nodes.length) container.append(text("p", id === "operatorEvidenceList" ? "No source records admitted." : "Your decisions will appear here.", "operator-empty"));
      for (const node of nodes) container.append(nodeCard(node, id === "operatorEvidenceList"));
    }
    for (const select of nodeSelects()) {
      const previous = select.value;
      select.replaceChildren();
      const placeholder = text("option", "Choose a current record"); placeholder.value = ""; select.append(placeholder);
      const kinds = select.dataset.nodeKind.split(",");
      const nodes = workspace.nodes.filter((node) => node.state === "VALID" && (kinds.includes("*") || kinds.includes(node.kind)) && (!select.dataset.nodeDecision || node.detail?.decision === select.dataset.nodeDecision));
      for (const node of nodes) {
        const option = text("option", `${label(node.kind)} · ${node.id.slice(0, 12)}${node.detail?.decision ? ` · ${label(node.detail.decision)}` : ""}`);
        option.value = node.id; select.append(option);
      }
      if (nodes.some((node) => node.id === previous)) select.value = previous;
      else select.value = "";
    }
    updateSelection(); renderBriefPreview(); renderSourceHealth(); updateControls();
  }
  function showResult(result, endpoint) {
    const container = byId("operatorActionResult"); container.replaceChildren();
    container.append(text("h3", endpoint === "/source-refreshes" ? "Source check recorded" : "Server response recorded"));
    if (typeof result.id === "string" && /^[0-9a-f]{64}$/.test(result.id)) container.append(text("p", `Evidence reference: ${result.id}`));
    if (endpoint === "/corrections" && Array.isArray(result.impact)) {
      container.append(text("p", `${Number.isSafeInteger(result.revoked) ? result.revoked : result.impact.length} record(s) revoked. Impact on current evidence:`));
      const list = document.createElement("ul");
      for (const item of result.impact) if (item && typeof item.id === "string" && typeof item.kind === "string" && typeof item.state === "string") list.append(text("li", `${label(item.kind)} · ${item.id.slice(0, 12)} · ${item.state}`));
      container.append(list, text("p", "External recall is not guaranteed."));
    }
    if (endpoint === "/suppressions") container.append(text("p", "Workspace suppression recorded. External recall is not guaranteed."));
  }
  async function mutate(endpoint, buildBody) {
    if (pending || !token || !workspace) return;
    const serial = generation;
    let body;
    try { body = { ...buildBody(), expected_epoch: workspace.decision_epoch }; }
    catch (error) { status(errorMessage(error), "error"); return; }
    pending = true; updateControls();
    status("Submitting the decision for server validation…", "pending");
    let committed = false;
    try {
      const result = await request(path(endpoint), body);
      if (serial !== generation || !token) return;
      committed = true;
      if (endpoint === "/tasks") taskRetry = null;
      showResult(result, endpoint);
      await loadWorkspace(true, serial);
      if (serial === generation) status(endpoint === "/source-refreshes" ? "Source check recorded. Inspect its health dimensions below; admission remains a separate operation." : "Decision recorded and current evidence reloaded. Contact permission remains not granted.");
    } catch (error) {
      if (serial !== generation) return;
      if (error.status === 401) { reset(errorMessage(error)); return; }
      const failure = errorMessage(error);
      workspace = null;
      try { await loadWorkspace(true, serial); }
      catch (_) { clearEvidence(); }
      if (serial === generation) status(committed ? "The server recorded the decision, but the current evidence could not be reloaded. Reload before continuing." : failure, "error");
    } finally { if (serial === generation) { pending = false; updateControls(); } }
  }
  function taskBody() {
    const body = { clearance_id: reference("operatorClearanceRef"), task_type: byId("operatorTaskType").value };
    const fingerprint = `${scope}:${body.clearance_id}:${body.task_type}`;
    if (!taskRetry || taskRetry.fingerprint !== fingerprint) taskRetry = { fingerprint, key: crypto.randomUUID() };
    return { ...body, idempotency_key: taskRetry.key };
  }
  async function compare(event) {
    event.preventDefault();
    if (pending || !token || !workspace) return;
    let before, after;
    try { before = reference("operatorDiffBefore"); after = reference("operatorDiffAfter"); if (before === after) throw new Error("CHOOSE_TWO_DIFFERENT_BRIEFS"); }
    catch (error) { status(errorMessage(error), "error"); return; }
    const serial = generation;
    pending = true; updateControls(); status("Comparing the stored brief facts…", "pending");
    try {
      const result = await request(path(`/decision-diff?before=${encodeURIComponent(before)}&after=${encodeURIComponent(after)}`));
      if (serial !== generation || !token) return;
      const container = byId("operatorDiffResult"); container.replaceChildren();
      for (const key of ["known_then", "known_later"]) if (typeof result[key] === "string") container.append(text("p", `${label(key)}: ${result[key]}`));
      for (const key of ["added", "removed", "unchanged"]) if (Array.isArray(result[key])) {
        container.append(text("h4", `${label(key)} · ${result[key].length}`));
        for (const id of result[key]) if (typeof id === "string" && /^[0-9a-f]{64}$/.test(id)) container.append(text("code", id, "operator-parent"));
      }
      status("Stored brief comparison loaded. No later evidence was added to an earlier brief.");
    } catch (error) { if (serial === generation) { if (error.status === 401) reset(errorMessage(error)); else status(errorMessage(error), "error"); } }
    finally { if (serial === generation) { pending = false; updateControls(); } }
  }
  function init() {
    byId("operatorLogin").addEventListener("submit", signIn);
    byId("operatorLogout").addEventListener("click", signOut);
    byId("operatorScopeForm").addEventListener("submit", openWorkspace);
    byId("operatorReload").addEventListener("click", openWorkspace);
    byId("operatorBriefRef").addEventListener("change", renderBriefPreview);
    byId("operatorDiff").addEventListener("submit", compare);
    const routes = [
      ["operatorSourceRefresh", "/source-refreshes", () => ({ snapshot_revision: byId("operatorHealthSnapshot").value.trim() })],
      ["operatorAdmission", "/admissions", () => ({ source_id: byId("operatorSource").value, record_id: byId("operatorRecordId").value.trim(), snapshot_revision: byId("operatorSnapshot").value.trim() })],
      ["operatorIdentity", "/identity-reviews", () => ({ source_ids: sourceIds(), decision: byId("operatorIdentityDecision").value })],
      ["operatorBrief", "/briefs", () => ({ source_ids: sourceIds(), identity_review_id: reference("operatorIdentityRef") })],
      ["operatorReview", "/brief-reviews", () => ({ brief_id: reference("operatorBriefRef"), approved: byId("operatorBriefDecision").value === "APPROVED" })],
      ["operatorClearance", "/clearances", () => ({ review_id: reference("operatorReviewRef") })],
      ["operatorTask", "/tasks", taskBody],
      ["operatorCorrection", "/corrections", () => ({ node_id: reference("operatorCorrectionRef"), reason: byId("operatorCorrectionReason").value })],
      ["operatorSuppression", "/suppressions", () => { if (!byId("operatorSuppressConfirm").checked) throw new Error("SUPPRESSION_CONFIRMATION_REQUIRED"); return {}; }],
      ["operatorOutcome", "/outcomes", () => ({ task_id: reference("operatorTaskRef"), outcome: byId("operatorOutcomeType").value })],
      ["operatorCounter", "/counter-evidence", () => ({ source_ids: sourceIds(), reason: byId("operatorCounterReason").value })],
    ];
    for (const [id, endpoint, body] of routes) byId(id).addEventListener("submit", (event) => { event.preventDefault(); return mutate(endpoint, body); });
    env.addEventListener?.("pagehide", () => reset());
    updateControls();
  }
  return { init };
}

if (typeof window !== "undefined") window.DavidOperator = createOperatorWorkspace(window);
