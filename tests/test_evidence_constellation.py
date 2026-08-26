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
        "authoritative_entity_ids": [{"system": "UEI", "value": "ABC-123"}],
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
                authoritative_entity_ids=[{"system": "SAM UEI", "value": "ABC123"}],
                receipt_id="receipt-2",
            ),
        ]
        annotated, summary = constellation.annotate_constellation(records, now=NOW)

        self.assertEqual(summary["multi_source_entities"], 1)
        self.assertEqual(summary["resolution_counts"], {"DETERMINISTIC_IDENTIFIER": 1})
        self.assertEqual(annotated[0]["entity_resolution"]["status"], "DETERMINISTIC_IDENTIFIER")
        self.assertFalse(annotated[0]["entity_resolution"]["review_required"])
        self.assertEqual(annotated[0]["evidence_constellation"]["proof"]["grade"], "A")

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

        self.assertEqual(clock["state"], "CURRENT")
        self.assertIn("hypothesis", clock["basis"])
        self.assertNotIn("renewal", clock["basis"].lower())

    def test_proof_packet_is_replayable_but_never_contact_permission(self):
        annotated, summary = constellation.annotate_constellation([record()], now=NOW)
        evidence = annotated[0]["evidence_constellation"]

        self.assertEqual(evidence["proof_packet"]["state"], "REPLAYABLE")
        self.assertEqual(evidence["decision_dimensions"]["permission"], "PUBLIC_RESEARCH_ONLY")
        self.assertTrue(evidence["proof"]["not_a_sales_probability"])
        self.assertEqual(summary["replayable_packets"], 1)


if __name__ == "__main__":
    unittest.main()
