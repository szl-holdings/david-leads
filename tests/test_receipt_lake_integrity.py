"""Offline integrity checks for the process-local append-only receipt lake."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import receipt_lake as lake


def synthetic_receipt(identifier: str = "synthetic-1") -> dict:
    return {
        "id": identifier,
        "organ": "synthetic-organ",
        "decision": "synthetic-decision",
        "payload": {"observations": [{"state": "original"}]},
    }


class ReceiptLakeIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"SZL_RECEIPT_LAKE_PATH": ""})
        self.environment.start()
        lake.reset()

    def tearDown(self):
        lake.reset()
        self.environment.stop()

    def assert_stored_snapshot(self, expected):
        self.assertEqual(lake.all(), [expected])
        self.assertEqual(lake.query(organ="synthetic-organ"), [expected])
        self.assertEqual(lake.size(), 1)

    def test_mutating_the_appended_input_cannot_rewrite_history(self):
        receipt = synthetic_receipt()
        expected = copy.deepcopy(receipt)
        lake.append(receipt)
        receipt["organ"] = "rewritten"
        receipt["payload"]["observations"][0]["state"] = "rewritten"
        self.assert_stored_snapshot(expected)

    def test_mutating_the_append_result_cannot_rewrite_history(self):
        receipt = synthetic_receipt()
        expected = copy.deepcopy(receipt)
        result = lake.append(receipt)
        self.assertEqual(result, receipt)
        result["payload"]["observations"].clear()
        result["decision"] = "rewritten"
        self.assert_stored_snapshot(expected)

    def test_mutating_all_results_cannot_rewrite_history(self):
        receipt = synthetic_receipt()
        expected = copy.deepcopy(receipt)
        lake.append(receipt)
        result = lake.all()
        result[0]["payload"]["observations"][0]["state"] = "rewritten"
        result.clear()
        self.assert_stored_snapshot(expected)

    def test_mutating_filtered_query_results_cannot_rewrite_history(self):
        receipt = synthetic_receipt()
        expected = copy.deepcopy(receipt)
        lake.append(receipt)
        result = lake.query(organ="synthetic-organ", decision="synthetic-decision", limit=1)
        result[0]["payload"]["observations"].append({"state": "invented"})
        result[0]["organ"] = "rewritten"
        self.assert_stored_snapshot(expected)

    def test_memory_and_file_keep_the_same_appended_snapshot(self):
        receipt = synthetic_receipt()
        expected = copy.deepcopy(receipt)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.jsonl"
            with patch.dict(os.environ, {"SZL_RECEIPT_LAKE_PATH": str(path)}):
                result = lake.append(receipt)
            receipt["payload"]["observations"].clear()
            result["payload"]["observations"] = []
            self.assertEqual(json.loads(path.read_text()), expected)
            self.assert_stored_snapshot(expected)

    def test_zero_limit_returns_no_rows_and_positive_limits_keep_order(self):
        receipts = [synthetic_receipt(f"synthetic-{index}") for index in range(3)]
        for receipt in receipts:
            lake.append(receipt)
        self.assertEqual(lake.query(limit=0), [])
        self.assertEqual(lake.query(organ="synthetic-organ", limit=0), [])
        self.assertEqual(lake.query(limit=1), receipts[-1:])
        self.assertEqual(lake.query(limit=2), receipts[-2:])
        self.assertEqual(lake.query(limit=None), receipts)
        self.assertEqual(lake.query(limit=-1), receipts)
        self.assertEqual(lake.query(organ="unmatched", limit=0), [])


if __name__ == "__main__":
    unittest.main()
