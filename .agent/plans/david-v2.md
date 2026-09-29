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
- PostgreSQL 16 is available in a task-owned disposable local Docker container on loopback port 55432. No production database is being used for tests.

## Decisions
- BE1 owns evidence schema, adapter and real PostgreSQL role/race/restart tests.
- BE2 owns source policy, dynamic source health, DOL publisher/consumer reconciliation and focused tests.
- Coordinator owns authenticated API seams, workflow service, migration/CI integration, release evidence and this plan.
- Frontend work will extend app/static after the versioned API is agreed; no separate V2 app.
- Source rights, model admission and external publication remain independent gates. Synthetic test data must never enter the live research queue.
- Use scoped database serialization and version comparison. No global universal lock; no false exactly-once promise for external systems.

## Validation
Pending: real non-owner runtime-role isolation, deterministic two-connection correction/task races, process restart and restore, strict public projections, authenticated positive/negative API workflow, DOL snapshot parity, existing full Python/Node suites, browser behavior, exact-source CI and protected release.

## Recovery
Current implementation base: draft #118 at `bac608bec90208b4ce8df297265dca30efd6fa62`. Preserve all local modifications. Do not replay stale mutation commands. Refresh main, PR heads, ownership and checks immediately before publication. Do not migrate production or publish unreviewed source. Expanded schema must preserve old envelope bytes and legacy deal-desk tables.

## Outcomes
Implementation in progress. No V2 feature has been deployed or independently verified live. Next action: complete the production-equivalent storage and authenticated workflow contracts, then execute their integration tests.
