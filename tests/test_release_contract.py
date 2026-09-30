"""Synthetic offline contract tests; not CI, runtime, migration, or signature proof."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ops.release_contract import (
    MAX_BYTES, ContractError, assess, canonical_digest, parse_json,
)

NOW = datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc)
SHA = "a" * 40
HF = "b" * 40
BUNDLE = "c" * 64


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = {
            "schema": "szl.release-policy/v2",
            "source_repository": "szl-holdings/david-leads",
            "source_revision": SHA,
            "hf_repository": "SZLHOLDINGS/david-leads",
            "bundle_sha256": BUNDLE,
            "gates": {
                "unit": {"environment": "CI_ISOLATED", "max_age_seconds": 3600},
                "postgres": {"environment": "POSTGRES_RUNTIME_ROLE", "max_age_seconds": 3600},
                "live": {"environment": "LIVE_PUBLIC", "max_age_seconds": 3600},
            },
        }
        self.report = {
            "schema": "szl.release-report/v2",
            "policy_digest": canonical_digest(self.policy),
            "source_repository": self.policy["source_repository"],
            "source_revision": SHA,
            "hf_repository": self.policy["hf_repository"],
            "hf_revision": HF,
            "bundle_sha256": BUNDLE,
            "runtime_source_revision": SHA,
            "runtime_bundle_sha256": BUNDLE,
            "captured_at": "2026-09-12T08:59:00Z",
            "valid_until": "2026-09-12T09:10:00Z",
            "gates": [],
        }
        self.artifacts = {}
        for gate, spec in self.policy["gates"].items():
            self.artifacts[gate] = {
                "schema": "szl.gate-result/v2", "gate": gate,
                "environment": spec["environment"], "source_revision": SHA,
                "bundle_sha256": BUNDLE,
                "hf_revision": HF if gate == "live" else None,
                "status": "PASS", "checked_count": 4, "failed_count": 0,
                "skipped_count": 0, "started_at": "2026-09-12T08:50:00Z",
                "finished_at": "2026-09-12T08:55:00Z",
            }
            self.report["gates"].append({"gate": gate, "artifact": gate + ".json", "sha256": ""})
            self.write_artifact(gate)

    def write_artifact(self, gate):
        raw = json.dumps(self.artifacts[gate], sort_keys=True).encode()
        (self.root / (gate + ".json")).write_bytes(raw)
        next(x for x in self.report["gates"] if x["gate"] == gate)["sha256"] = hashlib.sha256(raw).hexdigest()

    def result(self):
        return assess(self.policy, self.report, self.root, NOW)

    def assert_hold(self, code=None):
        result = self.result()
        self.assertEqual(result.state, "HOLD")
        self.assertFalse(result.promotion_authorized)
        if code:
            self.assertIn(code, result.blockers)

    def test_complete_is_still_unverified(self):
        result = self.result()
        self.assertEqual(result.state, "CONTRACT_COMPLETE_UNVERIFIED")
        self.assertEqual(result.checked_gates, 3)
        self.assertEqual(result.cryptographic_verification, "NOT_PERFORMED")
        self.assertEqual(result.runtime_verification, "NOT_PERFORMED")
        self.assertFalse(result.promotion_authorized)

    def test_github_and_hf_shas_need_not_be_equal(self):
        self.assertNotEqual(SHA, HF)
        self.assertEqual(self.result().state, "CONTRACT_COMPLETE_UNVERIFIED")

    def test_policy_mutation_invalidates_digest(self):
        self.policy["gates"]["unit"]["max_age_seconds"] = 4000
        self.assert_hold("POLICY_DIGEST_MISMATCH")

    def test_empty_policy_is_not_all_passed(self):
        self.policy["gates"] = {}
        self.assert_hold("INVALID_REQUIRED_GATES")

    def test_unknown_policy_version(self):
        self.policy["schema"] = "v999"
        self.assert_hold("UNKNOWN_POLICY_SCHEMA")

    def test_wrong_github_org(self):
        self.policy["source_repository"] = "another/david-leads"
        self.assert_hold("WRONG_SOURCE_ORG")

    def test_wrong_hf_org(self):
        self.policy["hf_repository"] = "another/david-leads"
        self.assert_hold("WRONG_HF_ORG")

    def test_short_sha_denied(self):
        self.policy["source_revision"] = "a" * 7
        self.assert_hold("INVALID_SOURCE_REVISION")

    def test_boolean_ttl_denied(self):
        self.policy["gates"]["unit"]["max_age_seconds"] = True
        self.assert_hold("INVALID_MAX_AGE")

    def test_unknown_environment_denied(self):
        self.policy["gates"]["unit"]["environment"] = "TRUST_ME"
        self.assert_hold("UNKNOWN_ENVIRONMENT")

    def test_extra_report_fields_denied(self):
        self.report["secret"] = "synthetic-not-a-secret"
        self.assert_hold("INVALID_REPORT")

    def test_missing_report_field_denied(self):
        del self.report["source_revision"]
        self.assert_hold("INVALID_REPORT")

    def test_unknown_report_schema_denied(self):
        self.report["schema"] = "v999"
        self.assert_hold("UNKNOWN_REPORT_SCHEMA")

    def test_release_source_sha_mismatch(self):
        self.report["source_revision"] = "d" * 40
        self.assert_hold("RELEASE_SUBJECT_MISMATCH")

    def test_release_repo_mismatch(self):
        self.report["source_repository"] = "szl-holdings/other"
        self.assert_hold("RELEASE_SUBJECT_MISMATCH")

    def test_runtime_sha_mismatch(self):
        self.report["runtime_source_revision"] = "e" * 40
        self.assert_hold("RUNTIME_SHA_MISMATCH")

    def test_runtime_bundle_mismatch(self):
        self.report["runtime_bundle_sha256"] = "f" * 64
        self.assert_hold("RUNTIME_BUNDLE_MISMATCH")

    def test_invalid_hf_revision(self):
        self.report["hf_revision"] = "main"
        self.assert_hold("INVALID_HF_REVISION")

    def test_expiry_at_now_denied(self):
        self.report["valid_until"] = NOW.isoformat()
        self.assert_hold("REPORT_EXPIRED_OR_FUTURE")

    def test_future_report_denied(self):
        self.report["captured_at"] = "2026-09-12T09:01:00Z"
        self.assert_hold("REPORT_EXPIRED_OR_FUTURE")

    def test_naive_report_time_denied(self):
        self.report["captured_at"] = "2026-09-12T08:59:00"
        self.assert_hold("NAIVE_TIMESTAMP")

    def test_missing_gate_denied(self):
        self.report["gates"].pop()
        self.assert_hold("MISSING_OR_EXTRA_GATES")

    def test_duplicate_gate_denied(self):
        self.report["gates"][1] = copy.deepcopy(self.report["gates"][0])
        self.assert_hold("DUPLICATE_OR_UNKNOWN_GATE")

    def test_unknown_gate_denied(self):
        self.report["gates"][0]["gate"] = "invented"
        self.assert_hold("DUPLICATE_OR_UNKNOWN_GATE")

    def test_traversal_denied(self):
        self.report["gates"][0]["artifact"] = "../unit.json"
        self.assert_hold("INVALID_ARTIFACT_PATH")

    def test_windows_path_denied(self):
        self.report["gates"][0]["artifact"] = "C:\\unit.json"
        self.assert_hold("INVALID_ARTIFACT_PATH")

    def test_absolute_path_denied(self):
        self.report["gates"][0]["artifact"] = "/tmp/unit.json"
        self.assert_hold("INVALID_ARTIFACT_PATH")

    def test_url_path_denied(self):
        self.report["gates"][0]["artifact"] = "https://example.test/file.json"
        self.assert_hold("INVALID_ARTIFACT_PATH")

    def test_missing_artifact_denied(self):
        (self.root / "unit.json").unlink()
        self.assert_hold("ARTIFACT_UNREADABLE")

    def test_symlink_artifact_denied(self):
        target = self.root / "unit.json"
        other = self.root / "other.json"
        target.rename(other)
        target.symlink_to(other)
        self.assert_hold("SYMLINK_ARTIFACT")

    def test_hash_mismatch_denied(self):
        (self.root / "unit.json").write_text("{}")
        self.assert_hold("ARTIFACT_DIGEST_MISMATCH")

    def test_wrong_artifact_schema(self):
        self.artifacts["unit"]["schema"] = "v999"
        self.write_artifact("unit")
        self.assert_hold("UNKNOWN_GATE_SCHEMA")

    def test_gate_name_mismatch(self):
        self.artifacts["unit"]["gate"] = "postgres"
        self.write_artifact("unit")
        self.assert_hold("GATE_ARTIFACT_MISMATCH")

    def test_local_tests_cannot_masquerade_as_live(self):
        self.artifacts["live"]["environment"] = "CI_ISOLATED"
        self.write_artifact("live")
        self.assert_hold("ENVIRONMENT_MISMATCH")

    def test_gate_sha_mismatch(self):
        self.artifacts["unit"]["source_revision"] = "e" * 40
        self.write_artifact("unit")
        self.assert_hold("GATE_SHA_MISMATCH")

    def test_gate_bundle_mismatch(self):
        self.artifacts["unit"]["bundle_sha256"] = "e" * 64
        self.write_artifact("unit")
        self.assert_hold("GATE_BUNDLE_MISMATCH")

    def test_live_hf_revision_mismatch(self):
        self.artifacts["live"]["hf_revision"] = "e" * 40
        self.write_artifact("live")
        self.assert_hold("GATE_HF_MISMATCH")

    def test_nonruntime_hf_claim_denied(self):
        self.artifacts["unit"]["hf_revision"] = HF
        self.write_artifact("unit")
        self.assert_hold("NONRUNTIME_HF_BINDING")

    def test_skipped_status_is_not_success(self):
        self.artifacts["unit"]["status"] = "SKIPPED"
        self.write_artifact("unit")
        self.assert_hold("GATE_NOT_PASS")

    def test_zero_checks_is_not_success(self):
        self.artifacts["unit"]["checked_count"] = 0
        self.write_artifact("unit")
        self.assert_hold("EMPTY_OR_INVALID_GATE")

    def test_boolean_check_count_denied(self):
        self.artifacts["unit"]["checked_count"] = True
        self.write_artifact("unit")
        self.assert_hold("EMPTY_OR_INVALID_GATE")

    def test_failures_denied(self):
        self.artifacts["unit"]["failed_count"] = 1
        self.write_artifact("unit")
        self.assert_hold("FAILED_ASSERTIONS")

    def test_hidden_skips_denied(self):
        self.artifacts["unit"]["skipped_count"] = 1
        self.write_artifact("unit")
        self.assert_hold("SKIPPED_ASSERTIONS")

    def test_future_test_denied(self):
        self.artifacts["unit"]["finished_at"] = "2026-09-12T09:00:01Z"
        self.write_artifact("unit")
        self.assert_hold("INVALID_GATE_TIME_ORDER")

    def test_stale_gate_denied(self):
        self.artifacts["unit"]["started_at"] = "2026-09-11T06:00:00Z"
        self.artifacts["unit"]["finished_at"] = "2026-09-11T06:10:00Z"
        self.write_artifact("unit")
        self.assert_hold("STALE_GATE")

    def test_report_cannot_outlive_earliest_gate(self):
        self.report["valid_until"] = "2026-09-12T10:00:00Z"
        self.assert_hold("REPORT_OUTLIVES_GATE")

    def test_naive_now_denied(self):
        result = assess(self.policy, self.report, self.root, datetime(2026, 9, 12))
        self.assertEqual(result.blockers, ("NAIVE_NOW",))

    def test_malformed_nonobject_inputs_fail_closed(self):
        for value in (None, [], True, "PASS", 5):
            with self.subTest(value=value):
                self.assertEqual(assess(value, self.report, self.root, NOW).state, "HOLD")


class JsonTests(unittest.TestCase):
    def test_duplicate_keys_rejected(self):
        with self.assertRaisesRegex(ContractError, "DUPLICATE_JSON_KEY"):
            parse_json(b'{"x":1,"x":2}')

    def test_nonfinite_constants_rejected(self):
        for value in (b'NaN', b'Infinity', b'-Infinity'):
            with self.subTest(value=value), self.assertRaises(ContractError):
                parse_json(value)

    def test_float_overflow_rejected(self):
        with self.assertRaisesRegex(ContractError, "NONFINITE_JSON"):
            parse_json(b'{"x":1e999}')

    def test_oversize_json_rejected(self):
        with self.assertRaisesRegex(ContractError, "JSON_TOO_LARGE"):
            parse_json(b" " * (MAX_BYTES + 1))

    def test_invalid_utf8_rejected(self):
        with self.assertRaisesRegex(ContractError, "INVALID_JSON"):
            parse_json(b"\xff")

    def test_malformed_json_rejected(self):
        with self.assertRaisesRegex(ContractError, "INVALID_JSON"):
            parse_json(b"{")

    def test_digest_ignores_object_insertion_order(self):
        self.assertEqual(canonical_digest({"a": 1, "b": 2}),
                         canonical_digest({"b": 2, "a": 1}))

    def test_digest_rejects_nonfinite(self):
        with self.assertRaises(ContractError):
            canonical_digest({"x": float("nan")})


if __name__ == "__main__":
    unittest.main()
