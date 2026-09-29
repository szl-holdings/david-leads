import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../app/static/index.html", import.meta.url), "utf8");
const script = readFileSync(new URL("../app/static/operator.js", import.meta.url), "utf8");
const id = (character) => character.repeat(64);

// A small event/DOM harness executes the shipped controller. Setting innerHTML
// throws so protected record rendering cannot pass via an HTML interpolation.
class Element {
  constructor(tagName = "div", attributes = {}) {
    this.tagName = tagName; this.children = []; this.events = {}; this.attributes = attributes;
    this.id = attributes.id || ""; this.dataset = {};
    for (const [key, value] of Object.entries(attributes)) if (key.startsWith("data-")) this.dataset[key.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase())] = value;
    this._text = ""; this.value = attributes.value || ""; this.defaultValue = this.value;
    this.hidden = "hidden" in attributes; this.disabled = false; this.checked = false;
  }
  set innerHTML(_) { throw new Error("Unsafe protected HTML interpolation"); }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(" "); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this._text = ""; if (this.tagName === "select") this.value = ""; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(event, handler) { this.events[event] = handler; }
  focus() { this.focused = true; }
  all() { return this.children.flatMap((child) => [child, ...child.all()]); }
  querySelectorAll(selector) {
    const selectors = selector.split(/,\s*/);
    return this.all().filter((child) => selectors.some((item) => item.startsWith(".") ? child.className === item.slice(1) : child.tagName === item));
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  reset() { for (const child of this.all()) { child.value = child.defaultValue; child.checked = false; } }
}
function harness(handler = () => { throw new Error("Unexpected request"); }) {
  const elements = new Map();
  for (const match of html.matchAll(/<([a-z0-9]+)\b([^>]*\bid="[^"]+"[^>]*)>/g)) {
    const attrs = {};
    for (const attr of match[2].matchAll(/([a-zA-Z0-9_-]+)(?:="([^"]*)")?/g)) attrs[attr[1]] = attr[2] || "";
    elements.set(attrs.id, new Element(match[1], attrs));
  }
  for (const match of html.matchAll(/<form\b[^>]*\bid="([^"]+)"[^>]*>([\s\S]*?)<\/form>/g)) {
    const form = elements.get(match[1]);
    for (const child of match[2].matchAll(/<(input|select)\b[^>]*\bid="([^"]+)"[^>]*>/g)) form.append(elements.get(child[2]));
    for (const child of match[2].matchAll(/<button\b([^>]*)>/g)) {
      const buttonId = child[1].match(/id="([^"]+)"/)?.[1];
      form.append(buttonId ? elements.get(buttonId) : new Element("button"));
    }
  }
  for (const match of html.matchAll(/<select\b[^>]*\bid="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)) {
    const value = match[2].match(/<option\b[^>]*\bvalue="([^"]*)"/)?.[1] || "";
    elements.get(match[1]).value = value; elements.get(match[1]).defaultValue = value;
  }
  const requests = [], timers = new Map(), lifecycle = {};
  let nextTimer = 0, nextKey = 0;
  const context = { URL, Date, Set, Number, JSON };
  vm.runInNewContext(`${script}\nthis.factory = createOperatorWorkspace;`, context);
  const document = {
    getElementById(key) { assert.ok(elements.has(key), `Unknown element ${key}`); return elements.get(key); },
    createElement(tag) { return new Element(tag); },
    querySelectorAll(selector) {
      const key = selector === "[data-operator-action]" ? "operatorAction" : "nodeKind";
      return [...elements.values()].filter((element) => key in element.dataset);
    },
  };
  const controller = context.factory({
    document, crypto: { randomUUID: () => `request-key-${++nextKey}` },
    fetch: async (path, options) => { requests.push({ path, ...options, body: options.body ? JSON.parse(options.body) : undefined }); return handler(path, options); },
    setTimeout: (callback) => { timers.set(++nextTimer, callback); return nextTimer; },
    clearTimeout: (timer) => timers.delete(timer),
    addEventListener: (name, callback) => { lifecycle[name] = callback; },
  });
  controller.init();
  const element = (name) => elements.get(name);
  const event = async (name, kind = "submit") => element(name).events[kind]({ preventDefault() {} });
  const signIn = async () => {
    element("operatorUsername").value = "researcher";
    element("operatorPassword").value = "test-password";
    element("operatorAccessKey").value = "test-access-key";
    await event("operatorLogin");
  };
  const open = async () => { element("operatorScope").value = "research-one"; await event("operatorScopeForm"); };
  return { element, requests, timers, lifecycle, event, signIn, open };
}
function response(payload, status = 200) { return { ok: status < 400, status, json: async () => payload }; }
const login = () => response({ token: "test-bearer", user: "researcher", expires_in: 900 });
function node(character, kind = "source", state = "VALID", extras = {}) {
  return { id: id(character), kind, state, scope_id: "research-one", expires_at: "2030-01-01T00:00:00Z", parents: [], ...extras };
}
function workspace(nodes = [], epoch = 0, actions = ["read", "admit", "brief", "review", "clearance", "manual_task", "correct", "suppress", "outcome"]) {
  return { schema: "szl.david.workspace/v2", scope_id: "research-one", decision_epoch: epoch, nodes, available_actions: actions, contact_permission: "NOT_GRANTED" };
}

