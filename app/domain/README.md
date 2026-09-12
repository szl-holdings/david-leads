# David evidence kernel (reference)

Executable invariants from the 2026-09-11 payload. **Not the production FastAPI app.**

- SQLite is for offline tests only. Production must use the existing Postgres service, RLS, and migrations.
- Integrity label is `LOCAL_SHA256_UNSIGNED`. This is not Cosign / DSSE.
- No network collector, contact sender, or deployer.

Run from the repository root after this package is on `PYTHONPATH`:

```bash
python -m unittest -v tests.test_david_reference
```

Do not expose `Ledger` trusted-input methods as public APIs. Source policy and clearance facts must come from protected services.

This branch does **not** claim HF deployment, signed receipts, or live IRS/NYC collection.
