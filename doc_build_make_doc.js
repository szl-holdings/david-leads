#!/usr/bin/env node
"use strict";

/*
 * LEGACY / RETIRED / DO NOT USE FOR DEMOS, DATA, OR PRODUCT CLAIMS.
 *
 * This builder formerly produced David_Leads_Access_and_Tour.docx, an access
 * guide for a private-login, person-level prototype. That workflow is outside
 * the active organization-only, public-research-only, no-sample, fail-closed
 * contract. Git history preserves the old implementation.
 *
 * Current operating truth:
 *   - README.md describes the technical and evidence contract.
 *   - FOR_DAVID.md is the current operator walkthrough.
 *   - tools/build_david_broker_guide.py and tools/build_broker_guide.py build
 *     the supported organization-research guides.
 */

process.stderr.write(
  "RETIRED: doc_build_make_doc.js must not generate demo collateral. " +
  "Use README.md, FOR_DAVID.md, and the supported Python guide builders.\n",
);
process.exitCode = 2;
