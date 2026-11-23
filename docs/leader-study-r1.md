# david-leads domain leader study r1 (propose-only)

Date: 2026-11-22. Method: web-verified 2026 leaders. Documentation only: no code, CI, config, or existing-PR status changes. All absorb actions are FUTURE and non-authorizing; implementation and merges remain separately reviewed and gated by the signature wall.

## Domain: bounded runtime PostgreSQL preflight statements

## Leaders studied (web-verified 2026-11-22)

1. **PgBouncer** admission-control doctrine: cap real server connections below the database operational limit; bounded client queue; reject work before admission. [Normative admin docs](https://www.pgbouncer.org/config.html).
2. **PostgreSQL SME pooling best practices** (community opinion, non-normative). [SME article](https://postgresql.codeguides.io/en/practice/observability/monitoring-connection-pools.html).

## Absorb actions (FUTURE PROPOSALS, non-authorizing)

1. (PgBouncer doctrine) Preflight statement counts are hard-bounded per source; work is rejected pre-admission with explicit reason when the bound would be exceeded.
2. (pool discipline) Preflight queries carry per-query timeouts; overflow fail-closes the readiness path rather than queueing unbounded.
Read-only alignment: open PR #185 (bound runtime PostgreSQL preflight statements); no status claim.

## Sources (accessed 2026-11-22)

- PgBouncer config docs: https://www.pgbouncer.org/config.html (normative)
- PostgreSQL SME pooling article: https://postgresql.codeguides.io/en/practice/observability/monitoring-connection-pools.html (community opinion, non-normative)

## Do not do

Do not merge, bypass the signature wall, or claim implementation beyond this card.
