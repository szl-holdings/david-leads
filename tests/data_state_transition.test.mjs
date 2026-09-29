// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";

class FakeClassList {
  constructor(...tokens) {
    this.tokens = new Set(tokens);
  }

  add(...tokens) {
    tokens.forEach((token) => this.tokens.add(token));
  }

  remove(...tokens) {
    tokens.forEach((token) => this.tokens.delete(token));
  }

  toggle(token, force) {
    if (force === undefined) {
      force = !this.tokens.has(token);
    }
    if (force) this.tokens.add(token);
    else this.tokens.delete(token);
    return force;
  }

  contains(token) {
    return this.tokens.has(token);
  }
}

function fakeElement(classes = []) {
  return {
    attributes: {},
    classList: new FakeClassList(...classes),
    disabled: false,
    innerHTML: "",
    lastChild: { textContent: "" },
    textContent: "",
    title: "",
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
  };
}

const observationChips = ["metricOrganizationsEvidence", "metricStatesEvidence", "metricSourcesEvidence"];

function metricElements() {
  const elements = Object.fromEntries([
    "metricOrganizations", "metricStates", "metricWindows", "metricSources", "metricResearch",
    "metricCleared", "metricOrganizationsSub", "metricStatesSub", "metricWindowsSub",
    "metricSourcesSub", "proofLiveSources",
  ].map((id) => [id, fakeElement()]));
  for (const id of observationChips) elements[id] = fakeElement(["honesty-chip", "unknown"]);
  return elements;
}

function assertObservationState(elements, expected) {
  for (const id of observationChips) {
    assert.equal(elements[id].textContent, expected, id);
    assert.equal(elements[id].classList.contains("measured"), expected === "MEASURED", id);
    assert.equal(elements[id].classList.contains("unknown"), expected === "UNKNOWN", id);
  }
}

function admitPublicObservation(hooks, opportunities = [{ state: "NY" }, { state: "VA" }]) {
  Object.assign(hooks.state, hooks.admitSourceBoard({
    access_mode: "PUBLIC_READONLY",
    generated_at: "2026-09-25T12:00:00Z",
    opportunities,
    sources: [{ source: "FMCSA", mode: "LIVE", count: opportunities.length }, { mode: "UNAVAILABLE" }],
    summary: { total: opportunities.length, live: opportunities.length, call_ready: 0, needs_research: opportunities.length },
  }));
  hooks.state.selectedStates = new Set(["NY", "VA"]);
}

function createHarness(fetch) {
  const elements = {
    ...metricElements(),
    dataStatePill: fakeElement(["live-pill", "unavailable"]),
    emptyState: fakeElement(),
    errorState: fakeElement(["hidden"]),
    loadingState: fakeElement(["hidden"]),
    refreshData: fakeElement(),
    resultCount: fakeElement(),
    workspace: fakeElement(),
    scopeNotice: fakeElement(),
    scopeSummary: fakeElement(),
  };
  elements.dataStatePill.lastChild.textContent = "DATA: CHECKING";

  const document = {
    addEventListener() {},
    getElementById(id) {
      assert.ok(elements[id], `unexpected DOM lookup: ${id}`);
      return elements[id];
    },
  };
  const context = {
    AbortController,
    clearTimeout,
    setTimeout,
    document,
    fetch,
    performance: { now: () => 100 },
    window: {
      location: { origin: "https://example.test" },
    },
  };
  const app = fs.readFileSync(new URL("../app/static/app.js", import.meta.url), "utf8");
  vm.runInNewContext(
    `${app}\nglobalThis.__dataStateTest = { state, renderDataState, renderMetrics, renderScope, loadLeads, admitSourceBoard, fetchFrontierBoard };`,
    context,
  );

  return { elements, hooks: context.__dataStateTest };
}

