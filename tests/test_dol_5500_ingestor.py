"""Tests for the DOL Form 5500 bulk ingestor lane.

Fixtures are synthetic and live ONLY in tests (no-sample-substitution rule).
"""

import io
import zipfile

import pytest

from tools.ingestor.dol_5500_ingestor import parse_dol_5500, parse_dol_5500_report, run_dol_5500

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
    assert result["receipt"]["subject"]["parser_version"] == "2.0.0"
    assert result["receipt"]["signature"]["value"] == "UNSIGNED"


def test_personal_columns_are_discarded_before_record_hashing():
    payload = b"ACK_ID|SPONSOR_DFE_PN|SPONS_DFE_MAIL_US_STATE|EIN|BROKER_NAME|SIGNER_NAME\nA1|Fixture Org Corp|NY|EXCLUDED|EXCLUDED|EXCLUDED\n"
    result = parse_dol_5500(payload)[0]
    assert result.raw == {}
    assert "EXCLUDED" not in str(result)


def test_missing_identity_is_quarantined_without_row_number_fallback():
    report = parse_dol_5500_report(PIPE_TXT.replace(b"A1|", b"|"))
    assert len(report.records) == 1
    assert report.quarantined_rows == 1
    assert report.quarantine_reasons == {"FILING_ID_MISSING_OR_INVALID": 1}


def test_conflicting_filing_rows_are_both_withheld():
    report = parse_dol_5500_report(PIPE_TXT.replace(b"A2|", b"A1|"))
    assert report.records == []
    assert report.quarantined_rows == 2


def test_duplicate_rows_are_counted_without_new_identity():
    report = parse_dol_5500_report(PIPE_TXT + PIPE_TXT.splitlines()[1] + b"\n")
    assert len(report.records) == 2
    assert report.rejected_rows == 1
    assert report.rows_seen == 3


def test_unsupported_layout_never_falls_back_to_plan_name():
    with pytest.raises(ValueError, match="SCHEMA_CHANGED"):
        parse_dol_5500(b"ACK_ID|PLAN_NAME|SPONS_DFE_MAIL_US_STATE\nA1|Fixture Org|NY\n")


def test_multiple_archive_layouts_are_not_concatenated():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("5500.csv", PIPE_TXT)
        archive.writestr("5500_schedule.csv", PIPE_TXT)
    with pytest.raises(ValueError, match="LAYOUT_AMBIGUOUS"):
        parse_dol_5500(buf.getvalue())


def test_amended_filing_and_form_year_are_distinct_from_plan_dates():
    payload = b"ACK_ID|SPONSOR_DFE_PN|SPONS_DFE_MAIL_US_STATE|FORM_YEAR|PLAN_YEAR_BEGIN_DATE|PLAN_YEAR_END_DATE|AMENDED_IND\nA1|Fixture Org Corp|NY|2025|20240101|20241231|1\n"
    raw = parse_dol_5500(payload)[0].raw
    assert raw == {"form_year": 2025, "plan_year_begin": "2024-01-01", "plan_year_end": "2024-12-31", "amended_filing": True}


def test_quarantine_counts_make_partial_snapshot_visible():
    result = run_dol_5500(PIPE_TXT.replace(b"A1|", b"|"))
    assert result["snapshot"]["completeness"] == "PARTIAL"
    assert result["snapshot"]["counts"] == {"rows_seen": 2, "accepted": 1, "rejected": 0, "quarantined": 1}
