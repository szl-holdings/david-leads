from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import tools.ingestor.publish_snapshot as publisher
from tools.ingestor.publish_snapshot import PublicationError, publish_snapshot


DATASET_ID = "SZLHOLDINGS/david-leads-data"
PARENT_COMMIT = "1" * 40
PUBLISHED_COMMIT = "2" * 40
DIGEST = "a" * 64
TOKEN = "hf_test_token_never_print"


class FakeRemoteEntryNotFoundError(Exception):
    pass


class FakeNetworkError(Exception):
    pass


@dataclass
class FakeOperation:
    path_in_repo: str
    path_or_fileobj: Path | bytes


class FakeApi:
    def __init__(
        self,
        events: list[str],
        *,
        tree_result: object | None = None,
        tree_error: BaseException | None = None,
        tamper_path: str | None = None,
    ) -> None:
        self.events = events
        self.tree_result = tree_result
        self.tree_error = tree_error
        self.tamper_path = tamper_path
        self.create_repo_calls: list[dict[str, object]] = []
        self.repo_info_calls: list[dict[str, object]] = []
        self.tree_calls: list[dict[str, object]] = []
        self.commit_calls: list[dict[str, object]] = []
        self.download_calls: list[dict[str, object]] = []
        self.remote: dict[str, bytes] = {}

    def create_repo(self, **kwargs: object) -> None:
        self.events.append("create_repo")
        self.create_repo_calls.append(kwargs)

    def repo_info(self, **kwargs: object) -> SimpleNamespace:
        self.events.append("repo_info")
        self.repo_info_calls.append(kwargs)
        return SimpleNamespace(sha=PARENT_COMMIT)

    def list_repo_tree(self, **kwargs: object) -> list[object]:
        self.events.append("list_repo_tree")
        self.tree_calls.append(kwargs)
        if self.tree_error is not None:
            raise self.tree_error
        if self.tree_result is None:
            return []
        return list(self.tree_result)  # type: ignore[arg-type]

    def create_commit(self, **kwargs: object) -> SimpleNamespace:
        self.events.append("create_commit")
        self.commit_calls.append(kwargs)
        for operation in kwargs["operations"]:  # type: ignore[index]
            payload = operation.path_or_fileobj
            self.remote[operation.path_in_repo] = (
                payload.read_bytes() if isinstance(payload, Path) else payload
            )
        return SimpleNamespace(oid=PUBLISHED_COMMIT)

    def hf_hub_download(self, **kwargs: object) -> str:
        self.events.append("hf_hub_download")
        self.download_calls.append(kwargs)
        filename = str(kwargs["filename"])
        if kwargs["revision"] == PARENT_COMMIT:
            raise FakeRemoteEntryNotFoundError()
        target = Path(str(kwargs["local_dir"])) / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        content = self.remote[filename]
        if filename == self.tamper_path:
            content += b"tampered"
        target.write_bytes(content)
        return str(target)


class PublishSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.snapshot_dir = self.root / "snapshot"
        self.snapshot_dir.mkdir()
        self.publication = self.root / "publication.json"
        self.snapshot = {
            "snapshot_id": f"sha256:{DIGEST}",
            "snapshot_digest": DIGEST,
            "created_at": "2026-09-04T12:00:00Z",
            "record_count": 7,
            "records_root_sha256": "b" * 64,
            "records_file_sha256": "c" * 64,
            "parser": {"source_revision": "d" * 40},
            "source": {"source_as_of": "2026-08-30"},
        }
        (self.snapshot_dir / "snapshot.json").write_text(
            json.dumps(self.snapshot), encoding="utf-8"
        )
        (self.snapshot_dir / "receipt.json").write_bytes(b'{"receipt":"UNSIGNED"}\n')
        (self.snapshot_dir / "records.jsonl").write_bytes(b'{"record":1}\n')

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _publish(
        self,
        api: FakeApi,
        events: list[str],
        **overrides: object,
    ) -> dict[str, object]:
        def verifier(path: Path) -> int:
            self.assertNotEqual(path, self.snapshot_dir.resolve())
            self.assertEqual((path / "records.jsonl").read_bytes(),
                             (self.snapshot_dir / "records.jsonl").read_bytes())
            events.append("verify")
            return int(overrides.get("verify_result", 0))

        return publish_snapshot(
            DATASET_ID,
            self.snapshot_dir,
            self.publication,
            token=str(overrides.get("token", TOKEN)),
            verifier=verifier,
            api_factory=lambda token: (
                events.append("api_factory"),
                self.assertEqual(token, TOKEN),
                api,
            )[-1],
            operation_factory=FakeOperation,
            remote_entry_not_found=FakeRemoteEntryNotFoundError,
            clock=lambda: datetime(2026, 9, 4, 13, 0, tzinfo=timezone.utc),
        )

    def test_missing_token_fails_without_verifier_or_api(self) -> None:
        calls: list[str] = []
        with self.assertRaises(PublicationError):
            publish_snapshot(
                DATASET_ID,
                self.snapshot_dir,
                self.publication,
                token="",
                verifier=lambda _path: calls.append("verify") or 0,
                api_factory=lambda _token: calls.append("api"),
                operation_factory=FakeOperation,
                remote_entry_not_found=FakeRemoteEntryNotFoundError,
            )
        self.assertEqual(calls, [])

    def test_strict_verifier_runs_before_api_and_failure_stops(self) -> None:
        events: list[str] = []
        api = FakeApi(events, tree_error=FakeRemoteEntryNotFoundError())
        with self.assertRaises(PublicationError):
            self._publish(api, events, verify_result=1)
        self.assertEqual(events, ["verify"])
        self.assertFalse(self.publication.exists())

    def test_atomic_cas_commit_and_pinned_readback(self) -> None:
        events: list[str] = []
        api = FakeApi(events, tree_error=FakeRemoteEntryNotFoundError())
        result = self._publish(api, events)

        self.assertEqual(events[:4], ["verify", "api_factory", "create_repo", "repo_info"])
        self.assertEqual(
            api.create_repo_calls,
            [
                {
                    "repo_id": DATASET_ID,
                    "repo_type": "dataset",
                    "exist_ok": True,
                    "private": False,
                }
            ],
        )
        self.assertEqual(api.repo_info_calls[0]["revision"], "main")
        self.assertEqual(api.tree_calls[0]["revision"], PARENT_COMMIT)
        expected_prefix = f"snapshots/2026-09-04/{DIGEST}"
        self.assertEqual(api.tree_calls[0]["path_in_repo"], expected_prefix)

        self.assertEqual(len(api.commit_calls), 1)
        commit = api.commit_calls[0]
        self.assertEqual(commit["revision"], "main")
        self.assertEqual(commit["parent_commit"], PARENT_COMMIT)
        operations = commit["operations"]
        self.assertEqual(len(operations), 6)  # type: ignore[arg-type]
        self.assertEqual(
            {operation.path_in_repo for operation in operations},  # type: ignore[union-attr]
            {
                f"{expected_prefix}/snapshot.json",
                f"{expected_prefix}/receipt.json",
                f"{expected_prefix}/records.jsonl",
                "latest.json",
                "latest/echo-exporter.json",
                "README.md",
            },
        )
        card = api.remote["README.md"].decode("utf-8")
        self.assertIn("David Leads — verified Federal Refresh", card)
        self.assertIn("UNSIGNED", card)
        self.assertIn(DIGEST, card)
        latest = json.loads(api.remote["latest.json"])
        self.assertEqual(latest["path"], expected_prefix)
        self.assertEqual(latest["snapshot_digest"], DIGEST)
        self.assertEqual(latest["record_count"], 7)

        self.assertEqual(len(api.download_calls), 7)
        self.assertEqual(api.download_calls[0]["revision"], PARENT_COMMIT)
        for call in api.download_calls[1:]:
            self.assertEqual(call["revision"], PUBLISHED_COMMIT)
            self.assertTrue(call["force_download"])
        self.assertEqual(result["status"], "VERIFIED_PUBLISHED")
        self.assertEqual(result["published_commit"], PUBLISHED_COMMIT)
        self.assertEqual(result["verification"]["pinned_hub_readback"], "PASS")
        self.assertEqual(json.loads(self.publication.read_text()), result)

    def test_existing_content_addressed_prefix_fails_without_commit(self) -> None:
        events: list[str] = []
        api = FakeApi(events, tree_result=[object()])
        with self.assertRaises(PublicationError):
            self._publish(api, events)
        self.assertEqual(api.commit_calls, [])
        self.assertFalse(self.publication.exists())

    def test_only_exact_remote_not_found_is_treated_as_absent(self) -> None:
        events: list[str] = []
        api = FakeApi(events, tree_error=FakeNetworkError("timeout"))
        with self.assertRaises(FakeNetworkError):
            self._publish(api, events)
        self.assertEqual(api.commit_calls, [])
        self.assertFalse(self.publication.exists())

    def test_pinned_readback_mismatch_fails_without_success_receipt(self) -> None:
        events: list[str] = []
        api = FakeApi(
            events,
            tree_error=FakeRemoteEntryNotFoundError(),
            tamper_path="latest.json",
        )
        with self.assertRaises(PublicationError):
            self._publish(api, events)
        self.assertEqual(len(api.commit_calls), 1)
        self.assertFalse(self.publication.exists())

    def test_publication_receipt_inside_bundle_is_rejected(self) -> None:
        calls: list[str] = []
        with self.assertRaises(PublicationError):
            publish_snapshot(
                DATASET_ID,
                self.snapshot_dir,
                self.snapshot_dir / "publication.json",
                token=TOKEN,
                verifier=lambda _path: calls.append("verify") or 0,
                api_factory=lambda _token: calls.append("api"),
                operation_factory=FakeOperation,
                remote_entry_not_found=FakeRemoteEntryNotFoundError,
            )
        self.assertEqual(calls, [])

    def test_existing_publication_receipt_is_rejected_before_remote_calls(self) -> None:
        self.publication.write_text("existing evidence", encoding="utf-8")
        calls: list[str] = []
        with self.assertRaises(PublicationError):
            publish_snapshot(
                DATASET_ID,
                self.snapshot_dir,
                self.publication,
                token=TOKEN,
                verifier=lambda _path: calls.append("verify") or 0,
                api_factory=lambda _token: calls.append("api"),
                operation_factory=FakeOperation,
                remote_entry_not_found=FakeRemoteEntryNotFoundError,
            )
        self.assertEqual(calls, [])
        self.assertEqual(self.publication.read_text(encoding="utf-8"), "existing evidence")

    def test_cli_never_echoes_token_or_remote_exception_text(self) -> None:
        secret = "hf_do_not_echo_this_secret"
        stderr = io.StringIO()
        stdout = io.StringIO()
        argv = [
            "publish_snapshot",
            "--dataset",
            DATASET_ID,
            "--snapshot",
            str(self.snapshot_dir),
            "--receipt-out",
            str(self.publication),
        ]
        with (
            mock.patch.object(publisher.sys, "argv", argv),
            mock.patch.dict(os.environ, {"HF_TOKEN": secret}),
            mock.patch.object(
                publisher,
                "publish_snapshot",
                side_effect=RuntimeError(f"remote reflected {secret}"),
            ),
            contextlib.redirect_stderr(stderr),
            contextlib.redirect_stdout(stdout),
        ):
            self.assertEqual(publisher.main(), 1)
        combined = stderr.getvalue() + stdout.getvalue()
        self.assertNotIn(secret, combined)
        self.assertNotIn("remote reflected", combined)


if __name__ == "__main__":
    unittest.main()