test("public initialization never fetches operator data or writes browser storage", () => {
  const h = harness();
  assert.equal(h.requests.length, 0);
  assert.equal(h.element("operatorSession").hidden, true);
  assert.equal(h.element("operatorWorkspace").hidden, true);
  assert.doesNotMatch(script, /localStorage|sessionStorage|indexedDB/);
});

test("existing login and protected reads use no-store, memory token, and empty state", async () => {
  const h = harness((path) => path === "/api/login" ? login() : response(workspace()));
  await h.signIn(); await h.open();
  assert.equal(h.requests[0].body.username, "researcher");
  assert.equal(h.element("operatorPassword").value, "");
  assert.equal(h.element("operatorAccessKey").value, "");
  assert.equal(h.requests[1].path, "/api/v1/operator/workspaces/research-one");
  assert.equal(h.requests[1].headers.Authorization, "Bearer test-bearer");
  for (const request of h.requests) { assert.equal(request.cache, "no-store"); assert.equal(request.credentials, "omit"); assert.equal(request.redirect, "error"); }
  assert.match(h.element("operatorStatus").textContent, /no admitted evidence/);
  assert.equal(h.element("operatorEpoch").textContent, "0");
});

test("admission sends a reference and current version, never browser grants or raw records", async () => {
  let epoch = 3;
  const h = harness((path, options) => {
    if (path === "/api/login") return login();
    if (options.method === "POST") { epoch += 1; return response(node("a")); }
    return response(workspace([], epoch));
  });
  await h.signIn(); await h.open();
  h.element("operatorRecordId").value = "filing-1";
  h.element("operatorSnapshot").value = "b".repeat(40);
  await h.event("operatorAdmission");
  assert.deepEqual(h.requests[2].body, { source_id: "dol-form5500-benefit-timing", record_id: "filing-1", snapshot_revision: "b".repeat(40), expected_epoch: 3 });
  assert.equal(h.requests[3].method, "GET");
  assert.equal(h.element("operatorEpoch").textContent, "4");
});

test("brief approval defaults to rejection and resets after every reload", async () => {
  const brief = node("b", "brief", "VALID", { detail: { summary: "Review source", facts: [] } });
  const h = harness((path, options) => path === "/api/login" ? login() : response(options.method === "POST" ? node("c", "brief_review") : workspace([brief], 5)));
  await h.signIn(); await h.open();
  h.element("operatorBriefRef").value = brief.id;
  assert.equal(h.element("operatorBriefDecision").value, "REJECTED");
  await h.event("operatorReview");
  assert.equal(h.requests[2].body.approved, false);
  h.element("operatorBriefDecision").value = "APPROVED";
  await h.event("operatorReload", "click");
  assert.equal(h.element("operatorBriefDecision").value, "REJECTED");
});

test("stale decision is never retried automatically and reloads the current epoch", async () => {
  let reads = 0;
  const h = harness((path, options) => {
    if (path === "/api/login") return login();
    if (options.method === "POST") return response({ detail: { code: "DECISION_EPOCH_STALE" } }, 409);
    return response(workspace([node("a")], ++reads === 1 ? 2 : 8));
  });
  await h.signIn(); await h.open();
  h.element("operatorCorrectionRef").value = id("a");
  await h.event("operatorCorrection");
  assert.equal(h.requests.filter((request) => request.path.endsWith("/corrections")).length, 1);
  assert.equal(h.requests[2].body.expected_epoch, 2);
  assert.equal(h.element("operatorEpoch").textContent, "8");
  assert.match(h.element("operatorStatus").textContent, /Decision held/);
});

test("late workspace response after logout cannot repopulate protected data", async () => {
  let release;
  const h = harness((path) => {
    if (path === "/api/login") return login();
    if (path === "/api/logout") return response({ ok: true });
    return new Promise((resolve) => { release = resolve; });
  });
  await h.signIn();
  const pending = h.open();
  await h.event("operatorLogout", "click");
  release(response(workspace([node("a", "source", "VALID", { facts: { legal_name: "Protected organization" } })])));
  await pending;
  assert.equal(h.element("operatorSession").hidden, true);
  assert.equal(h.element("operatorWorkspace").hidden, true);
  assert.equal(h.element("operatorEvidenceList").textContent, "");
});

