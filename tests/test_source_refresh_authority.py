"""Refresh health must present current authority after network work completes.

This service-contract regression uses real policy, snapshot and HMAC validation;
its in-memory persistence substitute does not establish PostgreSQL proof.
"""
from contextlib import contextmanager
from datetime import timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.domain import source_admission
from app.domain.david_reference import stamp
from app.domain.david_workflow import Workflow
from app.domain.operator_policy import OperatorContext
from app.domain.source_policy import SourceHealthRecord, record_source_attempt
from app.federal_refresh_store import load_dol_snapshot
from tests.dol_fixtures import KEY, NOW, REVISION, bundle_files, fixture, policy


class SourceRefreshAuthorityTests(unittest.TestCase):
    def test_research_revoked_during_download_is_absent_from_refresh_response(self):
        value = fixture()
        files = bundle_files(value)
        reviewed = policy(value)
        context = OperatorContext("synthetic-reviewer", "synthetic-refresh", frozenset({"read", "admit"}),
                                  "synthetic-v1", "synthetic-policy-digest", NOW + timedelta(hours=1))
        retained = {}

        class Ledger:
            @contextmanager
            def scope_read(self, tenant, scope):
                yield

            def decision_epoch(self, tenant, scope):
                return 0

        class Store:
            def __init__(self, ledger):
                pass

            def record_attempt(self, tenant, attempt):
                record = record_source_attempt(SourceHealthRecord(attempt.source_id), attempt)
                retained["record"] = record
                return record

        with tempfile.TemporaryDirectory() as temporary:
            policy_path = Path(temporary) / "policy.json"
            key_path = Path(temporary) / "key"
            policy_path.write_text(json.dumps(reviewed), encoding="utf-8")
            key_path.write_bytes(KEY)

            def download(filename, requested_revision):
                self.assertEqual(requested_revision, REVISION)
                # The snapshot remains byte-identical and valid, but its earlier
                # reviewed authority is withdrawn while the attempt is running.
                reviewed["rights"]["research"] = "DENY"
                policy_path.write_text(json.dumps(reviewed), encoding="utf-8")
                return files[filename]

            def snapshot(revision, **kwargs):
                return load_dol_snapshot(revision, downloader=download, **kwargs)

            with patch.dict(os.environ, {"DAVID_DOL_POLICY_PATH": str(policy_path),
                                        "DAVID_DOL_SIGNING_KEY_FILE": str(key_path)}), \
                 patch.object(source_admission, "load_dol_snapshot", side_effect=snapshot), \
                 patch("app.domain.source_health_store.SourceHealthStore", Store):
                workflow = Workflow(Ledger(), context, NOW, reauthorize=lambda: (context, NOW))
                result = workflow.refresh_source("synthetic-scope", 0, REVISION)

        saved = retained["record"]
        self.assertIsNotNone(saved.last_success_at, "Completed verified download remains historical evidence")
        self.assertEqual(result["last_success_at"], stamp(saved.last_success_at))
        self.assertEqual(result["eligible_operations"], [])
        self.assertNotEqual(result["policy_state"], "APPROVED")
        self.assertIn("POLICY_NOT_EVALUATED", result["blocking_reasons"])
