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

function createHarness(fetch) {
  const elements = {
    dataStatePill: fakeElement(["live-pill", "unavailable"]),
    emptyState: fakeElement(),
    errorState: fakeElement(["hidden"]),
    loadingState: fakeElement(["hidden"]),
    refreshData: fakeElement(),
    resultCount: fakeElement(),
    workspace: fakeElement(),
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
    `${app}\nglobalThis.__dataStateTest = { state, renderDataState, loadLeads, admitSourceBoard, fetchFrontierBoard };`,
    context,
  );

  return { elements, hooks: context.__dataStateTest };
}

test("a new territory pull replaces stale LIVE evidence with CHECKING", () => {
  const { elements, hooks } = createHarness(() => new Promise(() => {}));

  hooks.state.board = { generated_at: "2026-08-01T20:00:00Z" };
  hooks.state.sources = [{ mode: "LIVE" }, { mode: "UNAVAILABLE" }];
  hooks.renderDataState();

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
  const { hooks } = createHarness(async () => board);
  const admitted = hooks.admitSourceBoard(board);

  assert.equal(admitted.board, board);
  assert.equal(admitted.sources.length, 2);
  assert.equal(admitted.leads.length, 0);
  assert.match(admitted.loadError, /No official source completed a live observation/);
});

test("a failed pull clears prior territory evidence without false zeros", () => {
  const strong = { textContent: "Old broker brief: 72 organizations" };
  const small = { textContent: "Old New York observation" };
  const elements = {
    metricOrganizations: fakeElement(),
    metricStates: fakeElement(),
    metricWindows: fakeElement(),
    metricSources: fakeElement(),
    metricResearch: fakeElement(),
    metricCleared: fakeElement(),
    metricOrganizationsSub: fakeElement(),
    metricStatesSub: fakeElement(),
    metricWindowsSub: fakeElement(),
    metricSourcesSub: fakeElement(),
    proofLiveSources: fakeElement(),
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
    `${app}\nglobalThis.__unavailableTest = { state, renderUnavailableEvidence };`,
    context,
  );

  const { state: appState, renderUnavailableEvidence } = context.__unavailableTest;
  appState.board = null;
  appState.leads = [];
  appState.sources = [];
  appState.selectedStates = new Set(["NY"]);
  appState.loadError = "The Virginia pull did not complete.";
  renderUnavailableEvidence();

  for (const id of [
    "metricOrganizations", "metricStates", "metricWindows", "metricSources",
    "metricResearch", "metricCleared", "proofLiveSources",
  ]) {
    assert.equal(elements[id].textContent, "--");
  }
  assert.equal(elements.freshness.textContent, "Live sources unavailable");
  assert.match(strong.textContent, /unavailable/i);
  assert.doesNotMatch(`${strong.textContent} ${small.textContent}`, /72 organizations|Old New York/);
  assert.match(elements.stateAtlas.innerHTML, /<span>--<\/span>/);
  assert.doesNotMatch(elements.stateAtlas.innerHTML, /<span>0<\/span>/);
  assert.match(elements.atlasNote.textContent, /dash is not a zero/i);
  assert.match(elements.sourceCards.innerHTML, /UNAVAILABLE/);
  assert.doesNotMatch(elements.operatingFacts.innerHTML, /0\/0|>0</);
  assert.equal(elements.proofPackets.textContent, "--");
  assert.equal(elements.proofClock.textContent, "--");
  assert.match(elements.largestAward.textContent, /unavailable/i);
  assert.doesNotMatch(elements.largestAward.textContent, /\$|Old/);
});
