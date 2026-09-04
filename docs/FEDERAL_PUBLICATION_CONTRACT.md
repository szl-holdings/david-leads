# Federal Refresh publication contract

The publisher verifies frozen input bytes and uses one optimistic-concurrency Hub commit for the snapshot, receipt, records, and latest pointer. A failed commit cannot expose a partially uploaded snapshot as latest. Only a remote path-not-found 404 permits a new path; repository, authentication, transport, rate-limit, and server errors fail closed. Concurrent-head 409 responses receive at most four total attempts, each with a new immutable read revision and newly constructed commit operations.

Snapshots are stored at `snapshots/<source.name>/<YYYY-MM-DD>/<snapshot_id>/`. Each lane owns `latest/<source.name>.json`. The original `latest.json` is retained as an ECHO-only compatibility pointer; MOTUS, DOL and USAspending never overwrite it. Existing dated snapshot folders are retained unchanged. The three payload digests are included in each pointer.

The publisher also checks receipt-to-snapshot identity, records hash, lane, issued-at, record count, future timestamps, safe path components and a 1 GiB total input limit. The existing verifier is reused unchanged. Hash verification is not cryptographic signer verification; an `UNSIGNED` receipt stays unsigned.

`VERIFIED_NOT_PUBLISHED` means credentials were absent after local verification; it never means Hub publication succeeded. Provider exceptions are reduced to error types rather than logged with potentially sensitive request details. No repository or Space is created, renamed, deleted, or made public.

This repair completes publication mechanics, not the whole federal-data product. Provider URLs still require independent live validation, authenticated dataset-write authority is still required, and the app's non-ECHO lane consumers still need explicit integration. No bulk dataset has been downloaded or published merely by merging this change.
