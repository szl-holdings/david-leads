# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads receipt-honesty guard
"""
test_receipt_honesty.py — stdlib-only, no-network, no-dep honesty guard for the
receipt / provenance layer (app/receipts.py + app/receipt_lake.py).

Locks in the SZL honesty doctrine for the receipt emitter:
  * energy is measured-or-UNAVAILABLE — a receipt NEVER carries a fabricated joule.
  * signatures are real-or-UNSIGNED — a receipt NEVER carries a fabricated base64
    signature literal (a signature only ever comes from a real key.sign()).
  * every served "verified" claim resolves — verify_receipt re-derives the payload
    hash and reports VERIFIED only when the checks genuinely pass; tamper is rejected.

Runs on the Python standard library only (unittest) so CI needs no network and no
third-party deps. The signed path (which needs the `cryptography` lib + a real key)
is exercised opportunistically and skipped when the lib is absent — the point of
this guard is that the UNSIGNED path is honest and no value is ever fabricated.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import unittest
from copy import deepcopy

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app import receipts  # noqa: E402
from app import receipt_lake  # noqa: E402

_RECEIPTS_SRC = os.path.join(_REPO_ROOT, "app", "receipts.py")
_LAKE_SRC = os.path.join(_REPO_ROOT, "app", "receipt_lake.py")

# The only honest string a non-measured quantity may carry (doctrine).
_HONEST_UNAVAILABLE = "UNAVAILABLE"

# Keys that would carry an energy quantity if the receipt ever bound one.
_ENERGY_KEY = re.compile(r"(?i)(joule|energy|kwh|watt)")


def _sample_lead():
    return {"id": "L-1001", "name": "Acme Freight Co", "bucket": "A", "product": "commercial-auto"}


def _sample_signals():
    return [
        {"source": "SEC-EDGAR", "signal": "8-K filed", "public": True},
        {"source": "state-WARN", "signal": "layoff notice", "public": True},
    ]


def _walk(obj, path="$"):
    """Yield (json-path, key, value) for every mapping entry in a nested structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = f"{path}.{k}"
            yield (child, k, v)
            yield from _walk(v, child)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


