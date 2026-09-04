"""Tests for the USAspending award-archive ingestor lane.

Fixtures are synthetic and live ONLY in tests (no-sample-substitution rule).
"""

import io
import zipfile

import pytest

from tools.ingestor.usaspending_ingestor import parse_usaspending, run_usaspending

CSV_TXT = ("UNIQUE_AWARD_KEY,RECIPIENT_NAME,RECIPIENT_STATE_CODE,TOTAL_OBLIGATION\n"
           "CONT_AWD_1234,Fixture Awardee One Corp,PA,100000\n"
           "CONT_AWD_5678,Fixture Awardee Two LLC,OH,250000\n").encode()


def test_parse_binds_by_header_name():
    records = parse_usaspending(CSV_TXT)
    assert len(records) == 2
    assert records[0].source_record_id == "usaspending:CONT_AWD_1234"
    assert records[0].org_name == "Fixture Awardee One Corp"
    assert records[0].state == "PA"


def test_pipe_delimited_variant():
    assert len(parse_usaspending(b"PIID|RECIPIENT_NAME|RECIPIENT_STATE_CODE\nW91|Pipe Awardee Inc|NY\n")) == 1


def test_legacy_key_variants():
    assert len(parse_usaspending(b"AWARD_ID,VENDOR_NAME,STATE\nX9,Legacy Vendor Co,VA\n")) == 1


def test_zip_wrapped_accepted():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("awards_2026_08.csv", CSV_TXT.decode())
    assert len(parse_usaspending(buf.getvalue())) == 2


def test_fail_closed_on_empty():
    with pytest.raises(ValueError):
        run_usaspending(b"")


def test_fail_closed_on_non_award_header():
    with pytest.raises(ValueError):
        parse_usaspending(b"COL_A,COL_B\n1,2\n")


def test_snapshot_and_receipt_carry_lane_identity():
    result = run_usaspending(CSV_TXT, session_id="s-usa")
    assert result["snapshot"]["source"]["name"] == "usaspending-archive"
    assert result["receipt"]["subject"]["parser_version"] == "1.0.0"
    assert result["receipt"]["signature"]["value"] == "UNSIGNED"
