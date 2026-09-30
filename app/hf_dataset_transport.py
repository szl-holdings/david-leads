"""Read the canonical dataset without forwarding its credential to other origins.

The optional runtime credential is explicit and separate from the publisher.
Without it, reads stay anonymous; no local SDK token cache is consulted.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from typing import BinaryIO

DATASET_ID = "SZLHOLDINGS/david-leads-data"
READ_TOKEN_ENV = "DAVID_DATASET_READ_TOKEN"
_REPO_PREFIXES = (
    f"/datasets/{DATASET_ID}/resolve/",
    f"/api/resolve-cache/datasets/{DATASET_ID}/",
)


class DatasetTransportPolicyError(ValueError):
    """A request cannot safely use the canonical dataset transport."""


def dataset_read_token() -> str | None:
    """Return only the explicitly configured read credential, or anonymous mode."""
    value = os.environ.get(READ_TOKEN_ENV)
    if value is None or value == "":
        return None
    value = value.rstrip("\r\n")
    if not value or len(value) > 4096 or any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise DatasetTransportPolicyError("dataset read credential is invalid")
    return value


def _secure_url(url: str) -> urllib.parse.SplitResult:
    if not isinstance(url, str) or any(ord(char) < 32 or ord(char) == 127 for char in url):
        raise DatasetTransportPolicyError("dataset transport URL is invalid")
    try:
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port not in {None, 443} or parsed.fragment):
            raise ValueError
    except (ValueError, UnicodeError):
        raise DatasetTransportPolicyError("dataset transport requires an HTTPS URL") from None
    return parsed


def _canonical_repo_url(url: str) -> bool:
    parsed = _secure_url(url)
    path = urllib.parse.unquote(parsed.path)
    return (parsed.hostname == "huggingface.co" and "\\" not in path and "%" not in path
            and not any(part in {".", ".."} for part in path.split("/"))
            and any(path.startswith(prefix) for prefix in _REPO_PREFIXES))


class _DatasetRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Reject a downgrade before any redirected request can be sent. Signed
        # HTTPS storage/CDN URLs may be followed, with no dataset bearer token.
        _secure_url(newurl)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        redirected.remove_header("Authorization")
        authorization = req.get_header("Authorization")
        if authorization and _canonical_repo_url(req.full_url) and _canonical_repo_url(newurl):
            redirected.add_unredirected_header("Authorization", authorization)
        return redirected


def open_dataset_url(url: str, *, timeout: float, user_agent: str,
                     accept: str | None = None) -> BinaryIO:
    """Open a bounded caller-owned read from the fixed canonical dataset."""
    if not _canonical_repo_url(url):
        raise DatasetTransportPolicyError("dataset transport repository is not approved")
    headers = {"User-Agent": user_agent}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers, method="GET")
    token = dataset_read_token()
    if token:
        # urllib never automatically copies unredirected headers; the handler
        # adds this header back only for this repository on the canonical host.
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    opener = urllib.request.build_opener(_DatasetRedirectHandler())
    return opener.open(request, timeout=timeout)