class ReceiptEnergyHonesty(unittest.TestCase):
    def setUp(self):
        receipts.reset_chain()
        # Ensure no signing key leaks in from the environment for the honest-default path.
        self._saved = {k: os.environ.pop(k, None)
                       for k in ("SZL_COSIGN_PRIVATE_PEM", "SZL_COSIGN_PUBLIC_PEM")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v
        receipts.reset_chain()

    def _assert_no_fabricated_joule(self, receipt):
        for jpath, key, value in _walk(receipt):
            if _ENERGY_KEY.search(str(key)):
                # An energy field is allowed ONLY as the honest literal "UNAVAILABLE"
                # or a mapping that explicitly records a real measurement — never a
                # bare fabricated number.
                if isinstance(value, bool):
                    continue
                self.assertNotIsInstance(
                    value, (int, float),
                    msg=f"fabricated energy value at {jpath}: {value!r} "
                        f"(must be measured-or-UNAVAILABLE, never a bare joule literal)")
                if isinstance(value, str):
                    self.assertEqual(
                        value, _HONEST_UNAVAILABLE,
                        msg=f"energy string at {jpath} must be 'UNAVAILABLE', got {value!r}")

    def test_lead_receipt_carries_no_fabricated_joule(self):
        r = receipts.make_receipt(_sample_lead(), _sample_signals(), 87.5, witness=False)
        self._assert_no_fabricated_joule(r)

    def test_brief_receipt_carries_no_fabricated_joule(self):
        brief = {
            "lead_id": "L-1001",
            "lead_name": "Acme Freight Co",
            "score": 91.0,
            "bucket": "A",
            "freshness_state": "fresh",
            "parts": [
                {"key": "WHO", "body": "Acme Freight Co", "citations": [{"label": "SEC-EDGAR"}]},
            ],
        }
        r = receipts.make_brief_receipt(brief, _sample_signals(), witness=False)
        self._assert_no_fabricated_joule(r)


class ReceiptSignatureHonesty(unittest.TestCase):
    def setUp(self):
        receipts.reset_chain()
        self._saved = {k: os.environ.pop(k, None)
                       for k in ("SZL_COSIGN_PRIVATE_PEM", "SZL_COSIGN_PUBLIC_PEM")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v
        receipts.reset_chain()

    def test_unsigned_default_is_honestly_unsigned(self):
        r = receipts.make_receipt(_sample_lead(), _sample_signals(), 42.0, witness=False)
        self.assertFalse(r["signed"], "no key present → receipt must not claim signed")
        self.assertIsNone(r["signature"], "no key present → signature must be None, never fabricated")
        self.assertIn("UNSIGNED", r["signature_status"])

    def test_signature_only_ever_from_a_real_key(self):
        # With no private key in the env, the signer must return None — never a literal.
        self.assertIsNone(receipts._try_sign(b"DSSEv1 test payload"))

    def test_verify_does_not_claim_verified_signature_without_material(self):
        r = receipts.make_receipt(_sample_lead(), _sample_signals(), 55.0, witness=False)
        # Unsigned receipt: no signature check is added, and the honest checks resolve.
        verdict = receipts.verify_receipt(r)
        sig_checks = [c for c in verdict["checks"] if "signature" in c["check"].lower()]
        self.assertEqual(sig_checks, [], "unsigned receipt must not assert a signature check")

    def test_signed_path_is_a_real_signature_when_key_present(self):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec
        except Exception:  # pragma: no cover - stdlib-only environments skip this
            self.skipTest("cryptography not installed; unsigned honesty is covered above")
        key = ec.generate_private_key(ec.SECP256R1())
        priv_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        pub_pem = key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        os.environ["SZL_COSIGN_PRIVATE_PEM"] = priv_pem
        os.environ["SZL_COSIGN_PUBLIC_PEM"] = pub_pem
        r = receipts.make_receipt(_sample_lead(), _sample_signals(), 99.0, witness=False)
        self.assertTrue(r["signed"])
        self.assertIsNotNone(r["signature"])
        # The signature must genuinely verify against the payload — not a fabricated literal.
        verdict = receipts.verify_receipt(r)
        self.assertEqual(verdict["verdict"], "SIGNATURE_VERIFIED")
        self.assertEqual(verdict["signature_state"], "VERIFIED")
        self.assertTrue(any(c["check"].startswith("ECDSA-P256 signature verifies") and c["pass"]
                            for c in verdict["checks"]))


class ReceiptVerifiedClaimResolves(unittest.TestCase):
    def setUp(self):
        receipts.reset_chain()
        self._saved = {k: os.environ.pop(k, None)
                       for k in ("SZL_COSIGN_PRIVATE_PEM", "SZL_COSIGN_PUBLIC_PEM")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v
        receipts.reset_chain()

    def test_verified_claim_resolves_for_untampered_receipt(self):
        r = receipts.make_receipt(_sample_lead(), _sample_signals(), 73.0, witness=False)
        verdict = receipts.verify_receipt(r)
        self.assertEqual(verdict["verdict"], "HASH_INTEGRITY_VERIFIED")
        self.assertEqual(verdict["signature_state"], "UNSIGNED")
        self.assertEqual(verdict["recomputed_hash"], r["payload_sha256"])
        self.assertTrue(all(c["pass"] for c in verdict["checks"]))

    def test_tamper_is_rejected(self):
        r = receipts.make_receipt(_sample_lead(), _sample_signals(), 73.0, witness=False)
        r["payload"]["score"] = 100.0  # tamper: inflate the served score
        verdict = receipts.verify_receipt(r)
        self.assertEqual(verdict["verdict"], "FAILED")
        hash_check = next(c for c in verdict["checks"] if "hash re-derives" in c["check"])
        self.assertFalse(hash_check["pass"])

    def test_brief_receipt_derives_fabricated_signal_count(self):
        brief = {
            "lead_id": "L-1001",
            "lead_name": "Acme Freight Co",
            "parts": [],
        }
        signals = _sample_signals() + [{
            "source": "synthetic-fallback",
            "signal": "invented",
            "public": True,
            "fabricated": True,
        }]
        receipt = receipts.make_brief_receipt(brief, signals, witness=False)
        self.assertEqual(receipt["payload"]["fabricated_signals"], 1)
        verdict = receipts.verify_receipt(receipt)
        self.assertEqual(verdict["verdict"], "FAILED")
        fabricated = next(
            check for check in verdict["checks"]
            if check["check"] == "Zero fabricated signals declared"
        )
        self.assertFalse(fabricated["pass"])

    def test_invented_predecessor_is_not_claimed_as_verified(self):
        receipt = receipts.make_receipt(
            _sample_lead(),
            _sample_signals(),
            73.0,
            witness=False,
        )
        forged = deepcopy(receipt)
        forged["payload"]["prev_receipt_hash"] = "f" * 64
        forged_hash = hashlib.sha256(receipts._canon(forged["payload"])).hexdigest()
        forged["payload_sha256"] = forged_hash
        forged["id"] = "rcpt_" + forged_hash[:16]

        verdict = receipts.verify_receipt(forged)

        self.assertEqual(verdict["verdict"], "HASH_INTEGRITY_VERIFIED")
        self.assertEqual(verdict["chain_state"], "UNVERIFIED_PREDECESSOR")
        self.assertFalse(
            any(
                check["pass"] is True and "predecessor" in check["check"].lower()
                and "structurally" not in check["check"].lower()
                for check in verdict["checks"]
            )
        )

    def test_supplied_predecessor_must_rederive_and_match(self):
        previous = receipts.make_receipt(
            _sample_lead(),
            _sample_signals(),
            70.0,
            witness=False,
        )
        current = receipts.make_receipt(
            {**_sample_lead(), "id": "L-1002"},
            _sample_signals(),
            71.0,
            witness=False,
        )
        verified = receipts.verify_receipt(current, previous_receipt=previous)
        self.assertEqual(verified["chain_state"], "VERIFIED")

        wrong = deepcopy(previous)
        wrong["payload"]["score"] = 100.0
        failed = receipts.verify_receipt(current, previous_receipt=wrong)
        self.assertEqual(failed["verdict"], "FAILED")
        self.assertEqual(failed["chain_state"], "FAILED")


class ReceiptLakeHonesty(unittest.TestCase):
    def setUp(self):
        receipt_lake.reset()

    def tearDown(self):
        receipt_lake.reset()

    def test_lake_stores_only_real_appended_receipts(self):
        self.assertEqual(receipt_lake.size(), 0)
        r = receipts.make_receipt(_sample_lead(), _sample_signals(), 60.0, witness=False)
        stored = receipt_lake.append(r)
        self.assertEqual(stored, r)
        self.assertEqual(receipt_lake.size(), 1)
        self.assertEqual(receipt_lake.all()[0], r)


class SourceLevelHonestyGreps(unittest.TestCase):
    """Static 'honesty grep' over the receipt-layer source — no fabricated literals."""

    def _read(self, path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    def test_no_hardcoded_energy_joule_literal(self):
        for path in (_RECEIPTS_SRC, _LAKE_SRC):
            src = self._read(path)
            offenders = re.findall(
                r'(?i)["\'](?:joules?|energy|kwh|watt[_\-]?hours?)["\']\s*:\s*[0-9]', src)
            self.assertEqual(
                offenders, [],
                msg=f"{path} hardcodes an energy/joule number: {offenders} "
                    f"(doctrine: measured-or-UNAVAILABLE, never a fabricated joule)")

    def test_signature_is_produced_only_via_real_crypto(self):
        src = self._read(_RECEIPTS_SRC)
        # A real signature comes from key.sign(...) then base64 of that bytes output.
        self.assertIn("key.sign(", src)
        self.assertIn("base64.b64encode(sig)", src)
        # The honest fallback label must exist for the no-key path.
        self.assertIn("UNSIGNED", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
