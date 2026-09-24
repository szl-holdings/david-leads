"""Offline synthetic-only acceptance examples for the SZL reference kernel."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "domain"))

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from david_reference import (
    ClearanceFacts, Grant, Hold, Identifier, Ledger, Observation, Verdict,
    aware, canonical, clearance_decision, digest, inventory_plan, minimize,
    name_candidate, relationship, research_priority,
)

NOW = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def grant(**changes):
    base = Grant("synthetic-source", "review-v1", "test-review-only",
                 NOW + 30 * DAY,
                 {"collect": Verdict.ALLOW, "research": Verdict.ALLOW,
                  "public_display": Verdict.REVIEW, "redistribute": Verdict.DENY,
                  "train": Verdict.DENY},
                 frozenset({"organization_name", "state", "participant_count"}))
    return replace(base, **changes)


class PolicyTests(unittest.TestCase):
    def test_research_allowed(self):
        grant().require("research", NOW)

    def test_public_display_not_inferred(self):
        with self.assertRaises(Hold): grant().require("public_display", NOW)

    def test_training_not_inferred(self):
        with self.assertRaises(Hold): grant().require("train", NOW)

    def test_unknown_operation_denied(self):
        with self.assertRaises(Hold): grant().require("send_email", NOW)

    def test_expired_review_denied(self):
        with self.assertRaises(Hold): grant(expires_at=NOW).require("research", NOW)

    def test_missing_review_denied(self):
        with self.assertRaises(Hold): grant(review_reference="").require("research", NOW)

    def test_prohibited_field_policy_denied(self):
        with self.assertRaises(Hold):
            grant(allowed_fields=frozenset({"email"})).require("research", NOW)

    def test_projection_drops_unselected_private_fields(self):
        data = {"organization_name": "SYNTHETIC TEST LLC", "email": "not-a-real-contact",
                "officer_name": "SYNTHETIC PERSON", "state": "NY"}
        out = minimize(data, grant(), "research", NOW,
                       organization_admission="VERIFIED_LEGAL_ORGANIZATION")
        self.assertEqual(set(out), {"organization_name", "state"})
        self.assertNotIn("email", canonical(out))

    def test_person_or_unknown_entity_denied(self):
        with self.assertRaises(Hold):
            minimize({"state": "NY"}, grant(), "research", NOW,
                     organization_admission="UNKNOWN")

    def test_nested_value_denied(self):
        with self.assertRaises(Hold):
            minimize({"state": {"email": "hidden"}}, grant(), "research", NOW,
                     organization_admission="VERIFIED_LEGAL_ORGANIZATION")

    def test_nan_denied(self):
        with self.assertRaises(Hold):
            minimize({"participant_count": float("nan")}, grant(), "research", NOW,
                     organization_admission="VERIFIED_LEGAL_ORGANIZATION")

    def test_naive_timestamp_denied(self):
        with self.assertRaises(Hold): aware(datetime(2026, 9, 11))


class IdentityTests(unittest.TestCase):
    def test_cik_normalizes_zero_padding(self):
        a = Identifier("organization", "SEC_CIK", "US", "123")
        b = Identifier("organization", "SEC_CIK", "US", "0000000123")
        self.assertEqual(relationship([a], [b]), "SAME_ORGANIZATION_ID")

    def test_same_name_is_candidate_only(self):
        self.assertEqual(relationship([], [], same_name_state_postal=True), "CANDIDATE_REVIEW")

    def test_facility_not_organization(self):
        a = Identifier("facility", "EPA_FRS", "US", "123456789012")
        self.assertEqual(relationship([a], [a]), "SAME_NON_ORGANIZATION_RECORD")

    def test_parcel_scoped_to_jurisdiction(self):
        a = Identifier("parcel", "PARCEL", "US-NY-NYC", "123")
        b = Identifier("parcel", "PARCEL", "US-NJ-ESSEX", "123")
        self.assertEqual(relationship([a], [b]), "UNRESOLVED")

    def test_conflicting_id_beats_other_shared_id(self):
        uei = Identifier("organization", "UEI", "US", "ABC123DEF456")
        a = Identifier("organization", "SEC_CIK", "US", "123")
        b = Identifier("organization", "SEC_CIK", "US", "124")
        self.assertEqual(relationship([uei, a], [uei, b]), "CONFLICT_REVIEW")

    def test_identifier_type_mismatch_denied(self):
        with self.assertRaises(Hold): Identifier("organization", "EPA_FRS", "US", "123").key()

    def test_name_normalization_is_not_an_identity_assertion(self):
        self.assertEqual(name_candidate("Synthetic Test, LLC", "NY", "10001"),
                         ("synthetictestllc", "NY", "10001"))


class ObservationTests(unittest.TestCase):
    def item(self, **changes):
        obj = Observation("synthetic-source", "fixture-1", "r1", NOW-DAY, NOW,
                          NOW+DAY, {"state": "NY"})
        return replace(obj, **changes)

    def test_normalized_record_binds_policy(self):
        obj = self.item().body(grant(), NOW)
        self.assertEqual(obj["policy_revision"], "review-v1")
        self.assertTrue(obj["not_for_underwriting"])

    def test_future_observation_denied(self):
        with self.assertRaises(Hold): self.item(observed_at=NOW+DAY).body(grant(), NOW)

    def test_publication_after_observation_denied(self):
        with self.assertRaises(Hold): self.item(published_at=NOW+DAY).body(grant(), NOW)

    def test_unapproved_normalized_fields_denied(self):
        with self.assertRaises(Hold): self.item(fields={"email": "hidden"}).body(grant(), NOW)

    def test_expiry_cannot_outlive_review(self):
        with self.assertRaises(Hold): self.item(expires_at=NOW+31*DAY).body(grant(), NOW)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "reference.sqlite3"
        self.ledger = Ledger(self.path)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def add(self, kind="source", parents=(), body=None, tenant="test-tenant", expiry=None):
        return self.ledger.append(tenant, kind, body or {"synthetic": True}, parents,
                                  expiry or NOW+DAY, NOW)

    def test_idempotent_ingestion(self):
        self.assertEqual(self.add(), self.add())
        self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 1)

    def test_restart_preserves_evidence(self):
        node = self.add()
        self.ledger.close()
        self.ledger = Ledger(self.path)
        self.assertEqual(self.ledger.state("test-tenant", node, NOW), "VALID")
        self.assertTrue(self.ledger.verify("test-tenant", node))

    def test_cross_tenant_dependency_denied(self):
        node = self.add()
        with self.assertRaises(Hold): self.add("brief", (node,), tenant="other-tenant")
        self.assertEqual(self.ledger.state("other-tenant", node, NOW), "MISSING")

    def test_unknown_dependency_rolls_back(self):
        with self.assertRaises(Hold): self.add("brief", ("missing",))
        self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 0)

    def test_retraction_invalidates_full_derivation(self):
        source = self.add()
        identity = self.add("identity", (source,))
        score = self.add("score", (identity,))
        brief = self.add("brief", (score,))
        clearance = self.add("clearance", (brief,))
        self.assertEqual(self.ledger.revoke("test-tenant", source, "SOURCE_CORRECTED", NOW), 5)
        for node in (source, identity, score, brief, clearance):
            self.assertEqual(self.ledger.state("test-tenant", node, NOW), "REVOKED")
        self.assertEqual(self.ledger.revoke("test-tenant", source, "RETRY", NOW), 0)

    def test_corrected_revision_new_node_not_overwrite(self):
        old = self.add(body={"synthetic": True, "revision": "r1"})
        self.ledger.revoke("test-tenant", old, "SOURCE_CORRECTED", NOW)
        new = self.add(body={"synthetic": True, "revision": "r2"})
        self.assertNotEqual(old, new)
        self.assertEqual(self.ledger.state("test-tenant", new, NOW), "VALID")

    def test_idempotent_retry_cannot_revive(self):
        node = self.add()
        self.ledger.revoke("test-tenant", node, "REVOKED", NOW)
        with self.assertRaises(Hold): self.add()

    def test_expiration_blocks_derived_action(self):
        parent = self.add()
        child = self.add("brief", (parent,))
        self.assertEqual(self.ledger.state("test-tenant", child, NOW+DAY), "STALE")

    def test_child_cannot_outlive_parent(self):
        parent = self.add()
        with self.assertRaises(Hold): self.add("brief", (parent,), expiry=NOW+2*DAY)

    def test_tampered_content_fails_integrity(self):
        node = self.add()
        self.ledger.db.execute("UPDATE nodes SET envelope=? WHERE id=?", ('{}', node))
        self.assertFalse(self.ledger.verify("test-tenant", node))
        self.assertEqual(self.ledger.state("test-tenant", node, NOW), "INTEGRITY_FAILED")

    def test_tampered_edges_fail_integrity(self):
        source = self.add()
        child = self.add("brief", (source,))
        self.ledger.db.execute("DELETE FROM edges WHERE child=?", (child,))
        self.assertFalse(self.ledger.verify("test-tenant", child))

    def test_unsigned_status_not_confused_with_signature(self):
        node = self.add()
        row = self.ledger.db.execute("SELECT envelope FROM nodes WHERE id=?", (node,)).fetchone()
        self.assertEqual(json.loads(row[0])["integrity"], "LOCAL_SHA256_UNSIGNED")


class ActionAndInventoryTests(unittest.TestCase):
    def facts(self, **changes):
        obj = ClearanceFacts("synthetic-operator", True, True, True, True, True, True, True,
                             NOW, NOW+timedelta(hours=1), "policy-v1", "talk-track-v1")
        return replace(obj, **changes)

    def test_clearance_requires_all_gates(self):
        for field in ("business_channel_verified", "license_scope_passed", "jurisdiction_passed",
                      "suppression_passed", "purpose_passed", "policy_passed", "human_approved"):
            with self.subTest(field=field):
                self.assertFalse(clearance_decision(self.facts(**{field: False}), NOW, True)[0])

    def test_clearance_pass_is_not_an_actual_message_send(self):
        self.assertTrue(clearance_decision(self.facts(), NOW, True)[0])

    def test_clearance_revoked_dependency_fails(self):
        self.assertFalse(clearance_decision(self.facts(), NOW, False)[0])

    def test_clearance_expired_fails(self):
        self.assertFalse(clearance_decision(self.facts(expires_at=NOW), NOW, True)[0])

    def test_clearance_lifetime_over_24h_fails(self):
        self.assertFalse(clearance_decision(self.facts(expires_at=NOW+2*DAY), NOW, True)[0])

    def test_score_is_not_probability_or_contact_permission(self):
        result = research_priority(.8, .7, 2, evidence_valid=True,
                                   identity_verified=True, contradiction_unresolved=False)
        self.assertEqual(result["priority"], 79.0)
        self.assertIsNone(result["conversion_probability"])
        self.assertEqual(result["contact_permission"], "NOT_EVALUATED")

    def test_score_abstains_on_identity_or_counterevidence(self):
        for identity, contradiction in ((False, False), (True, True)):
            self.assertIsNone(research_priority(.8, .7, 2, evidence_valid=True,
                               identity_verified=identity,
                               contradiction_unresolved=contradiction)["priority"])

    def test_inventory_does_not_assert_running(self):
        snap = {"org": "SZLHOLDINGS", "observedAt": "2026-09-10T03:20:41Z",
                "counts": {"spaces": 1}, "inventory": {"spaces": [
                    {"id": "SZLHOLDINGS/terra", "license": "apache-2.0"}]}}
        out = inventory_plan(snap)
        self.assertIn("PUBLICATION_GUARDRAIL_REVIEW", out["plan"][0]["required"])
        self.assertEqual(out["plan"][0]["runtime"], "NOT_OBSERVED_BY_THIS_TOOL")

    def test_inventory_duplicate_rejected(self):
        row = {"id": "SZLHOLDINGS/terra"}
        with self.assertRaises(Hold):
            inventory_plan({"org": "SZLHOLDINGS", "observedAt": "2026-09-11T00:00:00Z",
                            "inventory": {"spaces": [row, row]}})

    def test_inventory_count_mismatch_rejected(self):
        with self.assertRaises(Hold):
            inventory_plan({"org": "SZLHOLDINGS", "observedAt": "2026-09-11T00:00:00Z",
                            "counts": {"spaces": 2}, "inventory": {"spaces": []}})

    def test_digest_is_key_order_stable(self):
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
