import unittest
from unittest.mock import patch

from app import real_leads, tax_leads, warn_leads


def _sample_source(limit=12):
    del limit
    return {
        "source": "Official registry",
        "citation": {
            "label": "Official registry",
            "portal": "https://example.gov/registry",
        },
        "mode": "SAMPLE",
        "records": [
            {
                "type": "business",
                "name": "[SAMPLE] Example Company",
                "state": "NY",
                "city": "Albany",
                "address": "100 Main St",
                "_sample": True,
            }
        ],
    }


class NoSampleProductionModeTests(unittest.TestCase):
    def test_strict_mode_returns_unavailable_instead_of_sample_leads(self):
        with patch.object(
            real_leads,
            "_STATE_FETCHERS",
            {"NY": [("official", _sample_source)]},
        ):
            result = real_leads.real_callable_leads(
                ["NY"],
                include_samples=False,
            )

        self.assertEqual(result["leads"], [])
        self.assertEqual(result["summary"]["sample_count"], 0)
        self.assertEqual(result["sources"][0]["mode"], "UNAVAILABLE")
        self.assertEqual(result["sources"][0]["count"], 0)
        self.assertEqual(
            result["sources"][0]["reason"],
            "LIVE_SOURCE_UNAVAILABLE_NO_SAMPLE_FALLBACK",
        )

    def test_default_mode_rejects_record_level_sample_markers_even_if_block_says_live(self):
        def mislabelled_source(limit=12):
            del limit
            block = _sample_source()
            block["mode"] = "LIVE"
            return block

        with patch.object(
            real_leads,
            "_STATE_FETCHERS",
            {"NY": [("official", mislabelled_source)]},
        ):
            result = real_leads.real_callable_leads(["NY"])

        self.assertEqual(result["leads"], [])
        self.assertEqual(result["sources"][0]["mode"], "UNAVAILABLE")
        self.assertEqual(result["sources"][0]["reason"], "SAMPLE_RECORDS_REJECTED")
        self.assertEqual(result["sources"][0]["rejected_sample_records"], 1)

    def test_fetcher_exception_is_visible_as_unavailable(self):
        def broken_source(limit=12):
            del limit
            raise RuntimeError("upstream unavailable")

        with patch.object(
            real_leads,
            "_STATE_FETCHERS",
            {"NY": [("official-registry", broken_source)]},
        ):
            result = real_leads.real_callable_leads(["NY"])

        self.assertEqual(result["leads"], [])
        self.assertEqual(result["sources"], [{
            "state": "NY",
            "source": "official-registry",
            "mode": "UNAVAILABLE",
            "citation": {},
            "count": 0,
            "reason": "SOURCE_FETCH_FAILED",
        }])

    def test_warn_without_live_structured_feed_returns_no_example_employers(self):
        with patch.object(warn_leads, "_fetch_live", return_value=[]):
            result = warn_leads.warn_leads(["NY", "NJ"])

        self.assertEqual(result["leads"], [])
        self.assertEqual(result["live_states"], [])
        self.assertEqual(result["unavailable_states"], ["NY", "NJ"])
        self.assertNotIn("sample_states", result)

    def test_tax_loader_failure_returns_unavailable_and_no_synthetic_rows(self):
        tax_leads._CACHE["zip"] = None
        tax_leads._CACHE["inflow"] = None
        try:
            with patch.object(tax_leads, "_open", side_effect=OSError("offline")):
                result = tax_leads.real_tax_territories(["NY"])
        finally:
            tax_leads._CACHE["zip"] = None
            tax_leads._CACHE["inflow"] = None

        self.assertEqual(result["affluent_zips"], [])
        self.assertEqual(result["money_in_motion"], [])
        self.assertEqual([source["mode"] for source in result["sources"]], ["UNAVAILABLE", "UNAVAILABLE"])
        self.assertIsNone(result["receipt_id"])


if __name__ == "__main__":
    unittest.main()
