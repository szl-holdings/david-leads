# Third-party notices

David Leads is licensed under Apache-2.0. The repository also vendors or depends on the following
third-party software and assets. This inventory is a notice record, not a substitute for reviewing
the complete licence text and transitive dependency graph when producing a release SBOM.

## Vendored browser assets

- **Three.js r128** — Copyright 2010-2021 Three.js Authors — MIT License.
  The same-origin minimized file is `app/static/vendor/three.min.js`; its embedded `@license`
  header is retained. Source: <https://github.com/mrdoob/three.js/tree/r128>.
- **Inter font** — Copyright The Inter Project Authors — SIL Open Font License 1.1.
  Source: <https://github.com/rsms/inter>.
- **Fraunces font** — Copyright The Fraunces Project Authors — SIL Open Font License 1.1.
  Source: <https://github.com/undercasetype/Fraunces>.

The fonts and Three.js are self-hosted; the application has no runtime CDN dependency.

## Direct Python dependencies

The pinned direct dependencies are declared in `requirements.txt` and `requirements-dev.txt`.
Their upstream licences include:

- FastAPI — MIT
- Uvicorn — BSD-3-Clause
- cryptography — Apache-2.0 OR BSD-3-Clause
- Pydantic — MIT
- Psycopg 3 — LGPL-3.0-only
- HTTPX (development/test) — BSD-3-Clause
- pytest (development/test) — MIT

Release automation should generate an SPDX or CycloneDX SBOM from the exact resolved environment
and fail closed on an unknown or disallowed licence. A library licence does not license the data
processed through that library.

## Competitive research boundary

`research/COMPETITIVE_SYNTHESIS_2026-08-26.md` describes publicly observable product patterns.
No competitor source code, proprietary dataset, copy, screenshot, logo, or brand asset is included.
