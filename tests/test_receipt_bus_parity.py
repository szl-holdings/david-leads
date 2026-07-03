# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads receipt-bus parity / divergence guard
"""
test_receipt_bus_parity.py — stdlib-only characterization guard that LOCKS the
DSSE wire contract of the David-Leads receipt bus against the rest of the estate.

Context (receipt-bus unification audit, 2026-07-03)
---------------------------------------------------
The SZL estate has TWO incompatible DSSE Pre-Authentication-Encoding (PAE)
families, and they produce DIFFERENT signed bytes for the same payload:

  * ASCII-decimal PAE (the DSSE-v1 spec form, cosign verify-blob compatible):
        b"DSSEv1 " + len(type) + " " + type + " " + len(body) + " " + body
    Used by: khipu-consensus, app/receipts.py (this repo), app/consensus.py
    (this repo), and a11oy szl_dsse.py. This is the MAJORITY / spec-correct form.

  * struct-packed little-endian PAE (NON-standard, NOT cosign-compatible despite
    its docstring):
        b"DSSEv1 " + struct.pack("<Q", len(type)) + type + " " + struct.pack("<Q", len(body)) + body
    Used by: szl-receipt (szl_receipt/_canonical.py) and its consumers.

Because the two PAE forms differ byte-for-byte, a signature made by one family
does NOT verify under the other. Therefore david-leads MUST NOT be "unified" by
naively delegating to szl-receipt: doing so would silently change the signed
bytes and break cosign verify-blob for every previously issued lead receipt.

This guard does three honest things — it does NOT change any signing behaviour:
  1. Proves app/receipts.py and app/consensus.py agree on the ASCII-decimal PAE
     (internal family consistency).
  2. Locks the divergence from szl-receipt's struct-packed PAE with an inline
     reference vector, so a future "just import szl-receipt" refactor fails here
     LOUDLY instead of shipping unverifiable receipts.
  3. Documents (and locks) the one internal inconsistency found in this repo:
     receipts._canon uses ensure_ascii=True while consensus.canonical_json uses
     ensure_ascii=False — identical for ASCII payloads (all lead fields today),
     divergent only for non-ASCII. Recorded here so it is a known, tested fact.
"""
from __future__ import annotations

import os
import struct
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app import receipts  # noqa: E402
from app import consensus  # noqa: E402

_PT = "application/vnd.szl.lead-receipt+json"
_BODY = b'{"a":1,"b":"c"}'


def _szl_receipt_reference_pae(payload_type: str, body: bytes) -> bytes:
    """The szl-receipt (struct-packed LE) PAE — inlined as a locked reference
    vector so this repo needs no dependency on szl-receipt to assert divergence.
    Mirrors szl_receipt/_canonical.py::pae verbatim."""
    def _enc(s: bytes) -> bytes:
        return struct.pack("<Q", len(s)) + s

    return b"DSSEv1 " + _enc(payload_type.encode("utf-8")) + b" " + _enc(body)


class AsciiDecimalPaeFamily(unittest.TestCase):
    def test_receipts_pae_is_ascii_decimal_dsse_spec(self):
        got = receipts._pae(_PT, _BODY)
        expected = (b"DSSEv1 " + str(len(_PT)).encode() + b" " + _PT.encode()
                    + b" " + str(len(_BODY)).encode() + b" " + _BODY)
        self.assertEqual(got, expected, "receipts._pae must be ASCII-decimal DSSE-v1 PAE")
        # No NUL bytes -> not a struct-packed length prefix.
        self.assertNotIn(b"\x00", got)

    def test_receipts_and_consensus_share_the_same_pae(self):
        self.assertEqual(
            receipts._pae(_PT, _BODY),
            consensus.pae(_PT, _BODY),
            "receipts.py and consensus.py must agree on the DSSE PAE (khipu family)")


class DivergesFromSzlReceipt(unittest.TestCase):
    def test_receipts_pae_differs_from_szl_receipt_struct_packed(self):
        ours = receipts._pae(_PT, _BODY)
        theirs = _szl_receipt_reference_pae(_PT, _BODY)
        self.assertNotEqual(
            ours, theirs,
            "SAFETY LOCK: if these ever match, someone re-based the receipt bus onto "
            "szl-receipt's struct-packed PAE — which breaks cosign verify-blob for "
            "existing lead receipts. Do NOT delegate to szl-receipt without a "
            "coordinated re-sign; update RECEIPT_BUS_EXEC.md before changing this.")
        # The szl-receipt form carries an 8-byte LE length prefix (NUL bytes present).
        self.assertIn(b"\x00", theirs)


class CanonicalJsonInternalConsistency(unittest.TestCase):
    def test_ascii_payloads_are_identical_across_both_canonicalisers(self):
        obj = {"lead_id": "L-1", "score": 87.5, "bucket": "A"}
        self.assertEqual(
            receipts._canon(obj), consensus.canonical_json(obj),
            "for ASCII payloads (all lead fields today) the two canonicalisers must agree")

    def test_non_ascii_divergence_is_a_known_locked_fact(self):
        # receipts._canon uses ensure_ascii=True (default); consensus.canonical_json
        # uses ensure_ascii=False. They diverge ONLY for non-ASCII. This is recorded
        # as a known, tested fact — not a fabricated claim of equivalence.
        obj = {"name": "café"}
        self.assertNotEqual(receipts._canon(obj), consensus.canonical_json(obj))
        self.assertIn(b"\\u00e9", receipts._canon(obj))   # escaped (ensure_ascii=True)
        self.assertIn(b"\xc3\xa9", consensus.canonical_json(obj))  # raw utf-8 (False)


class LocalSignerRoundTrips(unittest.TestCase):
    """The local (ASCII-decimal) signer must sign->verify against itself — i.e. the
    receipt bus is internally sound and cosign-family, independent of szl-receipt."""

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None)
                       for k in ("SZL_COSIGN_PRIVATE_PEM", "SZL_COSIGN_PUBLIC_PEM")}
        receipts.reset_chain()

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v
        receipts.reset_chain()

    def test_sign_then_verify_with_real_key(self):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec
        except Exception:  # pragma: no cover - stdlib-only runners skip
            self.skipTest("cryptography not installed; family/divergence locks above still run")
        key = ec.generate_private_key(ec.SECP256R1())
        os.environ["SZL_COSIGN_PRIVATE_PEM"] = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        os.environ["SZL_COSIGN_PUBLIC_PEM"] = key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        r = receipts.make_receipt(
            {"id": "L-1", "name": "Acme", "bucket": "A", "product": "commercial-auto"},
            [{"source": "SEC-EDGAR", "signal": "8-K", "public": True}],
            88.0, witness=False)
        self.assertTrue(r["signed"])
        self.assertEqual(receipts.verify_receipt(r)["verdict"], "VERIFIED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