test("a new territory pull replaces stale LIVE evidence with CHECKING", () => {
  const { elements, hooks } = createHarness(() => new Promise(() => {}));

  hooks.state.board = { generated_at: "2026-08-01T20:00:00Z" };
  hooks.state.sources = [{ mode: "LIVE" }, { mode: "UNAVAILABLE" }];
  hooks.renderDataState();
  hooks.renderMetrics();
  assertObservationState(elements, "MEASURED");

  assert.equal(elements.dataStatePill.lastChild.textContent, "LIVE / MEASURED · 1/2");
  assert.equal(elements.dataStatePill.classList.contains("measured"), true);
  assert.equal(elements.dataStatePill.classList.contains("checking"), false);
  assert.match(elements.dataStatePill.title, /^Current pull observed /);

  hooks.state.selectedStates = new Set(["VA"]);
  void hooks.loadLeads();

  assert.equal(elements.dataStatePill.lastChild.textContent, "DATA: CHECKING");
  assert.equal(elements.dataStatePill.classList.contains("checking"), true);
  assert.equal(elements.dataStatePill.classList.contains("measured"), false);
  assert.equal(elements.dataStatePill.classList.contains("unavailable"), false);
  assert.equal(elements.dataStatePill.title, "Loading current source records for Virginia");
  assert.equal(elements.workspace.attributes["aria-busy"], "true");
  assert.equal(elements.refreshData.disabled, true);
  assert.equal(elements.resultCount.textContent, "Loading current source records");
  assertObservationState(elements, "UNKNOWN");
  assert.equal(elements.metricOrganizations.textContent, "UNKNOWN");
  assert.equal(elements.metricStates.textContent, "UNKNOWN");
  assert.equal(elements.metricSources.textContent, "UNKNOWN");
});

test("an aborted older pull cannot clear the newer pull's busy state", async () => {
  const requests = [];
  const fetch = (_path, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener("abort", () => {
      const error = new Error("aborted");
      error.name = "AbortError";
      reject(error);
    }, { once: true });
    requests.push({ resolve });
  });
  const { elements, hooks } = createHarness(fetch);
  hooks.state.selectedStates = new Set(["VA"]);

  const olderPull = hooks.loadLeads();
  void hooks.loadLeads();
  await olderPull;

  assert.equal(requests.length, 2);
  assert.equal(elements.dataStatePill.lastChild.textContent, "DATA: CHECKING");
  assert.equal(elements.dataStatePill.classList.contains("checking"), true);
  assert.equal(elements.workspace.attributes["aria-busy"], "true");
  assert.equal(elements.refreshData.disabled, true);
  assert.equal(elements.loadingState.classList.contains("hidden"), false);
  assertObservationState(elements, "UNKNOWN");
});

test("a busy public refresh honors Retry-After and retries without clearing state", async () => {
  const expected = {
    generated_at: "2026-08-28T07:30:00Z",
    opportunities: [],
    sources: [{ source: "FMCSA", mode: "LIVE", count: 0 }],
  };
  let attempts = 0;
  const fetch = async () => {
    attempts += 1;
    if (attempts === 1) {
      return {
        ok: false,
        status: 429,
        headers: { get: (name) => name === "Retry-After" ? "0" : null },
        json: async () => ({ detail: "live refresh already running" }),
      };
    }
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => expected,
    };
  };
  const { hooks } = createHarness(fetch);
  const controller = new AbortController();

  const actual = await hooks.fetchFrontierBoard(
    "/api/frontier-desk?states=VA&limit_per_source=8",
    controller,
  );

  assert.equal(attempts, 2);
  assert.equal(actual, expected);
});

