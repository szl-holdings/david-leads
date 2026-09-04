# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "ops" / "frontier_live_canary.py"
SPEC = importlib.util.spec_from_file_location("frontier_live_canary", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
canary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(canary)


class FrontierLiveCanaryTests(unittest.TestCase):
    def _build(self, revision: str = "a" * 40) -> dict:
        return {
            "source_revision": revision,
            "receipt_minted": True,
            "release_receipt": {
                "state": "GITHUB_OIDC_ATTESTED",
                "source_revision": revision,
            },
        }

    def _board(self) -> dict:
        return {
            "sources": [
                {"source_id": source_id, "mode": "LIVE", "count": 1}
                for source_id in canary.REQUIRED_LANES
            ],
            "opportunities": [
                {
                    "name": "ACME SHOULD NEVER ENTER THE CANARY RECEIPT",
                    "source_record_id": "record-1",
                    "normalized_record_sha256": "b" * 64,
                    "parser_version": "frontier-sources/1.2",
                    "receipt_state": "HASH_CHAINED_UNSIGNED",
                }
            ],
        }

    def test_complete_proof_exports_only_aggregate_evidence(self) -> None:
        report = canary.evaluate(
            self._board(),
            self._build(),
            expected_revision="a" * 40,
        )
        self.assertTrue(report["complete"])
        self.assertFalse(report["sample_substitution"])
        self.assertFalse(report["records_exported"])
        serialized = json.dumps(report)
        self.assertNotIn("ACME", serialized)
        self.assertNotIn("record-1", serialized)
        self.assertEqual(
            report["record_contract"]["records_observed"],
            1,
        )

    def test_missing_or_empty_lane_fails_closed(self) -> None:
        board = self._board()
        board["sources"] = board["sources"][:-1]
        report = canary.evaluate(board, self._build())
        self.assertFalse(report["complete"])
        missing = report["required_lanes"][-1]
        self.assertEqual(missing["mode"], "UNAVAILABLE")
        self.assertEqual(missing["reason"], "SOURCE_NOT_RETURNED")

    def test_non_live_or_zero_count_never_passes(self) -> None:
        board = self._board()
        board["sources"][0]["mode"] = "UNAVAILABLE"
        board["sources"][1]["count"] = 0
        report = canary.evaluate(board, self._build())
        self.assertFalse(report["complete"])
        self.assertFalse(report["required_lanes"][0]["operational"])
        self.assertFalse(report["required_lanes"][1]["operational"])

    def test_record_hash_receipt_and_parser_are_mandatory(self) -> None:
        board = self._board()
        board["opportunities"][0].update(
            normalized_record_sha256="not-a-hash",
            parser_version="",
            receipt_state="UNAVAILABLE",
        )
        report = canary.evaluate(board, self._build())
        self.assertFalse(report["complete"])
        contract = report["record_contract"]
        self.assertEqual(contract["invalid_hash"], 1)
        self.assertEqual(contract["missing_parser_version"], 1)
        self.assertEqual(contract["invalid_receipt_state"], 1)

    def test_exact_expected_revision_is_enforced(self) -> None:
        report = canary.evaluate(
            self._board(),
            self._build("a" * 40),
            expected_revision="c" * 40,
        )
        self.assertFalse(report["complete"])
        self.assertFalse(report["deployment"]["source_bound"])


if __name__ == "__main__":
    unittest.main()
