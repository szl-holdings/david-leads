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
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
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

function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-US");
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
      return `<button class="region-button${active ? " active" : ""}" type="button" data-region="${esc(name)}">${esc(name)}${name === "All East" ? " (27)" : ""}</button>`;
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
  const sourceCount = Number(evidence.source_count || 1);
  return {
    label: sourceCount > 1
      ? `${sourceCount}-source match`
      : (evidence.strength === "DIRECT_FILING" ? "Direct filing" : "Official record"),
    detail: sourceCount > 1
      ? "Independent official signals"
      : (lead.receipt_signed ? "Signed source receipt" : (lead.receipt_id ? "Source receipt linked" : "Citation linked")),
  };
}

function dealLane(lead) {
  if (lead.source_frontier === "BENEFIT_PLAN_TIMING") return "timing";
  if (lead.source_frontier === "FEDERAL_CONTRACT" || lead.source_frontier === "SAM_ENTITY") return "growth";
  if (["FMCSA", "EPA_ECHO", "FCC_ULS", "CHICAGO_BUSINESS_LICENSE"].includes(lead.source_frontier)) return "operations";
  return "research";
}

function renderMobileTerritoryControls() {
  const select = $("mobileStateSelect");
  if (!select.dataset.ready) {
    select.innerHTML = [
      `<option value="">Choose a state</option>`,
      `<option value="__ALL__">All East (27 markets)</option>`,
      ...EASTERN_REGIONS["All East"].map((code) => `<option value="${code}">${esc(STATE_NAMES[code])} (${code})</option>`),
    ].join("");
    select.dataset.ready = "true";
  }
  const selected = [...state.selectedStates];
  const isAllEast = selected.length === EASTERN_REGIONS["All East"].length
    && EASTERN_REGIONS["All East"].every((code) => state.selectedStates.has(code));
  select.value = selected.length === 1 ? selected[0] : isAllEast ? "__ALL__" : "";
  $("mobileTerritoryLabel").textContent = selectedRegionName();
  $("mobileTerritoryCount").textContent = `${selected.length} market${selected.length === 1 ? "" : "s"} selected`;
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
  loadLeads();
}

function selectOnlyState(code) {
  if (!STATE_NAMES[code]) return;
  state.selectedStates = new Set([code]);
  syncTerritoryControls();
  updateUrl();
  switchView("leads");
  loadLeads();
  window.scrollTo({ top: 0, behavior: "smooth" });
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
    renderDataStateChecking();
    $("emptyState").classList.add("hidden");
    $("resultCount").textContent = "Loading current source records";
  }
}

async function loadLeads() {
  if (!state.selectedStates.size) return;
  if (state.controller) state.controller.abort();
  state.controller = new AbortController();
  showLoading(true);
  const selected = [...state.selectedStates];
  const query = encodeURIComponent(selected.join(","));
  const started = performance.now();
  try {
    const board = await api(`/api/frontier-desk?states=${query}`, { signal: state.controller.signal });
    state.board = board;
    state.leads = Array.isArray(board.opportunities) ? board.opportunities : [];
    state.sources = Array.isArray(board.sources) ? board.sources : [];
    renderEverything();
    const seconds = ((performance.now() - started) / 1000).toFixed(1);
    $("freshness").textContent = `${relativeTime(board.generated_at)} in ${seconds}s`;
  } catch (error) {
    if (error.name === "AbortError") return;
    state.board = null;
    state.leads = [];
    state.sources = [];
    renderEverything();
    $("scopeNotice").textContent = `Live sources could not complete: ${error.message}`;
    showToast("The live source pull did not complete. Try again.");
  } finally {
    showLoading(false);
  }
}

function renderEverything() {
  renderMetrics();
  renderDataState();
  renderFilters();
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
}

function renderMetrics() {
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
}

function renderDailyBrief() {
  const timing = state.leads
    .filter((lead) => Number.isFinite(Number(lead.timing?.days_to_anniversary)))
    .sort((a, b) => Number(a.timing.days_to_anniversary) - Number(b.timing.days_to_anniversary));
  const top = [...state.leads].sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0))[0];
  const brief = $("dailyBrief");
  if (!state.board) return;
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
        <span class="company-meta">${esc(lead.city || "City unavailable")}, ${esc(lead.state || "--")}</span>
      </div>
      <span class="market-badge">${esc(lead.state || "--")}</span>
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
  $("resultCount").textContent = `${formatNumber(state.filtered.length)} of ${formatNumber(state.leads.length)} records`;
  $("emptyState").classList.toggle("hidden", state.filtered.length > 0 || state.leads.length === 0 && !state.board);
}

