"""Real PostgreSQL HTTP workflow with explicitly synthetic reviewed policy/facts."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app import server
from app.domain.david_reference import Grant, Observation, Verdict
from app.domain.david_postgres import connect_postgres_ledger
from app.domain.operator_policy import ACTIONS
from tests.postgres_support import bootstrap_test_database


class RealWorkflowApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = bootstrap_test_database()

    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.expiry = self.now + timedelta(hours=1)
        self.tenant = "synthetic-" + uuid4().hex
        self.scope = "synthetic-organization"
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.policy_path = Path(self.tmp.name) / "synthetic-policy.json"
        self.policy = {"schema": "szl.david.operator-policy/v1", "revision": "synthetic-v1",
            "review_reference": "SYNTHETIC_TEST_ONLY", "expires_at": self.expiry.isoformat(), "operators": [
            {"username": "synthetic-operator", "tenant": self.tenant, "actions": sorted(ACTIONS),
             "purpose": "organization_research", "expires_at": self.expiry.isoformat()},
            {"username": "synthetic-other", "tenant": "other-" + self.tenant, "actions": ["read"],
             "purpose": "organization_research", "expires_at": self.expiry.isoformat()}]}
        self.write_policy()
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"DAVID_DATABASE_URL": self.dsn,
            "DAVID_OPERATOR_POLICY_PATH": str(self.policy_path)}).start()
        self.token = "synthetic-session-" + uuid4().hex
        server._TOKENS[self.token] = {"username": "synthetic-operator", "expires_at": time.time()+3600}
        self.addCleanup(server._TOKENS.pop, self.token, None)
        self.headers = {"Authorization": "Bearer " + self.token}
        self.client = TestClient(server.app)
        self.base = "/api/v1/operator/workspaces/" + self.scope
        grant = Grant("synthetic-source", "synthetic-policy", "SYNTHETIC_TEST_ONLY", self.expiry,
            {"collect": Verdict.ALLOW, "research": Verdict.ALLOW, "public_display": Verdict.DENY},
            frozenset({"organization_name", "state", "participant_count"}))
        observation = Observation(grant.source_id, "synthetic-filing", "synthetic-revision",
            self.now-timedelta(days=1), self.now, self.expiry,
            {"organization_name": "SYNTHETIC Example Organization", "state": "NY", "participant_count": 12})
        body = observation.body(grant, self.now)
        body.update(entity_type="organization", classification_evidence="SYNTHETIC_TEST_ONLY")
        ledger = connect_postgres_ledger(self.dsn)
        try:
            self.source = ledger.admit_observation(self.tenant, self.scope, grant, body,
                self.expiry, self.now, expected_epoch=0)
        finally:
            ledger.close()

    def write_policy(self):
        self.policy_path.write_text(json.dumps(self.policy), encoding="utf-8")

    def workspace(self):
        result = self.client.get(self.base, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn("no-store", result.headers["cache-control"])
        return result.json()

    def post(self, path, values, status=200, epoch=None):
        if epoch is None:
            epoch = self.workspace()["decision_epoch"]
        result = self.client.post(self.base + "/" + path, headers=self.headers,
            json={"expected_epoch": epoch, **values})
        self.assertEqual(result.status_code, status, result.text)
        self.assertIn("no-store", result.headers["cache-control"])
        return result.json()

    def reviewed_brief(self):
        identity = self.post("identity-reviews", {"source_ids": [self.source], "decision": "ORGANIZATION_CONFIRMED"})
        brief = self.post("briefs", {"source_ids": [self.source], "identity_review_id": identity["id"]})
        self.assertEqual(brief["detail"]["facts"][0]["fields"]["participant_count"], 12)
        review = self.post("brief-reviews", {"brief_id": brief["id"], "approved": True})
        return brief, review

    def clearance(self):
        brief, review = self.reviewed_brief()
        return self.post("clearances", {"review_id": review["id"]})

    def test_authorized_brief_review_clearance_and_durable_manual_task(self):
        clearance = self.clearance()
        values = {"clearance_id": clearance["id"], "task_type": "VERIFY_SOURCE", "idempotency_key": "synthetic-task-1"}
        created = self.post("tasks", values)
        replay = self.post("tasks", values)
        self.assertEqual(created, replay)
        nodes = self.workspace()["nodes"]
        tasks = [n for n in nodes if n["kind"] in {"crm_task", "manual_task"}]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["state"], "VALID")
        self.post("outcomes", {"task_id": tasks[0]["id"], "outcome": "RESEARCH_COMPLETED"})
        self.assertEqual(self.workspace()["contact_permission"], "NOT_GRANTED")

    def test_stale_epoch_and_cross_scope_source_cannot_create_brief(self):
        epoch = self.workspace()["decision_epoch"]
        self.post("identity-reviews", {"source_ids": [self.source], "decision": "NEEDS_REVIEW"})
        self.post("identity-reviews", {"source_ids": [self.source], "decision": "ORGANIZATION_CONFIRMED"}, status=409, epoch=epoch)
        response = self.client.post("/api/v1/operator/workspaces/other-scope/identity-reviews", headers=self.headers,
            json={"source_ids": [self.source], "decision": "ORGANIZATION_CONFIRMED", "expected_epoch": 0})
        self.assertEqual(response.status_code, 404, response.text)

    def test_policy_change_revokes_existing_clearance_authority(self):
        clearance = self.clearance()
        self.policy["revision"] = "synthetic-v2"
        self.write_policy()
        result = self.post("tasks", {"clearance_id": clearance["id"], "task_type": "VERIFY_SOURCE",
            "idempotency_key": "synthetic-policy-change"}, status=403)
        self.assertEqual(result["detail"]["code"], "OPERATOR_POLICY_CHANGED")

    def test_rejection_supersedes_prior_brief_approval(self):
        brief, approved = self.reviewed_brief()
        self.post("brief-reviews", {"brief_id": brief["id"], "approved": False})
        result = self.post("clearances", {"review_id": approved["id"]}, status=409)
        self.assertEqual(result["detail"]["code"], "REVIEW_SUPERSEDED")

    def test_rejection_supersedes_prior_organization_confirmation(self):
        identity = self.post("identity-reviews", {"source_ids": [self.source], "decision": "ORGANIZATION_CONFIRMED"})
        self.post("identity-reviews", {"source_ids": [self.source], "decision": "REJECTED"})
        result = self.post("briefs", {"source_ids": [self.source], "identity_review_id": identity["id"]}, status=409)
        self.assertEqual(result["detail"]["code"], "REVIEW_SUPERSEDED")

    def test_distinct_task_requests_do_not_collide_and_retry_is_stable(self):
        clearance = self.clearance()
        first = self.post("tasks", {"clearance_id": clearance["id"], "task_type": "VERIFY_SOURCE", "idempotency_key": "synthetic-first-task"})
        second = self.post("tasks", {"clearance_id": clearance["id"], "task_type": "VERIFY_SOURCE", "idempotency_key": "synthetic-second-task"})
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(second, self.post("tasks", {"clearance_id": clearance["id"], "task_type": "VERIFY_SOURCE", "idempotency_key": "synthetic-second-task"}))

    def test_new_evidence_decision_cannot_reuse_an_older_approved_brief(self):
        brief, review = self.reviewed_brief()
        self.post("counter-evidence", {"source_ids": [self.source], "reason": "IDENTITY_CONFLICT"})
        result = self.post("clearances", {"review_id": review["id"]}, status=409)
        self.assertEqual(result["detail"]["code"], "BRIEF_EVIDENCE_CHANGED_REVIEW_REQUIRED")

    def test_correction_invalidates_transitive_brief_clearance_task_and_hides_facts(self):
        clearance = self.clearance()
        self.post("tasks", {"clearance_id": clearance["id"], "task_type": "VERIFY_SOURCE", "idempotency_key": "synthetic-correct-task"})
        result = self.post("corrections", {"node_id": self.source, "reason": "SOURCE_WITHDRAWN"})
        self.assertGreaterEqual(result["revoked"], 5)
        nodes = self.workspace()["nodes"]
        for node in nodes:
            if node["kind"] != "grant":
                self.assertNotEqual(node["state"], "VALID")
                self.assertNotIn("facts", node)
                self.assertNotIn("detail", node)

    def test_counter_evidence_blocks_approval_and_suppression_blocks_tasks(self):
        self.post("counter-evidence", {"source_ids": [self.source], "reason": "CONTRADICTORY_SOURCE"})
        identity = self.post("identity-reviews", {"source_ids": [self.source], "decision": "ORGANIZATION_CONFIRMED"})
        brief = self.post("briefs", {"source_ids": [self.source], "identity_review_id": identity["id"]})
        self.assertEqual(len(brief["detail"]["counter_evidence_ids"]), 1)
        self.post("brief-reviews", {"brief_id": brief["id"], "approved": True}, status=409)
        self.post("suppressions", {})
        self.post("identity-reviews", {"source_ids": [self.source], "decision": "ORGANIZATION_CONFIRMED"}, status=409)

    def test_other_tenant_and_anonymous_cannot_retrieve_private_node(self):
        other = "synthetic-other-session-" + uuid4().hex
        server._TOKENS[other] = {"username": "synthetic-other", "expires_at": time.time()+3600}
        self.addCleanup(server._TOKENS.pop, other, None)
        url = self.base + "/nodes/" + self.source
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(url, headers={"Authorization": "Bearer "+other,
            "X-Tenant-ID": self.tenant}).status_code, 404)
        public = self.client.get("/api/v1/public/capabilities")
        self.assertNotIn(self.tenant, public.text)
        self.assertNotIn("SYNTHETIC Example Organization", public.text)

    def test_decision_diff_uses_stored_brief_features(self):
        first, _ = self.reviewed_brief()
        second, _ = self.reviewed_brief()
        result = self.client.get(self.base+"/decision-diff", headers=self.headers,
            params={"before": first["id"], "after": second["id"]})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["unchanged"], [self.source])
        self.assertEqual(result.json()["added"], [])

    def test_real_snapshot_admission_then_policy_revocation_hides_derived_payload(self):
        from tests.dol_fixtures import fixture, policy, bundle_files, KEY, REVISION
        from app.domain import source_admission
        from app.federal_refresh_store import load_dol_snapshot
        value = fixture()
        reviewed_policy = policy(value)
        path = Path(self.tmp.name) / "dol-policy.json"
        key = Path(self.tmp.name) / "dol-key"
        path.write_text(json.dumps(reviewed_policy), encoding="utf-8")
        key.write_bytes(KEY)
        files = bundle_files(value)
        with patch.dict(os.environ, {"DAVID_DOL_POLICY_PATH": str(path), "DAVID_DOL_SIGNING_KEY_FILE": str(key)}), patch.object(
            source_admission, "load_dol_snapshot", side_effect=lambda revision, **kwargs:
                load_dol_snapshot(revision, downloader=lambda filename, _revision: files[filename], **kwargs)):
            admitted = self.post("admissions", {"source_id": source_admission.SOURCE_ID,
                "record_id": "dol-5500:SYNTHETIC-A1", "snapshot_revision": REVISION})
            self.source = admitted["id"]
            self.assertIsNone(admitted["published_at"])
            self.assertIsNotNone(admitted["snapshot_published_at"])
            brief, review = self.reviewed_brief()
            clearance = self.post("clearances", {"review_id": review["id"]})
            reviewed_policy["rights"]["research"] = "DENY"
            path.write_text(json.dumps(reviewed_policy), encoding="utf-8")
            response = self.client.get(self.base+"/nodes/"+brief["id"], headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["state"], "HOLD")
            self.assertNotIn("detail", response.json())
            response = self.client.post(self.base+"/tasks", headers=self.headers,
                json={"expected_epoch": self.workspace()["decision_epoch"], "clearance_id": clearance["id"],
                      "task_type": "VERIFY_SOURCE", "idempotency_key": "synthetic-revoked-source"})
            self.assertIn(response.status_code, (403, 409), response.text)


if __name__ == "__main__":
    unittest.main()