test("a successful response with no LIVE source is admitted as unavailable, not zero demand", async () => {
  const board = {
    generated_at: "2026-08-26T20:00:00Z",
    opportunities: [{ opportunity_id: "must-not-render" }],
    sources: [
      { source: "DOL Form 5500", mode: "UNAVAILABLE", count: 0 },
      { source: "FMCSA", mode: "UNAVAILABLE", count: 0 },
    ],
  };
  const { hooks, elements } = createHarness(async () => board);
  const admitted = hooks.admitSourceBoard(board);

  assert.equal(admitted.board, board);
  assert.equal(admitted.sources.length, 2);
  assert.equal(admitted.leads.length, 0);
  assert.match(admitted.loadError, /No official source completed a live observation/);
  Object.assign(hooks.state, admitted);
  hooks.renderMetrics();
  assertObservationState(elements, "UNKNOWN");
  assert.equal(elements.metricOrganizations.textContent, "UNKNOWN");
  assert.equal(elements.metricSources.textContent, "UNKNOWN");
});

test("observation chips start unknown in the document and never imply public clearance", () => {
  const html = fs.readFileSync(new URL("../app/static/index.html", import.meta.url), "utf8");
  for (const id of observationChips) {
    assert.match(html, new RegExp(`id="${id}" class="honesty-chip unknown">UNKNOWN</span>`));
  }
  assert.match(html, /Cleared to contact <span class="honesty-chip unknown">UNKNOWN<\/span>/);
  assert.match(html, /id="metricCleared">UNKNOWN<\/strong>/);
  assert.match(html, /Private clearance is not exposed in this public view/);
  assert.match(html, /Public data never creates consent/);
});

test("admitted live observations measure counts while public clearance remains protected", () => {
  const { hooks, elements } = createHarness(async () => {});
  admitPublicObservation(hooks);
  hooks.renderMetrics();

  assertObservationState(elements, "MEASURED");
  assert.equal(elements.metricOrganizations.textContent, "2");
  assert.equal(elements.metricStates.textContent, "2/2");
  assert.equal(elements.metricSources.textContent, "1/2");
  assert.equal(elements.metricCleared.textContent, "Protected");
  // Even an unexpected count cannot expose or manufacture clearance in this public view.
  hooks.state.board.summary.call_ready = 42;
  hooks.renderMetrics();
  assert.equal(elements.metricCleared.textContent, "Protected");
});

test("a completed LIVE source with no records produces measured zeros", () => {
  const { hooks, elements } = createHarness(async () => {});
  admitPublicObservation(hooks, []);
  hooks.renderMetrics();

  assertObservationState(elements, "MEASURED");
  assert.equal(elements.metricOrganizations.textContent, "0");
  assert.equal(elements.metricStates.textContent, "0/2");
  assert.equal(elements.metricSources.textContent, "1/2");
  assert.equal(elements.metricCleared.textContent, "Protected");
});

test("unproved or missing clearance contracts do not manufacture measured clearance", () => {
  const { hooks, elements } = createHarness(async () => {});
  admitPublicObservation(hooks);
  for (const accessMode of [undefined, "AUTHENTICATED"]) {
    hooks.state.board.access_mode = accessMode;
    hooks.state.board.summary.call_ready = 3;
    hooks.renderMetrics();
    assert.equal(elements.metricCleared.textContent, "UNKNOWN");
  }
  delete hooks.state.board.summary.call_ready;
  hooks.renderMetrics();
  assert.equal(elements.metricCleared.textContent, "UNKNOWN");
});

test("metric evidence stays unknown while a busy pull retries", async () => {
  let attempts = 0;
  let secondAttempt;
  const retryStarted = new Promise((resolve) => { secondAttempt = resolve; });
  const { hooks, elements } = createHarness(async () => {
    attempts += 1;
    if (attempts === 1) {
      return {
        ok: false, status: 429,
        headers: { get: (name) => name === "Retry-After" ? "0" : null },
        json: async () => ({ detail: "live refresh already running" }),
      };
    }
    secondAttempt();
    return new Promise(() => {});
  });
  admitPublicObservation(hooks);
  hooks.renderMetrics();
  assertObservationState(elements, "MEASURED");
  void hooks.loadLeads();
  await retryStarted;

  assert.equal(attempts, 2);
  assertObservationState(elements, "UNKNOWN");
  assert.equal(elements.metricOrganizations.textContent, "UNKNOWN");
  assert.equal(elements.dataStatePill.lastChild.textContent, "DATA: CHECKING");
  assert.equal(elements.workspace.attributes["aria-busy"], "true");
});

