// SPDX-License-Identifier: Apache-2.0
// Pure local DOM/transport doubles: these tests never start the app or contact an endpoint.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";

class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.attributes = {};
    this.hidden = false;
    this.disabled = false;
    this.listeners = {};
    this.value = "";
  }
  set textContent(value) { this.value = String(value); this.children = []; }
  get textContent() { return this.value + this.children.map((node) => node.textContent).join(""); }
  set innerHTML(_) { throw new Error("API text must never pass through an HTML sink"); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.value = ""; this.children = [...nodes]; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  addEventListener(key, value) { this.listeners[key] = value; }
  scrollIntoView(value) { this.scrolled = value; }
}

const response = (value, status = 200) => ({ ok: status < 400, status, json: async () => value });
const pending = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const tick = () => new Promise((resolve) => setImmediate(resolve));
const score = (id = "LOCAL-SYNTHETIC") => ({
  legal_name: `SYNTHETIC ${id} <img src=x onerror=alert(1)>`, score: 42, bucket: "DEMO <b>text</b>",
  truth_state: "UNKNOWN", admitted_signals: 2, denied_signals: [],
  disclaimers: ["LOCAL fixture only <script>not markup</script>"],
  receipt: { receipt_id: id, signature_status: "UNSIGNED (LOCAL TEST FIXTURE)", payload: { synthetic: true } },
});

function harness() {
  const nodes = Object.fromEntries(["#sources tbody", "#leads", "#result", "#result-summary", "#receipt", "#verify-out", "#verify-btn"].map((id) => [id, new Element()]));
  nodes["#verify-btn"].disabled = true;
  const created = [];
  const timers = new Map();
  const requests = [];
  let sequence = 0;
  const fixture = {
    sources: { adapters: [] }, leads: { leads: [] },
    post: () => { throw new Error("No explicit local POST fixture installed"); },
  };
  const context = {
    AbortController,
    document: {
      querySelector(selector) { assert.ok(nodes[selector], selector); return nodes[selector]; },
      createElement(tag) { const node = new Element(tag); created.push(node); return node; },
    },
    fetch: async (url, opts) => {
      requests.push({ url, opts });
      if (opts.method === "POST") return fixture.post(url, opts);
      if (url === "v1/sources") return response(fixture.sources);
      if (url === "v1/leads") return response(fixture.leads);
      throw new Error(`Unexpected fixture path: ${url}`);
    },
    window: {
      matchMedia: () => ({ matches: true }),
      setTimeout(fn, delay) { assert.equal(delay, 20000); const id = ++sequence; timers.set(id, fn); return id; },
      clearTimeout(id) { timers.delete(id); },
    },
  };
  const source = fs.readFileSync(new URL("../backend/static/app.js", import.meta.url), "utf8");
  vm.runInNewContext(source + "\nglobalThis.hooks = {loadSources,loadLeads,scoreLead,verifyReceipt,stateClass,get receipt(){return lastReceipt}};", context);
  return { nodes, requests, created, fixture, timers, hooks: context.hooks };
}

test("adapter and lead API fields remain literal text, including hostile markup and prototype names", async () => {
  const h = harness();
  await tick();
  const hostile = '<svg onload="alert(1)"><script>never execute</script></svg>';
  h.fixture.sources = { adapters: [{ name: hostile, kind: hostile, truth_state: "__proto__", detail: hostile }] };
  h.fixture.leads = { leads: [{ id: "LOCAL-DEMO", legal_name: hostile, state: hostile, signals: [], synthetic: true }] };
  await h.hooks.loadSources();
  await h.hooks.loadLeads();
  assert.ok(h.nodes["#sources tbody"].textContent.includes(hostile));
  assert.ok(h.nodes["#leads"].textContent.includes(hostile));
  assert.equal(h.hooks.stateClass("__proto__"), "unknown");
  assert.equal(h.hooks.stateClass("constructor"), "unknown");
  assert.equal(h.created.filter((node) => ["svg", "script", "img"].includes(node.tagName)).length, 0);
  const button = h.created.find((node) => node.tagName === "button");
  assert.equal(button.attributes["aria-label"], `Score ${hostile}`);
  assert.equal(h.requests.filter((r) => r.opts.method === "POST").length, 0);
});

test("empty and malformed catalogs expose absence without a fabricated populated table", async () => {
  const h = harness(); await tick();
  assert.match(h.nodes["#sources tbody"].textContent, /UNKNOWN: no adapters/);
  assert.match(h.nodes["#leads"].textContent, /No demo records loaded/);
  h.fixture.sources = null; h.fixture.leads = { leads: null };
  await h.hooks.loadSources(); await h.hooks.loadLeads();
  assert.match(h.nodes["#sources tbody"].textContent, /UNAVAILABLE: Source response is incomplete/);
  assert.match(h.nodes["#leads"].textContent, /UNAVAILABLE: Demonstration response is incomplete/);
  assert.equal(h.nodes["#verify-btn"].disabled, true);
});

