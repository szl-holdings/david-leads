# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import csv
import io
import sys
import unittest
import zipfile
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import benefit_frontier, dealdesk  # noqa: E402


def _archive(filename: str, fieldnames: list[str], rows: list[dict[str, str]]) -> bytes:
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, csv_buffer.getvalue())
    return output.getvalue()


class Form5500BenefitFrontierTests(unittest.TestCase):
    def setUp(self):
        benefit_frontier._FILE_CACHE.clear()

    def tearDown(self):
        benefit_frontier._FILE_CACHE.clear()

    def test_joins_plan_and_schedule_without_person_or_ein_fields(self):
        ack_id = "20990225154215NAL0002291731001"
        main = _archive(
            "f_5500_2099_latest.csv",
            [
                "ACK_ID",
                "PLAN_NAME",
                "SPONSOR_DFE_NAME",
                "SPONS_DFE_LOC_US_CITY",
                "SPONS_DFE_LOC_US_STATE",
                "SPONS_DFE_LOC_US_ZIP",
                "TOT_ACTIVE_PARTCP_CNT",
                "TOT_PARTCP_BOY_CNT",
                "SCH_A_ATTACHED_IND",
                "FILING_STATUS",
                "DATE_RECEIVED",
                "SPONS_DFE_EIN",
                "ADMIN_NAME",
                "SPONS_SIGNED_NAME",
                "SPONS_DFE_PHONE_NUM",
            ],
            [{
                "ACK_ID": ack_id,
                "PLAN_NAME": "EXAMPLE MANUFACTURING BENEFITS (EIN 12-3456789)",
                "SPONSOR_DFE_NAME": "EXAMPLE MANUFACTURING LLC (EIN 12-3456789)",
                "SPONS_DFE_LOC_US_CITY": "ALBANY",
                "SPONS_DFE_LOC_US_STATE": "NY",
                "SPONS_DFE_LOC_US_ZIP": "12207-1000",
                "TOT_ACTIVE_PARTCP_CNT": "325",
                "TOT_PARTCP_BOY_CNT": "310",
                "SCH_A_ATTACHED_IND": "1",
                "FILING_STATUS": "FILING_RECEIVED",
                "DATE_RECEIVED": "2099-03-01",
                "SPONS_DFE_EIN": "12-3456789",
                "ADMIN_NAME": "PRIVATE PERSON",
                "SPONS_SIGNED_NAME": "PRIVATE SIGNER",
                "SPONS_DFE_PHONE_NUM": "5550100",
            }],
        )
        schedule = _archive(
            "F_SCH_A_2099_latest.csv",
            [
                "ACK_ID",
                "SCH_A_PLAN_YEAR_END_DATE",
                "INS_POLICY_TO_DATE",
                "INS_CARRIER_NAME",
                "WLFR_BNFT_HEALTH_IND",
                "WLFR_BNFT_DENTAL_IND",
                "WLFR_BNFT_VISION_IND",
                "WLFR_BNFT_LIFE_INSUR_IND",
                "BROKER_NAME",
                "BROKER_COMM_TOT_AMT",
            ],
            [{
                "ACK_ID": ack_id,
                "SCH_A_PLAN_YEAR_END_DATE": "2099-12-31",
                "INS_POLICY_TO_DATE": "2099-12-31",
                "INS_CARRIER_NAME": "EXAMPLE INSURANCE COMPANY",
                "WLFR_BNFT_HEALTH_IND": "1",
                "WLFR_BNFT_DENTAL_IND": "1",
                "WLFR_BNFT_VISION_IND": "0",
                "WLFR_BNFT_LIFE_INSUR_IND": "1",
                "BROKER_NAME": "PRIVATE BROKER",
                "BROKER_COMM_TOT_AMT": "999999",
            }],
        )

        def loader(url: str) -> bytes:
            return schedule if "SCH_A" in url else main

        result = benefit_frontier.collect(
            ["NY"],
            5,
            loader=loader,
            today=date(2099, 7, 30),
            year=2099,
        )

        self.assertEqual(result["mode"], "LIVE")
        self.assertEqual(result["count"], 1)
        record = result["records"][0]
        self.assertEqual(record["name"], "EXAMPLE MANUFACTURING LLC")
        self.assertEqual(record["state"], "NY")
        self.assertEqual(record["zip"], "12207")
        self.assertEqual(record["timing"]["days_to_anniversary"], 154)
        self.assertTrue(record["timing"]["hypothesis_only"])
        self.assertEqual(
            record["product_fit"],
            [
                "Life insurance review",
                "Business protection research",
                "Executive benefits research",
            ],
        )
        self.assertEqual(
            record["operational_snapshot"]["participants_reported"],
            325,
        )
        serialized = str(record).lower()
        for forbidden in (
            "12-3456789",
            "private person",
            "private signer",
            "private broker",
            "5550100",
            "999999",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertIn("not proof of a renewal", record["why"].lower())

    def test_public_projection_keeps_timing_and_fit_but_never_contact_data(self):
        board = dealdesk.public_board([{
            "name": "EXAMPLE LLC",
            "state": "PA",
            "credential": "DOL filing test",
            "license_or_issue_date": "2099-03-01",
            "citation": {"label": "DOL", "url": benefit_frontier.PORTAL},
            "contact_quality": "organization location (public)",
            "type": "benefit_plan",
            "timing": {
                "label": "91-180 days",
                "next_anniversary": "2099-12-31",
                "days_to_anniversary": 154,
                "hypothesis_only": True,
            },
            "product_fit": ["Medical", "Dental"],
            "evidence": {"strength": "DIRECT_FILING", "source_count": 1},
            "phone": "5550100",
            "email": "private@example.test",
        }])
        item = board["opportunities"][0]
        self.assertEqual(item["timing"]["days_to_anniversary"], 154)
        self.assertEqual(item["product_fit"], ["Medical", "Dental"])
        self.assertEqual(item["evidence"]["strength"], "DIRECT_FILING")
        self.assertFalse(item["call_ready"])
        self.assertNotIn("phone", item)
        self.assertNotIn("email", item)


if __name__ == "__main__":
    unittest.main()
