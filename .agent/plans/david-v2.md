# David V2 execution

## Purpose
Continue the existing David application and draft evidence/Postgres stack. Deliver a durable, tenant-scoped organization research workflow through reviewed briefs, permission-bound manual research tasks, and corrections. Preserve source restrictions and the protected GitHub to Hugging Face to product to proof release order.

## Progress
- 2026-09-12: Read the complete V2 payload in sections. Current main is `8e2158fe2572932040d11e271c11811e6fe5e743`; draft #117 is `7baa923e10b458645076dc790e8ac06230c7065a`; stacked draft #118 is `bac608bec90208b4ce8df297265dca30efd6fa62`.
- Adopted #118 in an isolated local checkout; no source reset or remote mutation. No applicable AGENTS, override, or PLANS files were found by the adoption audit.
- Confirmed unsafe parent-validation/correction interleaving, inconsistent multi-transaction ancestor reads, runtime-role test gap, non-organization SQL identity gap, and semicolon-splitting schema execution.
- Confirmed DOL bulk publisher and runtime consumer use different paths. Source capability configuration currently masquerades as live health.
- Prior task: www redirect is now live, preserves path/query, and reaches the apex with HTTP 200. Old A11oy landing repair replayed onto current main `a0f4f15fb4a324c8d24eb40f5d02d6bb02e8705c`. Forge's old publication patch needs reconciliation with seven now-owned publisher targets. Platform changes remain handed off to its active owner.

## Discoveries
- David's current auth uses an expiring server-side bearer session for the configured operator. The new workflow must derive tenant and allowed actions from server-owned grants, never a request tenant header or client gate flags.
- Existing legacy deal-desk state and tables remain in place. The new manual research workflow does not dispatch contact or grant outreach permission.
- PostgreSQL 16 is available as task-owned native binaries and a preserved disposable cluster on loopback port 55433. The cluster recovered after the September 19 disk-full interruption without a data reset. No production database is being used for tests.

## Decisions
- BE1 owns evidence schema, adapter and real PostgreSQL role/race/restart tests.
- BE2 owns source policy, dynamic source health, DOL publisher/consumer reconciliation and focused tests.
- Coordinator owns authenticated API seams, workflow service, migration/CI integration, release evidence and this plan.
- Frontend work will extend app/static after the versioned API is agreed; no separate V2 app.
- Source rights, model admission and external publication remain independent gates. Synthetic test data must never enter the live research queue.
- Use scoped database serialization and version comparison. No global universal lock; no false exactly-once promise for external systems.

## Validation
On September 29, the integrated runtime subset passed 57 tests and four subtests with zero skips on real PostgreSQL. It covers non-owner runtime-role isolation, deterministic races, process restart and dump/restore, HTTP workflow and actual inline migration execution. The source integration passed canonical publisher/readback/private admission contracts. Subsequent review repairs add collect-only revocation and wrong-scope lock filtering; their final full run remains necessary. Operator policy and operational safety passed 95 tests and eleven subtests. The full Python/Node run and actual browser journey are in progress. Hosted exact-source CI, protected migration and provider/runtime verification remain release gates.

## Recovery
The original #117/#118 stack merged upstream. Local implementation checkpoint is signed commit `ae5b9aead144824930cdda1a06bb08ab97339d88`; integration of current main `901f19f0ed2a11113a98d59ccec4e873161ec494` preserves the canonical federal pipeline and shared provider locks. Preserve local modifications. Refresh main, PR heads and checks immediately before publication. Expanded schema preserves old envelope bytes and legacy deal-desk tables. The obsolete waiting September 12 migration cannot satisfy current-source release admission.

## Outcomes
Implementation is integrated locally, including operator UI/API, durable evidence workflow, current-policy health and admission, manual task/outbox fencing, correction impact and deterministic brief comparison. New source adapters and shared vertical extraction remain gated by actual reviewed inputs and two real consumers. No V2 feature has yet been independently verified live. The latest main provider deployment failed its dataset-admission read with HTTP 401; publication and attestation were skipped. Proceed through signed source and exact CI, current-main migration, verified provider publication and live functional probes in that order.
