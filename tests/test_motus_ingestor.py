"""Tests for the FMCSA MOTUS ingestor lane.

Fixtures are synthetic and live ONLY in tests (no-sample-substitution rule).
"""

import io
import zipfile

import pytest

from tools.ingestor.motus_ingestor import parse_motus_carrier, run_motus

MOTUS_CSV = ("DOT_NUMBER,LEGAL_NAME,DBA_NAME,PHY_STATE,PHY_CITY\n"
             "123456,Fixture Carrier One LLC,,PA,Pittsburgh\n"
             "789012,Fixture Carrier Two Inc,,OH,Columbus\n").encode()


def test_parse_binds_by_header_name():
    records = parse_motus_carrier(MOTUS_CSV)
    assert len(records) == 2
    assert records[0].source_record_id == "fmcsa-motus:123456"
    assert records[0].org_name == "Fixture Carrier One LLC"
    assert records[0].state == "PA"


def test_parser_version_is_lane_scoped():
    r = parse_motus_carrier(MOTUS_CSV)[0]
    assert r.parser_version == "1.0.0"


def test_zip_wrapped_csv_accepted():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("motus_carrier.csv", MOTUS_CSV.decode())
    assert len(parse_motus_carrier(buf.getvalue())) == 2


def test_fail_closed_on_empty():
    with pytest.raises(ValueError):
        run_motus(b"")


def test_fail_closed_on_non_motus_header():
    with pytest.raises(ValueError):
        parse_motus_carrier(b"COL_A,COL_B\n1,2\n")


def test_snapshot_and_receipt_carry_lane_identity():
    result = run_motus(MOTUS_CSV, session_id="s-motus")
    assert result["snapshot"]["source"]["name"] == "fmcsa-motus-carrier"
    assert result["receipt"]["subject"]["parser_version"] == "1.0.0"
    assert result["receipt"]["signature"]["value"] == "UNSIGNED"
