# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import dealdesk, frontier_sources, receipts  # noqa: E402


class FmcsaFrontierSafety(unittest.TestCase):
    def setUp(self):
        receipts.reset_chain()

    def test_query_excludes_contact_safety_and_insurance_fields(self):
        captured = {}

        def fake_request(url, payload=None):
            captured["url"] = url
            self.assertIsNone(payload)
            return [{
                "legal_name": "EXAMPLE FREIGHT LLC",
                "dba_name": "EXAMPLE FREIGHT",
                "dot_number": "1234567",
                "add_date": "20260727",
                "status_code": "A",
                "classdef": "AUTHORIZED FOR HIRE",
                "power_units": "4",
                "truck_units": "3",
                "bus_units": "0",
                "total_drivers": "5",
                "phy_street": "10 BUSINESS RD",
                "phy_city": "ALBANY",
                "phy_state": "NY",
                "phy_zip": "12207-0001",
                # The adapter must ignore these even if a test response includes them.
                "phone": "5550100",
                "email_address": "private@example.test",
                "company_officer_1": "PERSON NAME",
                "safety_rating": "NOT RATED",
                "insurance_field": "SHOULD NOT FLOW",
            }]

        with mock.patch.object(frontier_sources, "_request_json", side_effect=fake_request):
            result = frontier_sources.fetch_fmcsa(["NY"], limit=4)

        query = urllib.parse.parse_qs(urllib.parse.urlparse(captured["url"]).query)
        selected = query["$select"][0].split(",")
        for forbidden in (
            "phone",
            "email_address",
            "company_officer_1",
            "recordable_crash_rate",
            "safety_rating",
            "insurance_field",
        ):
            self.assertNotIn(forbidden, selected)

        record = result["records"][0]
        for forbidden in (
            "phone",
            "email_address",
            "company_officer_1",
            "safety_rating",
            "insurance_field",
        ):
            self.assertNotIn(forbidden, record)
        self.assertEqual(record["credential"], "USDOT 1234567")
        self.assertEqual(record["contact_quality"], "business address (public)")
        self.assertTrue(record["not_for_underwriting"])
        self.assertEqual(record["purpose"], "PROSPECTING_ONLY")


class UsaSpendingFrontierSafety(unittest.TestCase):
    def setUp(self):
        receipts.reset_chain()

    def test_contract_activity_is_not_labeled_a_new_award(self):
        captured = {}

        def fake_request(url, payload=None):
            captured["url"] = url
            captured["payload"] = payload
            return {
                "results": [{
                    "Award ID": "TEST-AWARD-1",
                    "Recipient Name": "EXAMPLE TECHNOLOGY LLC",
                    "Recipient UEI": "EXAMPLEUEI12",
                    "Recipient Location": {
                        "state_code": "NY",
                        "city_name": "SYRACUSE",
                        "address_line1": "20 BUSINESS AVE",
                        "zip5": "13202",
                    },
                    "Start Date": "2025-01-01",
                    "End Date": "2027-01-01",
                    "Award Amount": 125000,
                    "Awarding Agency": "Example Federal Agency",
                    "Description": "Example contract action",
                    "generated_internal_id": "CONT_AWD_TEST_0001",
                }],
            }

        with mock.patch.object(frontier_sources, "_request_json", side_effect=fake_request):
            result = frontier_sources.fetch_usaspending(["NY"], limit=3)

        self.assertEqual(captured["url"], frontier_sources.USASPENDING["api"])
        self.assertIn("Recipient Location", captured["payload"]["fields"])
        self.assertNotIn("Recipient Phone", captured["payload"]["fields"])
        record = result["records"][0]
        self.assertEqual(record["status"], "ACTIVITY_WINDOW_OBSERVED")
        self.assertNotIn("new contract", record["observed_trigger"].lower())
        self.assertIn("modification", " ".join(record["limitations"]).lower())
        self.assertEqual(record["award"]["amount"], 125000.0)
        self.assertTrue(record["not_for_underwriting"])

    def test_government_recipients_are_not_returned_as_broker_entities(self):
        response = {
            "results": [{
                "Award ID": "GOV-1",
                "Recipient Name": "CITY OF EXAMPLE",
                "Recipient Location": {
                    "state_code": "NY",
                    "city_name": "EXAMPLE",
                    "address_line1": "1 CITY HALL",
                    "zip5": "10001",
                },
                "Award Amount": 100000,
                "Awarding Agency": "Agency",
                "generated_internal_id": "CONT_AWD_GOV_1",
            }],
        }
        with mock.patch.object(frontier_sources, "_request_json", return_value=response):
            result = frontier_sources.fetch_usaspending(["NY"], limit=3)
        self.assertEqual(result["records"], [])


class FrontierAggregationSafety(unittest.TestCase):
    def setUp(self):
        dealdesk.reset_for_tests()

    def tearDown(self):
        dealdesk.reset_for_tests()

    def test_source_failure_never_creates_sample_records(self):
        live = {
            "source": "USAspending federal contract activity",
            "source_id": "usaspending-contract-activity",
            "mode": "LIVE",
            "count": 0,
            "records": [],
            "citation": {"label": "USAspending", "url": "https://api.usaspending.gov"},
            "privacy": "ENTITY_FIELDS_ONLY",
        }
        with (
            mock.patch.object(frontier_sources, "fetch_fmcsa", side_effect=TimeoutError),
            mock.patch.object(frontier_sources, "fetch_usaspending", return_value=live),
        ):
            result = frontier_sources.frontier_opportunities(["NY"])
        self.assertEqual(result["leads"], [])
        self.assertEqual(result["sources"][0]["mode"], "UNAVAILABLE")
        self.assertNotIn("SAMPLE", str(result))


if __name__ == "__main__":
    unittest.main(verbosity=2)
