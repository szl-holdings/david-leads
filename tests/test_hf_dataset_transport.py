"""Credential boundaries for the private canonical dataset reader."""

import io
import urllib.request
from unittest import mock

import pytest

from app import echo_snapshot, federal_snapshot
from app import hf_dataset_transport as transport

URL = "https://huggingface.co/datasets/SZLHOLDINGS/david-leads-data/resolve/main/latest.json"
TOKEN = "synthetic-read-token-only"


@pytest.fixture(autouse=True)
def isolated_read_credential(monkeypatch):
    monkeypatch.delenv(transport.READ_TOKEN_ENV, raising=False)


def _request_with_token():
    request = urllib.request.Request(URL)
    request.add_unredirected_header("Authorization", f"Bearer {TOKEN}")
    return request


def _redirect(request, target):
    return transport._DatasetRedirectHandler().redirect_request(
        request, None, 302, "Found", {}, target,
    )


def test_private_read_uses_explicit_token_and_preserves_timeout(monkeypatch):
    monkeypatch.setenv(transport.READ_TOKEN_ENV, TOKEN + "\r\n")
    opener = mock.Mock()
    with mock.patch.object(urllib.request, "build_opener", return_value=opener):
        transport.open_dataset_url(URL, timeout=9, user_agent="test", accept="application/json")
    request = opener.open.call_args.args[0]
    assert request.get_header("Authorization") == f"Bearer {TOKEN}"
    assert "Authorization" not in request.headers
    assert request.get_header("Accept") == "application/json"
    assert opener.open.call_args.kwargs == {"timeout": 9}


def test_no_read_token_stays_anonymous_even_with_publisher_token(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "synthetic-publisher-token-must-not-be-used")
    opener = mock.Mock()
    with mock.patch.object(urllib.request, "build_opener", return_value=opener):
        transport.open_dataset_url(URL, timeout=9, user_agent="test")
    assert opener.open.call_args.args[0].get_header("Authorization") is None


@pytest.mark.parametrize("url", [
    URL.replace("huggingface.co", "huggingface.co.attacker.invalid"),
    URL.replace("david-leads-data", "other-private-data"),
    URL.replace("https:", "http:"),
    URL.replace("huggingface.co", "user:password@huggingface.co"),
    URL.replace("huggingface.co", "huggingface.co:444"),
    URL.replace("latest.json", "../other-private-data/latest.json"),
    URL.replace("latest.json", "%2e%2e/other-private-data/latest.json"),
    URL.replace("latest.json", "%252e%252e/other-private-data/latest.json"),
    URL.replace("latest.json", "%5cother-private-data/latest.json"),
])
def test_unapproved_request_never_reaches_network(monkeypatch, url):
    monkeypatch.setenv(transport.READ_TOKEN_ENV, TOKEN)
    with mock.patch.object(urllib.request, "build_opener") as opener:
        with pytest.raises(transport.DatasetTransportPolicyError):
            transport.open_dataset_url(url, timeout=9, user_agent="test")
    opener.assert_not_called()


def test_same_repository_cache_redirect_retains_read_credential():
    target = "https://huggingface.co/api/resolve-cache/datasets/SZLHOLDINGS/david-leads-data/" + "a" * 40 + "/latest.json"
    redirected = _redirect(_request_with_token(), target)
    assert redirected.get_header("Authorization") == f"Bearer {TOKEN}"
    assert "Authorization" not in redirected.headers


@pytest.mark.parametrize("target", [
    "https://signed-storage.example.invalid/file?signature=synthetic",
    "https://huggingface.co/datasets/SZLHOLDINGS/other-data/resolve/main/latest.json",
    "https://huggingface.co/api/whoami-v2",
])
def test_redirect_outside_repository_never_receives_read_credential(target):
    redirected = _redirect(_request_with_token(), target)
    assert redirected.get_header("Authorization") is None
    # Returning from an untrusted storage URL cannot regain the initial token.
    second_redirect = _redirect(redirected, URL)
    assert second_redirect.get_header("Authorization") is None


@pytest.mark.parametrize("target", ["http://storage.example.invalid/file", "https://user:password@storage.example.invalid/file"])
def test_unsafe_redirect_is_rejected(target):
    with pytest.raises(transport.DatasetTransportPolicyError):
        _redirect(_request_with_token(), target)


@pytest.mark.parametrize("token", ["\r\n", "synthetic\nsecret", "synthetic secret", "x" * 4097])
def test_malformed_credential_fails_without_recording_value(monkeypatch, token):
    monkeypatch.setenv(transport.READ_TOKEN_ENV, token)
    with mock.patch.object(urllib.request, "build_opener") as opener:
        with pytest.raises(transport.DatasetTransportPolicyError) as raised:
            transport.open_dataset_url(URL, timeout=9, user_agent="test")
    assert str(raised.value) == "dataset read credential is invalid"
    opener.assert_not_called()


def test_both_runtime_readers_use_safe_transport_and_keep_byte_budget():
    with mock.patch.object(transport, "open_dataset_url", return_value=io.BytesIO(b"{}")) as open_url:
        assert echo_snapshot._load_json(URL, "fixture") == {}
    assert open_url.call_args.kwargs["timeout"] == echo_snapshot.HTTP_TIMEOUT_SECONDS
    with mock.patch.object(transport, "open_dataset_url", return_value=io.BytesIO(b"12345")) as open_url:
        with pytest.raises(federal_snapshot.SnapshotError, match="download exceeds bounds"):
            federal_snapshot._download("latest/form5500.json", 4)
    assert open_url.call_args.args[0] == federal_snapshot.DATASET_BASE + "/latest/form5500.json"
    assert open_url.call_args.kwargs["timeout"] == 45
