# Leader-Study Upgrade Plan - W27 loop-5 - 2026-11-23

Status: PROPOSE-ONLY DRAFT - DO NOT MERGE. Owner-gated: merging requires governing approval and the estate signature-wall owner unlock.

Repo: david-leads - David Leads — official-source broker research with evidence receipts. Public Space: SZLHOLDINGS/david-leads.

Frame: OUROBOROS loop-5 leader study. Governing seat: Kimi kimi-k3.1-pro (json_ok, think off). Advisory seats: Astra/Sol/Claude community rails (provenance unverified, advisory only). Leader evidence web-verified 2026-11-23.

## Leader moats to absorb
- in-toto / DSSE: Supply-chain attestation framework: DSSE v1.0 envelopes wrapping in-toto Statements with predicateType, plus layouts that prove fixed step sequences executed by the right actors. Moat: Cryptographic, actor-bound proof of process — not just logs. A verifier can check that each step ran, in order, by the authorized functionary, with signed predicate metadata.
- SpiderFoot / Maltego: OSINT automation and link-analysis platforms for entity resolution across public sources. Moat: Breadth of source integrations plus graph-based entity correlation; transforms raw public records into navigable relationship evidence.
- Recorded Future / Sayari: Commercial intelligence platforms fusing public and licensed records into risk and ownership intelligence. Moat: Licensed-source access, continuous collection, and hardened entity-resolution pipelines that turn registries into decision-grade risk graphs.

## Honest gaps (grounded in repo facts)
- Evidence receipts are described but their format is unspecified in the facts: there is no stated DSSE envelope, predicateType, signature scheme, or verification command, so 'evidence after' is not yet independently verifiable by a third party.
- Fail-closed behavior is asserted for the federal lanes but the only stated external check is the canary workflow; there is no described signed attestation that a given deployed revision actually served UNAVAILABLE rather than stale or synthetic data.
- The private dataset gate (DAVID_DATASET_READ_TOKEN, anonymous 401) protects access but says nothing about snapshot provenance: no described signing, hashing, or admission receipt for the scheduled snapshots themselves, so 'verified scheduled snapshots' is an unverified claim from the facts alone.
- Priority scores are explicitly advisory work-order signals, but no calibration, scoring-rubric versioning, or rationale payload is described, so two revisions cannot be compared for scoring drift.
- Entity resolution across the four federal lanes is not described; without it, broker research risks per-lane silos rather than a unified evidence graph.
- The local run path is offline with synthetic demo records, which is honest, but no described conformance test ties synthetic-mode behavior to live-lane behavior, so the demo cannot prove the live path correct.
- Build provenance is limited to a /api/build-info revision string; no described SLSA/in-toto provenance links that revision to the exact source commit and dataset snapshot digests.

## Dosed upgrade plan
- Dose 1 (receipt format, propose-only): define a versioned evidence-receipt schema as a DSSE v1.0 envelope wrapping an in-toto Statement with a custom predicateType (e.g. https://a11oy.net/predicates/lane-snapshot/v1) carrying lane name, source URL, snapshot digest, retrieval timestamp, admission decision, and deployed revision; keep it offline and synthetic-first.
- Dose 2 (snapshot admission receipts): at each scheduled snapshot, emit a signed admission receipt per federal lane recording digest and schema-validation result; store receipts alongside the private dataset so the reader can present proof, not just rows.
- Dose 3 (layout for the lane pipeline): publish an in-toto layout fixing the step sequence fetch -> validate -> admit -> score with named functionaries (snapshot workflow, admission service, scorer), and expose a verify command in the repo.
- Dose 4 (canary emits attestations): extend frontier-live-canary.yml to sign a per-lane liveness/fail-closed attestation bound to the /api/build-info revision, and surface the latest attestation digest on a read-only endpoint.
- Dose 5 (scoring rubric versioning): version the advisory scoring rubric, embed rubric version and per-factor rationale in each work-order receipt, and add a regression fixture so scoring drift between revisions is diffable.
- Dose 6 (entity resolution, offline first): introduce canonical entity keys with deterministic matching rules over synthetic fixtures, then gate live activation behind measured precision on labeled samples; keep merges advisory and reversible.
- Dose 7 (build provenance): emit SLSA-style provenance linking container image, source commit, and dataset snapshot digests, and have /api/build-info return the provenance digest alongside the revision.
- Risk note: Signing and attestation add key-management burden and new failure modes: a misconfigured signer could either block all federal lanes (availability risk, mitigated by fail-closed behavior already being the default) or, worse, attest stale snapshots as fresh (integrity risk). Entity resolution carries false-merge risk that could misattribute broker evidence, so it must stay deterministic, labeled, and reversible. Provenance and receipt endpoints must not leak the private dataset contents or the read token; receipts should expose digests and decisions only. Scope risk is real — sequencing the doses as above avoids big-bang changes to a system whose core safety property is refusing to answer without verified sources.
- Propose-only note: All steps are proposals for human review; no repo files, workflows, credentials, or live lanes were modified. Each dose is independently revertible, starts offline against synthetic fixtures, and preserves the documented fail-closed contract: any lane lacking a valid signed admission receipt must report UNAVAILABLE rather than substitute samples.

## Advisory notes (unverified rails, non-binding)
- astra: YARQA-ATTN: Hardware-specific compiler optimizations for proprietary AI accelerators. curation-atlas: Real-time integration with private enterprise security telemetry. david-leads: Proprietary cross-referenced datasets of non-public government procurement.
- sol: YARQA-ATTN: Hardware-specific Triton/CUDA optimization primitives curation-atlas: Real-time GitHub event stream ingestion pipeline david-leads: Proprietary DSSE-evidence signal mapping schema
- claude: YARQA-ATTN: Hardware-specific compiler optimizations for proprietary AI accelerators. curation-atlas: Direct API integration with private enterprise security telemetry streams. david-leads: Exclusive access to non-public government procurement and intelligence feeds.

## DO NOT MERGE
This plan is a proposal artifact of the 10-pass OUROBOROS loop (loop-5 of 10). No code, no CI, no behavior changes in this file. A reviewer with authority may convert to a work order later.