test("session expiry clears protected DOM and admission inputs", async () => {
  const h = harness((path) => path === "/api/login" ? login() : response(workspace([node("a")])));
  await h.signIn(); await h.open();
  h.element("operatorRecordId").value = "private-reference";
  [...h.timers.values()][0]();
  assert.equal(h.element("operatorEvidenceList").textContent, "");
  assert.equal(h.element("operatorRecordId").value, "");
  assert.equal(h.element("operatorSession").hidden, true);
  const previous = h.requests.length;
  await h.event("operatorAdmission");
  assert.equal(h.requests.length, previous);
});

test("protected rendering uses text nodes, nested allowlists, and withheld invalid facts", async () => {
  const unsafeName = '<img src=x onerror="steal()">';
  const source = node("a", "source", "VALID", { facts: { legal_name: unsafeName, secret: "never-render", channels: [{ value: "private-address" }] } });
  const invalid = node("b", "source", "REVOKED", { facts: { legal_name: "revoked-private" } });
  const brief = node("c", "brief", "VALID", { detail: { summary: "Known summary", secret: "hidden-detail", facts: [{ source_node_id: source.id, fields: { legal_name: "Brief organization", secret: "hidden-brief" } }] } });
  const h = harness((path) => path === "/api/login" ? login() : response(workspace([source, invalid, brief])));
  await h.signIn(); await h.open();
  const content = h.element("operatorEvidenceList").textContent + h.element("operatorHistory").textContent;
  assert.match(content, /<img src=x/);
  assert.doesNotMatch(content, /never-render|private-address|hidden-detail|hidden-brief/);
  // Even the invalid row's title must not use a withheld fact.
  assert.doesNotMatch(content, /revoked-private/);
  assert.match(content, /Facts are withheld/);
  assert.match(content, /Brief organization/);
});

test("uncertain task request retains the same idempotency key for explicit retry", async () => {
  let attempts = 0;
  const h = harness((path, options) => {
    if (path === "/api/login") return login();
    if (path.endsWith("/tasks")) { if (++attempts === 1) throw new Error("Connection lost"); return response(node("b", "manual_task")); }
    return response(workspace([node("a", "clearance")], 9));
  });
  await h.signIn(); await h.open();
  h.element("operatorClearanceRef").value = id("a");
  await h.event("operatorTask");
  await h.event("operatorTask");
  const posts = h.requests.filter((request) => request.path.endsWith("/tasks"));
  assert.equal(posts.length, 2);
  assert.equal(posts[0].body.idempotency_key, posts[1].body.idempotency_key);
  assert.equal(posts[0].body.task_type, "VERIFY_SOURCE");
  assert.equal(posts[0].body.expected_epoch, 9);
});

test("server permission removal disables actions and a malformed contract cannot unlock them", async () => {
  const h = harness((path) => path === "/api/login" ? login() : response(workspace([], 0, ["read"])));
  await h.signIn(); await h.open();
  assert.equal(h.element("operatorAdmission").querySelector("button").disabled, true);
  assert.match(h.element("operatorAdmission").textContent, /not included in your current operator policy/);
  const broken = harness((path) => path === "/api/login" ? login() : response({ ...workspace(), contact_permission: "GRANTED" }));
  await broken.signIn(); await broken.open();
  assert.equal(broken.element("operatorWorkspace").hidden, true);
  assert.match(broken.element("operatorStatus").textContent, /workspace contract invalid/);
});

test("a server 401 clears all protected state before another operation", async () => {
  let calls = 0;
  const h = harness((path) => path === "/api/login" ? login() : ++calls === 1 ? response(workspace([node("a")])) : response({ detail: "expired" }, 401));
  await h.signIn(); await h.open();
  h.element("operatorCorrectionRef").value = id("a");
  await h.event("operatorCorrection");
  assert.equal(h.element("operatorSession").hidden, true);
  assert.equal(h.element("operatorEvidenceList").textContent, "");
  assert.match(h.element("operatorStatus").textContent, /session is no longer valid/);
});

