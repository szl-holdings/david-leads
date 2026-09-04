"""Tests for the DOL Form 5500 bulk ingestor lane.

Fixtures are synthetic and live ONLY in tests (no-sample-substitution rule).
"""

import io
import zipfile

import pytest

from tools.ingestor.dol_5500_ingestor import parse_dol_5500, run_dol_5500

PIPE_TXT = ("ACK_ID|SPONSOR_DFE_PN|SPONS_DFE_MAIL_US_STATE|FORM5500_SF_MARKER\n"
            "A1|Fixture Sponsor One Corp|PA|1\n"
            "A2|Fixture Sponsor Two LLC|OH|1\n").encode()


def test_pipe_delimited_parse():
    records = parse_dol_5500(PIPE_TXT)
    assert len(records) == 2
    assert records[0].source_record_id == "dol-5500:A1"
    assert records[0].org_name == "Fixture Sponsor One Corp"
    assert records[0].state == "PA"


def test_comma_delimited_variant():
    assert len(parse_dol_5500(b"ACK_ID,SPONSOR_DFE_PN,SPONS_DFE_MAIL_US_STATE\nA3,Comma Sponsor Inc,NY\n")) == 1


def test_zip_wrapped_accepted():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("f_5500_2025_latest.csv", PIPE_TXT.decode())
    assert len(parse_dol_5500(buf.getvalue())) == 2


def test_fail_closed_on_empty():
    with pytest.raises(ValueError):
        run_dol_5500(b"")


def test_fail_closed_on_non_5500_header():
    with pytest.raises(ValueError):
        parse_dol_5500(b"COL_A|COL_B\n1|2\n")


def test_snapshot_and_receipt_carry_lane_identity():
    result = run_dol_5500(PIPE_TXT, session_id="s-dol")
    assert result["snapshot"]["source"]["name"] == "dol-5500-bulk"
    assert result["receipt"]["subject"]["parser_version"] == "1.0.0"
    assert result["receipt"]["signature"]["value"] == "UNSIGNED"
