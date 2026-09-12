# David evidence kernel (reference)

Executable invariants from the 2026-09-11 payload. **Not the production FastAPI app.**

- SQLite is for offline tests only. Production must use the existing Postgres service, RLS, and migrations.
- Integrity label is `LOCAL_SHA256_UNSIGNED`. This is not Cosign / DSSE.
- No network collector, contact sender, or deployer.
- P1b Postgres adapter (`david_postgres.py`) implements the same Hold / revoke / verify contracts on the existing Neon database. It does not replace `david_dealdesk_state` / `david_dealdesk_events`.
- Public `GET /api/v1/public/capabilities` is sanitized. READY cannot be PATCHed from a browser. IRS/NYC remain POLICY_HOLD; Chicago/SAM remain AUTH_REQUIRED; FCC remains NOT_IMPLEMENTED.

Run from the repository root after this package is on `PYTHONPATH`:

```bash
python -m unittest -v tests.test_david_reference
python -m unittest -v tests.test_david_postgres tests.test_david_p1b_api
```

Do not expose `Ledger` trusted-input methods as public APIs. Source policy and clearance facts must come from protected services.

This branch does **not** claim HF deployment, signed receipts, live IRS/NYC collection, or `receipt_minted`.