test("comparison requests exact stored brief references and renders only known fields", async () => {
  const h = harness((path) => {
    if (path === "/api/login") return login();
    if (path.includes("decision-diff")) return response({ known_then: "2026-09-12T00:00:00Z", known_later: "2026-09-19T00:00:00Z", added: [id("c")], removed: [], unchanged: [id("d")], secret: "must-not-render" });
    return response(workspace([node("a", "brief"), node("b", "brief")]));
  });
  await h.signIn(); await h.open();
  h.element("operatorDiffBefore").value = id("a"); h.element("operatorDiffAfter").value = id("b");
  await h.event("operatorDiff");
  assert.equal(h.requests[2].path, `/api/v1/operator/workspaces/research-one/decision-diff?before=${id("a")}&after=${id("b")}`);
  assert.match(h.element("operatorDiffResult").textContent, /2026-09-19/);
  assert.doesNotMatch(h.element("operatorDiffResult").textContent, /must-not-render/);
});

test("source health keeps failed attempt and last success distinct and checks references separately", async () => {
  const health = { status: "HOLD", configured_enabled: true, policy_state: "ALLOW", credential_state: "NOT_REQUIRED", transport_state: "FAILED", schema_state: "NOT_EVALUATED", integrity_state: "NOT_EVALUATED", completeness_state: "NOT_EVALUATED", freshness_state: "STALE", last_attempt_at: "2026-09-19T00:00:00Z", last_success_at: "2026-09-12T00:00:00Z", snapshot_revision: "a".repeat(40), eligible_operations: [], blocking_reasons: ["TRANSPORT_FAILED"], future_secret: "never-render-health" };
  const h = harness((path, options) => path === "/api/login" ? login() : response(options.method === "POST" ? health : { ...workspace([], 7), source_health: health }));
  await h.signIn(); await h.open();
  const display = h.element("operatorSourceHealth").textContent;
  assert.match(display, /Last attempt 2026-09-19/);
  assert.match(display, /Last success 2026-09-12/);
  assert.match(display, /Enabled; checks still required/);
  assert.match(display, /transport failed/);
  assert.doesNotMatch(display, /never-render-health/);
  h.element("operatorHealthSnapshot").value = "b".repeat(40);
  await h.event("operatorSourceRefresh");
  assert.equal(h.requests[2].path, "/api/v1/operator/workspaces/research-one/source-refreshes");
  assert.deepEqual(h.requests[2].body, { snapshot_revision: "b".repeat(40), expected_epoch: 7 });
  assert.match(h.element("operatorStatus").textContent, /admission remains a separate operation/);
});

test("selected source to reviewed brief to clearance to task uses returned references and reloaded epochs", async () => {
  const nodes = [node("a", "observation", "VALID", { facts: { legal_name: "Organization research fixture" } })];
  let epoch = 1;
  const kinds = { "identity-reviews": ["b", "organization_review", "ORGANIZATION_CONFIRMED"], briefs: ["c", "brief", null], "brief-reviews": ["d", "brief_review", "APPROVED"], clearances: ["e", "clearance", null], tasks: ["f", "manual_task", null] };
  const h = harness((path, options) => {
    if (path === "/api/login") return login();
    if (options.method === "POST") {
      const [character, kind, decision] = kinds[path.split("/").at(-1)];
      const created = node(character, kind, "VALID", { detail: { ...(decision ? { decision } : {}) } });
      nodes.push(created); epoch += 1; return response(created);
    }
    return response(workspace([...nodes], epoch));
  });
  await h.signIn(); await h.open();
  const selection = h.element("operatorEvidenceList").all().find((element) => element.dataset.sourceNodeId);
  selection.checked = true; selection.events.change();
  h.element("operatorIdentityDecision").value = "ORGANIZATION_CONFIRMED";
  await h.event("operatorIdentity");
  h.element("operatorIdentityRef").value = id("b"); await h.event("operatorBrief");
  h.element("operatorBriefRef").value = id("c"); h.element("operatorBriefDecision").value = "APPROVED"; await h.event("operatorReview");
  h.element("operatorReviewRef").value = id("d"); await h.event("operatorClearance");
  h.element("operatorClearanceRef").value = id("e"); await h.event("operatorTask");
  const posts = h.requests.filter((request) => request.method === "POST" && request.path !== "/api/login");
  assert.deepEqual(posts.map((request) => request.body.expected_epoch), [1, 2, 3, 4, 5]);
  assert.deepEqual(posts[0].body.source_ids, [id("a")]);
  assert.equal(posts[1].body.identity_review_id, id("b"));
  assert.equal(posts[2].body.brief_id, id("c"));
  assert.equal(posts[2].body.approved, true);
  assert.equal(posts[3].body.review_id, id("d"));
  assert.equal(posts[4].body.clearance_id, id("e"));
  assert.equal(h.element("operatorEpoch").textContent, "6");
  assert.match(h.element("operatorHistory").textContent, /manual task/);
});