function renderScope() {
  const selected = [...state.selectedStates];
  const name = selectedRegionName();
  const selectedCopy = selected.length === 1
    ? `${STATE_NAMES[selected[0]]} is selected. This is a deeper state-specific pull.`
    : `${name} is selected (${selected.length} markets). The cross-territory view shows the latest records per source; choose one state for a deeper pull.`;
  $("scopeNotice").textContent = selectedCopy;
  $("scopeSummary").textContent = state.board
    ? `${formatNumber(state.leads.length)} official organization records in ${name}. Choose any state to focus David's research.`
    : `Loading the latest official records in ${name}.`;
}

function renderAtlas() {
  const counts = state.leads.reduce((acc, lead) => {
    const code = lead.state;
    if (STATE_NAMES[code]) acc[code] = (acc[code] || 0) + 1;
    return acc;
  }, {});
  $("stateAtlas").innerHTML = EASTERN_REGIONS["All East"].map((code) => `
    <button class="atlas-state${state.selectedStates.has(code) ? " selected" : ""}" type="button" data-atlas-state="${code}" aria-label="Load ${esc(STATE_NAMES[code])} leads">
      <strong>${code}</strong>
      <small>${esc(STATE_NAMES[code])}</small>
      <span>${formatNumber(counts[code] || 0)}</span>
    </button>
  `).join("");
}

function cleanReason(source) {
  if (source.mode === "LIVE") return `${formatNumber(source.count)} records in this live pull`;
  if (source.mode === "NOT_APPLICABLE") return "Not applicable to the selected territory";
  return String(source.reason || "Source unavailable").replaceAll("_", " ").toLowerCase();
}

function renderSources() {
  $("sourceCards").innerHTML = state.sources.map((source) => `
    <a class="source-card" href="${safeUrl(source.citation?.url)}" target="_blank" rel="noopener">
      <span class="source-dot${source.mode === "LIVE" ? " live" : ""}"></span>
      <span>
        <span class="source-title">${esc(source.source || "Official source")}</span>
        <span class="source-reason">${esc(cleanReason(source))}</span>
      </span>
      <span class="source-count">${esc(source.mode)}</span>
    </a>
  `).join("");
}

function renderInvestorProof() {
  const represented = new Set(state.leads.map((lead) => lead.state).filter(Boolean));
  const signed = state.leads.filter((lead) => lead.receipt_signed).length;
  const latest = state.board?.generated_at ? formatDate(state.board.generated_at) : "Unavailable";
  const facts = [
    ["Organizations returned in current pull", formatNumber(state.leads.length)],
    ["Eastern markets queryable", "27"],
    ["Markets represented in this pull", formatNumber(represented.size)],
    ["Signed source receipts in this pull", `${signed}/${state.leads.length || 0}`],
    ["Persistence health", state.health?.deal_desk_persistence || "Checking"],
    ["Generated", latest],
  ];
  $("operatingFacts").innerHTML = facts.map(([label, value]) => `
    <div class="fact-row"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>
  `).join("");

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
  document.querySelectorAll(".view-panel").forEach((panel) => panel.classList.remove("active"));
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.classList.toggle("active", button.dataset.viewTarget === view);
  });
  $(`${view}View`).classList.add("active");
}

function openLead(id) {
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
    <div class="drawer-fact"><span>${esc(item.system || "Identifier")}</span><strong>${esc(item.value || "--")}</strong></div>
  `).join("");
  const receiptLink = lead.receipt_id
    ? `<button class="drawer-link" type="button" data-proof-id="${esc(lead.receipt_id)}">Verify source receipt</button>`
    : "";
  const timing = timingSummary(lead);
  const fit = productFit(lead);
  const evidence = evidenceSummary(lead);
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
        <div class="drawer-fact"><span>State</span><strong>${esc(lead.state || "--")}</strong></div>
        <div class="drawer-fact"><span>Observed</span><strong>${esc(formatDate(observedDate(lead)))}</strong></div>
        <div class="drawer-fact"><span>Timing</span><strong>${esc(timing.label)}</strong></div>
        <div class="drawer-fact"><span>Evidence</span><strong>${esc(evidence.label)}</strong></div>
        <div class="drawer-fact"><span>${esc(value.label)}</span><strong>${esc(value.value)}</strong></div>
        <div class="drawer-fact"><span>Source state</span><strong>${esc(lead.truth_label || "LIVE")}</strong></div>
        ${idFacts}
      </div>
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
      <div id="proofResult"></div>
    </section>
  `;
  $("drawerBackdrop").classList.remove("hidden");
  $("drawerBackdrop").setAttribute("aria-hidden", "false");
  $("leadDrawer").classList.add("open");
  $("leadDrawer").setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  $("closeDrawer").focus();
}

