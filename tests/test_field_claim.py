from hashlib import sha256
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import claim_nlp
import field_claim
import field_equality
from protocol import canonical


class ClaimTests(TestCase):
    def record(self, kind, value, unit=""):
        region = [0, 0, 0, 20, 20]
        item = {"label": "Registered field", "type": kind, "unit": unit,
                "value": value, "region": region}
        signer = Ed25519PrivateKey.generate()
        (record,), witnesses = field_equality.issue([item], {}, {"hide": [region]}, "aa" * 32, signer)
        field_equality.check_record(record, signer.public_key().public_bytes_raw().hex())
        return record, next(iter(witnesses.values()))

    def request(self, record, operator, *values):
        return {"field_id": record["field"]["id"], "record_sha256": sha256(canonical(record)).hexdigest(),
                "nonce": "ab" * 32, "operator": operator, "values": list(values)}

    def test_numeric_bounds_and_binding(self):
        record, witness = self.record("amount", "-5.55", "USD")
        for operator, values in (("ge", ["-5.55"]), ("lt", ["-5.54"]), ("between", ["-100", "-5.55"])):
            request = self.request(record, operator, *values)
            proof = field_claim.prove(witness, request)
            self.assertTrue(field_claim.verify(record, request, proof))
            self.assertFalse(field_claim.verify(record, dict(request, nonce="ba" * 32), proof))
            lower = self.request(record, operator, *[str(float(x) - 1) for x in values])
            self.assertFalse(field_claim.verify(record, lower, proof))
        self.assertIsNone(field_claim.prove(witness, self.request(record, "gt", "-5.55")))

    def test_clinical_whole_number_and_code(self):
        record, witness = self.record("integer", "18")
        request = self.request(record, "ge", "18")
        self.assertTrue(field_claim.verify(record, request, field_claim.prove(witness, request)))
        self.assertIsNone(field_claim.prove(witness, self.request(record, "lt", "18")))
        code, code_witness = self.record("code", "E11.9")
        equality = self.request(code, "eq", "e11.9")
        self.assertTrue(field_claim.verify(code, equality, field_claim.prove(code_witness, equality)))
        with self.assertRaises(ValueError):
            field_claim.prove(code_witness, self.request(code, "ge", "E11.9"))

    def test_model_output_validation(self):
        fields = [{"id": "a"}, {"id": "b"}]
        self.assertEqual(claim_nlp.decode('"field":2,"operator":"ge","values":["18"]', fields),
                         ("b", "ge", ["18"]))
        for raw in ('{"field":3,"operator":"ge","values":["18"]}', '{"status":"clarify"}', 'garbled'):
            with self.assertRaises(ValueError):
                claim_nlp.decode(raw, fields)

    def test_model_rejects_explicit_currency_mismatch(self):
        field = {"type": "amount", "unit": "USD"}
        claim_nlp.check_currency("Did the balance reach $7,000 USD?", field)
        with self.assertRaisesRegex(ValueError, "different currency"):
            claim_nlp.check_currency("Did the balance reach EUR 7,000?", field)

    def test_invented_threshold_is_rejected(self):
        field = {"type": "amount", "unit": "USD"}
        claim_nlp.check_thresholds("Was the balance at least $7,000?", field, ["7000"])
        claim_nlp.check_thresholds("Was the balance seven grand or more?", field, ["7000"])
        silent = "What was the balance?"
        altered = "Was the balance greater than $700?"
        for question in (silent, altered):
            with self.assertRaisesRegex(ValueError, "does not clearly supply"):
                claim_nlp.check_thresholds(question, field, ["7000"])
