# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
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
        now = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=1)
        created = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        source_date = now.date().isoformat()
        sources = []
        for source_id in canary.REQUIRED_LANES:
            source = {"source_id": source_id, "mode": "LIVE", "count": 1}
            if source_id == canary.ECHO_SOURCE_ID:
                source.update({
                    "delivery": "VERIFIED_BULK_SNAPSHOT",
                    "dataset": {"immutable_path": f"snapshots/{source_date}/{'d' * 64}"},
                    "snapshot": {
                        "snapshot_id": f"sha256:{'d' * 64}",
                        "snapshot_digest": "d" * 64,
                        "created_at": created,
                        "record_count": 100,
                        "source": {"name": "echo-exporter", "source_as_of": source_date},
                    },
                    "snapshot_receipt": {"state": "PAYLOAD_VERIFIED_UNSIGNED"},
                })
            else:
                lane, source_path = canary.SCHEDULED_LANES[source_id]
                source.update({
                    "delivery": "VERIFIED_SCHEDULED_SNAPSHOT",
                    "source_path": list(source_path),
                    "snapshot": {
                        "id": f"sha256:{'e' * 64}",
                        "as_of": created,
                        "path": f"snapshots/{lane}/{source_date}/{'e' * 64}",
                        "receipt_state": "PAYLOAD_VERIFIED_UNSIGNED",
                        "record_count": 100,
                    },
                })
            sources.append(source)
        return {
            "sources": sources,
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
        self.assertEqual(report["snapshot_contract"]["verified_lanes"], 4)
        self.assertTrue(report["snapshot_contract"]["complete"])
        for lane in report["required_lanes"]:
            self.assertTrue(lane["snapshot"]["complete"])
            self.assertEqual(lane["snapshot"]["receipt_state"], "PAYLOAD_VERIFIED_UNSIGNED")
            self.assertFalse(lane["snapshot"]["signature_verified"])

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

    def test_missing_snapshot_or_delivery_never_passes_live_counts(self) -> None:
        for index in range(4):
            for field in ("snapshot", "delivery"):
                with self.subTest(index=index, field=field):
                    board = self._board()
                    del board["sources"][index][field]
                    report = canary.evaluate(board, self._build())
                    self.assertFalse(report["complete"])
                    self.assertFalse(report["required_lanes"][index]["operational"])

    def test_tampered_snapshot_metadata_fails_closed(self) -> None:
        for index in range(4):
            echo = index == 3
            mutations = (
                ("snapshot_id" if echo else "id", f"sha256:{'x' * 64}"),
                ("record_count", 0),
                ("record_count", True),
                ("created_at" if echo else "as_of", "2026-02-30T00:00:00Z"),
            )
            for field, value in mutations:
                with self.subTest(index=index, field=field, value=value):
                    board = self._board()
                    board["sources"][index]["snapshot"][field] = value
                    self.assertFalse(canary.evaluate(board, self._build())["complete"])

    def test_receipt_state_must_be_explicitly_payload_verified_unsigned(self) -> None:
        for index in range(4):
            for state in (None, "SIGNED", "UNSIGNED", "GITHUB_OIDC_ATTESTED"):
                with self.subTest(index=index, state=state):
                    board = self._board()
                    source = board["sources"][index]
                    if index == 3:
                        source["snapshot_receipt"]["state"] = state
                    else:
                        source["snapshot"]["receipt_state"] = state
                    report = canary.evaluate(board, self._build())
                    self.assertFalse(report["complete"])
                    self.assertIn("SNAPSHOT_RECEIPT_STATE_INVALID", report["required_lanes"][index]["snapshot"]["errors"])

    def test_content_addressed_path_binds_lane_date_and_digest(self) -> None:
        for index in range(4):
            for path in ("latest.json", "snapshots/../records.jsonl", f"snapshots/1900-01-01/{'f' * 64}"):
                with self.subTest(index=index, path=path):
                    board = self._board()
                    source = board["sources"][index]
                    if index == 3:
                        source["dataset"]["immutable_path"] = path
                    else:
                        source["snapshot"]["path"] = path
                    report = canary.evaluate(board, self._build())
                    self.assertFalse(report["complete"])
                    self.assertIn("SNAPSHOT_PATH_MISMATCH", report["required_lanes"][index]["snapshot"]["errors"])

    def test_echo_digest_must_match_identity(self) -> None:
        board = self._board()
        board["sources"][3]["snapshot"]["snapshot_digest"] = "f" * 64
        report = canary.evaluate(board, self._build())
        self.assertFalse(report["complete"])
        self.assertIn("SNAPSHOT_ID_INVALID", report["required_lanes"][3]["snapshot"]["errors"])

    def test_scheduled_lineage_is_bound_to_the_lane(self) -> None:
        for index in range(3):
            board = self._board()
            board["sources"][index]["source_path"] = ["unexpected-source"]
            report = canary.evaluate(board, self._build())
            self.assertFalse(report["complete"])
            self.assertIn("SNAPSHOT_SOURCE_PATH_MISMATCH", report["required_lanes"][index]["snapshot"]["errors"])

    def test_stale_or_future_source_dates_fail_for_every_lane(self) -> None:
        for index in range(4):
            for days, error in ((-9, "SNAPSHOT_STALE"), (2, "SNAPSHOT_AS_OF_FUTURE")):
                with self.subTest(index=index, days=days):
                    board = self._board()
                    changed = datetime.now(timezone.utc) + timedelta(days=days)
                    source = board["sources"][index]
                    if index == 3:
                        source["snapshot"]["source"]["source_as_of"] = changed.date().isoformat()
                    else:
                        source["snapshot"]["as_of"] = changed.strftime("%Y-%m-%dT%H:%M:%SZ")
                        lane = canary.SCHEDULED_LANES[source["source_id"]][0]
                        source["snapshot"]["path"] = f"snapshots/{lane}/{changed.date().isoformat()}/{'e' * 64}"
                    report = canary.evaluate(board, self._build())
                    self.assertFalse(report["complete"])
                    self.assertIn(error, report["required_lanes"][index]["snapshot"]["errors"])

    def test_fresh_republication_cannot_rejuvenate_stale_echo_export(self) -> None:
        board = self._board()
        source = board["sources"][3]
        old = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
        source["snapshot"]["source"]["source_as_of"] = old
        report = canary.evaluate(board, self._build())
        snapshot = report["required_lanes"][3]["snapshot"]
        self.assertFalse(report["complete"])
        self.assertEqual(snapshot["source_as_of"], old)
        self.assertEqual(snapshot["freshness_basis"], "SOURCE_EXPORT_DATE")
        self.assertIn("SNAPSHOT_STALE", snapshot["errors"])
        self.assertNotIn("SNAPSHOT_CREATED_AT_INVALID", snapshot["errors"])

    def test_echo_source_date_cannot_follow_creation(self) -> None:
        board = self._board()
        source = board["sources"][3]
        created = datetime.now(timezone.utc) - timedelta(days=2)
        source["snapshot"]["created_at"] = created.strftime("%Y-%m-%dT%H:%M:%SZ")
        source["dataset"]["immutable_path"] = f"snapshots/{created.date().isoformat()}/{'d' * 64}"
        report = canary.evaluate(board, self._build())
        self.assertFalse(report["complete"])
        self.assertIn("SNAPSHOT_AS_OF_AFTER_CREATION", report["required_lanes"][3]["snapshot"]["errors"])

    def test_future_echo_creation_is_rejected_even_with_fresh_source(self) -> None:
        board = self._board()
        source = board["sources"][3]
        created = datetime.now(timezone.utc) + timedelta(days=1)
        source["snapshot"]["created_at"] = created.strftime("%Y-%m-%dT%H:%M:%SZ")
        source["dataset"]["immutable_path"] = f"snapshots/{created.date().isoformat()}/{'d' * 64}"
        report = canary.evaluate(board, self._build())
        self.assertFalse(report["complete"])
        self.assertIn("SNAPSHOT_CREATED_AT_FUTURE", report["required_lanes"][3]["snapshot"]["errors"])

    def test_untrusted_snapshot_fields_never_export_organization_records(self) -> None:
        board = self._board()
        for source in board["sources"]:
            source["snapshot"]["raw"] = {"name": "PRIVATE ORGANIZATION SENTINEL"}
        report = canary.evaluate(board, self._build())
        self.assertTrue(report["complete"])
        self.assertNotIn("PRIVATE ORGANIZATION SENTINEL", json.dumps(report))

    def test_release_attestation_and_source_record_checks_still_apply(self) -> None:
        board = self._board()
        build = self._build()
        build["receipt_minted"] = False
        self.assertFalse(canary.evaluate(board, build)["complete"])
        board["opportunities"][0]["_sample"] = True
        self.assertFalse(canary.evaluate(board, self._build())["complete"])


if __name__ == "__main__":
    unittest.main()
