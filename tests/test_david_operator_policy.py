"""Synthetic scope/HTTP boundary tests. No production grants or source admission."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import server
from app.domain.david_reference import Hold
from app.domain.operator_policy import ACTIONS, load_operator_context


def synthetic_policy(now):
    expiry = (now + timedelta(hours=2)).isoformat()
    return {"schema": "szl.david.operator-policy/v1", "revision": "synthetic-test-policy-v1",
        "review_reference": "SYNTHETIC_TEST_ONLY", "expires_at": expiry, "operators": [
        {"username": "synthetic-a", "tenant": "synthetic-tenant-a", "actions": sorted(ACTIONS),
         "purpose": "organization_research", "expires_at": expiry},
        {"username": "synthetic-b", "tenant": "synthetic-tenant-b", "actions": ["read"],
         "purpose": "organization_research", "expires_at": expiry}]}


class OperatorPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "synthetic-policy.json"
        self.now = datetime.now(timezone.utc)
        self.policy = synthetic_policy(self.now)

    def load(self, username="synthetic-a", policy=None):
        self.path.write_text(json.dumps(policy or self.policy), encoding="utf-8")
        return load_operator_context(str(self.path), username, self.now+timedelta(hours=1), self.now)

    def test_named_operator_gets_only_server_owned_tenant(self):
        self.assertEqual(self.load().tenant, "synthetic-tenant-a")
        self.assertEqual(self.load("synthetic-b").tenant, "synthetic-tenant-b")

    def test_unknown_operator_has_no_scope(self):
        with self.assertRaisesRegex(Hold, "DENIED"):
            self.load("unregistered")

    def test_read_only_operator_cannot_clear_or_create_tasks(self):
        context = self.load("synthetic-b")
        for action in ("clearance", "manual_task", "correct", "suppress"):
            with self.subTest(action=action), self.assertRaises(Hold):
                context.require(action, self.now)

    def test_missing_policy_is_held(self):
        with self.assertRaisesRegex(Hold, "NOT_CONFIGURED"):
            load_operator_context(None, "synthetic-a", self.now, self.now)

    def test_write_only_policy_is_denied_before_a_mutation_can_commit(self):
        self.policy["operators"][0]["actions"] = ["manual_task"]
        with self.assertRaisesRegex(Hold, "OPERATOR_POLICY_INVALID"):
            self.load()

    def test_relative_policy_path_is_held(self):
        with self.assertRaisesRegex(Hold, "ABSOLUTE"):
            load_operator_context("local-policy.json", "synthetic-a", self.now, self.now)

    def test_session_expiry_limits_grant(self):
        context = self.load()
        self.assertEqual(context.expires_at, self.now + timedelta(hours=1))
        with self.assertRaises(Hold):
            context.require("read", context.expires_at)

    def test_policy_expiry_cannot_be_extended_by_session(self):
        self.policy["expires_at"] = self.now.isoformat()
        with self.assertRaises(Hold):
            self.load()

    def test_duplicate_operator_is_not_ambiguous(self):
        self.policy["operators"].append(copy.deepcopy(self.policy["operators"][0]))
        with self.assertRaises(Hold):
            self.load()

    def test_unknown_action_and_wrong_purpose_denied(self):
        for field, value in (("actions", ["send_email"]), ("purpose", "underwriting")):
            with self.subTest(field=field):
                policy = copy.deepcopy(self.policy)
                policy["operators"][0][field] = value
                with self.assertRaises(Hold):
                    self.load(policy=policy)

    def test_nested_injected_policy_fields_rejected(self):
        self.policy["operators"][0]["credentials"] = {"secret": "synthetic"}
        with self.assertRaises(Hold):
            self.load()

    def test_policy_change_changes_bound_digest(self):
        before = self.load().policy_digest
        self.policy["operators"][0]["actions"].remove("manual_task")
        self.assertNotEqual(before, self.load().policy_digest)

    def test_duplicate_json_keys_rejected(self):
        self.path.write_text('{"schema":"one","schema":"two"}')
        with self.assertRaises(Hold):
            load_operator_context(str(self.path), "synthetic-a", self.now, self.now)

    def test_secret_policy_supports_deployment_without_a_mutable_file(self):
        with patch.dict(os.environ, {"DAVID_OPERATOR_POLICY_JSON": json.dumps(self.policy)}):
            context = load_operator_context(None, "synthetic-a", self.now+timedelta(hours=1), self.now)
        self.assertEqual(context.tenant, "synthetic-tenant-a")

    def test_explicit_invalid_file_does_not_fall_back_to_secret_authority(self):
        with patch.dict(os.environ, {"DAVID_OPERATOR_POLICY_JSON": json.dumps(self.policy)}):
            with self.assertRaisesRegex(Hold, "OPERATOR_POLICY_INVALID"):
                load_operator_context(str(self.path), "synthetic-a", self.now+timedelta(hours=1), self.now)

    def test_public_readiness_reports_current_operator_policy_separately(self):
        client = TestClient(server.app)
        with (
            patch.object(server, "_CREDS_CONFIGURED", True),
            patch.object(server, "_CREDS_ROTATION_REQUIRED", False),
            patch.object(server, "DAVID_USER", "synthetic-a"),
            patch.object(server.dd, "persistence_state", return_value="POSTGRES_READY"),
            patch.object(server, "_evidence_readiness", return_value="POSTGRES_READY"),
            patch.dict(os.environ, {"DAVID_OPERATOR_POLICY_PATH": "", "DAVID_OPERATOR_POLICY_JSON": ""}),
        ):
            missing = client.get("/readyz")
            self.assertEqual(missing.status_code, 200)
            self.assertEqual(missing.json()["operator_workflow"]["workspace_access"], "BLOCKED")
            with patch(
                "app.domain.operator_policy.load_operator_context",
                side_effect=Hold("private-policy-path-and-operator-detail"),
            ):
                denied = client.get("/readyz").json()
                self.assertEqual(
                    denied["operator_workflow"]["blockers"],
                    ["OPERATOR_POLICY_NOT_ADMITTED"],
                )
                self.assertNotIn("private-policy-path-and-operator-detail", json.dumps(denied))
            with patch.dict(os.environ, {"DAVID_OPERATOR_POLICY_JSON": json.dumps(self.policy)}):
                current = client.get("/readyz").json()
                self.assertEqual(current["operator_workflow"]["workspace_access"], "AVAILABLE")
                self.assertEqual(current["operator_workflow"]["source_admission"], "CURRENT_SOURCE_GRANT_REQUIRED")
                self.assertNotIn("synthetic-a", json.dumps(current))
            self.policy["expires_at"] = (self.now-timedelta(seconds=1)).isoformat()
            with patch.dict(os.environ, {"DAVID_OPERATOR_POLICY_JSON": json.dumps(self.policy)}):
                expired = client.get("/readyz").json()
                self.assertEqual(expired["operator_workflow"]["workspace_access"], "BLOCKED")


class WorkflowHttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.token = "synthetic-workflow-boundary"
        server._TOKENS[self.token] = {"username": "synthetic-a", "expires_at": time.time()+3600}
        self.addCleanup(server._TOKENS.pop, self.token, None)
        self.headers = {"Authorization": "Bearer " + self.token}

    def test_anonymous_workspace_is_denied_and_never_cached(self):
        response = self.client.get("/api/v1/operator/workspaces/synthetic-a")
        self.assertEqual(response.status_code, 401)
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_header_tenant_does_not_establish_operator_grant(self):
        with patch.dict(os.environ, {"DAVID_OPERATOR_POLICY_PATH": ""}):
            response = self.client.get("/api/v1/operator/workspaces/synthetic-a",
                headers={**self.headers, "X-Tenant-ID": "synthetic-admin"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "OPERATOR_POLICY_NOT_CONFIGURED")

    def test_expired_session_denied(self):
        server._TOKENS[self.token]["expires_at"] = time.time()-1
        response = self.client.get("/api/v1/operator/workspaces/synthetic-a", headers=self.headers)
        self.assertEqual(response.status_code, 401)

    def test_unnamed_legacy_session_cannot_create_workflow_authority(self):
        server._TOKENS[self.token] = time.time()+3600
        response = self.client.get("/api/v1/operator/workspaces/synthetic-a", headers=self.headers)
        self.assertEqual(response.status_code, 401)

    def test_client_cannot_assert_clearance_gates_or_tenant(self):
        for field in ("gates_complete", "tenant", "operator", "approved", "source_rights"):
            with self.subTest(field=field):
                response = self.client.post("/api/v1/operator/workspaces/synthetic-a/clearances",
                    headers=self.headers, json={"expected_epoch": 0, "review_id": "a"*64, field: True})
                self.assertEqual(response.status_code, 422)

    def test_boolean_epoch_and_external_task_are_denied(self):
        for changes in ({"expected_epoch": True}, {"task_type": "SEND_EMAIL"}, {"destination": "https://example.test"}):
            response = self.client.post("/api/v1/operator/workspaces/synthetic-a/tasks", headers=self.headers,
                json={"expected_epoch": 0, "clearance_id": "a"*64, "task_type": "VERIFY_SOURCE",
                      "idempotency_key": "synthetic-task-1", **changes})
            self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
