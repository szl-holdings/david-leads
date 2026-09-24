# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
import sys
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import dealdesk, frontier_sources, receipts  # noqa: E402


class TerritoryNormalization(unittest.TestCase):
    def test_all_eastern_markets_reach_the_source_adapters(self):
        eastern = [
            "AL", "CT", "DC", "DE", "FL", "GA", "IL", "IN", "KY", "ME", "MD",
            "MA", "MI", "MS", "NH", "NJ", "NY", "NC", "OH", "PA", "RI", "SC",
            "TN", "VT", "VA", "WV", "WI",
        ]
        self.assertEqual(frontier_sources._states(eastern), eastern)

    def test_invalid_or_duplicate_state_codes_are_removed(self):
        self.assertEqual(
            frontier_sources._states(["ny", "NY", "XX", "PA", "123"]),
            ["NY", "PA"],
        )


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
                "business_org_desc": "CORPORATION",
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
            result = frontier_sources.collect_fmcsa_live(["NY"], limit=4)

        query = urllib.parse.parse_qs(urllib.parse.urlparse(captured["url"]).query)
        selected = query["$select"][0].split(",")
        for forbidden in (
            "phone",
            "email_address",
            "company_officer_1",
            "recordable_crash_rate",
            "safety_rating",
            "insurance_field",
            "phy_street",
        ):
            self.assertNotIn(forbidden, selected)

        record = result["records"][0]
        for forbidden in (
            "phone",
            "email_address",
            "company_officer_1",
            "safety_rating",
            "insurance_field",
            "address",
        ):
            self.assertNotIn(forbidden, record)
        self.assertEqual(record["credential"], "USDOT 1234567")
        self.assertEqual(record["organization_admission"], "RECOGNIZED_LEGAL_ORGANIZATION_SUFFIX")
        self.assertEqual(record["contact_quality"], "entity registry only")
        self.assertTrue(record["not_for_underwriting"])
        self.assertEqual(record["purpose"], "PROSPECTING_ONLY")

    def test_person_or_nonorganization_names_fail_closed(self):
        base = {
            "legal_name": "JANE DOE",
            "dot_number": "1234567",
            "add_date": "20260727",
            "status_code": "A",
            "classdef": "AUTHORIZED FOR HIRE",
            "power_units": "1",
            "total_drivers": "1",
            "phy_street": "10 PRIVATE RD",
            "phy_city": "ALBANY",
            "phy_state": "NY",
            "phy_zip": "12207",
        }
        for organization_type in ("INDIVIDUAL", "SOLE PROPRIETOR", "PARTNERSHIP", "", "CORPORATION"):
            with self.subTest(organization_type=organization_type):
                row = {**base, "business_org_desc": organization_type}
                with mock.patch.object(frontier_sources, "_request_json", return_value=[row]):
                    result = frontier_sources.collect_fmcsa_live(["NY"], limit=4)
                self.assertEqual(result["records"], [])
                self.assertNotIn("10 PRIVATE RD", str(result))
                self.assertNotIn("JANE DOE", str(result))
                self.assertEqual(
                    result["reason"],
                    "NO_SUFFIX_VALIDATED_ORGANIZATIONS_IN_CURRENT_WINDOW",
                )

    def test_missing_classification_with_legal_organization_suffix_is_admitted(self):
        row = {
            "legal_name": "CURRENT FREIGHT LLC",
            "dot_number": "7654321",
            "add_date": "20260825",
            "status_code": "A",
            "business_org_desc": "",
            "phy_city": "ALBANY",
            "phy_state": "NY",
            "phy_zip": "12207",
        }
        with mock.patch.object(frontier_sources, "_request_json", return_value=[row]):
            result = frontier_sources.collect_fmcsa_live(["NY"], limit=4)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["records"][0]["name"], "CURRENT FREIGHT LLC")
        self.assertNotIn("address", result["records"][0])
        self.assertIsNone(result["reason"])

    def test_parallel_frontier_collection_preserves_declared_source_order(self):
        def result(label):
            return {
                "source": label,
                "source_id": label.lower(),
                "mode": "LIVE",
                "count": 0,
                "records": [],
            }

        patches = [
            mock.patch.object(frontier_sources, name, return_value=result(label))
            for name, label in (
                ("fetch_form5500", "DOL"),
                ("fetch_fmcsa", "FMCSA"),
                ("fetch_usaspending", "USAspending"),
                ("fetch_echo", "EPA"),
            )
        ]
        held = [
            mock.patch.object(frontier_sources, name, side_effect=AssertionError("held source must not collect"))
            for name in (
                "fetch_fcc_uls",
                "fetch_chicago_licenses",
                "fetch_sam_entities",
            )
        ]
        mocks = [patcher.start() for patcher in patches + held]
        self.addCleanup(lambda: [patcher.stop() for patcher in reversed(patches + held)])
        output = frontier_sources.frontier_opportunities(["NY"], limit_per_source=2)

        self.assertEqual(
            [source["source"] for source in output["sources"]],
            [
                "DOL",
                "FMCSA",
                "USAspending",
                "EPA",
                frontier_sources.FCC["label"],
                frontier_sources.CHICAGO["label"],
                frontier_sources.SAM["label"],
            ],
        )
        self.assertEqual(output["sources"][0]["source"], "DOL")
        self.assertEqual(output["sources"][-3]["mode"], "NOT_IMPLEMENTED")
        self.assertEqual(output["sources"][-2]["mode"], "AUTH_REQUIRED")
        self.assertEqual(output["sources"][-1]["mode"], "AUTH_REQUIRED")
        self.assertTrue(all(item.call_count == 1 for item in mocks[:4]))
        self.assertTrue(all(item.call_count == 0 for item in mocks[4:]))


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
            result = frontier_sources.collect_usaspending_live(["NY"], limit=3)

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
            result = frontier_sources.collect_usaspending_live(["NY"], limit=3)
        self.assertEqual(result["records"], [])


