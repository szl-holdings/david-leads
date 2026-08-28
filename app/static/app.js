"use strict";

const EASTERN_REGIONS = {
  "All East": ["AL", "CT", "DC", "DE", "FL", "GA", "IL", "IN", "KY", "ME", "MD", "MA", "MI", "MS", "NH", "NJ", "NY", "NC", "OH", "PA", "RI", "SC", "TN", "VT", "VA", "WV", "WI"],
  "New England": ["CT", "ME", "MA", "NH", "RI", "VT"],
  "Mid-Atlantic": ["DC", "DE", "MD", "NJ", "NY", "PA", "VA", "WV"],
  "Great Lakes": ["IL", "IN", "MI", "OH", "WI"],
  "Southeast": ["AL", "FL", "GA", "KY", "MS", "NC", "SC", "TN"],
};

const STATE_NAMES = {
  AL: "Alabama", CT: "Connecticut", DC: "District of Columbia", DE: "Delaware",
  FL: "Florida", GA: "Georgia", IL: "Illinois", IN: "Indiana", KY: "Kentucky",
  ME: "Maine", MD: "Maryland", MA: "Massachusetts", MI: "Michigan",
  MS: "Mississippi", NH: "New Hampshire", NJ: "New Jersey", NY: "New York",
  NC: "North Carolina", OH: "Ohio", PA: "Pennsylvania", RI: "Rhode Island",
  SC: "South Carolina", TN: "Tennessee", VT: "Vermont", VA: "Virginia",
  WV: "West Virginia", WI: "Wisconsin",
};

const SOURCE_NAMES = {
  FEDERAL_CONTRACT: "Federal award activity",
  FMCSA: "Carrier registration",
  EPA_ECHO: "Facility monitoring activity",
  CHICAGO_BUSINESS_LICENSE: "Business license activity",
  SAM_ENTITY: "Federal entity registration",
  FCC_ULS: "Organization license activity",
  BENEFIT_PLAN_TIMING: "Employer life-plan filing",
};

const $ = (id) => document.getElementById(id);
const state = {
  accessMode: null,
  selectedStates: new Set(EASTERN_REGIONS["All East"]),
  board: null,
  leads: [],
  filtered: [],
  sources: [],
  build: null,
  health: null,
  activeView: "leads",
  activeLane: "all",
  controller: null,
  toastTimer: null,
  currentRevision: "",
  releaseCheckTimer: null,
  loadError: "",
  drawerReturnFocus: null,
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const failure = new Error(body.detail || `Request failed (${response.status})`);
    failure.status = response.status;
    const retryAfterHeader = response.headers?.get?.("Retry-After");
    if (retryAfterHeader !== null && retryAfterHeader !== "") {
      const retryAfterSeconds = Number(retryAfterHeader);
      if (Number.isFinite(retryAfterSeconds) && retryAfterSeconds >= 0) {
        failure.retryAfterMs = Math.min(10_000, retryAfterSeconds * 1000);
      }
    }
    throw failure;
  }
  return response.json();
}

const MAX_PUBLIC_REFRESH_RETRIES = 6;
const DEFAULT_PUBLIC_REFRESH_RETRY_MS = 5000;