test("cross-territory scope describes bounded snapshot selection without a recency claim", () => {
  const { hooks, elements } = createHarness(async () => {});
  admitPublicObservation(hooks);
  hooks.renderScope();

  assert.match(elements.scopeNotice.textContent, /bounded selection from each verified source snapshot/);
  assert.doesNotMatch(elements.scopeNotice.textContent, /latest records per source/);
  assert.match(elements.scopeNotice.textContent, /choose one state for a deeper view/);
});

test("a failed pull clears prior territory evidence without false zeros", () => {
  const strong = { textContent: "Old broker brief: 72 organizations" };
  const small = { textContent: "Old New York observation" };
  const elements = {
    ...metricElements(),
    freshness: fakeElement(),
    dailyBrief: {
      querySelector(selector) {
        return selector === "strong" ? strong : small;
      },
    },
    stateAtlas: fakeElement(),
    atlasNote: fakeElement(),
    sourceCards: fakeElement(),
    operatingFacts: fakeElement(),
    proofPackets: fakeElement(),
    proofClock: fakeElement(),
    largestAward: fakeElement(),
  };
  const document = {
    addEventListener() {},
    getElementById(id) {
      assert.ok(elements[id], `unexpected DOM lookup: ${id}`);
      return elements[id];
    },
  };
  const context = {
    AbortController,
    document,
    fetch: async () => { throw new Error("not used"); },
    performance: { now: () => 100 },
    window: { location: { origin: "https://example.test" } },
  };
  const app = fs.readFileSync(new URL("../app/static/app.js", import.meta.url), "utf8");
  vm.runInNewContext(
    `${app}\nglobalThis.__unavailableTest = { state, renderMetrics, admitSourceBoard, renderUnavailableEvidence };`,
    context,
  );

  const { state: appState, renderMetrics, renderUnavailableEvidence } = context.__unavailableTest;
  admitPublicObservation(context.__unavailableTest);
  renderMetrics();
  assertObservationState(elements, "MEASURED");
  appState.board = null;
  appState.leads = [];
  appState.sources = [];
  appState.selectedStates = new Set(["NY"]);
  appState.loadError = "The Virginia pull did not complete.";
  renderUnavailableEvidence();
  assertObservationState(elements, "UNKNOWN");

  for (const id of [
    "metricOrganizations", "metricStates", "metricWindows", "metricSources",
    "metricResearch", "metricCleared", "proofLiveSources",
  ]) {
    assert.equal(elements[id].textContent, "UNKNOWN");
  }
  assert.equal(elements.freshness.textContent, "Live sources unavailable");
  assert.match(strong.textContent, /unavailable/i);
  assert.doesNotMatch(`${strong.textContent} ${small.textContent}`, /72 organizations|Old New York/);
  assert.match(elements.stateAtlas.innerHTML, /UNKNOWN/);
  assert.doesNotMatch(elements.stateAtlas.innerHTML, /<span>0<\/span>/);
  assert.match(elements.atlasNote.textContent, /UNKNOWN is not a zero/i);
  assert.match(elements.sourceCards.innerHTML, /UNAVAILABLE/);
  assert.doesNotMatch(elements.operatingFacts.innerHTML, /0\/0|>0</);
  assert.equal(elements.proofPackets.textContent, "UNKNOWN");
  assert.equal(elements.proofClock.textContent, "UNKNOWN");
  assert.match(elements.largestAward.textContent, /unavailable/i);
  assert.doesNotMatch(elements.largestAward.textContent, /\$|Old/);
});