class EchoFrontierSafety(unittest.TestCase):
    def setUp(self):
        receipts.reset_chain()
        frontier_sources._ECHO_CACHE.clear()

    def test_echo_uses_verified_bulk_snapshot_without_live_web_api(self):
        verified = {
            "records": [{
                "source_record_id": "echo:110000000001",
                "org_name": "EXAMPLE MANUFACTURING LLC",
                "city": "ALBANY",
                "state": "NY",
                "postal_code": "12207",
                "county": "ALBANY",
                "epa_region": "02",
                "last_inspection_date": "2026-09-01",
                "days_since_last_inspection": 3,
                "inspection_count": 4,
                "naics_codes": ["332710"],
                "programs": ["AIR", "RCRA"],
                "facility_report_url": (
                    "https://echo.epa.gov/detailed-facility-report?fid=110000000001"
                ),
                "normalized_record_hash": "a" * 64,
                "parser_version": "3.0.0",
                "projection_policy_sha256": "b" * 64,
                "source_receipt": "c" * 64,
            }],
            "dataset": {
                "repo_id": "SZLHOLDINGS/david-leads-data",
                "url": "https://huggingface.co/datasets/SZLHOLDINGS/david-leads-data",
                "immutable_path": "snapshots/2026-09-04/" + "d" * 64,
            },
            "snapshot": {
                "snapshot_id": "sha256:" + "d" * 64,
                "snapshot_digest": "d" * 64,
                "created_at": "2026-09-04T12:00:00Z",
                "record_count": 1,
                "records_root_sha256": "e" * 64,
                "records_file_sha256": "f" * 64,
                "parser_version": "3.0.0",
                "freshness_state": "FRESH",
                "freshness_days": 8,
            },
            "receipt": {
                "receipt_id": "123e4567-e89b-42d3-a456-426614174000",
                "payload_hash": "1" * 64,
                "state": "PAYLOAD_VERIFIED_UNSIGNED",
            },
        }

        with (
            mock.patch.object(
                frontier_sources.echo_snapshot,
                "load_verified_records",
                return_value=verified,
            ) as snapshot_reader,
            mock.patch.object(frontier_sources, "_request_json") as live_request,
        ):
            result = frontier_sources.fetch_echo(["NY"], limit=4)

        snapshot_reader.assert_called_once_with(["NY"], 4)
        live_request.assert_not_called()
        self.assertEqual(result["mode"], "LIVE")
        self.assertEqual(result["delivery"], "VERIFIED_BULK_SNAPSHOT")
        self.assertEqual(result["snapshot"]["freshness_state"], "FRESH")
        self.assertEqual(
            result["snapshot_receipt"]["state"], "PAYLOAD_VERIFIED_UNSIGNED"
        )
        record = result["records"][0]
        self.assertEqual(record["status"], "MONITORING_ACTIVITY_OBSERVED")
        self.assertTrue(record["not_for_underwriting"])
        self.assertEqual(record["contact_quality"], "entity id only")
        self.assertEqual(
            record["operational_snapshot"]["delivery"],
            "VERIFIED_BULK_SNAPSHOT",
        )
        self.assertEqual(record["source_path"], ["echo-exporter"])
        self.assertEqual(
            record["operational_snapshot"]["dataset_snapshot_created_at"],
            "2026-09-04T12:00:00Z",
        )
        self.assertEqual(
            record["operational_snapshot"]["dataset_receipt_state"],
            "PAYLOAD_VERIFIED_UNSIGNED",
        )
        self.assertNotIn("address", record)
        serialized = str(record).lower()
        self.assertNotIn("street", serialized)
        self.assertNotIn("contact name", serialized)
        self.assertNotIn("penalty amount", serialized)
        self.assertNotIn("violation observed", serialized)
        self.assertIn("not a violation", " ".join(record["limitations"]).lower())

    def test_echo_snapshot_failure_is_reported_and_never_falls_back(self):
        with (
            mock.patch.object(
                frontier_sources.echo_snapshot,
                "load_verified_records",
                side_effect=frontier_sources.echo_snapshot.EchoSnapshotUnavailable(
                    "data as of 2026-09-04, refresh pending"
                ),
            ),
            mock.patch.object(frontier_sources, "_request_json") as live_request,
        ):
            with self.assertRaisesRegex(
                frontier_sources.SourceConfigurationUnavailable,
                "ECHO_VERIFIED_SNAPSHOT_UNAVAILABLE: data as of 2026-09-04, refresh pending",
            ):
                frontier_sources.fetch_echo(["NY"], limit=4)
        live_request.assert_not_called()


