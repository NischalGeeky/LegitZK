import base64
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import fitz

import protocol as p
import rangeproof as zk


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = Ed25519PrivateKey.generate()
        cls.values = p.parse_json(Path("fixtures/contract.json").read_bytes())
        cls.trust = {"Test Lab": cls.key.public_key().public_bytes_raw().hex()}
        cls.now = 1780000000
        cls.record, cls.source = p.issue(cls.values, "Test Lab", cls.key, cls.now)
        cls.request = p.request_for(cls.record["manifest"]["id"], "Test Lab", 7000000, "auditor-a", False, cls.now)
        cls.package = p.present(cls.record, cls.request)

    def verify(self, package=None, request=None, trust=None, now=None):
        return p.verify(self.package if package is None else package,
                        self.request if request is None else request,
                        self.trust if trust is None else trust, self.now if now is None else now)

    def test_positive(self):
        self.assertTrue(self.verify()["valid"])
        self.assertEqual(sha256(self.source).hexdigest(), self.record["manifest"]["source_sha256"])

    def test_reject_forged_and_untrusted_signatures(self):
        forged = deepcopy(self.package)
        forged["signature"] = "00" * 64
        self.assertFalse(self.verify(forged)["valid"])
        self.assertFalse(self.verify(trust={})["valid"])
        forged = deepcopy(self.package)
        forged["manifest"]["amount_commitment"] = zk.commit(9000000, 10).hex()
        self.assertFalse(self.verify(forged)["valid"])

    def test_incorrect_openings_and_omission(self):
        for edit in ("remove", "replace", "add"):
            with self.subTest(edit=edit):
                package = deepcopy(self.package)
                if edit == "remove":
                    del package["disclosure"]["vendor"]
                elif edit == "replace":
                    package["disclosure"]["vendor"]["value"] = "Another vendor"
                else:
                    package["disclosure"]["bank_reference"] = {"value": "Added", "salt": "00" * 32}
                self.assertFalse(self.verify(package)["valid"])

    def test_context_swap_against_valid_new_request(self):
        for field, value in (("nonce", "01" * 32), ("audience", "auditor-b"), ("expires", self.now + 120)):
            with self.subTest(field=field):
                expected = deepcopy(self.request)
                expected["context"][field] = value
                package = deepcopy(self.package)
                package["request"] = expected
                result = self.verify(package, expected)
                self.assertEqual(result["checks"][-1], {"check":"Private threshold proof", "passed": False})

    def test_policy_transplant(self):
        for field, value in (("threshold", 1), ("visible", ["buyer", "effective_date", "service", "vendor"])):
            expected = deepcopy(self.request)
            expected["policy"][field] = value
            prepared = p.present(self.record, expected)
            prepared["proof"] = self.package["proof"]
            self.assertFalse(self.verify(prepared, expected)["valid"])

    def test_signed_source_swap(self):
        other, _ = p.issue(self.values, "Test Lab", self.key, self.now)
        expected = p.request_for(other["manifest"]["id"], "Test Lab", 7000000, "auditor-a", False, self.now)
        bundle = p.present(other, expected)
        bundle["proof"] = self.package["proof"]
        self.assertFalse(self.verify(bundle, expected)["valid"])

    def test_boundary_and_invalid_ranges(self):
        for amount, threshold in ((0, 0), (1, 1), (zk.MAX, zk.MAX), (zk.MAX, 0)):
            with self.subTest(amount=amount, threshold=threshold):
                commitment = zk.commit(amount, 1234)
                self.assertTrue(zk.verify(zk.prove(amount, 1234, threshold, bytes(32)), commitment, threshold, bytes(32)))
        for amount, threshold in ((0, 1), (zk.MAX + 1, 1), (-1, 0)):
            with self.subTest(amount=amount, threshold=threshold):
                with self.assertRaises(ValueError):
                    zk.prove(amount, 1234, threshold, bytes(32))

    def test_modified_proof_and_expiry(self):
        bundle = deepcopy(self.package)
        bundle["proof"][0][0] = "00" * 160
        self.assertFalse(self.verify(bundle)["valid"])
        self.assertFalse(self.verify(now=self.request["context"]["expires"])["valid"])
        self.assertFalse(self.verify(trust=[] )["valid"])

    def test_pdf_and_no_witness(self):
        raw = base64.b64decode(self.package["pdf"])
        with fitz.open(stream=raw, filetype="pdf") as pdf:
            text = pdf[0].get_text()
            self.assertIn(self.values["vendor"], text)
            self.assertNotIn(self.values["bank_reference"], text)
            self.assertNotIn(str(self.values["amount"]), text)
            self.assertNotIn(self.values["service"], text)
            self.assertFalse(pdf.embfile_names())
            self.assertIsNone(pdf[0].first_annot)
            self.assertNotIn(self.values["bank_reference"], str(pdf.metadata))
        serialized = p.canonical(self.package)
        self.assertNotIn(self.record["blind"].encode(), serialized)
        for key in ("bank_reference", "service"):
            self.assertNotIn(self.record["salts"][key].encode(), serialized)

    def test_modified_pdf_even_when_checksum_recomputed(self):
        with fitz.open(stream=base64.b64decode(self.package["pdf"]), filetype="pdf") as pdf:
            pdf.embfile_add("sample.txt", b"synthetic sample", filename="sample.txt")
            pdf[0].add_text_annot((50, 50), "synthetic annotation")
            changed = pdf.tobytes()
        package = deepcopy(self.package)
        package["pdf"] = base64.b64encode(changed).decode()
        package["pdf_sha256"] = sha256(changed).hexdigest()
        self.assertEqual(self.verify(package)["checks"][-1]["check"], "Disclosure PDF")

    def test_duplicate_json_keys(self):
        for invalid in ('{"x":0,"x":1}', '{"x":NaN}'):
            with self.assertRaises(ValueError):
                p.parse_json(invalid)
