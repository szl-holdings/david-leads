# David V2 requirement traceability

| Requirement | Implementation owner and seam | Required evidence | Current status |
|---|---|---|---|
| G1 runtime-role isolation | Postgres adapter, schema, runtime-role tests | Real non-owner role, A/B and missing-tenant SQL, pool reuse | In progress |
| G2 process restart and restore | Postgres integration tests | Different writer/reader processes and disposable restore | In progress |
| G3 typed identity | Adapter and SQL constraints | SQL-level rejection of parcel/facility canonical organization | In progress |
| G4 correction/action races | Scoped decision epoch and outbox | Deterministic two-connection interleavings and fencing | In progress |
| G5 source health | Source policy and DOL snapshot consumer | Grant, manifest, schema, completeness, freshness; last success preserved | In progress |
| G6 authorized workflow | Existing session boundary, workflow service and app/static | Allowed manual research path plus tamper, stale and denied paths | In progress |
| G7 nested privacy | Explicit public response models | Nested injection, anonymous/operator isolation, no shared caching | In progress |
| G8 migration/release | Existing migration and protected deploy lane | Schema/role shape, failure admission, compatibility, exact source | Pending integration |
| M6 decision diff/impact | Evidence versions and dependencies | Point-in-time replay and correction impact without unsupported lift claims | Pending core slice |
| M8 vertical reuse | Refreshed canonical inventory | Two real consumers before extraction, per-capability policy gates | Inventory in progress |

Offline, local PostgreSQL, CI, staging, public runtime and operator-sandbox results are separate evidence categories. This document authorizes no merge, data grant, signature, deployment or contact.
