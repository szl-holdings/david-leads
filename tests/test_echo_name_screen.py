# SPDX-License-Identifier: Apache-2.0
"""ECHO person/residence name screen tests. Every name here is synthetic."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.echo_name_screen import (  # noqa: E402
    PRIVATE_HOUSEHOLD_NAICS,
    REJECTION_REASON,
    excluded_name_reason,
)


class EchoNameScreen(unittest.TestCase):
    def test_rejection_reason_is_the_published_accounting_key(self):
        self.assertEqual(REJECTION_REASON, "PERSON_OR_RESIDENCE_NAME")
        self.assertEqual(PRIVATE_HOUSEHOLD_NAICS, "814110")

    def test_private_household_naics_is_rejected_whatever_the_name(self):
        for name in ("FIXTURE ALPHA MANUFACTURING LLC", "FIXTURE SITE"):
            with self.subTest(name=name):
                self.assertEqual(
                    excluded_name_reason(name, ("332710", "814110")),
                    "PRIVATE_HOUSEHOLD_NAICS",
                )

    def test_residential_permit_designations_are_rejected(self):
        for token in (
            "SRSTP",
            "SFTF",
            "SFS",
            "RES",
            "RES.",
            "RESIDENCE",
            "PRIVATE RESIDENCE",
            "PROP",
            "SFR",
            "HSTS",
            "HOMEOWNER",
            "HOUSEHOLD",
            "SINGLE FAMILY DWELLING",
            "SINGLE-FAMILY",
        ):
            name = f"SAMPLE {token}"
            with self.subTest(name=name):
                self.assertEqual(excluded_name_reason(name), "RESIDENTIAL_PERMIT_NAME")

    def test_house_number_with_street_type_is_rejected(self):
        for name in (
            "100 EXAMPLE LN",
            "FIXTURE 12 N EXAMPLE RD",
            "FIXTURE 42A EXAMPLE AVE.",
            "SAMPLE PLANT 7 FIXTURE HILL ROAD",
            "FIXTURE ALPHA LLC 900 EXAMPLE PIKE",
        ):
            with self.subTest(name=name):
                self.assertEqual(excluded_name_reason(name), "STREET_ADDRESS_IN_NAME")

    def test_person_shaped_names_without_organization_word_are_rejected(self):
        for name in (
            "JANE SAMPLE",
            "jane q sample",
            "SAMPLE, JANE",
            "JOHN & JANE SAMPLE",
            "SAMPLE JOHN AND JANE",
            "JANE SAMPLE JR",
            "JOHN O'SAMPLE",
            "MARY-JANE SAMPLE",
            "JANE SAMPLE STP",
            "JANE SAMPLE SEWAGE TREATMENT PLANT",
            "ESTATE OF JANE SAMPLE",
            "JANE SAMPLE FAMILY TRUST",
            "JANE SAMPLE PROPERTY",
            "JANE SAMPLE DBA FIXTURE PLUMBING",
            "JANE SAMPLE T/A FIXTURE TRUCKING",
        ):
            with self.subTest(name=name):
                self.assertEqual(excluded_name_reason(name), "PERSON_SHAPED_NAME")

    def test_organizations_and_facilities_are_admitted(self):
        for name in (
            "FIXTURE ALPHA MANUFACTURING LLC",
            "BRAVO COMPONENTS INC",
            "JANE SAMPLE LLC",
            "SAMPLE HOMEOWNERS ASSN",
            "SAMPLE HOMEOWNER ASSOCIATION",
            "EXAMPLE COUNTY HOUSEHOLD HAZARDOUS WASTE",
            "HOUSEHOLD HAZARDOUS WASTE FIXTURE",
            "SFS FIXTURE INC",
            "FIXTURE PROP LLC",
            "RESIDENCE INN FIXTURE",
            "CITY OF EXAMPLE RES",
            "SAMPLE TWP STP",
            "FIXTURE RESOURCES INC",
            "PROPANE FIXTURE CO",
            "FIXTURE RESIDENTIAL SUBDIVISION",
            "ROUTE 9 FIXTURE PLANT",
            "PLANT 2 FIXTURE WORKS",
            "FIXTURE 2 ST PLANT",
            "PARCEL 1234567 EXAMPLE RD",
            "SAMPLE FAMILY FARM",
            "ACME FIXTURE LLC DBA JANE'S PLACE",
            "FIXTURE",
            "",
        ):
            with self.subTest(name=name):
                self.assertIsNone(excluded_name_reason(name, ("332710",)))

    def test_reason_code_never_echoes_the_name(self):
        name = "JANE SAMPLE SRSTP"
        reason = excluded_name_reason(name)
        self.assertIsNotNone(reason)
        for part in name.split():
            self.assertNotIn(part, reason)


if __name__ == "__main__":
    unittest.main()