test("successful local scoring preserves exact POST shapes, literal text and reduced motion", async () => {
  const h = harness(); await tick(); const data = score();
  h.fixture.post = (url, opts) => {
    assert.equal(opts.headers["Content-Type"], "application/json");
    if (url === "v1/score") { assert.deepEqual(JSON.parse(opts.body), { lead_id: "LOCAL-DEMO" }); return response(data); }
    assert.equal(url, "v1/receipts/verify");
    assert.deepEqual(JSON.parse(opts.body), { receipt: data.receipt });
    return response({ verdict: "LOCAL TEST ONLY", signature_state: "UNSIGNED" });
  };
  await h.hooks.scoreLead("LOCAL-DEMO");
  assert.ok(h.nodes["#result-summary"].textContent.includes(data.legal_name));
  assert.ok(h.nodes["#result-summary"].textContent.includes(data.disclaimers[0]));
  assert.equal(h.nodes["#result"].scrolled.behavior, "auto");
  assert.equal(h.nodes["#verify-btn"].disabled, false);
  assert.equal(h.nodes["#result"].attributes["aria-busy"], "false");
  await h.hooks.verifyReceipt();
  assert.match(h.nodes["#verify-out"].textContent, /LOCAL TEST ONLY/);
  assert.equal(h.requests.filter((r) => r.opts.method === "POST").length, 2);
  assert.equal(h.timers.size, 0);
});

test("a new pending or failed score immediately clears the prior receipt and verification", async () => {
  const h = harness(); await tick();
  h.fixture.post = () => response(score("OLD-LOCAL"));
  await h.hooks.scoreLead("old");
  h.nodes["#verify-out"].textContent = "OLD LOCAL verification";
  const next = pending(); h.fixture.post = () => next.promise;
  const attempt = h.hooks.scoreLead("new");
  assert.equal(h.hooks.receipt, null);
  assert.equal(h.nodes["#verify-btn"].disabled, true);
  assert.equal(h.nodes["#receipt"].textContent, "");
  assert.equal(h.nodes["#verify-out"].textContent, "");
  assert.equal(h.nodes["#verify-out"].hidden, true);
  const count = h.requests.length;
  await h.hooks.verifyReceipt(); assert.equal(h.requests.length, count);
  next.reject(new Error("LOCAL source unavailable <img>")); await attempt;
  assert.match(h.nodes["#result-summary"].textContent, /scoring UNAVAILABLE: LOCAL source unavailable <img>/);
  assert.equal(h.hooks.receipt, null);
  assert.equal(h.nodes["#verify-btn"].disabled, true);
});

test("late score replies cannot replace the selected record or clear its pending state", async () => {
  const h = harness(); await tick(); const first = pending(), second = pending(); let index = 0;
  h.fixture.post = () => [first, second][index++].promise;
  const older = h.hooks.scoreLead("old"); const current = h.hooks.scoreLead("new");
  first.resolve(response(score("OLDER"))); await older;
  assert.equal(h.hooks.receipt, null);
  assert.equal(h.nodes["#result"].attributes["aria-busy"], "true");
  second.resolve(response(score("CURRENT"))); await current;
  assert.equal(h.hooks.receipt.receipt_id, "CURRENT");
  assert.doesNotMatch(h.nodes["#result-summary"].textContent, /OLDER/);
});

test("late verification cannot reappear after a different scoring selection", async () => {
  const h = harness(); await tick(); const verification = pending();
  h.fixture.post = (url) => url === "v1/score" ? response(score("OLD")) : verification.promise;
  await h.hooks.scoreLead("old"); const verifying = h.hooks.verifyReceipt();
  h.fixture.post = () => response(score("CURRENT")); await h.hooks.scoreLead("current");
  verification.resolve(response({ verdict: "OLD VERIFICATION" })); await verifying;
  assert.equal(h.nodes["#verify-out"].hidden, true);
  assert.equal(h.nodes["#verify-out"].textContent, "");
  assert.equal(h.nodes["#verify-btn"].disabled, false);
  assert.equal(h.hooks.receipt.receipt_id, "CURRENT");
});

test("invalid score response keeps receipt actions disabled and null scores remain absent", async () => {
  const h = harness(); await tick();
  h.fixture.post = () => response({ ...score(), score: null }); await h.hooks.scoreLead("none");
  assert.match(h.nodes["#result-summary"].textContent, /no score emitted/);
  assert.doesNotMatch(h.nodes["#result-summary"].textContent, /0 \/ 100/);
  h.fixture.post = () => response({ ...score(), receipt: null }); await h.hooks.scoreLead("malformed");
  assert.match(h.nodes["#result-summary"].textContent, /scoring UNAVAILABLE/);
  assert.equal(h.hooks.receipt, null);
  assert.equal(h.nodes["#verify-btn"].disabled, true);
});

test("a bounded timeout reports an unreceived result and does not retry or retain a receipt", async () => {
  const h = harness(); await tick();
  h.fixture.post = (_url, opts) => new Promise((_resolve, reject) => opts.signal.addEventListener("abort", () => {
    const error = new Error("LOCAL abort"); error.name = "AbortError"; reject(error);
  }));
  const task = h.hooks.scoreLead("LOCAL-TIMEOUT");
  assert.equal(h.timers.size, 1);
  [...h.timers.values()][0](); await task;
  assert.match(h.nodes["#result-summary"].textContent, /Request timed out; no result was received/);
  assert.equal(h.requests.filter((r) => r.opts.method === "POST").length, 1);
  assert.equal(h.nodes["#verify-btn"].disabled, true);
  assert.equal(h.timers.size, 0);
});
