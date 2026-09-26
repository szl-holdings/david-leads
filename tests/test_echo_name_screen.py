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

    def test_widened_given_names_are_rejected(self):
        for name in (
            "MARK SAMPLE",
            "GERALD SAMPLE",
            "RAYMOND SAMPLE",
            "GLEN SAMPLE",
            "DEAN SAMPLE",
            "LEE SAMPLE",
        ):
            with self.subTest(name=name):
                self.assertEqual(excluded_name_reason(name), "PERSON_SHAPED_NAME")

    def test_initials_and_surname_first_forms_are_rejected(self):
        for name in (
            "GERALD R SAMPLE",
            "FIXTURE R SAMPLE",
            "J SAMPLE",
            "J R SAMPLE",
            "SAMPLE J",
            "SAMPLE, J",
            "SAMPLE, J R",
            "SAMPLE-DOE, FIXTURE Q",
            "SAMPLE JANE",
            "SAMPLE JANE MARIE",
            "SAMPLE JANE Q",
        ):
            with self.subTest(name=name):
                self.assertEqual(excluded_name_reason(name), "PERSON_SHAPED_NAME")

    def test_honorific_names_are_rejected(self):
        for name in (
            "MR SAMPLE",
            "MS SAMPLE",
            "MRS JANE SAMPLE",
            "MR & MRS SAMPLE",
            "MR. AND MRS. SAMPLE",
            "DR SAMPLE",
            "MR SAMPLE STP",
        ):
            with self.subTest(name=name):
                self.assertEqual(excluded_name_reason(name), "PERSON_SHAPED_NAME")

    def test_personal_trust_estate_heirs_and_et_al_are_rejected(self):
        for name in (
            "SAMPLE FAMILY TRUST",
            "SAMPLE LIVING TRUST",
            "THE SAMPLE REVOCABLE TRUST",
            "ESTATE OF SAMPLE",
            "HEIRS OF SAMPLE",
            "SAMPLE HEIRS",
            "SAMPLE ET AL",
            "SAMPLE ET. AL.",
            "SAMPLE ETUX",
            "SAMPLE ET UX",
        ):
            with self.subTest(name=name):
                self.assertEqual(excluded_name_reason(name), "PERSON_SHAPED_NAME")

    def test_long_personal_names_are_rejected(self):
        for name in (
            "JANE MARIE SAMPLE FIXTURE DOE",
            "JUAN CARLOS SAMPLE DE LA FIXTURE",
            "JANE SAMPLE 3RD",
            "JOHN Q SAMPLE AND JANE R SAMPLE DOE",
        ):
            with self.subTest(name=name):
                self.assertEqual(excluded_name_reason(name), "PERSON_SHAPED_NAME")

    def test_dwelling_words_are_rejected(self):
        for name in (
            "SAMPLE COTTAGE",
            "SAMPLE CABIN",
            "SAMPLE DUPLEX",
            "SAMPLE DWELLING",
            "SAMPLE RESIDENTIAL",
            "SAMPLE HOMESTEAD",
        ):
            with self.subTest(name=name):
                self.assertEqual(excluded_name_reason(name), "RESIDENTIAL_PERMIT_NAME")

    def test_grid_and_numbered_route_addresses_are_rejected(self):
        for name in (
            "W1234 EXAMPLE RD",
            "N1234 COUNTY RD X",
            "FIXTURE W123 N4567 EXAMPLE LN",
            "1234 STATE ROUTE 9",
            "FIXTURE 1234 US 20",
            "1234 US HWY 20",
            "1234 SR 9",
            "1234 CR K",
            "1234 CR ABC",
        ):
            with self.subTest(name=name):
                self.assertEqual(excluded_name_reason(name), "STREET_ADDRESS_IN_NAME")

    def test_widened_screen_still_admits_organizations_and_places(self):
        for name in (
            "FORT JANE",
            "MOUNT JANE",
            "SAN JUAN",
            "CIRCLE Q",
            "CIRCLE Q FIXTURE",
            "FIXTURE PAD A",
            "SAMPLE LAND TRUST",
            "MR FIXTURE PLUMBING",
            "SAMPLE COTTAGE INN",
            "FIXTURE RESIDENTIAL SUBDIVISION",
            "PLANT 2 ROUTE 9",
            "FIXTURE N1234",
            "MARK SAMPLE LLC",
            "GERALD R SAMPLE INC",
        ):
            with self.subTest(name=name):
                self.assertIsNone(excluded_name_reason(name, ("332710",)))

    def test_place_and_facility_words_never_admit_a_narrow_person_shape(self):
        # These words stop only the wider shapes; a name led by a given name,
        # a "SURNAME, GIVEN" name, or a joint name stays rejected.
        for name in (
            "JANE SAMPLE DOCK",
            "SAMPLE, JANE CIRCLE",
            "JOHN & JANE FORT",
        ):
            with self.subTest(name=name):
                self.assertEqual(excluded_name_reason(name), "PERSON_SHAPED_NAME")

    def test_reason_code_never_echoes_the_name(self):
        name = "JANE SAMPLE SRSTP"
        reason = excluded_name_reason(name)
        self.assertIsNotNone(reason)
        for part in name.split():
            self.assertNotIn(part, reason)


if __name__ == "__main__":
    unittest.main()
