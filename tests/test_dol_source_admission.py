"""DOL byte verification, source permission and privacy boundary tests."""
from datetime import timedelta
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from app.domain.david_reference import Hold
from app.domain import source_admission as admission
from app.domain.source_policy import SourceHealthRecord, public_capabilities, record_source_attempt, sanitize_public_payload, source_status
from app.federal_refresh_store import load_dol_snapshot
from tests.dol_fixtures import KEY, NOW, REVISION, fixture, bundle_files, policy

class ImmutableSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.value = fixture()
        self.now = max(NOW, __import__('datetime').datetime.now(__import__('datetime').timezone.utc))
    def load(self, value=None, *, files=None, revision=REVISION, key=KEY, now=None):
        files = files if files is not None else bundle_files(value or self.value)
        seen = []
        def downloader(path, requested_revision):
            seen.append(requested_revision)
            return files[path]
        result = load_dol_snapshot(revision, signing_key=key, now=now or self.now, downloader=downloader)
        self.assertEqual(set(seen), {REVISION})
        return result
    def test_real_hash_and_hmac_verification(self):
        result = self.load()
        self.assertEqual(result.records[0]['source_record_id'], 'dol-5500:SYNTHETIC-A1')
        self.assertNotIn('EXCLUDED', json.dumps(result.records))
    def test_main_and_unknown_revision_denied(self):
        for revision in ['main', REVISION.upper(), '../main', 'a'*39]:
            with self.subTest(revision=revision), self.assertRaises(Hold): self.load(revision=revision)
    def test_wrong_key_and_unsigned_denied(self):
        with self.assertRaisesRegex(Hold, 'SIGNATURE_INVALID'): self.load(key=b'b'*32)
        files = bundle_files(self.value)
        receipt_path = next(x for x in files if x.endswith('/receipt.json'))
        data = json.loads(files[receipt_path]); data['signature']['value']='UNSIGNED'
        self.value['receipt'] = data
        with self.assertRaises(Hold): self.load(files=bundle_files(self.value, resign=False))
    def test_pointer_file_hash_mutation(self):
        files = bundle_files(self.value)
        path = next(x for x in files if x.endswith('/records.jsonl'))
        files[path] += b' '
        with self.assertRaisesRegex(Hold, 'INTEGRITY_FAILED'): self.load(files=files)
    def test_wrong_lane_and_traversal(self):
        for key, value in [('lane','echo-exporter'), ('path','../secrets')]:
            files = bundle_files(self.value)
            pointer=json.loads(files['latest/dol-5500-bulk.json']); pointer[key]=value
            files['latest/dol-5500-bulk.json']=json.dumps(pointer).encode()
            with self.subTest(key=key),self.assertRaises(Hold):self.load(files=files)
    def test_snapshot_completeness_bound_to_signature(self):
        self.value['snapshot']['freshness_days']=35
        with self.assertRaisesRegex(Hold,'RECEIPT_BINDING'): self.load(files=bundle_files(self.value,resign=False))
    def test_partial_unsupported_and_future_denied(self):
        for field,value in [('completeness','PARTIAL'),('parser_version','0.0.0'),('created_at','2099-01-01T00:00:00Z')]:
            changed=copy.deepcopy(self.value); changed['snapshot'][field]=value
            with self.subTest(field=field),self.assertRaises(Hold):self.load(changed)
    def test_stale_denied_without_refreshing_source_time(self):
        with self.assertRaisesRegex(Hold,'SOURCE_STALE'):self.load(now=self.now+timedelta(days=10))
    def test_private_nested_field_cannot_pass_even_resigned(self):
        self.value['records'][0]['raw']['ein']='synthetic-excluded'
        with self.assertRaisesRegex(Hold,'MINIMIZATION'):self.load()
    def test_duplicate_record_denied(self):
        self.value['records'].append(copy.deepcopy(self.value['records'][0]))
        self.value['snapshot']['record_count']=2
        self.value['snapshot']['counts']['accepted']=2
        self.value['snapshot']['counts']['rows_seen']=2
        with self.assertRaises(Hold): self.load()
    def test_network_failure_is_unavailable(self):
        with self.assertRaisesRegex(Hold,'TRANSPORT_UNAVAILABLE'):
            load_dol_snapshot(REVISION,signing_key=KEY,now=self.now,downloader=mock.Mock(side_effect=TimeoutError))
    def test_duplicate_json_keys_fail(self):
        with self.assertRaisesRegex(Hold,'SCHEMA_CHANGED'):
            load_dol_snapshot(REVISION,signing_key=KEY,now=self.now,downloader=lambda *_:b'{"lane":1,"lane":2}')

