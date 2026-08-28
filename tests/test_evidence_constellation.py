from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app import evidence_constellation as constellation


NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)


def record(**overrides):
    base = {
        "name": "Acme Industrial, Inc.",
        "state": "NY",
        "zip": "10001-1200",
        "source_frontier": "FEDERAL_CONTRACT",
        "source_class": "OFFICIAL_PUBLIC_API",
        "source_record_id": "record-1",
        "trigger_date": "2026-08-20",
        "citation": {"url": "https://example.gov/record"},
        "authoritative_entity_ids": [{"system": "UEI", "value": "ABC-123-DEF-456"}],
        "normalized_record_sha256": "a" * 64,
        "parser_version": "frontier-sources/1.2",
        "receipt_id": "receipt-1",
        "receipt_state": "SIGNED",
        "receipt_signed": True,
        "product_fit": ["Business protection research"],
        "limitations": ["The event may not reflect current operating conditions."],
    }
    base.update(overrides)
    return base


class EvidenceConstellationTests(unittest.TestCase):
    def test_shared_uei_creates_deterministic_multi_source_entity(self):
        records = [
            record(),
            record(
                source_frontier="SAM_ENTITY",
                source_record_id="record-2",
                authoritative_entity_ids=[{"system": "SAM UEI", "value": "ABC123DEF456"}],
                receipt_id="receipt-2",
            ),
        ]
        annotated, summary = constellation.annotate_constellation(records, now=NOW)

        self.assertEqual(summary["multi_source_entities"], 1)
        self.assertEqual(summary["resolution_counts"], {"DETERMINISTIC_IDENTIFIER": 1})
        self.assertEqual(annotated[0]["entity_resolution"]["status"], "DETERMINISTIC_IDENTIFIER")
        self.assertFalse(annotated[0]["entity_resolution"]["review_required"])
        self.assertEqual(annotated[0]["evidence_constellation"]["proof"]["grade"], "A")

    def test_shared_identifier_group_id_is_stable_as_events_are_added(self):
        first = record()
        second = record(
            source_frontier="SAM_ENTITY",
            source_record_id="record-2",
            receipt_id="receipt-2",
            authoritative_entity_ids=[{"system": "SAM UEI", "value": "ABC123DEF456"}],
        )

        one, _ = constellation.annotate_constellation([first], now=NOW)
        two, _ = constellation.annotate_constellation([first, second], now=NOW)

        self.assertEqual(
            one[0]["entity_resolution"]["group_id"],
            two[0]["entity_resolution"]["group_id"],
        )
        self.assertEqual(
            two[0]["entity_resolution"]["status"],
            "DETERMINISTIC_IDENTIFIER",
        )

    def test_exact_name_state_zip_candidate_stays_review_required(self):
        records = [
            record(authoritative_entity_ids=[], source_frontier="FMCSA"),
            record(
                authoritative_entity_ids=[],
                source_frontier="EPA_ECHO",
                source_record_id="record-2",
                name="ACME INDUSTRIAL LLC",
            ),
        ]
        annotated, summary = constellation.annotate_constellation(records, now=NOW)

        self.assertEqual(summary["multi_source_entities"], 1)
        self.assertEqual(summary["review_required_groups"], 1)
        resolution = annotated[0]["entity_resolution"]
        self.assertEqual(resolution["status"], "EXACT_NAME_STATE_ZIP_CANDIDATE")
        self.assertTrue(resolution["review_required"])
        self.assertIn("human review", " ".join(annotated[0]["evidence_constellation"]["counter_evidence"]))

    def test_exact_candidate_cannot_inherit_deterministic_status_from_another_pair(self):
        records = [
            record(source_frontier="FEDERAL_CONTRACT"),
            record(
                source_frontier="SAM_ENTITY",
                source_record_id="record-2",
                receipt_id="receipt-2",
            ),
            record(
                source_frontier="EPA_ECHO",
                source_record_id="record-3",
                receipt_id="receipt-3",
                authoritative_entity_ids=[],
            ),
        ]

        annotated, summary = constellation.annotate_constellation(records, now=NOW)

        self.assertEqual(
            annotated[0]["entity_resolution"]["status"],
            "MIXED_IDENTIFIER_AND_EXACT_CANDIDATE",
        )
        self.assertTrue(annotated[0]["entity_resolution"]["review_required"])
        self.assertEqual(summary["review_required_groups"], 1)
        self.assertNotEqual(annotated[0]["evidence_constellation"]["proof"]["grade"], "A")

    def test_unknown_identifier_system_never_creates_authoritative_link(self):
        annotated, summary = constellation.annotate_constellation([
            record(
                name="North Company",
                zip="10001",
                authoritative_entity_ids=[{"system": "LOCAL CRM ID", "value": "42"}],
            ),
            record(
                name="South Company",
                zip="10002",
                source_frontier="EPA_ECHO",
                source_record_id="record-2",
                receipt_id="receipt-2",
                authoritative_entity_ids=[{"system": "LOCAL CRM ID", "value": "42"}],
            ),
        ], now=NOW)

        self.assertEqual(summary["entity_groups"], 2)
        self.assertEqual(summary["multi_source_entities"], 0)
        self.assertTrue(all(
            item["entity_resolution"]["status"] == "UNRESOLVED"
            for item in annotated
        ))

    def test_malformed_allowlisted_identifier_never_creates_authoritative_link(self):
        annotated, summary = constellation.annotate_constellation([
            record(
                name="North Company",
                zip="10001",
                authoritative_entity_ids=[{"system": "UEI", "value": "N/A"}],
            ),
            record(
                name="South Company",
                zip="10002",
                source_frontier="EPA_ECHO",
                source_record_id="record-2",
                receipt_id="receipt-2",
                authoritative_entity_ids=[{"system": "UEI", "value": "N/A"}],
            ),
        ], now=NOW)

        self.assertEqual(summary["entity_groups"], 2)
        self.assertEqual(summary["multi_source_entities"], 0)
        self.assertTrue(all(
            item["entity_resolution"]["status"] == "UNRESOLVED"
            for item in annotated
        ))

    def test_unresolved_records_receive_distinct_provenance_bound_group_ids(self):
        annotated, summary = constellation.annotate_constellation([
            record(
                name="Tiny Co",
                zip="",
                source_record_id="record-1",
                authoritative_entity_ids=[],
                normalized_record_sha256="a" * 64,
                receipt_id="receipt-1",
            ),
            record(
                name="Tiny Co",
                zip="",
                source_record_id="record-2",
                authoritative_entity_ids=[],
                normalized_record_sha256="b" * 64,
                receipt_id="receipt-2",
            ),
        ], now=NOW)

        self.assertEqual(summary["entity_groups"], 2)
        self.assertNotEqual(
            annotated[0]["entity_resolution"]["group_id"],
            annotated[1]["entity_resolution"]["group_id"],
        )

    def test_same_source_candidate_keys_do_not_collide_as_group_ids(self):
        annotated, summary = constellation.annotate_constellation([
            record(
                authoritative_entity_ids=[],
                source_record_id="record-1",
                receipt_id="receipt-1",
            ),
            record(
                authoritative_entity_ids=[],
                source_record_id="record-2",
                receipt_id="receipt-2",
            ),
        ], now=NOW)

        self.assertEqual(summary["entity_groups"], 2)
        self.assertEqual(summary["multi_source_entities"], 0)
        self.assertNotEqual(
            annotated[0]["entity_resolution"]["group_id"],
            annotated[1]["entity_resolution"]["group_id"],
        )

    def test_same_name_different_zip_is_not_linked(self):
        annotated, summary = constellation.annotate_constellation([
            record(authoritative_entity_ids=[], source_frontier="FMCSA", zip="10001"),
            record(
                authoritative_entity_ids=[],
                source_frontier="EPA_ECHO",
                source_record_id="record-2",
                zip="12207",
            ),
        ], now=NOW)

        self.assertEqual(summary["multi_source_entities"], 0)
        self.assertNotEqual(
            annotated[0]["entity_resolution"]["group_id"],
            annotated[1]["entity_resolution"]["group_id"],
        )

    def test_stale_event_is_grade_d_and_requires_recheck(self):
        annotated, summary = constellation.annotate_constellation([
            record(source_frontier="FEDERAL_CONTRACT", trigger_date="2026-01-01")
        ], now=NOW)
        evidence = annotated[0]["evidence_constellation"]

        self.assertEqual(evidence["deal_clock"]["state"], "STALE")
        self.assertEqual(evidence["proof"]["grade"], "D")
        self.assertEqual(summary["deal_clock"]["STALE"], 1)

    def test_form5500_clock_says_anniversary_hypothesis(self):
        annotated, _ = constellation.annotate_constellation([
            record(
                source_frontier="BENEFIT_PLAN_TIMING",
                timing={"next_anniversary": "2026-10-01", "hypothesis_only": True},
            )
        ], now=NOW)
        clock = annotated[0]["evidence_constellation"]["deal_clock"]

        self.assertEqual(clock["state"], "RECHECK_DUE")
        self.assertIn("hypothesis", clock["basis"])
        self.assertNotIn("renewal", clock["basis"].lower())

    def test_form5500_recheck_deadline_is_stable_and_can_become_due(self):
        item = record(
            source_frontier="BENEFIT_PLAN_TIMING",
            timing={"next_anniversary": "2026-12-31", "hypothesis_only": True},
        )
        early, _ = constellation.annotate_constellation(
            [item], now=datetime(2026, 8, 1, tzinfo=timezone.utc)
        )
        due, _ = constellation.annotate_constellation(
            [item], now=datetime(2026, 10, 15, tzinfo=timezone.utc)
        )

        early_clock = early[0]["evidence_constellation"]["deal_clock"]
        due_clock = due[0]["evidence_constellation"]["deal_clock"]
        self.assertEqual(early_clock["recheck_at"], due_clock["recheck_at"])
        self.assertEqual(early_clock["state"], "CURRENT")
        self.assertEqual(due_clock["state"], "RECHECK_DUE")

    def test_proof_reference_is_session_verifiable_but_never_contact_permission(self):
        annotated, summary = constellation.annotate_constellation([record()], now=NOW)
        evidence = annotated[0]["evidence_constellation"]

        self.assertEqual(
            evidence["proof_packet"]["state"],
            "SESSION_VERIFIABLE_REFERENCE",
        )
        self.assertEqual(evidence["proof_packet"]["durability"], "PROCESS_MEMORY")
        self.assertFalse(evidence["proof_packet"]["historical_replay"])
        self.assertEqual(
            evidence["proof"]["dimensions"]["integrity"],
            "SIGNED_SOURCE_RECEIPT",
        )
        self.assertEqual(evidence["decision_dimensions"]["permission"], "PUBLIC_RESEARCH_ONLY")
        self.assertTrue(evidence["proof"]["not_a_sales_probability"])
        self.assertEqual(summary["session_verifiable_references"], 1)
        self.assertEqual(summary["signed_source_receipts"], 1)
        self.assertEqual(summary["proof_reference_durability"], "PROCESS_MEMORY")
        self.assertFalse(summary["historical_replay"])

    def test_incoherent_signed_receipt_claims_fail_closed(self):
        cases = (
            {"receipt_id": None, "receipt_signed": False},
            {"receipt_id": None, "receipt_signed": True},
            {"receipt_id": "receipt-1", "receipt_signed": False},
            {"receipt_id": "receipt-1", "receipt_signed": True, "normalized_record_sha256": "short"},
            {"receipt_id": "receipt-1", "receipt_signed": True, "receipt_state": "UNSIGNED"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                annotated, summary = constellation.annotate_constellation(
                    [record(**overrides)], now=NOW
                )
                evidence = annotated[0]["evidence_constellation"]
                self.assertNotEqual(
                    evidence["proof"]["dimensions"]["integrity"],
                    "SIGNED_SOURCE_RECEIPT",
                )
                self.assertEqual(evidence["proof_packet"]["state"], "PARTIAL")
                self.assertEqual(summary["signed_source_receipts"], 0)
                self.assertEqual(summary["session_verifiable_references"], 0)


if __name__ == "__main__":
    unittest.main()
