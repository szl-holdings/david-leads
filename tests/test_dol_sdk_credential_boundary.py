"""Private snapshot reads must not inherit publisher credentials or SDK endpoints."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import huggingface_hub

from app.federal_refresh_store import DATASET_ID, load_dol_snapshot
from tests.dol_fixtures import KEY, NOW, REVISION, bundle_files, fixture


@pytest.mark.parametrize("configured", [None, "", "synthetic-explicit-dataset-read-token"])
def test_sdk_reads_bind_explicit_reader_and_canonical_endpoint(tmp_path, monkeypatch, configured):
    """Execute full canonical bundle verification through the default SDK branch."""
    files = bundle_files(fixture())
    cache = tmp_path / "publisher-token"
    cache.write_text("synthetic-cached-publisher-token", encoding="utf-8")
    monkeypatch.setenv("HF_TOKEN", "synthetic-environment-publisher-token")
    monkeypatch.setenv("HF_TOKEN_PATH", str(cache))
    monkeypatch.setenv("HF_ENDPOINT", "https://unapproved-sdk-endpoint.invalid")
    if configured is None:
        monkeypatch.delenv("DAVID_DATASET_READ_TOKEN", raising=False)
    else:
        monkeypatch.setenv("DAVID_DATASET_READ_TOKEN", configured)
    expected_token = configured or False
    observed = []

    def info(repo_id, paths, *, repo_type, revision):
        assert repo_id == DATASET_ID
        assert repo_type == "dataset"
        assert revision == REVISION
        return [SimpleNamespace(path=name, size=len(files[name])) for name in paths]

    client = Mock()
    client.get_paths_info.side_effect = info
    api = Mock(return_value=client)

    def download(repo_id, filename, *, repo_type, revision, endpoint, token):
        assert repo_id == DATASET_ID
        assert repo_type == "dataset"
        assert revision == REVISION
        assert endpoint == "https://huggingface.co"
        assert token == expected_token
        # Return actual bundle files: the verifier must still enforce pointer,
        # canonical record hash, coverage, freshness, receipt and private HMAC.
        local = tmp_path / "bundle" / filename
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(files[filename])
        observed.append(filename)
        return str(local)

    downloader = Mock(side_effect=download)
    cached_token_lookup = Mock(side_effect=AssertionError("implicit publisher token lookup is forbidden"))
    monkeypatch.setattr(huggingface_hub, "HfApi", api)
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", downloader)
    monkeypatch.setattr(huggingface_hub, "get_token", cached_token_lookup)

    bundle = load_dol_snapshot(REVISION, signing_key=KEY, now=NOW)

    assert bundle.revision == REVISION
    assert bundle.records[0]["source_record_id"] == "dol-5500:SYNTHETIC-A1"
    assert set(observed) == set(files)
    assert api.call_count == len(files)
    for call in api.call_args_list:
        assert call.args == ()
        assert call.kwargs == {"endpoint": "https://huggingface.co", "token": expected_token}
    assert downloader.call_count == len(files)
    cached_token_lookup.assert_not_called()
