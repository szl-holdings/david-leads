# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import csv
import io
import json
import sys
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import echo_snapshot  # noqa: E402
from tools.ingestor.echo_ingestor import (  # noqa: E402
    ECHO_REQUIRED_HEADERS,
    canonical_json,
    run,
    serialize_record,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
BASE_URL = "https://dataset.test/resolve/main"


class _Response(io.BytesIO):
    def __init__(self, body: bytes):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
        return False


def _archive(
    *,
    source_date: datetime = NOW,
    first_inspection_age: int = 3,
    first_name: str = "ALPHA MANUFACTURING LLC",
    first_naics: str = "332710",
) -> bytes:
    values = [
        {
            "REGISTRY_ID": "110000000001",
            "FAC_NAME": first_name,
            "FAC_CITY": "ALBANY",
            "FAC_STATE": "NY",
            "FAC_ZIP": "12207",
            "FAC_COUNTY": "ALBANY",
            "FAC_EPA_REGION": "02",
            "FAC_FEDERAL_FLG": "N",
            "FAC_ACTIVE_FLAG": "Y",
            "FAC_INSPECTION_COUNT": "4",
            "FAC_DATE_LAST_INSPECTION": (NOW - timedelta(days=first_inspection_age)).strftime("%m/%d/%Y"),
            "FAC_DAYS_LAST_INSPECTION": str(first_inspection_age),
            "FAC_NAICS_CODES": first_naics,
            "AIR_FLAG": "Y",
            "NPDES_FLAG": "N",
            "SDWIS_FLAG": "N",
            "RCRA_FLAG": "Y",
            "TRI_FLAG": "N",
            "GHG_FLAG": "N",
        },
        {
            "REGISTRY_ID": "110000000002",
            "FAC_NAME": "BRAVO COMPONENTS INC",
            "FAC_CITY": "ERIE",
            "FAC_STATE": "PA",
            "FAC_ZIP": "16501",
            "FAC_COUNTY": "ERIE",
            "FAC_EPA_REGION": "03",
            "FAC_FEDERAL_FLG": "N",
            "FAC_ACTIVE_FLAG": "Y",
            "FAC_INSPECTION_COUNT": "2",
            "FAC_DATE_LAST_INSPECTION": (NOW - timedelta(days=1)).strftime("%m/%d/%Y"),
            "FAC_DAYS_LAST_INSPECTION": "1",
            "FAC_NAICS_CODES": "336390",
            "AIR_FLAG": "Y",
            "NPDES_FLAG": "Y",
            "SDWIS_FLAG": "N",
            "RCRA_FLAG": "N",
            "TRI_FLAG": "N",
            "GHG_FLAG": "N",
        },
        {
            "REGISTRY_ID": "110000000003",
            "FAC_NAME": "BETA FABRICATION CORP",
            "FAC_CITY": "BUFFALO",
            "FAC_STATE": "NY",
            "FAC_ZIP": "14202",
            "FAC_COUNTY": "ERIE",
            "FAC_EPA_REGION": "02",
            "FAC_FEDERAL_FLG": "N",
            "FAC_ACTIVE_FLAG": "Y",
            "FAC_INSPECTION_COUNT": "7",
            "FAC_DATE_LAST_INSPECTION": (NOW - timedelta(days=1)).strftime("%m/%d/%Y"),
            "FAC_DAYS_LAST_INSPECTION": "1",
            "FAC_NAICS_CODES": "332312",
            "AIR_FLAG": "N",
            "NPDES_FLAG": "Y",
            "SDWIS_FLAG": "N",
            "RCRA_FLAG": "Y",
            "TRI_FLAG": "N",
            "GHG_FLAG": "N",
        },
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(ECHO_REQUIRED_HEADERS))
    writer.writeheader()
    writer.writerows(values)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        member = zipfile.ZipInfo("ECHO_EXPORTER.csv", source_date.timetuple()[:6])
        member.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(member, buffer.getvalue().encode("utf-8"))
    return archive.getvalue()


def _bundle(
    *,
    source_date: datetime = NOW,
    first_inspection_age: int = 3,
    first_name: str = "ALPHA MANUFACTURING LLC",
    first_naics: str = "332710",
) -> dict[str, bytes]:
    result = run(
        _archive(
            source_date=source_date,
            first_inspection_age=first_inspection_age,
            first_name=first_name,
            first_naics=first_naics,
        ),
        session_id="123e4567-e89b-42d3-a456-426614174000",
        source_revision="a" * 40,
        created_at=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    snapshot = result["snapshot"]
    records = b"".join(
        canonical_json(serialize_record(record)) + b"\n"
        for record in result["records"]
    )
    latest = {
        "pointer_version": 1,
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_digest": snapshot["snapshot_digest"],
        "created_at": snapshot["created_at"],
        "record_count": snapshot["record_count"],
        "records_root_sha256": snapshot["records_root_sha256"],
        "records_file_sha256": snapshot["records_file_sha256"],
        "path": f"snapshots/{NOW.date().isoformat()}/{snapshot['snapshot_digest']}",
    }
    prefix = f"{BASE_URL}/{latest['path']}"
    return {
        f"{BASE_URL}/latest.json": json.dumps(latest).encode("utf-8"),
        f"{prefix}/snapshot.json": json.dumps(snapshot).encode("utf-8"),
        f"{prefix}/receipt.json": json.dumps(result["receipt"]).encode("utf-8"),
        f"{prefix}/records.jsonl": records,
    }


def _opener(files: dict[str, bytes], calls: list[str] | None = None):
    def open_url(url: str):
        if calls is not None:
            calls.append(url)
        if url not in files:
            raise OSError("not found")
        return _Response(files[url])

    return open_url


class EchoSnapshotVerification(unittest.TestCase):
    def test_complete_bundle_verifies_before_deterministic_bounded_selection(self):
        files = _bundle()
        calls: list[str] = []
        with mock.patch.object(
            echo_snapshot, "_open_url", side_effect=_opener(files, calls)
        ):
            result = echo_snapshot.load_verified_records(
                ["PA", "NY"], 2, now=NOW, base_url=BASE_URL
            )

        self.assertEqual(len(calls), 4)
        self.assertTrue(all("echodata.epa.gov" not in url for url in calls))
        self.assertEqual(
            [record["source_record_id"] for record in result["records"]],
            ["echo:110000000003", "echo:110000000002"],
        )
        self.assertEqual(result["snapshot"]["freshness_state"], "FRESH")
        self.assertEqual(result["receipt"]["state"], "PAYLOAD_VERIFIED_UNSIGNED")
        self.assertEqual(
            set(result["records"][0]), set(echo_snapshot.SERIALIZED_RECORD_FIELDS)
        )

    def test_record_source_receipt_tamper_fails_closed(self):
        files = _bundle()
        records_url = next(url for url in files if url.endswith("/records.jsonl"))
        records = files[records_url].splitlines()
        first = json.loads(records[0])
        first["source_receipt"] = "0" * 64
        records[0] = canonical_json(first)
        files[records_url] = b"\n".join(records) + b"\n"

        with mock.patch.object(
            echo_snapshot, "_open_url", side_effect=_opener(files)
        ):
            with self.assertRaisesRegex(
                echo_snapshot.EchoSnapshotUnavailable, "source receipt mismatch"
            ):
                echo_snapshot.load_verified_records(
                    ["NY"], 2, now=NOW, base_url=BASE_URL
                )

    def test_snapshot_digest_tamper_fails_before_records_are_returned(self):
        files = _bundle()
        snapshot_url = next(url for url in files if url.endswith("/snapshot.json"))
        snapshot = json.loads(files[snapshot_url])
        snapshot["record_count"] = 2
        files[snapshot_url] = json.dumps(snapshot).encode("utf-8")

        with mock.patch.object(
            echo_snapshot, "_open_url", side_effect=_opener(files)
        ):
            with self.assertRaisesRegex(
                echo_snapshot.EchoSnapshotUnavailable, "snapshot digest mismatch"
            ):
                echo_snapshot.load_verified_records(
                    ["NY"], 2, now=NOW, base_url=BASE_URL
                )

    def test_receipt_payload_tamper_fails_closed(self):
        files = _bundle()
        receipt_url = next(url for url in files if url.endswith("/receipt.json"))
        receipt = json.loads(files[receipt_url])
        receipt["ranking_inputs"]["caveats"].append("tampered")
        files[receipt_url] = json.dumps(receipt).encode("utf-8")

        with mock.patch.object(
            echo_snapshot, "_open_url", side_effect=_opener(files)
        ):
            with self.assertRaisesRegex(
                echo_snapshot.EchoSnapshotUnavailable, "receipt payload hash mismatch"
            ):
                echo_snapshot.load_verified_records(
                    ["NY"], 2, now=NOW, base_url=BASE_URL
                )

    def test_stale_snapshot_fails_closed(self):
        files = _bundle()
        stale_clock = NOW + timedelta(days=9)
        with mock.patch.object(
            echo_snapshot, "_open_url", side_effect=_opener(files)
        ):
            with self.assertRaisesRegex(
                echo_snapshot.EchoSnapshotUnavailable,
                f"data as of {NOW.date().isoformat()}, refresh pending",
            ):
                echo_snapshot.load_verified_records(
                    ["NY"], 2, now=stale_clock, base_url=BASE_URL
                )

    def test_latest_pointer_cannot_escape_immutable_snapshot_path(self):
        files = _bundle()
        latest_url = f"{BASE_URL}/latest.json"
        latest = json.loads(files[latest_url])
        latest["path"] = "snapshots/../../main"
        files[latest_url] = json.dumps(latest).encode("utf-8")
        with mock.patch.object(
            echo_snapshot, "_open_url", side_effect=_opener(files)
        ):
            with self.assertRaisesRegex(
                echo_snapshot.EchoSnapshotUnavailable, "path is not immutable"
            ):
                echo_snapshot.load_verified_records(
                    ["NY"], 2, now=NOW, base_url=BASE_URL
                )

    def test_new_snapshot_creation_does_not_hide_stale_upstream_date(self):
        source_date = NOW - timedelta(days=30)
        files = _bundle(source_date=source_date)
        with mock.patch.object(echo_snapshot, "_open_url", side_effect=_opener(files)):
            with self.assertRaisesRegex(
                echo_snapshot.EchoSnapshotUnavailable,
                f"data as of {source_date.date().isoformat()}, refresh pending",
            ):
                echo_snapshot.load_verified_records(["NY"], 2, now=NOW, base_url=BASE_URL)

    def test_records_that_age_out_are_excluded_without_invalidating_bundle(self):
        files = _bundle(first_inspection_age=365)
        with mock.patch.object(echo_snapshot, "_open_url", side_effect=_opener(files)):
            at_admission = echo_snapshot.load_verified_records(["NY"], 2, now=NOW, base_url=BASE_URL)
        self.assertEqual(len(at_admission["records"]), 2)
        with mock.patch.object(echo_snapshot, "_open_url", side_effect=_opener(files)):
            next_day = echo_snapshot.load_verified_records(["NY"], 2, now=NOW + timedelta(days=1), base_url=BASE_URL)
        self.assertEqual([row["source_record_id"] for row in next_day["records"]], ["echo:110000000003"])
        self.assertEqual(next_day["snapshot"]["record_count"], 3)

    def test_reported_age_cannot_admit_an_old_inspection(self):
        files = _bundle(first_inspection_age=366)
        records_url = next(url for url in files if url.endswith("/records.jsonl"))
        records = files[records_url].splitlines()
        first = json.loads(records[0])
        first["days_since_last_inspection"] = 1
        records[0] = canonical_json(first)
        files[records_url] = b"\n".join(records) + b"\n"
        with mock.patch.object(echo_snapshot, "_open_url", side_effect=_opener(files)):
            with self.assertRaisesRegex(echo_snapshot.EchoSnapshotUnavailable, "inspection date outside monitoring window"):
                echo_snapshot.load_verified_records(["NY"], 2, now=NOW, base_url=BASE_URL)

    def test_person_or_residence_record_fails_closed_despite_valid_bindings(self):
        # Simulates a bundle produced without the ingestion name screen: all
        # hashes, the root, and the receipt bind, but the declared
        # person/street exclusion does not hold. Every name is synthetic.
        for first_name, first_naics in (
            ("JANE SAMPLE SRSTP", "332710"),
            ("SAMPLE 100 EXAMPLE LN", "332710"),
            ("JOHN & JANE SAMPLE", "332710"),
            ("ALPHA MANUFACTURING LLC", "814110"),
            ("GERALD R SAMPLE", "332710"),
            ("SAMPLE JANE", "332710"),
            ("W1234 EXAMPLE RD", "332710"),
        ):
            with self.subTest(first_name=first_name, first_naics=first_naics):
                with mock.patch(
                    "tools.ingestor.echo_ingestor.excluded_name_reason",
                    return_value=None,
                ):
                    files = _bundle(first_name=first_name, first_naics=first_naics)
                with mock.patch.object(
                    echo_snapshot, "_open_url", side_effect=_opener(files)
                ):
                    with self.assertRaisesRegex(
                        echo_snapshot.EchoSnapshotUnavailable,
                        "record 1 violates the person/residence exclusion",
                    ):
                        echo_snapshot.load_verified_records(
                            ["PA"], 2, now=NOW, base_url=BASE_URL
                        )

    def test_transport_failure_never_falls_back_to_sample_records(self):
        with mock.patch.object(
            echo_snapshot, "_open_url", side_effect=OSError("offline")
        ):
            with self.assertRaisesRegex(
                echo_snapshot.EchoSnapshotUnavailable, "snapshot transport failed"
            ):
                echo_snapshot.load_verified_records(
                    ["NY"], 2, now=NOW, base_url=BASE_URL
                )


if __name__ == "__main__":
    unittest.main()
