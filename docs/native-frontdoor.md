# Native presentation for both David Leads fronts

## Actual source and delivery

This change starts from accepted source `0cd3cf2f7edb7cbbbd7a9b72c30e41bab69d2197` and updates two frontends that the current application actually serves.

| Runtime route | Source | Delivery |
| --- | --- | --- |
| `/` | `app/static/index.html`, `holo.css`, `app.js`; existing local fonts and unchanged `operator.js` | The root Dockerfile copies `app/`; `app/server.py` mounts this static root after its API routes. |
| `/v0/` | `backend/static/index.html`, `style.css`, `app.js` | The same Dockerfile copies `backend/`; the parent mounts `backend.main` at `/v0`. Relative `static/` and `v1/` URLs continue to resolve inside that mount. |

`app/static/holo.js` remains the inert compatibility stub. It is not loaded by the public entrypoint and is not restored as a second frontend.

The existing `.github/workflows/hf-deploy.yml` remains the writer. It selects one current protected-main source, retains the dataset-admission and schema-migration gates, and invokes `szl-holdings/.github/.github/workflows/reusable-hf-deploy.yml` at `47607d3149dd54c4e107d7eeb2129ebdff5d2d03`. That reusable derives its payload from the Docker `COPY` sources. This change is included by the existing `app/**` push trigger and both existing copied trees. It does not change writer credentials, target, migration sequencing, dataset snapshots, release attestation, readiness, or live admission requirements.

## Presentation

Both fronts use the approved native Orbit artwork at **40px** inside a 44px link. Its SVG geometry, title, description, and bytes are unchanged from `szl-brand` source `27d12e77fc0f9f1a0e5fae8b34adf2380d51d070`, `kit/logos/orbit-v2/suite/szl-icon-32.svg`. The file SHA-256 is `6e2b7d72a3af3d9602b79de41df0194ede6496a9661f057108ec224c0efc92e6`. Each page links the artwork's exact-source CC BY 4.0 license. The inline SVG avoids introducing another runtime asset dependency or publisher path.

The application receives a **local graphite/teal palette projection**, opaque reading panels, silver borders, more legible muted text and footer copy, and a quiet hero atmosphere. This is not an installation of the full KANCHAY bundle. David's own product glyph, blue/gold evidence semantics, information architecture and local Space Grotesk / JetBrains Mono fonts remain intact. The legacy generated Public Experience v3.1 CSS block is byte-identical.

The synthetic demonstration receives a clear identity and hierarchy, source and API navigation, a keyboard-scrollable source table, intact truth-state and synthetic-data labels, larger controls, and responsive cards. Its API reference remains under the existing mounted route. “Verify receipt integrity” describes the existing server verification action accurately; the former label said “offline” despite performing a request.

## Interaction and state repairs

The public skip link now reaches a focusable main landmark. The policy dialog has its own accessible name, and the operator tab panel has a keyboard focus target. The `/` shortcut selects the lead explorer before focusing its search field and respects an open dialog. Public and operator controllers retain their API, authentication, contact, source-admission and evidence contracts; `operator.js` is unchanged.

In the synthetic view, provider values render through text nodes rather than HTML interpolation. An empty or malformed source catalog stays explicit. Starting another score clears the prior receipt and verification display immediately; a failed or malformed reply cannot leave the old receipt available. Request identities keep a late score or verification from overwriting a newer selection. Requests have a bounded 20-second wait, with no automatic retry and no assertion that a timeout cancelled a server action. The score and verification POST paths, headers and JSON payloads retain their existing protocol. Scoring, receipt generation, signature and verification implementations are unchanged.

## Qualification

All observations below are **local source/presentation evidence**, not live application, dataset, model-quality, signature or release proof.

- **137 Chromium checks pass** over all four main workspace panels and the synthetic front, widths 320/390/768/1280/1920, 200/400% reflow, forced colors, keyboard targets, named policy dialog and focus return, tab arrows, search shortcut, opaque surfaces, text/action contrast, table scrolling, absence states and exact Orbit bytes. Representative renders were visually inspected. The preview uses the actual source assets under the application's strict content-security policy.
- The browser server returns only labeled **local unavailable / synthetic fixtures**. Every non-GET and every external request is denied. No backend is imported or started, no operator form is submitted, and no scoring or verification action is called by the browser.
- **38 Node tests pass**: all 30 existing source/data/operator tests plus eight focused synthetic-view regressions. The new tests use local DOM/transport doubles for literal hostile text, malformed/empty catalogs, unchanged request shapes, stale receipt removal, late replies, null scores and bounded timeout. Their POSTs never leave the in-memory fixture.
- **64 Python source, presentation and release-contract tests pass**, with unmocked socket/URL transport denied before imports and zero attempts. These are the three existing modules listed below, not a substitute for the full hosted PostgreSQL/application gates.
- All **224 other tracked files** remain byte-identical to the accepted base, including both backends, schemas, policy, source admission, publisher workflows, attestations, signing code, fonts, retired compatibility stub and root README. Exactly seven tracked source/test paths change, plus this document and the two new local qualification tools.
- The new browser helper passes Ruff; both controllers pass Node syntax checks; `git diff --check` passes.

Reproduce the local source tests:

```sh
python -m pytest -q tests/test_kanchay_visual_honesty.py tests/test_hf_deploy_release_sequencing.py tests/test_release_contract.py
node --test tests/*.test.mjs
```

Reproduce presentation checks with Playwright and a local Chromium installation:

```sh
CHROME_PATH=/absolute/path/to/chromium python tools/verify_native_frontdoor.py --output /absolute/path/to/new-proof-directory
```

The helper writes its source asset hashes, every check result, and representative screenshots. It records a failed browser qualification as a failure in its report. The normal protected-branch CI, actual existing publisher, immutable Hub files, runtime source binding, dataset admission and release receipt must still qualify the eventual accepted source before a live delivery claim.