class FccFrontierSafety(unittest.TestCase):
    def test_request_path_fails_closed_without_durable_ingestion(self):
        with mock.patch.object(frontier_sources, "_request_json") as request:
            with self.assertRaisesRegex(
                frontier_sources.SourceConfigurationUnavailable,
                "NOT_IMPLEMENTED",
            ):
                frontier_sources.fetch_fcc_uls(["NY"], limit=4)
        request.assert_not_called()


class ChicagoLicenseSafety(unittest.TestCase):
    def setUp(self):
        receipts.reset_chain()
        frontier_sources._CHICAGO_CACHE.clear()

    def test_only_allowlisted_organization_license_fields_flow(self):
        captured = {}

        def fake_request(url, headers):
            captured["url"] = url
            captured["headers"] = headers
            return [{
                "id": "3095829-20260728",
                "license_id": "3095829",
                "license_number": "3095001",
                "legal_name": "RISE ELECTRIC LLC",
                "doing_business_as_name": "RISE ELECTRIC",
                "address": "10 PRIVATE HOME ROAD",
                "city": "CHICAGO",
                "state": "IL",
                "zip_code": "60601",
                "license_description": "Limited Business License",
                "application_type": "ISSUE",
                "date_issued": "2026-07-28T00:00:00.000",
                "license_status": "AAI",
                "owner_name": "PRIVATE PERSON",
            }]

        with (
            mock.patch.dict(
                os.environ,
                {
                    "CHICAGO_PUBLIC_DATA_APPROVED": "1",
                    "CHICAGO_SOCRATA_APP_TOKEN": "app-token",
                },
            ),
            mock.patch.object(
                frontier_sources,
                "_request_json_headers",
                side_effect=fake_request,
            ),
        ):
            result = frontier_sources.fetch_chicago_licenses(["IL"], limit=4)

        selected = urllib.parse.parse_qs(
            urllib.parse.urlparse(captured["url"]).query
        )["$select"][0].split(",")
        self.assertNotIn("address", selected)
        self.assertNotIn("owner_name", selected)
        self.assertEqual(captured["headers"]["X-App-Token"], "app-token")
        record = result["records"][0]
        self.assertEqual(record["name"], "RISE ELECTRIC LLC")
        self.assertEqual(record["address"], "")
        self.assertRegex(record["normalized_record_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(record["source_record_id"], "3095829")
        self.assertIn(
            ("chicago_license", "3095001"),
            dealdesk._official_identifiers(record),
        )
        self.assertIn(record["receipt_state"], {"SIGNED", "HASH_CHAINED_UNSIGNED"})
        serialized = str(record).lower()
        self.assertNotIn("private person", serialized)
        self.assertNotIn("10 private home road", serialized)
        self.assertNotIn("60601", serialized)

    def test_non_illinois_territory_does_not_query_chicago(self):
        with mock.patch.object(frontier_sources, "_request_json_headers") as request:
            result = frontier_sources.fetch_chicago_licenses(["NY"], limit=4)
        request.assert_not_called()
        self.assertEqual(result["mode"], "NOT_APPLICABLE")

    def test_reuse_approval_and_app_token_are_both_required(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                frontier_sources.SourceConfigurationUnavailable,
                "CHICAGO_REUSE_APPROVAL_NOT_CONFIGURED",
            ):
                frontier_sources.fetch_chicago_licenses(["IL"], limit=4)
        with mock.patch.dict(
            os.environ,
            {"CHICAGO_PUBLIC_DATA_APPROVED": "1"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                frontier_sources.SourceConfigurationUnavailable,
                "CHICAGO_SOCRATA_APP_TOKEN_NOT_CONFIGURED",
            ):
                frontier_sources.fetch_chicago_licenses(["IL"], limit=4)


class SamEntitySafety(unittest.TestCase):
    def setUp(self):
        receipts.reset_chain()
        frontier_sources._SAM_CACHE.clear()

    def test_key_is_required_without_fabricating_records(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                frontier_sources.SourceConfigurationUnavailable,
                "SAM_GOV_API_KEY_NOT_CONFIGURED",
            ):
                frontier_sources.fetch_sam_entities(["NY"], limit=4)

    def test_request_failure_redacts_query_parameter_key(self):
        with (
            mock.patch.dict(
                os.environ,
                {"SAM_GOV_API_KEY": "never-emit-this-key"},
            ),
            mock.patch.object(
                frontier_sources,
                "_request_json",
                side_effect=RuntimeError("transport failed"),
            ),
        ):
            with self.assertRaises(
                frontier_sources.SourceConfigurationUnavailable
            ) as raised:
                frontier_sources.fetch_sam_entities(["NY"], limit=4)
        self.assertEqual(str(raised.exception), "SAM_API_REQUEST_FAILED")
        self.assertNotIn("never-emit-this-key", str(raised.exception))

    def test_only_public_post_dnb_entity_fields_are_returned(self):
        captured = {}

        def fake_request(url, payload=None):
            captured["url"] = url
            self.assertIsNone(payload)
            return {
                "entityData": [
                    {
                        "entityRegistration": {
                            "samRegistered": "Yes",
                            "ueiSAM": "EXAMPLEUEI12",
                            "legalBusinessName": "EXAMPLE FEDERAL SERVICES LLC",
                            "registrationStatus": "Active",
                            "lastUpdateDate": "2026-07-28",
                            "publicDisplayFlag": "Y",
                            "evsSource": "E&Y",
                            "dnbOpenData": None,
                            "entityTypeCode": "F",
                            "registrationExpirationDate": "2027-07-28",
                            "purposeOfRegistrationDesc": "All Awards",
                        },
                        "coreData": {
                            "physicalAddress": {
                                "addressLine1": "10 BUSINESS ROAD",
                                "city": "ALBANY",
                                "stateOrProvinceCode": "NY",
                                "zipCode": "12207",
                            },
                            "pointsOfContact": {
                                "email": "private@example.test",
                                "phone": "555-0100",
                            },
                        },
                    },
                    {
                        "entityRegistration": {
                            "samRegistered": "Yes",
                            "ueiSAM": "OLDDNBRECORD1",
                            "legalBusinessName": "OLD DNB RECORD LLC",
                            "lastUpdateDate": "2021-01-01",
                            "publicDisplayFlag": "Y",
                            "evsSource": "D&B",
                        },
                        "coreData": {
                            "physicalAddress": {
                                "city": "ALBANY",
                                "stateOrProvinceCode": "NY",
                            },
                        },
                    },
                ],
            }

        with (
            mock.patch.dict(os.environ, {"SAM_GOV_API_KEY": "secret-test-key"}),
            mock.patch.object(
                frontier_sources,
                "_request_json",
                side_effect=fake_request,
            ),
        ):
            result = frontier_sources.fetch_sam_entities(["NY"], limit=4)

        query = urllib.parse.parse_qs(urllib.parse.urlparse(captured["url"]).query)
        self.assertEqual(query["api_key"], ["secret-test-key"])
        self.assertEqual(query["page"], ["0"])
        self.assertEqual(query["size"], ["10"])
        self.assertIn("sensitivity=public", captured["url"])
        self.assertEqual(len(result["records"]), 1)
        record = result["records"][0]
        self.assertEqual(record["credential"], "UEI EXAMPLEUEI12")
        self.assertEqual(record["address"], "")
        serialized = str(record).lower()
        self.assertNotIn("private@example.test", serialized)
        self.assertNotIn("555-0100", serialized)
        self.assertNotIn("10 business road", serialized)
        self.assertNotIn("old dnb record", serialized)
        self.assertNotIn("secret-test-key", str(result))


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
            mock.patch.object(frontier_sources, "fetch_form5500", return_value={
                **live,
                "source": "DOL Form 5500",
                "source_id": "dol-form5500-benefit-timing",
            }),
            mock.patch.object(frontier_sources, "fetch_fmcsa", side_effect=TimeoutError),
            mock.patch.object(frontier_sources, "fetch_usaspending", return_value=live),
            mock.patch.object(frontier_sources, "fetch_echo", return_value={
                **live,
                "source": "EPA ECHO",
                "source_id": "epa-echo-monitoring-activity",
            }),
        ):
            result = frontier_sources.frontier_opportunities(["NY"])
        self.assertEqual(result["leads"], [])
        fmcsa = next(
            source
            for source in result["sources"]
            if source["source_id"] == "fmcsa-company-census"
        )
        self.assertEqual(fmcsa["mode"], "UNAVAILABLE")
        self.assertEqual(result["sources"][-3]["mode"], "NOT_IMPLEMENTED")
        self.assertEqual(result["sources"][-2]["mode"], "AUTH_REQUIRED")
        self.assertEqual(
            result["sources"][-1]["reason"],
            "AUTH_REQUIRED",
        )
        self.assertNotIn("SAMPLE", str(result))

    def test_triangulation_matches_only_same_state_organization_across_sources(self):
        records = [
            {
                "name": "Example Manufacturing, Inc.",
                "state": "NY",
                "source_frontier": "BENEFIT_PLAN_TIMING",
                "observed_trigger": "Life-plan anniversary",
                "citation": {"label": "DOL", "url": "https://www.dol.gov/"},
            },
            {
                "name": "EXAMPLE MANUFACTURING INC",
                "state": "NY",
                "source_frontier": "FEDERAL_CONTRACT",
                "observed_trigger": "Federal contract activity",
                "citation": {"label": "USAspending", "url": "https://www.usaspending.gov/"},
            },
            {
                "name": "Example Manufacturing Inc",
                "state": "PA",
                "source_frontier": "FMCSA",
                "observed_trigger": "Carrier registration",
                "citation": {"label": "FMCSA", "url": "https://www.fmcsa.dot.gov/"},
            },
        ]
        annotated, count = frontier_sources.triangulate(records)
        self.assertEqual(count, 1)
        self.assertEqual(annotated[0]["evidence"]["source_count"], 2)
        self.assertEqual(annotated[0]["evidence"]["triangulation_state"], "MULTI_SOURCE")
        self.assertEqual(len(annotated[0]["corroborating_signals"]), 2)
        self.assertEqual(annotated[2]["evidence"]["source_count"], 1)
        self.assertEqual(annotated[2]["evidence"]["triangulation_state"], "SINGLE_SOURCE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