class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.value=fixture(); self.policy=policy(self.value)
        self.now=__import__('datetime').datetime.now(__import__('datetime').timezone.utc)
        self.path=Path(self.temp.name)/'policy.json'; self.keypath=Path(self.temp.name)/'key'; self.keypath.write_bytes(KEY)
        patcher=mock.patch.dict(os.environ,{'DAVID_DOL_POLICY_PATH':str(self.path),'DAVID_DOL_SIGNING_KEY_FILE':str(self.keypath)})
        patcher.start();self.addCleanup(patcher.stop)
        files=bundle_files(self.value)
        original=load_dol_snapshot
        loader=mock.patch.object(admission,'load_dol_snapshot',side_effect=lambda revision,**kwargs:original(revision,downloader=lambda path,rev:files[path],**kwargs))
        loader.start();self.addCleanup(loader.stop)
        self.save()
    def save(self):self.path.write_text(json.dumps(self.policy))
    def admit(self):return admission.get_admitted_observation(admission.SOURCE_ID,'dol-5500:SYNTHETIC-A1',REVISION,self.now)
    def test_full_reviewed_organization_admission(self):
        result=self.admit();self.assertEqual(result.entity_type,'organization');self.assertEqual(result.observation.fields['form_year'],2025)
        self.assertTrue(result.observation.fields['amended_filing']);self.assertEqual(result.observation.fields['plan_year_begin'],'2025-01-01')

    def stored_body(self):
        value = self.admit()
        body = value.observation.body(value.grant, self.now)
        body.update(entity_type=value.entity_type, classification_evidence=value.classification_evidence,
                    snapshot_revision=value.snapshot_revision, signing_key_fingerprint=value.signing_key_fingerprint)
        return body

    def test_current_policy_revocation_denies_already_admitted_evidence(self):
        body = self.stored_body()
        admission.validate_stored_admission(body, self.now)
        self.policy['rights']['research'] = 'DENY'
        self.save()
        with self.assertRaises(Hold):
            admission.validate_stored_admission(body, self.now)

    def test_current_classification_removal_denies_admitted_evidence(self):
        body = self.stored_body()
        self.policy['classifications'] = {}
        self.save()
        with self.assertRaises(Hold):
            admission.validate_stored_admission(body, self.now)

    def test_key_rotation_requires_new_admission(self):
        body = self.stored_body()
        self.keypath.write_bytes(b'new-synthetic-signing-key-32-bytes-only')
        with self.assertRaisesRegex(Hold, 'SIGNING_KEY'):
            admission.validate_stored_admission(body, self.now)
    def test_missing_policy_is_not_a_grant(self):
        self.path.unlink()
        with self.assertRaisesRegex(Hold,'NOT_CONFIGURED'):self.admit()
    def test_name_suffix_never_admits_organization(self):
        self.policy['classifications']={};self.save()
        with self.assertRaisesRegex(Hold,'CLASSIFICATION_REVIEW'):self.admit()
    def test_review_binds_exact_record_hash(self):
        self.policy['classifications']['dol-5500:SYNTHETIC-A1']['record_hash']='0'*64;self.save()
        with self.assertRaisesRegex(Hold,'CLASSIFICATION_REVIEW'):self.admit()
    def test_unadmitted_revision_denied(self):
        with self.assertRaisesRegex(Hold,'REVISION_NOT_ADMITTED'):
            admission.get_admitted_observation(admission.SOURCE_ID,'dol-5500:SYNTHETIC-A1','b'*40,self.now)
    def test_private_research_does_not_allow_public_display(self):
        self.admit()
        with self.assertRaises(Hold):admission.public_dol_records(['NY'],10,self.now)
    def test_public_projection_requires_separate_right_and_review(self):
        self.policy['rights']['public_display']='ALLOW';self.save()
        rows,revision=admission.public_dol_records(['NY'],10,self.now)
        self.assertEqual(len(rows),1);self.assertEqual(revision,REVISION)
        self.assertNotIn('review_reference',json.dumps(rows));self.assertNotIn('EXCLUDED',json.dumps(rows))
    def test_denied_jurisdiction_and_expired_policy(self):
        self.policy['jurisdictions']=['PA'];self.save()
        with self.assertRaises(Hold):self.admit()
        self.policy['expires_at']=(self.now-timedelta(seconds=1)).isoformat();self.save()
        with self.assertRaises(Hold):self.admit()
    def test_unknown_and_prohibited_fields_rejected(self):
        self.policy['allowed_fields'].append('ein');self.save()
        with self.assertRaises(Hold):self.admit()
    def test_real_health_and_failure_last_success(self):
        success=admission.evaluate_source_health(REVISION,self.now)
        saved=record_source_attempt(SourceHealthRecord(admission.SOURCE_ID),success)
        self.assertEqual(source_status(admission.SOURCE_ID,health=saved,now=self.now)['status'],'HEALTHY')
        failed=SourceHealthRecord(admission.SOURCE_ID,grant=saved.grant,transport_state='UNAVAILABLE',last_attempt_at=self.now+timedelta(minutes=1))
        retained=record_source_attempt(saved,failed)
        self.assertEqual(retained.last_success_at,saved.last_success_at);self.assertEqual(retained.snapshot_revision,REVISION)
        self.assertEqual(source_status(admission.SOURCE_ID,health=retained,now=failed.last_attempt_at)['status'],'UNAVAILABLE')
    def test_partial_dimensions_and_chicago_both_blockers(self):
        status=source_status('chicago-new-business-licenses',now=self.now)
        self.assertIn('POLICY_HOLD',status['blocking_reasons']);self.assertIn('AUTH_REQUIRED',status['blocking_reasons'])
    def test_public_nested_allowlist(self):
        data=public_capabilities(now=self.now);sanitize_public_payload(data)
        data['sources'][0]['private_note']='secret'
        with self.assertRaisesRegex(Hold,'PUBLIC_CAPABILITIES_CONTRACT'):sanitize_public_payload(data)
