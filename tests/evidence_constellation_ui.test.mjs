import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const app = await readFile(new URL("../app/static/app.js", import.meta.url), "utf8");
const html = await readFile(new URL("../app/static/index.html", import.meta.url), "utf8");

test("Evidence Constellation is mounted in the lead drawer", () => {
  assert.match(app, /lead\.evidence_constellation/);
  assert.match(app, /Why this may be wrong/);
  assert.match(app, /PUBLIC_RESEARCH_ONLY/);
  assert.match(app, /Proof quality is not a sales probability/);
});

test("investor proof cards are wired to live constellation metrics", () => {
  assert.match(html, /id="proofPackets"/);
  assert.match(html, /id="proofClock"/);
  assert.match(app, /state\.board\?\.evidence_constellation/);
  assert.match(app, /session_verifiable_references/);
  assert.match(app, /constellation\.signed_source_receipts/);
  assert.doesNotMatch(app, /filter\(\(lead\) => lead\.receipt_signed\)/);
  assert.doesNotMatch(app, /replayable_packets/);
  assert.match(app, /RECHECK_DUE/);
});

test("receipt verification exposes signature, chain, scope, and witness limits", () => {
  assert.match(app, /Predecessor chain/);
  assert.match(app, /Chain limit/);
  assert.match(app, /claim_scope/);
  assert.match(app, /witness\.durability/);
  assert.match(app, /Witness mode/);
});
