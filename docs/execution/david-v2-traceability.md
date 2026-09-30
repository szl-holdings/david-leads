# David V2 requirement traceability

| Requirement | Implementation owner and seam | Required evidence | Current status |
|---|---|---|---|
| G1 runtime-role isolation | Postgres adapter and schema | Real non-owner role, A/B and missing-tenant SQL, pool reuse | Executed locally on PostgreSQL; final hosted CI pending |
| G2 process restart and restore | Postgres integration tests | Different writer/reader processes and disposable restore | Actual process crash and pg_dump/restore executed locally |
| G3 typed identity | Adapter and SQL constraints | SQL-level rejection of parcel/facility canonical organization | Executed locally; no automatic organization union |
| G4 correction/action races | Scoped epoch, current authority and outbox | Two-connection interleavings, fencing, expiry/revocation during waits | Local barrier tests passed; final collect-only/scope-filter regression run pending |
| G5 source health | Current-policy overlay and canonical immutable DOL consumer | Reviewed grant, manifest, signature, completeness, freshness; last success preserved | Synthetic signed canonical publisher/readback/admission tests passed; real private source grant pending |
| G6 authorized workflow | Existing sessions, workflow API and operator UI | Positive manual research flow plus tamper, stale and denied paths | Real local PostgreSQL HTTP contracts passed; actual browser journey and live release pending |
| G7 nested privacy | Public response models and isolated operator controller | Nested injection, anonymous/operator isolation, no shared caching | Local policy/DTO and Node controller tests passed |
| G8 migration/release | Complete SQL transaction and existing protected deploy lane | Role/schema, rollback, compatibility, exact source and runtime | Actual migration tests passed; protected production migration/publication pending |
| M6 decision diff/impact | Stored brief features, counter-evidence and dependencies | Point-in-time stored comparison and correction impact | Implemented and locally exercised; no held-out lift or model-performance claim |
| M8 vertical reuse | Per-vertical disposition and canonical inventory | Two actual consumers before extraction, per-capability gates | No shared extraction or vertical readiness claim from metadata |

Offline, local PostgreSQL, CI, staging, public runtime and operator-sandbox results are separate evidence categories. This document authorizes no merge, data grant, signature, deployment or contact.