function closeLead() {
  $("leadDrawer").classList.remove("open");
  $("leadDrawer").setAttribute("aria-hidden", "true");
  $("drawerBackdrop").classList.add("hidden");
  $("drawerBackdrop").setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

async function verifyProof(receiptId) {
  const result = $("proofResult");
  result.innerHTML = `<div class="proof-result">Verifying ${esc(receiptId)}...</div>`;
  try {
    const proof = await api(`/api/verify/${encodeURIComponent(receiptId)}`);
    const stateLabel = proof.signature_state || proof.state || (proof.verified ? "VERIFIED" : "OBSERVED");
    result.innerHTML = `<div class="proof-result">Receipt: ${esc(receiptId)}<br>Verification state: ${esc(stateLabel)}<br>Hash and source-normalization checks were returned by the current runtime response.</div>`;
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
    $("proofRelease").textContent = attested ? "OIDC attested" : "Observed";
    $("proofReleaseCopy").textContent = attested
      ? `Exact source revision ${revision} has a published GitHub OIDC receipt.`
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
  try {
    const access = await api("/api/access-mode");
    state.accessMode = access.mode;
    if (access.mode !== "public_readonly") {
      throw new Error("The public workspace is not enabled.");
    }
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
  $("mobileStateSelect").addEventListener("change", (event) => {
    const code = event.target.value;
    if (code === "__ALL__") {
      chooseRegion("All East");
    } else if (STATE_NAMES[code]) {
      selectOnlyState(code);
    }
  });
  $("stateAtlas").addEventListener("click", (event) => {
    const button = event.target.closest("[data-atlas-state]");
    if (button) selectOnlyState(button.dataset.atlasState);
  });
  $("refreshData").addEventListener("click", () => loadLeads());
  $("searchInput").addEventListener("input", applyFilters);
  $("sourceFilter").addEventListener("change", applyFilters);
  $("sortFilter").addEventListener("change", applyFilters);
  $("resetFilters").addEventListener("click", () => {
    $("searchInput").value = "";
    $("sourceFilter").value = "all";
    $("sortFilter").value = "priority";
    state.activeLane = "all";
    document.querySelectorAll("[data-lane]").forEach((item) => {
      item.classList.toggle("active", item.dataset.lane === "all");
    });
    applyFilters();
  });
  $("laneFilters").addEventListener("click", (event) => {
    const button = event.target.closest("[data-lane]");
    if (!button) return;
    state.activeLane = button.dataset.lane;
    document.querySelectorAll("[data-lane]").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    applyFilters();
  });
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.viewTarget));
  });
  ["leadRows", "leadCards"].forEach((id) => {
    $(id).addEventListener("click", (event) => {
      const button = event.target.closest("[data-lead-id]");
      if (button) openLead(button.dataset.leadId);
    });
  });
  $("drawerBody").addEventListener("click", (event) => {
    const button = event.target.closest("[data-proof-id]");
    if (button) verifyProof(button.dataset.proofId);
  });
  $("closeDrawer").addEventListener("click", closeLead);
  $("drawerBackdrop").addEventListener("click", closeLead);
  $("openPolicy").addEventListener("click", () => $("policyDialog").showModal());
  $("openPolicyMobile").addEventListener("click", () => $("policyDialog").showModal());
  $("reloadRelease").addEventListener("click", () => window.location.reload());
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && document.activeElement?.tagName !== "INPUT") {
      event.preventDefault();
      $("searchInput").focus();
    }
    if (event.key === "Escape" && $("leadDrawer").classList.contains("open")) {
      closeLead();
    }
  });
}

document.addEventListener("DOMContentLoaded", bootstrap);
