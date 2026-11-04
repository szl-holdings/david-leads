# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

MODULE_PATH = Path(__file__).parents[1] / "ops" / "frontier_live_canary.py"
SPEC = importlib.util.spec_from_file_location("frontier_live_canary", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
canary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(canary)


class FrontierLiveCanaryTests(unittest.TestCase):
    ROTATION_GENERATION = "sha256:" + "f" * 64

    def _build(self, revision: str = "a" * 40) -> dict:
        return {
            "source_revision": revision,
            "receipt_minted": True,
            "rotation_generation": self.ROTATION_GENERATION,
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
            "rotation_generation": self.ROTATION_GENERATION,
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

    def test_duplicate_required_lanes_never_choose_a_favorable_observation(self) -> None:
        for index, source_id in enumerate(canary.REQUIRED_LANES):
            for position in (0, len(canary.REQUIRED_LANES)):
                with self.subTest(source_id=source_id, position=position):
                    board = self._board()
                    conflicting = dict(board["sources"][index])
                    conflicting.update(mode="UNAVAILABLE", count=0,
                                       reason="private diagnostic must not enter the artifact")
                    board["sources"].insert(position, conflicting)
                    report = canary.evaluate(board, self._build())
                    self.assertFalse(report["complete"])
                    lane = report["required_lanes"][index]
                    self.assertFalse(lane["operational"])
                    self.assertEqual(lane["reason"], "SOURCE_ID_DUPLICATED")
                    self.assertEqual(lane["count"], -1)
                    self.assertFalse(lane["snapshot"]["complete"])
                    self.assertNotIn("private diagnostic", json.dumps(report))

    def test_identical_duplicate_lane_is_still_ambiguous(self) -> None:
        for index, source_id in enumerate(canary.REQUIRED_LANES):
            with self.subTest(source_id=source_id):
                board = self._board()
                board["sources"].append(dict(board["sources"][index]))
                report = canary.evaluate(board, self._build())
                self.assertFalse(report["complete"])
                self.assertEqual(report["required_lanes"][index]["reason"],
                                 "SOURCE_ID_DUPLICATED")

    def test_unrelated_source_rows_do_not_replace_required_lanes(self) -> None:
        board = self._board()
        board["sources"].extend([
            {"source_id": "optional-source", "mode": "UNAVAILABLE"},
            {"source_id": "optional-source", "mode": "LIVE", "count": 1},
        ])
        self.assertTrue(canary.evaluate(board, self._build())["complete"])

    def test_non_live_or_zero_count_never_passes(self) -> None:
        board = self._board()
        board["sources"][0]["mode"] = "UNAVAILABLE"
        board["sources"][1]["count"] = 0
        report = canary.evaluate(board, self._build())
        self.assertFalse(report["complete"])
        self.assertFalse(report["required_lanes"][0]["operational"])
        self.assertFalse(report["required_lanes"][1]["operational"])

    def test_non_integer_lane_counts_never_pass_or_raise(self) -> None:
        for index in range(len(canary.REQUIRED_LANES)):
            for count in (True, False, "1", 1.0, 1.9, None, [], {}, float("inf"), float("nan")):
                with self.subTest(index=index, count=count):
                    board = self._board()
                    board["sources"][index]["count"] = count
                    report = canary.evaluate(board, self._build())
                    self.assertFalse(report["complete"])
                    lane = report["required_lanes"][index]
                    self.assertFalse(lane["operational"])
                    self.assertEqual(lane["count"], -1)

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

    def test_expected_rotation_generation_binds_board_and_build_processes(self) -> None:
        report = canary.evaluate(
            self._board(),
            self._build(),
            expected_revision="a" * 40,
            expected_rotation_generation=self.ROTATION_GENERATION,
        )
        self.assertTrue(report["complete"])
        self.assertTrue(report["deployment"]["rotation_generation_bound"])

        board = self._board()
        board["rotation_generation"] = "sha256:" + "e" * 64
        report = canary.evaluate(
            board,
            self._build(),
            expected_revision="a" * 40,
            expected_rotation_generation=self.ROTATION_GENERATION,
        )
        self.assertFalse(report["complete"])
        self.assertFalse(report["deployment"]["rotation_generation_bound"])

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

    def test_remote_lane_diagnostics_export_only_known_codes(self) -> None:
        sentinel = "PRIVATE ORGANIZATION SENTINEL"
        for reason, expected in (
            (sentinel, "SOURCE_DIAGNOSTIC_REDACTED"),
            ({"organization": sentinel}, "SOURCE_DIAGNOSTIC_REDACTED"),
            ("FORM5500_VERIFIED_SNAPSHOT_UNAVAILABLE: " + sentinel,
             "FORM5500_VERIFIED_SNAPSHOT_UNAVAILABLE"),
            ("NO_MATCHING_RECORDS_IN_VERIFIED_SNAPSHOT",
             "NO_MATCHING_RECORDS_IN_VERIFIED_SNAPSHOT"),
        ):
            with self.subTest(reason=reason):
                board = self._board()
                board["sources"][0]["reason"] = reason
                report = canary.evaluate(board, self._build())
                self.assertEqual(report["required_lanes"][0]["reason"], expected)
                self.assertNotIn(sentinel, json.dumps(report))

    def test_unknown_remote_modes_are_redacted_and_never_qualify(self) -> None:
        sentinel = "PRIVATE ORGANIZATION SENTINEL"
        board = self._board()
        board["sources"][0]["mode"] = sentinel
        report = canary.evaluate(board, self._build())
        self.assertFalse(report["complete"])
        self.assertEqual(report["required_lanes"][0]["mode"], "UNAVAILABLE")
        self.assertNotIn(sentinel, json.dumps(report))

    def test_parser_versions_must_be_bounded_local_identifiers(self) -> None:
        sentinel = "PRIVATE ORGANIZATION SENTINEL"
        for parser in (sentinel, "other-parser/1.2", "frontier-sources/1.2\n" + sentinel,
                       "frontier-sources/12345.2", {"private": sentinel}):
            with self.subTest(parser=parser):
                board = self._board()
                board["opportunities"][0]["parser_version"] = parser
                report = canary.evaluate(board, self._build())
                self.assertFalse(report["complete"])
                self.assertEqual(report["record_contract"]["invalid_parser_version"], 1)
                self.assertEqual(report["record_contract"]["parser_versions"], [])
                self.assertNotIn(sentinel, json.dumps(report))
        for parser in ("frontier-sources/1.2", "frontier-sources/1.2.3"):
            board = self._board()
            board["opportunities"][0]["parser_version"] = parser
            report = canary.evaluate(board, self._build())
            self.assertTrue(report["complete"])
            self.assertEqual(report["record_contract"]["parser_versions"], [parser])

    def test_malformed_revision_metadata_is_not_copied_into_artifacts(self) -> None:
        sentinel = "PRIVATE ORGANIZATION SENTINEL"
        cases = (
            (self._build(sentinel), {}),
            (self._build(), {"expected_revision": sentinel}),
            (self._build(), {"expected_rotation_generation": sentinel}),
        )
        for build, kwargs in cases:
            with self.subTest(kwargs=kwargs, source=build["source_revision"]):
                report = canary.evaluate(self._board(), build, **kwargs)
                self.assertFalse(report["complete"])
                self.assertNotIn(sentinel.lower(), json.dumps(report).lower())

    def test_success_response_metadata_stays_redacted_in_stdout_and_file(self) -> None:
        sentinel = "PRIVATE ORGANIZATION SENTINEL"
        board = self._board()
        board["sources"][0]["reason"] = "FORM5500_VERIFIED_SNAPSHOT_UNAVAILABLE: " + sentinel
        board["opportunities"][0]["parser_version"] = sentinel
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "canary.json"
            with patch.object(canary, "_get_json", side_effect=[board, self._build()]):
                with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                    self.assertEqual(canary.main(["--output", str(output)]), 1)
            contents = output.read_text(encoding="utf-8")
            self.assertNotIn(sentinel, contents)
            self.assertEqual(stdout.getvalue(), contents)

    def test_release_attestation_and_source_record_checks_still_apply(self) -> None:
        board = self._board()
        build = self._build()
        build["receipt_minted"] = False
        self.assertFalse(canary.evaluate(board, build)["complete"])
        board["opportunities"][0]["_sample"] = True
        self.assertFalse(canary.evaluate(board, self._build())["complete"])

    def _failure_artifact(self, error: Exception, *, transport: bool = False) -> tuple[dict, str]:
        target = canary.urllib.request if transport else canary
        method = "urlopen" if transport else "run"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "canary.json"
            with patch.object(target, method, side_effect=error), patch("sys.stdout", new_callable=io.StringIO) as stdout:
                self.assertEqual(canary.main(["--output", str(output)]), 1)
                report = json.loads(output.read_text(encoding="utf-8"))
                printed = stdout.getvalue()
            self.assertEqual(json.loads(printed), report)
            self.assertFalse(report["complete"])
            self.assertFalse(report["records_exported"])
            return report, printed

    def test_http_failure_retains_status_without_response_body_or_url(self) -> None:
        sentinel = "PRIVATE-ORGANIZATION-RESPONSE-SENTINEL"
        error = HTTPError("https://example.invalid/" + sentinel, 403, sentinel, {},
                          io.BytesIO(sentinel.encode()))
        report, printed = self._failure_artifact(error, transport=True)
        self.assertNotIn(sentinel, printed)
        self.assertEqual(report["failure"], "HTTP_ERROR")
        self.assertEqual(report["http_status"], 403)

    def test_unexpected_failure_does_not_export_exception_message(self) -> None:
        sentinel = "PRIVATE-ORGANIZATION-EXCEPTION-SENTINEL"
        report, printed = self._failure_artifact(RuntimeError(sentinel))
        self.assertNotIn(sentinel, printed)
        self.assertEqual(report["failure"], "PROBE_ERROR")

    def test_http_failure_never_reads_response_body(self) -> None:
        body = io.BytesIO(b"PRIVATE-RESPONSE-SENTINEL")
        error = HTTPError("https://example.invalid/", 502, "Bad Gateway", {}, body)
        with patch.object(body, "read", side_effect=AssertionError("body must remain unread")) as read:
            report, _ = self._failure_artifact(error, transport=True)
        read.assert_not_called()
        self.assertTrue(body.closed)
        self.assertEqual(report["http_status"], 502)

    def test_invalid_json_diagnostic_does_not_export_document(self) -> None:
        sentinel = "PRIVATE-ORGANIZATION-DOCUMENT-SENTINEL"
        report, printed = self._failure_artifact(json.JSONDecodeError(sentinel, sentinel, 0))
        self.assertNotIn(sentinel, printed)
        self.assertEqual(report["failure"], "PROBE_ERROR")


if __name__ == "__main__":
    unittest.main()
