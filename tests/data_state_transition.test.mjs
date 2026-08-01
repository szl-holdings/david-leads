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
    document,
    fetch,
    performance: { now: () => 100 },
    window: {
      location: { origin: "https://example.test" },
    },
  };
  const app = fs.readFileSync(new URL("../app/static/app.js", import.meta.url), "utf8");
  vm.runInNewContext(
    `${app}\nglobalThis.__dataStateTest = { state, renderDataState, loadLeads };`,
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