function waitForRetry(delayMs, signal) {
  return new Promise((resolve, reject) => {
    let timer;
    const onAbort = () => {
      clearTimeout(timer);
      const error = new Error("aborted");
      error.name = "AbortError";
      reject(error);
    };
    if (signal?.aborted) {
      onAbort();
      return;
    }
    timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, delayMs);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

async function fetchFrontierBoard(path, controller) {
  for (let retry = 0; ; retry += 1) {
    try {
      return await api(path, { signal: controller.signal });
    } catch (error) {
      if (
        error.name === "AbortError"
        || error.status !== 429
        || retry >= MAX_PUBLIC_REFRESH_RETRIES
      ) {
        throw error;
      }
      const delayMs = Number.isFinite(error.retryAfterMs)
        ? error.retryAfterMs
        : DEFAULT_PUBLIC_REFRESH_RETRY_MS;
      await waitForRetry(delayMs, controller.signal);
    }
  }
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeUrl(value) {
  try {
    const url = new URL(String(value || ""), window.location.origin);
    return url.protocol === "https:" ? url.href : "#";
  } catch (_) {
    return "#";
  }
}

function unknownValue(value) {
  return value == null || value === "" || value === "--" ? "UNKNOWN" : value;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-US");
}

function sourceHonesty(source) {
  const mode = String(source?.mode || "").toUpperCase();
  const reason = String(source?.reason || "").toUpperCase();
  if (mode === "LIVE") return "MEASURED";
  if (mode === "SAMPLE" || mode === "EXAMPLE" || mode === "SIMULATED") return "SIMULATED";
  if (mode === "NOT_APPLICABLE") return "UNKNOWN";
  if (
    reason.includes("NOT_CONFIGURED")
    || reason.includes("DURABLE_INGEST")
    || reason.includes("REUSE_APPROVAL")
  ) {
    return "ROADMAP";
  }
  return "UNAVAILABLE";
}

function markUnknown(node, isUnknown) {
  if (!node) return;
  node.classList.toggle("unknown", Boolean(isUnknown));
}

function formatMoney(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Not reported";
  if (Math.abs(number) >= 1_000_000_000) return `$${(number / 1_000_000_000).toFixed(1)}B`;
  if (Math.abs(number) >= 1_000_000) return `$${(number / 1_000_000).toFixed(1)}M`;
  if (Math.abs(number) >= 1_000) return `$${(number / 1_000).toFixed(0)}K`;
  return `$${number.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function formatDate(value) {
  if (!value) return "Date unavailable";
  const normalized = /^\d{8}$/.test(String(value))
    ? `${String(value).slice(0, 4)}-${String(value).slice(4, 6)}-${String(value).slice(6, 8)}`
    : value;
  const date = /^\d{4}-\d{2}-\d{2}$/.test(String(normalized))
    ? new Date(`${normalized}T12:00:00`)
    : new Date(normalized);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function relativeTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Live pull complete";
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return "Updated just now";
  if (seconds < 3600) return `Updated ${Math.floor(seconds / 60)}m ago`;
  return `Updated ${Math.floor(seconds / 3600)}h ago`;
}

function sourceName(lead) {
  return SOURCE_NAMES[lead.source_frontier] || lead.source_record?.label || "Official public record";
}

function observedDate(lead) {
  return lead.trigger_date || lead.license_or_issue_date || lead.observed_at || "";
}

function observedValue(lead) {
  const participants = Number(lead.operational_snapshot?.participants_reported);
  if (Number.isFinite(participants) && participants > 0) {
    return {
      value: formatNumber(participants),
      label: "Participants reported",
      raw: participants,
    };
  }
  if (lead.award && Number.isFinite(Number(lead.award.amount))) {
    return {
      value: formatMoney(lead.award.amount),
      label: "Federal award field",
      raw: Number(lead.award.amount),
    };
  }
  const snapshot = lead.operational_snapshot || {};
  const units = Number(snapshot.power_units || snapshot.truck_units || snapshot.total_drivers);
  if (Number.isFinite(units) && units > 0) {
    return {
      value: formatNumber(units),
      label: snapshot.power_units ? "Power units observed" : "Operational units observed",
      raw: 0,
    };
  }
  return {
    value: formatDate(observedDate(lead)),
    label: "Observed date",
    raw: 0,
  };
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.remove("show"), 3200);
}

function renderRegionButtons() {
  $("regionButtons").innerHTML = Object.entries(EASTERN_REGIONS)
    .map(([name, values]) => {
      const active = values.length === state.selectedStates.size
        && values.every((code) => state.selectedStates.has(code));
      return `<button class="region-button${active ? " active" : ""}" type="button" data-region="${esc(name)}" aria-pressed="${active}">${esc(name)}${name === "All East" ? " (27)" : ""}</button>`;
    })
    .join("");
}

function renderStateButtons() {
  $("stateButtons").innerHTML = EASTERN_REGIONS["All East"]
    .map((code) => `<button class="state-button${state.selectedStates.has(code) ? " selected" : ""}" type="button" data-state="${code}" aria-pressed="${state.selectedStates.has(code)}" title="Focus ${esc(STATE_NAMES[code])}">${code}</button>`)
    .join("");
}

function timingSummary(lead) {
  const timing = lead.timing || {};
  const days = Number(timing.days_to_anniversary);
  if (Number.isFinite(days) && timing.next_anniversary) {
    return {
      label: `${formatNumber(days)} days`,
      detail: `Anniversary ${formatDate(timing.next_anniversary)}`,
      urgent: days <= 180,
    };
  }
  return {
    label: formatDate(observedDate(lead)),
    detail: "Official observation",
    urgent: false,
  };
}

function productFit(lead) {
  const fit = Array.isArray(lead.product_fit) ? lead.product_fit.filter(Boolean) : [];
  if (fit.length) return fit.slice(0, 3);
  return [lead.product_angle || lead.product || "Business insurance review"];
}

function evidenceSummary(lead) {
  const evidence = lead.evidence || {};
  const constellation = lead.evidence_constellation || {};
  const proof = constellation.proof || {};
  const clock = constellation.deal_clock || {};
  const sourceCount = Number(evidence.source_count || 1);
  const legacyLabel = sourceCount > 1
    ? `${sourceCount}-source match`
    : (evidence.strength === "DIRECT_FILING" ? "Direct filing" : "Official record");
  const legacyDetail = sourceCount > 1
    ? "Independent official signals"
    : (lead.receipt_signed ? "Signed source receipt" : (lead.receipt_id ? "Source receipt linked" : "Citation linked"));
  return {
    label: proof.grade ? `Proof ${proof.grade} · ${sourceCount} source${sourceCount === 1 ? "" : "s"}` : legacyLabel,
    detail: proof.grade ? `${String(clock.state || "UNKNOWN").replaceAll("_", " ")} · ${proof.dimensions?.integrity || "UNAVAILABLE"}` : legacyDetail,
  };
}

function dealLane(lead) {
  if (lead.source_frontier === "BENEFIT_PLAN_TIMING") return "timing";
  if (lead.source_frontier === "FEDERAL_CONTRACT" || lead.source_frontier === "SAM_ENTITY") return "growth";
  if (["FMCSA", "EPA_ECHO", "FCC_ULS", "CHICAGO_BUSINESS_LICENSE"].includes(lead.source_frontier)) return "operations";
  return "research";
}

function selectedTerritoryChoice() {
  for (const [name, values] of Object.entries(EASTERN_REGIONS)) {
    if (values.length === state.selectedStates.size && values.every((code) => state.selectedStates.has(code))) {
      return `region:${name}`;
    }
  }
  const selected = [...state.selectedStates];
  return selected.length === 1 ? `state:${selected[0]}` : "";
}

function renderTerritorySelect(select) {
  if (!select.dataset.ready) {
    select.innerHTML = [
      `<option value="">Choose a region or state</option>`,
      `<optgroup label="Regions">`,
      ...Object.entries(EASTERN_REGIONS).map(([name, values]) => (
        `<option value="region:${esc(name)}">${name === "All East" ? "All Eastern states" : esc(name)} (${values.length})</option>`
      )),
      `</optgroup>`,
      `<optgroup label="States">`,
      ...EASTERN_REGIONS["All East"].map((code) => `<option value="state:${code}">${esc(STATE_NAMES[code])} (${code})</option>`),
      `</optgroup>`,
    ].join("");
    select.dataset.ready = "true";
  }
  select.value = selectedTerritoryChoice();
}

function renderMobileTerritoryControls() {
  renderTerritorySelect($("mobileStateSelect"));
  renderTerritorySelect($("quickTerritorySelect"));
  const selected = [...state.selectedStates];
  $("mobileTerritoryLabel").textContent = selectedRegionName();
  $("mobileTerritoryCount").textContent = `${selected.length} market${selected.length === 1 ? "" : "s"} selected`;
  $("quickTerritorySummary").textContent = `${selectedRegionName()} · ${selected.length} market${selected.length === 1 ? "" : "s"}`;
}

function selectedRegionName() {
  for (const [name, values] of Object.entries(EASTERN_REGIONS)) {
    if (values.length === state.selectedStates.size && values.every((code) => state.selectedStates.has(code))) {
      return name === "All East" ? "Eastern United States" : name;
    }
  }
  if (state.selectedStates.size === 1) {
    return STATE_NAMES[[...state.selectedStates][0]];
  }
  return "Custom Eastern territory";
}

function renderTerritorySummary() {
  const count = state.selectedStates.size;
  $("territoryCount").textContent = `${count} market${count === 1 ? "" : "s"} selected`;
  $("territoryLabel").textContent = selectedRegionName();
  renderMobileTerritoryControls();
}

function syncTerritoryControls() {
  renderRegionButtons();
  renderStateButtons();
  renderTerritorySummary();
}

function chooseRegion(name) {
  const values = EASTERN_REGIONS[name];
  if (!values) return;
  state.selectedStates = new Set(values);
  syncTerritoryControls();
  updateUrl();
  switchView("leads");
  loadLeads({ focusResults: true });
}

function selectOnlyState(code) {
  if (!STATE_NAMES[code]) return;
  state.selectedStates = new Set([code]);
  syncTerritoryControls();
  updateUrl();
  switchView("leads");
  loadLeads({ focusResults: true });
}

function chooseTerritory(value) {
  const [kind, raw] = String(value || "").split(":", 2);
  if (kind === "region" && EASTERN_REGIONS[raw]) {
    chooseRegion(raw);
  } else if (kind === "state" && STATE_NAMES[raw]) {
    selectOnlyState(raw);
  }
}

function focusResults() {
  const heading = $("leadsHeading");
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  heading.setAttribute("tabindex", "-1");
  heading.focus({ preventScroll: true });
  heading.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
}

function updateUrl() {
  const params = new URLSearchParams(window.location.search);
  params.set("states", [...state.selectedStates].join(","));
  const query = params.toString();
  history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
}

function restoreTerritoryFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const requested = String(params.get("states") || "")
    .split(",")
    .map((value) => value.trim().toUpperCase())
    .filter((value) => STATE_NAMES[value]);
  if (requested.length) state.selectedStates = new Set(requested);
}

function showLoading(show) {
  $("loadingState").classList.toggle("hidden", !show);
  $("refreshData").classList.toggle("loading", show);
  $("refreshData").disabled = show;
  $("workspace").setAttribute("aria-busy", String(show));
  if (show) {
    $("errorState").classList.add("hidden");
    renderDataStateChecking();
    $("emptyState").classList.add("hidden");
    $("resultCount").textContent = "Loading current source records";
  }
}

function admitSourceBoard(board) {
  const sources = Array.isArray(board?.sources) ? board.sources : [];
  const hasLiveSource = sources.some((source) => source.mode === "LIVE");
  return {
    board,
    sources,
    loadError: hasLiveSource
      ? ""
      : "No official source completed a live observation for the selected territory.",
    leads: hasLiveSource && Array.isArray(board?.opportunities)
      ? board.opportunities
      : [],
  };
}

async function loadLeads({ focusResults: focusAfterLoad = false } = {}) {
  if (!state.selectedStates.size) return;
  if (state.controller) state.controller.abort();
  const controller = new AbortController();
  state.controller = controller;
  showLoading(true);
  const selected = [...state.selectedStates];
  const query = encodeURIComponent(selected.join(","));
  const started = performance.now();
  try {
    const board = await fetchFrontierBoard(`/api/frontier-desk?states=${query}&limit_per_source=8`, controller);
    if (state.controller !== controller) return;
    const admitted = admitSourceBoard(board);
    state.board = admitted.board;
    state.sources = admitted.sources;
    state.loadError = admitted.loadError;
    state.leads = admitted.leads;
    renderEverything();
    const seconds = ((performance.now() - started) / 1000).toFixed(1);
    if (!state.loadError) {
      $("freshness").textContent = `${relativeTime(board.generated_at)} in ${seconds}s`;
    }
    if (focusAfterLoad && !state.loadError) focusResults();
  } catch (error) {
    if (error.name === "AbortError" || state.controller !== controller) return;
    state.board = null;
    state.leads = [];
    state.sources = [];
    state.loadError = error.message || "The current source pull did not complete.";
    renderEverything();
    showToast("The live source pull did not complete. Try again.");
  } finally {
    if (state.controller === controller) {
      state.controller = null;
      showLoading(false);
    }
  }
}

function renderEverything() {
  renderDataState();
  renderFilters();
  if (!state.board || state.loadError) {
    renderUnavailableEvidence();
    applyFilters();
    renderScope();
    return;
  }
  renderMetrics();
  renderDailyBrief();
  applyFilters();
  renderAtlas();
  renderSources();
  renderInvestorProof();
  renderScope();
}

function renderDataStateChecking() {
  const pill = $("dataStatePill");
  pill.classList.remove("measured");
  pill.classList.remove("unavailable");
  pill.classList.add("checking");
  pill.lastChild.textContent = "DATA: CHECKING";
  pill.title = `Loading current source records for ${selectedRegionName()}`;
}

function renderDataState() {
  const pill = $("dataStatePill");
  const liveSources = state.sources.filter((source) => source.mode === "LIVE");
  const totalSources = state.sources.length;
  const observedAt = state.board?.generated_at;
  pill.classList.remove("checking");
  pill.classList.toggle("measured", liveSources.length > 0);
  pill.classList.toggle("unavailable", liveSources.length === 0);
  if (liveSources.length > 0) {
    pill.lastChild.textContent = `LIVE / MEASURED · ${liveSources.length}/${totalSources}`;
    pill.title = observedAt ? `Current pull observed ${formatDate(observedAt)}` : "Current source pull observed";
  } else if (state.board) {
    pill.lastChild.textContent = `UNAVAILABLE · 0/${totalSources}`;
    pill.title = "No source adapter reported LIVE in the current pull";
  } else {
    pill.lastChild.textContent = "DATA: UNAVAILABLE";
    pill.title = "The current source pull did not complete";
  }
}

function renderAccessState(status) {
  const pill = $("accessStatePill");
  const boundary = $("accessBoundary");
  pill.classList.remove("checking", "confirmed", "unavailable");
  pill.classList.add(status);
  boundary.classList.remove("checking", "confirmed", "unavailable");
  boundary.classList.add(status);
  if (status === "confirmed") {
    pill.textContent = "PUBLIC VIEW · NO LOGIN";
    $("accessBoundaryCopy").textContent = "Viewing is open. Private notes, clearance, and outreach actions stay protected.";
  } else if (status === "unavailable") {
    pill.textContent = "PUBLIC VIEW: UNAVAILABLE";
    $("accessBoundaryCopy").textContent = "Public access could not be confirmed. No private workflow data was exposed.";
  } else {
    pill.textContent = "PUBLIC VIEW: CHECKING";
    $("accessBoundaryCopy").textContent = "Confirming public access. Viewing never grants permission to contact.";
  }
}

function renderWorkspaceUnavailable() {
  const pill = $("dataStatePill");
  pill.classList.remove("measured");
  pill.classList.remove("checking");
  pill.classList.add("unavailable");
  pill.lastChild.textContent = "DATA: UNAVAILABLE";
  pill.title = "The public workspace did not pass its access gate";
  $("sourceStamp").textContent = "Release unavailable";
  $("sourceStamp").classList.remove("observed");
  $("freshness").textContent = "Live sources unavailable";
  state.loadError = "The public workspace did not pass its access or readiness gate.";
  state.board = null;
  state.leads = [];
  state.sources = [];
  renderEverything();
  $("loadingState").classList.add("hidden");
  $("errorStateCopy").textContent = `This does not mean zero leads. ${state.loadError}`;
  $("errorState").classList.remove("hidden");
  $("resultCount").textContent = "Workspace unavailable";
  renderAccessState("unavailable");
}

function renderMetrics() {
  if (!state.board || state.loadError) {
    ["metricOrganizations", "metricStates", "metricWindows", "metricSources", "metricResearch", "metricCleared"]
      .forEach((id) => { $(id).textContent = "UNKNOWN"; });
    $("metricOrganizationsSub").textContent = "No completed live pull is available";
    $("metricStatesSub").textContent = "Choose a territory and retry";
    $("metricWindowsSub").textContent = "Waiting for a completed live pull";
    $("metricSourcesSub").textContent = "Source status is unavailable";
    $("proofLiveSources").textContent = "UNKNOWN";
    markUnknown($("proofLiveSources"), true);
    return;
  }
  const summary = state.board?.summary || {};
  const represented = new Set(state.leads.map((lead) => lead.state).filter(Boolean));
  const liveSources = state.sources.filter((source) => source.mode === "LIVE");
  $("metricOrganizations").textContent = formatNumber(summary.total ?? state.leads.length);
  $("metricOrganizationsSub").textContent = summary.live != null
    ? `${formatNumber(summary.live)} records reported LIVE by their source adapters`
    : "No LIVE record subtotal was reported";
  $("metricStates").textContent = `${represented.size}/${state.selectedStates.size}`;
  $("metricStatesSub").textContent = represented.size === state.selectedStates.size
    ? "Every selected market represented"
    : "Select one state for a deeper pull";
  $("metricSources").textContent = `${liveSources.length}/${state.sources.length || 0}`;
  $("metricSourcesSub").textContent = `${state.sources.length - liveSources.length} unavailable or not applicable`;
  $("metricResearch").textContent = formatNumber(summary.needs_research ?? state.leads.length);
  $("metricCleared").textContent = formatNumber(summary.call_ready ?? 0);
  const timingWindows = state.leads.filter((lead) => {
    const days = Number(lead.timing?.days_to_anniversary);
    return Number.isFinite(days) && days >= 0 && days <= 180;
  });
  $("metricWindows").textContent = formatNumber(timingWindows.length);
  $("metricWindowsSub").textContent = timingWindows.length
    ? `${formatNumber(timingWindows.reduce((sum, lead) => sum + Number(lead.operational_snapshot?.participants_reported || 0), 0))} reported participants represented`
    : "No reported anniversaries in this pull";
  $("proofLiveSources").textContent = `${liveSources.length} live`;
  markUnknown($("proofLiveSources"), false);
}

function renderUnavailableEvidence() {
  renderMetrics();
  const message = state.loadError || "Waiting for a completed live source pull.";
  $("freshness").textContent = state.loadError ? "Live sources unavailable" : "Waiting for live sources";
  const brief = $("dailyBrief");
  brief.querySelector("strong").textContent = state.loadError
    ? "Live broker brief unavailable"
    : "Waiting for the live broker brief";
  brief.querySelector("small").textContent = `${message} No prior territory result is being shown.`;
  $("stateAtlas").innerHTML = EASTERN_REGIONS["All East"].map((code) => `
    <button class="atlas-state${state.selectedStates.has(code) ? " selected" : ""}" type="button" data-atlas-state="${code}" aria-pressed="${state.selectedStates.has(code)}" aria-label="${esc(STATE_NAMES[code])}: current record count unavailable. Load state-specific leads">
      <strong>${code}</strong>
      <small>${esc(STATE_NAMES[code])}</small>
      <span class="unknown">UNKNOWN</span>
    </button>
  `).join("");
  $("atlasNote").textContent = "UNKNOWN is not a zero. Select a state or retry the live pull. ROADMAP lanes stay labeled until they have a configured ingest path.";
  $("sourceCards").innerHTML = `
    <div class="source-card unavailable" role="status">
      <span class="source-dot"></span>
      <span>
        <span class="source-title">Current source status unavailable</span>
        <span class="source-reason">${esc(message)} Retry to request a new source observation.</span>
      </span>
      <span class="source-count honesty-chip unavailable">UNAVAILABLE</span>
    </div>
  `;
  const facts = [
    ["Organizations returned in current pull", "UNKNOWN"],
    ["Eastern markets queryable", "27"],
    ["Markets represented in this pull", "UNKNOWN"],
    ["Signed source receipts in this pull", "UNKNOWN"],
    ["Multi-source organization groups", "UNKNOWN"],
    ["Review-required identity groups", "UNKNOWN"],
    ["Session-verifiable source references", "UNKNOWN"],
    ["Proof grades", "UNKNOWN"],
    ["Evidence clock", "UNKNOWN"],
    ["Persistence health", state.health?.deal_desk_persistence || "UNKNOWN"],
    ["Generated", "UNKNOWN"],
  ];
  $("operatingFacts").innerHTML = facts.map(([label, value]) => `
    <div class="fact-row"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>
  `).join("");
  $("proofPackets").textContent = "UNKNOWN";
  $("proofClock").textContent = "UNKNOWN";
  markUnknown($("proofPackets"), true);
  markUnknown($("proofClock"), true);
  $("largestAward").textContent = "The current live source pull is unavailable. No award value from a prior territory is being shown.";
}

function renderDailyBrief() {
  const timing = state.leads
    .filter((lead) => Number.isFinite(Number(lead.timing?.days_to_anniversary)))
    .sort((a, b) => Number(a.timing.days_to_anniversary) - Number(b.timing.days_to_anniversary));
  const top = [...state.leads].sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0))[0];
  const brief = $("dailyBrief");
  if (!state.board) {
    renderUnavailableEvidence();
    return;
  }
  const strong = timing[0] || top;
  if (!strong) {
    brief.querySelector("strong").textContent = "No deal moments returned for this territory";
    brief.querySelector("small").textContent = "Choose one state for a deeper pull or refresh the official sources.";
    return;
  }
  brief.querySelector("strong").textContent = timing.length
    ? `${timing.length} employer life-plan anniversary watches surfaced`
    : `${strong.name} is the highest evidence-ranked account`;
  brief.querySelector("small").textContent = timing.length
    ? `Nearest reported anniversary: ${timingSummary(timing[0]).label}. Open the filing before starting contact-clearance research.`
    : `${sourceName(strong)} — ${strong.observed_trigger || "official activity observed"}.`;
}

function renderFilters() {
  const current = $("sourceFilter").value || "all";
  const sources = [...new Set(state.leads.map((lead) => lead.source_frontier).filter(Boolean))]
    .sort((a, b) => sourceName({ source_frontier: a }).localeCompare(sourceName({ source_frontier: b })));
  $("sourceFilter").innerHTML = [
    `<option value="all">All official sources</option>`,
    ...sources.map((source) => `<option value="${esc(source)}">${esc(sourceName({ source_frontier: source }))}</option>`),
  ].join("");
  $("sourceFilter").value = sources.includes(current) ? current : "all";
}

function searchableText(lead) {
  return [
    lead.name, lead.dba, lead.city, lead.state, lead.zip, lead.category,
    lead.observed_trigger, lead.signal_summary, lead.why, sourceName(lead),
    ...(Array.isArray(lead.product_fit) ? lead.product_fit : []),
  ].filter(Boolean).join(" ").toLowerCase();
}

function applyFilters() {
  const query = $("searchInput").value.trim().toLowerCase();
  const source = $("sourceFilter").value;
  const sort = $("sortFilter").value;
  let leads = state.leads.filter((lead) => {
    const matchesSearch = !query || searchableText(lead).includes(query);
    const matchesSource = source === "all" || lead.source_frontier === source;
    const matchesLane = state.activeLane === "all"
      || (state.activeLane === "research" ? !lead.call_ready : dealLane(lead) === state.activeLane);
    return matchesSearch && matchesSource && matchesLane;
  });

  leads = [...leads].sort((a, b) => {
    if (sort === "newest") return String(observedDate(b)).localeCompare(String(observedDate(a)));
    if (sort === "value") return observedValue(b).raw - observedValue(a).raw;
    if (sort === "name") return String(a.name || "").localeCompare(String(b.name || ""));
    return Number(b.priority || 0) - Number(a.priority || 0)
      || String(observedDate(b)).localeCompare(String(observedDate(a)));
  });

  state.filtered = leads;
  renderLeads();
}

function leadRow(lead) {
  const timing = timingSummary(lead);
  const fit = productFit(lead);
  const evidence = evidenceSummary(lead);
  return `<tr>
    <td>
      <span class="company-name">${esc(lead.name || "Unnamed organization")}</span>
      <span class="company-meta">${esc(lead.city || "City unavailable")}${lead.state ? `, ${esc(lead.state)}` : ""}${lead.zip ? ` ${esc(lead.zip)}` : ""}</span>
    </td>
    <td>
      <span class="signal-name">${esc(lead.observed_trigger || sourceName(lead))}</span>
      <span class="signal-detail">${esc(lead.signal_summary || lead.category || "Official activity observed")}</span>
      <span class="source-inline">${esc(sourceName(lead))}</span>
    </td>
    <td>
      <span class="timing-badge${timing.urgent ? " urgent" : ""}">${esc(timing.label)}</span>
      <span class="observed-value-label">${esc(timing.detail)}</span>
    </td>
    <td>
      <span class="fit-primary">${esc(fit[0])}</span>
      <span class="fit-more">${esc(fit.slice(1).join(" · ") || lead.product || "Broker review")}</span>
    </td>
    <td>
      <span class="evidence-label"><i></i>${esc(evidence.label)}</span>
      <span class="evidence-detail">${esc(evidence.detail)}</span>
    </td>
    <td>
      <button class="lead-open" type="button" data-lead-id="${esc(lead.opportunity_id)}" aria-label="Open ${esc(lead.name)} details">
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h11m-4-4 4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path></svg>
      </button>
    </td>
  </tr>`;
}

function leadCard(lead) {
  const value = observedValue(lead);
  const timing = timingSummary(lead);
  const fit = productFit(lead);
  return `<article class="lead-card">
    <div class="lead-card-head">
      <div>
        <span class="company-name">${esc(lead.name || "Unnamed organization")}</span>
        <span class="company-meta">${esc(lead.city || "City unavailable")}, ${esc(unknownValue(lead.state))}</span>
      </div>
      <span class="market-badge">${esc(unknownValue(lead.state))}</span>
    </div>
    <div class="lead-card-signal">
      <span class="signal-name">${esc(lead.observed_trigger || sourceName(lead))}</span>
      <span class="signal-detail">${esc(sourceName(lead))}</span>
    </div>
    <div class="lead-card-intel">
      <span><small>Timing</small><strong>${esc(timing.label)}</strong></span>
      <span><small>Likely fit</small><strong>${esc(fit[0])}</strong></span>
    </div>
    <div class="lead-card-footer">
      <span class="lead-card-value">${esc(value.value)} - ${esc(value.label)}</span>
      <button class="lead-open" type="button" data-lead-id="${esc(lead.opportunity_id)}" aria-label="Open ${esc(lead.name)} details">
        <span>Review lead</span>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h11m-4-4 4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path></svg>
      </button>
    </div>
  </article>`;
}

function renderLeads() {
  $("leadRows").innerHTML = state.filtered.map(leadRow).join("");
  $("leadCards").innerHTML = state.filtered.map(leadCard).join("");
  const unavailable = Boolean(state.loadError);
  $("resultCount").textContent = unavailable
    ? "Live data unavailable"
    : `${formatNumber(state.filtered.length)} of ${formatNumber(state.leads.length)} records`;
  $("errorStateCopy").textContent = `This does not mean zero leads. ${state.loadError || "The current source pull did not complete."}`;
  $("errorState").classList.toggle("hidden", !unavailable);
  const empty = $("emptyState");
  const showEmpty = !unavailable && state.filtered.length === 0 && !(state.leads.length === 0 && !state.board);
  empty.classList.toggle("hidden", !showEmpty);
  if (showEmpty) {
    const chip = empty.querySelector?.(".honesty-chip");
    const heading = empty.querySelector?.("h3");
    const copy = empty.querySelector?.("p");
    const measuredEmpty = Boolean(state.board) && state.leads.length === 0;
    if (chip) {
      chip.className = `honesty-chip ${measuredEmpty ? "measured" : "unknown"}`;
      chip.textContent = measuredEmpty ? "MEASURED" : "UNKNOWN";
    }
    if (heading) {
      heading.textContent = measuredEmpty
        ? "This pull returned no organizations"
        : "No matching records in this filter set";
    }
    if (copy) {
      copy.textContent = measuredEmpty
        ? "A measured empty result is not unavailable coverage and not a ROADMAP lane. Try another state or source."
        : "This is not a zero-demand claim. A missing pull is UNAVAILABLE. An unfinished lane is ROADMAP.";
    }
  }
}

function renderScope() {
  const selected = [...state.selectedStates];
  const name = selectedRegionName();
  const selectedCopy = selected.length === 1
    ? `${STATE_NAMES[selected[0]]} is selected. This is a deeper state-specific pull.`
    : `${name} is selected (${selected.length} markets). The cross-territory view shows the latest records per source; choose one state for a deeper pull.`;
  $("scopeNotice").textContent = state.loadError
    ? `Live sources could not complete: ${state.loadError}`
    : selectedCopy;
  $("scopeSummary").textContent = state.loadError
    ? `Live records are temporarily unavailable in ${name}. Retry to distinguish an outage from zero results.`
    : state.board
      ? `${formatNumber(state.leads.length)} official organization records in ${name}. Choose any state to focus David's research.`
      : `Loading the latest official records in ${name}.`;
}

function renderAtlas() {
  if (!state.board) {
    renderUnavailableEvidence();
    return;
  }
  const counts = state.leads.reduce((acc, lead) => {
    const code = lead.state;
    if (STATE_NAMES[code]) acc[code] = (acc[code] || 0) + 1;
    return acc;
  }, {});
  $("stateAtlas").innerHTML = EASTERN_REGIONS["All East"].map((code) => `
    <button class="atlas-state${state.selectedStates.has(code) ? " selected" : ""}" type="button" data-atlas-state="${code}" aria-pressed="${state.selectedStates.has(code)}" aria-label="${esc(STATE_NAMES[code])}: ${formatNumber(counts[code] || 0)} records in this pull. Load state-specific leads">
      <strong>${code}</strong>
      <small>${esc(STATE_NAMES[code])}</small>
      <span>${formatNumber(counts[code] || 0)}</span>
    </button>
  `).join("");
  $("atlasNote").textContent = "A zero means the latest completed cross-territory pull did not return that state. Select the state to run a deeper state-specific query.";
}

function cleanReason(source) {
  if (source.mode === "LIVE") {
    if (source.reason) return String(source.reason).replaceAll("_", " ").toLowerCase();
    return `${formatNumber(source.count)} records in this live pull`;
  }
  if (source.mode === "NOT_APPLICABLE") return "Not applicable to the selected territory";
  return String(source.reason || "Source unavailable").replaceAll("_", " ").toLowerCase();
}

function renderSources() {
  if (!state.board) {
    renderUnavailableEvidence();
    return;
  }
  $("sourceCards").innerHTML = state.sources.map((source) => {
    const honesty = sourceHonesty(source);
    return `
    <a class="source-card" href="${safeUrl(source.citation?.url)}" target="_blank" rel="noopener">
      <span class="source-dot${source.mode === "LIVE" ? " live" : ""}"></span>
      <span>
        <span class="source-title">${esc(source.source || "Official source")}</span>
        <span class="source-reason">${esc(cleanReason(source))}</span>
      </span>
      <span class="source-count honesty-chip ${honesty.toLowerCase()}">${esc(honesty)}</span>
    </a>`;
  }).join("");
}

function renderInvestorProof() {
  if (!state.board) {
    renderUnavailableEvidence();
    return;
  }
  const represented = new Set(state.leads.map((lead) => lead.state).filter(Boolean));
  const constellation = state.board?.evidence_constellation || {};
  const signed = Number.isFinite(Number(constellation.signed_source_receipts))
    ? Number(constellation.signed_source_receipts)
    : 0;
  const clock = constellation.deal_clock || {};
  const proofGrades = constellation.proof_grades || {};
  const latest = state.board?.generated_at ? formatDate(state.board.generated_at) : "Unavailable";
  const facts = [
    ["Organizations returned in current pull", formatNumber(state.leads.length)],
    ["Eastern markets queryable", "27"],
    ["Markets represented in this pull", formatNumber(represented.size)],
    ["Signed source receipts in this pull", `${signed}/${state.leads.length || 0}`],
    ["Multi-source organization groups", formatNumber(constellation.multi_source_entities || 0)],
    ["Review-required identity groups", formatNumber(constellation.review_required_groups || 0)],
    ["Session-verifiable source references", `${formatNumber(constellation.session_verifiable_references || 0)}/${formatNumber(constellation.events_total || state.leads.length)}`],
    ["Proof grades (evidence quality, not likelihood)", `A ${proofGrades.A || 0} · B ${proofGrades.B || 0} · C ${proofGrades.C || 0} · D ${proofGrades.D || 0}`],
    ["Evidence clock", `${clock.CURRENT || 0} current · ${clock.RECHECK_DUE || 0} recheck · ${clock.STALE || 0} stale`],
    ["Persistence health", state.health?.deal_desk_persistence || "Checking"],
    ["Generated", latest],
  ];
  $("operatingFacts").innerHTML = facts.map(([label, value]) => `
    <div class="fact-row"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>
  `).join("");

  $("proofPackets").textContent = `${formatNumber(constellation.session_verifiable_references || 0)}/${formatNumber(constellation.events_total || state.leads.length)}`;
  $("proofClock").textContent = `${formatNumber(clock.CURRENT || 0)} current`;
  markUnknown($("proofPackets"), false);
  markUnknown($("proofClock"), false);
  const awards = state.leads
    .map((lead) => ({ lead, amount: Number(lead.award?.amount) }))
    .filter((item) => Number.isFinite(item.amount))
    .sort((a, b) => b.amount - a.amount);
  $("largestAward").textContent = awards.length
    ? `Largest observed federal award field in this pull: ${formatMoney(awards[0].amount)} for ${awards[0].lead.name}. This is not company revenue, deal value, or insurability.`
    : "No federal award amount is available in this pull. No financial field is being treated as company revenue.";
}

function switchView(view) {
  if (!["leads", "markets", "investors"].includes(view)) return;
  state.activeView = view;
  document.querySelectorAll(".view-panel").forEach((panel) => {
    const active = panel.id === `${view}View`;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
  document.querySelectorAll(".workspace-tab").forEach((button) => {
    const active = button.dataset.viewTarget === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  document.querySelectorAll(".role-button").forEach((button) => {
    const active = button.dataset.viewTarget === view;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
}

function openLead(id, opener = null) {
  const lead = state.leads.find((item) => item.opportunity_id === id);
  if (!lead) return;
  const value = observedValue(lead);
  $("drawerSource").textContent = sourceName(lead);
  $("drawerTitle").textContent = lead.name || "Unnamed organization";
  $("drawerLocation").textContent = [lead.address, lead.city, lead.state, lead.zip].filter(Boolean).join(", ");

  const limitations = Array.isArray(lead.limitations) && lead.limitations.length
    ? `<ul>${lead.limitations.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`
    : `<p>No source-specific limitation was returned. The public contact gate still applies.</p>`;
  const identifiers = Array.isArray(lead.authoritative_entity_ids)
    ? lead.authoritative_entity_ids
    : [];
  const idFacts = identifiers.map((item) => `
    <div class="drawer-fact"><span>${esc(item.system || "Identifier")}</span><strong>${esc(unknownValue(item.value))}</strong></div>
  `).join("");
  const receiptLink = lead.receipt_id
    ? `<button class="drawer-link" type="button" data-proof-id="${esc(lead.receipt_id)}">Verify source receipt</button>`
    : "";
  const timing = timingSummary(lead);
  const fit = productFit(lead);
  const evidence = evidenceSummary(lead);
  const constellation = lead.evidence_constellation || {};
  const proof = constellation.proof || {};
  const clock = constellation.deal_clock || {};
  const resolution = lead.entity_resolution || {};
  const counterEvidence = Array.isArray(constellation.counter_evidence) ? constellation.counter_evidence : [];
  const decisionDimensions = constellation.decision_dimensions || {};
  const carriers = Array.isArray(lead.operational_snapshot?.reported_carriers)
    ? lead.operational_snapshot.reported_carriers
    : [];
  const corroboration = Array.isArray(lead.corroborating_signals)
    ? lead.corroborating_signals
    : [];
  const corroborationList = corroboration.length > 1
    ? `<ul>${corroboration.map((item) => `<li>${esc(SOURCE_NAMES[item.source_frontier] || item.source_frontier || "Official source")}: ${esc(item.observed_trigger || "official activity observed")}</li>`).join("")}</ul>`
    : "";
  const fitChips = fit.map((item) => `<span class="fit-chip">${esc(item)}</span>`).join("");

  $("drawerBody").innerHTML = `
    <div class="drawer-alert">Research only. This public record is not permission to call, email, market, or make an underwriting decision.</div>
    <section class="drawer-section">
      <span class="drawer-section-label">Why this organization surfaced</span>
      <h3>${esc(lead.observed_trigger || lead.category || "Official activity observed")}</h3>
      <p>${esc(lead.signal_summary || lead.why || "Open the official source to understand the observed activity.")}</p>
    </section>
    <section class="drawer-section">
      <span class="drawer-section-label">Deal moment</span>
      <div class="drawer-facts">
        <div class="drawer-fact"><span>State</span><strong>${esc(unknownValue(lead.state))}</strong></div>
        <div class="drawer-fact"><span>Observed</span><strong>${esc(formatDate(observedDate(lead)))}</strong></div>
        <div class="drawer-fact"><span>Timing</span><strong>${esc(timing.label)}</strong></div>
        <div class="drawer-fact"><span>Evidence</span><strong>${esc(evidence.label)}</strong></div>
        <div class="drawer-fact"><span>${esc(value.label)}</span><strong>${esc(value.value)}</strong></div>
        <div class="drawer-fact"><span>Source state</span><strong>${esc(lead.truth_label || "LIVE")}</strong></div>
        ${idFacts}
      </div>
    </section>
    <section class="drawer-section">
      <span class="drawer-section-label">Evidence Constellation</span>
      <h3>Proof ${esc(unknownValue(proof.grade))} · ${esc(String(clock.state || "UNKNOWN").replaceAll("_", " "))}</h3>
      <div class="drawer-facts">
        <div class="drawer-fact"><span>Authority</span><strong>${esc(proof.dimensions?.authority || "UNAVAILABLE")}</strong></div>
        <div class="drawer-fact"><span>Integrity</span><strong>${esc(proof.dimensions?.integrity || "UNAVAILABLE")}</strong></div>
        <div class="drawer-fact"><span>Identity</span><strong>${esc(String(resolution.status || "UNRESOLVED").replaceAll("_", " "))}</strong></div>
        <div class="drawer-fact"><span>Permission</span><strong>${esc(lead.contact_gate || decisionDimensions.permission || "PUBLIC_RESEARCH_ONLY")}</strong></div>
      </div>
      <p class="supporting-detail"><strong>Why this may be wrong</strong></p>
      ${counterEvidence.length ? `<ul>${counterEvidence.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>` : `<p>No counter-evidence contract was returned.</p>`}
      <p class="supporting-detail">Proof quality is not a sales probability. Recheck ${esc(clock.recheck_at ? formatDate(clock.recheck_at) : "unknown")}; expires ${esc(clock.expires_at ? formatDate(clock.expires_at) : "unknown")}.</p>
    </section>
    <section class="drawer-section">
      <span class="drawer-section-label">Likely product fit</span>
      <div class="fit-chips">${fitChips}</div>
      <p>${esc(lead.why || "The observed activity may justify a licensed broker review after the organization is verified.")}</p>
      ${carriers.length ? `<p class="supporting-detail"><strong>Carriers named in the filing:</strong> ${esc(carriers.join(", "))}. This is context, not evidence of dissatisfaction or availability.</p>` : ""}
    </section>
    <section class="drawer-section">
      <span class="drawer-section-label">Three-step broker action</span>
      <ol class="action-path">
        <li><span>1</span><p><strong>Verify the moment.</strong> Open the cited official record and confirm the organization, date, and reported field.</p></li>
        <li><span>2</span><p><strong>Qualify the fit.</strong> Use the organization’s own website to confirm operations, current needs, and a first-party business channel.</p></li>
        <li><span>3</span><p><strong>Clear outreach.</strong> Complete suppression, licensing, state-rule, and purpose checks in the authenticated workspace.</p></li>
      </ol>
    </section>
    <section class="drawer-section">
      <span class="drawer-section-label">Source limitations</span>
      ${limitations}
    </section>
    <section class="drawer-section">
      <span class="drawer-section-label">Proof and sources</span>
      <p>Open the source record first. The receipt confirms the normalized public observation that created this research card.</p>
      ${corroborationList}
      <div class="drawer-links">
        <a class="drawer-link" href="${safeUrl(lead.citation?.url)}" target="_blank" rel="noopener">Open official record</a>
        <a class="drawer-link" href="${safeUrl(lead.source_record?.url)}" target="_blank" rel="noopener">Source documentation</a>
        ${receiptLink}
      </div>
      <p class="supporting-detail">A source receipt is a session-verifiable reference for the normalized official record. It is not a theorem, a conversion proof, or permission to contact.</p>
      <div id="proofResult"></div>
    </section>
  `;
  const drawer = $("leadDrawer");
  state.drawerReturnFocus = opener || document.activeElement;
  if (!drawer.open) drawer.showModal();
  window.requestAnimationFrame(() => drawer.classList.add("open"));
  document.body.style.overflow = "hidden";
  $("closeDrawer").focus();
}

function closeLead() {
  const drawer = $("leadDrawer");
  if (!drawer.open) return;
  drawer.classList.remove("open");
  drawer.close();
  document.body.style.overflow = "";
  if (state.drawerReturnFocus?.isConnected) state.drawerReturnFocus.focus();
  state.drawerReturnFocus = null;
}

async function verifyProof(receiptId) {
  const result = $("proofResult");
  result.innerHTML = `<div class="proof-result">Verifying ${esc(receiptId)}...</div>`;
  try {
    const proof = await api(`/api/verify/${encodeURIComponent(receiptId)}`);
    const signatureState = proof.signature_state || "UNAVAILABLE";
    const integrityState = proof.integrity_state || "UNAVAILABLE";
    const chainState = proof.chain_state || "UNAVAILABLE";
    const claimScope = proof.claim_scope || "UNAVAILABLE";
    const witness = proof.witness || {};
    const chainWarning = ["VERIFIED", "GENESIS_DECLARED"].includes(chainState)
      ? ""
      : `<br><strong>Chain limit:</strong> the signature may verify, but the predecessor chain was not independently supplied and verified.`;
    result.innerHTML = `<div class="proof-result">
      <strong>Receipt:</strong> ${esc(receiptId)}<br>
      <strong>Verdict:</strong> ${esc(proof.verdict || "UNAVAILABLE")}<br>
      <strong>Signature:</strong> ${esc(signatureState)}<br>
      <strong>Payload integrity:</strong> ${esc(integrityState)}<br>
      <strong>Predecessor chain:</strong> ${esc(chainState)}<br>
      <strong>Claim scope:</strong> ${esc(claimScope)}<br>
      <strong>Witness:</strong> ${esc(witness.state || "UNAVAILABLE")} · ${esc(witness.durability || "UNAVAILABLE")}<br>
      <strong>Witness mode:</strong> ${esc(witness.signing_mode || "UNAVAILABLE")}
      ${chainWarning}
    </div>`;
  } catch (error) {
    result.innerHTML = `<div class="proof-result">Receipt verification unavailable: ${esc(error.message)}</div>`;
  }
}

async function loadBuildAndHealth() {
  const [build, health] = await Promise.allSettled([
    api("/api/build-info"),
    api("/healthz"),
  ]);
  if (build.status === "fulfilled") {
    state.build = build.value;
    const fullRevision = String(state.build.source_revision || state.build.build?.revision || "");
    const revision = fullRevision.slice(0, 8);
    state.currentRevision = fullRevision;
    $("sourceStamp").textContent = revision ? `Release ${revision}` : "Release observed";
    $("sourceStamp").classList.add("observed");
    const receipt = state.build.release_receipt || {};
    const attested = state.build.receipt_minted === true && receipt.state === "GITHUB_OIDC_ATTESTED";
    $("proofRelease").textContent = attested ? "Identity verified" : "Observed";
    $("proofReleaseCopy").textContent = attested
      ? `The running release matches source revision ${revision} and has a published identity receipt.`
      : "The running revision is exposed, but an attested release receipt is not currently reported.";
    if (attested && safeUrl(receipt.attestation_url) !== "#") {
      $("attestationLink").href = safeUrl(receipt.attestation_url);
      $("attestationLink").classList.remove("disabled");
    }
  } else {
    $("sourceStamp").textContent = "Release unavailable";
    $("proofRelease").textContent = "Unavailable";
    $("proofReleaseCopy").textContent = "The runtime did not return its build identity.";
  }
  if (health.status === "fulfilled") {
    state.health = health.value;
  }
  renderInvestorProof();
}

async function checkForNewRelease() {
  if (document.visibilityState !== "visible" || !state.currentRevision) return;
  try {
    const build = await api(`/api/build-info?release_check=${Date.now()}`);
    const nextRevision = String(build.source_revision || build.build?.revision || "");
    if (nextRevision && nextRevision !== state.currentRevision) {
      $("releaseBanner").classList.remove("hidden");
    }
  } catch (_) {
    // A release check is advisory. Live-source errors remain visible elsewhere.
  }
}

async function bootstrap() {
  restoreTerritoryFromUrl();
  syncTerritoryControls();
  bindEvents();
  switchView(state.activeView);
  renderAccessState("checking");
  try {
    const access = await api("/api/access-mode");
    state.accessMode = access.mode;
    if (access.mode !== "public_readonly") {
      throw new Error("The public workspace is not enabled.");
    }
    renderAccessState("confirmed");
    $("boot").classList.add("done");
    await Promise.all([loadLeads(), loadBuildAndHealth()]);
    state.releaseCheckTimer = window.setInterval(checkForNewRelease, 120000);
  } catch (error) {
    renderWorkspaceUnavailable();
    $("scopeSummary").textContent = `The public workspace could not open: ${error.message}`;
    showToast("The public workspace could not open.");
  } finally {
    $("boot").classList.add("done");
  }
}

function bindEvents() {
  $("regionButtons").addEventListener("click", (event) => {
    const button = event.target.closest("[data-region]");
    if (button) chooseRegion(button.dataset.region);
  });
  $("stateButtons").addEventListener("click", (event) => {
    const button = event.target.closest("[data-state]");
    if (button) selectOnlyState(button.dataset.state);
  });
  ["mobileStateSelect", "quickTerritorySelect"].forEach((id) => {
    $(id).addEventListener("change", (event) => chooseTerritory(event.target.value));
  });
  $("stateAtlas").addEventListener("click", (event) => {
    const button = event.target.closest("[data-atlas-state]");
    if (button) selectOnlyState(button.dataset.atlasState);
  });
  $("refreshData").addEventListener("click", () => loadLeads());
  $("retryData").addEventListener("click", () => loadLeads({ focusResults: true }));
  $("viewSourceStatus").addEventListener("click", () => {
    switchView("markets");
    $("marketsHeading").focus({ preventScroll: true });
    $("marketsHeading").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("searchInput").addEventListener("input", applyFilters);
  $("sourceFilter").addEventListener("change", applyFilters);
  $("sortFilter").addEventListener("change", applyFilters);
  $("resetFilters").addEventListener("click", () => {
    $("searchInput").value = "";
    $("sourceFilter").value = "all";
    $("sortFilter").value = "priority";
    state.activeLane = "all";
    document.querySelectorAll("[data-lane]").forEach((item) => {
      const active = item.dataset.lane === "all";
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    applyFilters();
  });
  $("laneFilters").addEventListener("click", (event) => {
    const button = event.target.closest("[data-lane]");
    if (!button) return;
    state.activeLane = button.dataset.lane;
    document.querySelectorAll("[data-lane]").forEach((item) => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    applyFilters();
  });
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.viewTarget));
  });
  const workspaceTabs = [...document.querySelectorAll(".workspace-tab")];
  workspaceTabs.forEach((tab, index) => {
    tab.addEventListener("keydown", (event) => {
      let nextIndex = null;
      if (event.key === "ArrowRight") nextIndex = (index + 1) % workspaceTabs.length;
      if (event.key === "ArrowLeft") nextIndex = (index - 1 + workspaceTabs.length) % workspaceTabs.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = workspaceTabs.length - 1;
      if (nextIndex == null) return;
      event.preventDefault();
      const nextTab = workspaceTabs[nextIndex];
      switchView(nextTab.dataset.viewTarget);
      nextTab.focus();
    });
  });
  ["leadRows", "leadCards"].forEach((id) => {
    $(id).addEventListener("click", (event) => {
      const button = event.target.closest("[data-lead-id]");
      if (button) openLead(button.dataset.leadId, button);
    });
  });
  $("drawerBody").addEventListener("click", (event) => {
    const button = event.target.closest("[data-proof-id]");
    if (button) verifyProof(button.dataset.proofId);
  });
  $("closeDrawer").addEventListener("click", closeLead);
  $("leadDrawer").addEventListener("cancel", (event) => {
    event.preventDefault();
    closeLead();
  });
  $("openPolicy").addEventListener("click", () => $("policyDialog").showModal());
  $("openPolicyMobile").addEventListener("click", () => $("policyDialog").showModal());
  $("reloadRelease").addEventListener("click", () => window.location.reload());
  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const isEditing = target?.matches?.("input, textarea, select, [contenteditable='true']");
    if (event.key === "/" && !isEditing && !event.altKey && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      $("searchInput").focus();
    }
  });
}

document.addEventListener("DOMContentLoaded", bootstrap);
