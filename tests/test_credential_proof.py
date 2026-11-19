from copy import deepcopy
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import credential_proof as engine


class CredentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.now = 1000
        cls.records, cls.trust, clauses = {}, {}, []
        for index, (value, unit) in enumerate(((18, "years"), (84, "points"))):
            issuer = f"issuer-{index}"
            key = Ed25519PrivateKey.generate()
            cls.trust[issuer] = key.public_key().public_bytes_raw().hex()
            record = engine.issue(issuer, {"measure": {"value": value, "unit": unit}}, 2000, key, now=cls.now)
            identifier = record["credential"]["manifest"]["id"]
            cls.records[identifier] = record
            clauses.append({"credential_id": identifier, "issuer": issuer, "attribute": "measure",
                            "unit": unit, "min": value - 1, "max": value + 1})
        cls.policy = {"schema": engine.POLICY, "audience": "reviewer", "nonce": "ab" * 32,
                      "expires": 1500, "clauses": clauses}
        cls.proof = engine.prove(cls.records, cls.policy, cls.trust, cls.now)

    def test_two_issuers_and_expiration(self):
        self.assertTrue(engine.verify(self.proof, self.policy, self.trust, self.now))
        self.assertFalse(engine.verify(self.proof, self.policy, self.trust, 1500))
        self.assertFalse(engine.verify(self.proof, self.policy, {}, self.now))
        self.assertTrue(all("openings" not in record for record in self.proof["credentials"].values()))

    def test_policy_binding_and_bad_witness(self):
        policy = deepcopy(self.policy)
        policy["nonce"] = "ff" * 32
        self.assertFalse(engine.verify({**self.proof, "policy": policy}, policy, self.trust, self.now))
        policy["clauses"][0]["min"] = policy["clauses"][0]["max"]
        with self.assertRaises(ValueError):
            engine.prove(self.records, policy, self.trust, self.now)
        policy = deepcopy(self.policy)
        policy["clauses"][0]["unit"] = "days"
        with self.assertRaises(ValueError):
            engine.prove(self.records, policy, self.trust, self.now)

    def test_signed_metadata_and_proof_order(self):
        proof = deepcopy(self.proof)
        proof["proofs"].reverse()
        self.assertFalse(engine.verify(proof, self.policy, self.trust, self.now))
        proof = deepcopy(self.proof)
        item = next(iter(proof["credentials"].values()))
        item["manifest"]["source_sha256"] = "ab" * 32
        self.assertFalse(engine.verify(proof, self.policy, self.trust, self.now))

    def test_interval_review_uses_only_valid_history(self):
        proposed = deepcopy(self.policy)
        proposed["clauses"][0]["min"] = 19
        proposed["clauses"][0]["max"] = 21
        result = engine.interval_review(proposed, [self.proof], self.trust, self.now)
        self.assertEqual(result[0]["previous"], (17, 19))
        self.assertEqual(result[0]["combined"], (19, 19))
        self.assertEqual(result[0]["possible_values"], 1)
        with self.assertRaises(ValueError):
            engine.interval_review(proposed, [{**self.proof, "proofs": []}], self.trust, self.now)
