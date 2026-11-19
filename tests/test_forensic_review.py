from base64 import b64encode
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from protocol import canonical
import pdf_studio


def sample(value):
    with fitz.open() as doc:
        page = doc.new_page(width=250, height=250)
        page.insert_text((20, 50), f"Review code: {value}")
        return doc.tobytes()


class SourceForensicsTests(TestCase):
    def test_signed_baseline_and_candidate_differences(self):
        reference, candidate = sample("ABC-01"), sample("DEF-02")
        action = {"x-legitzk-action": "1"}
        with TemporaryDirectory() as home, patch.dict("os.environ", {"LEGITZK_PDF_HOME": home}):
            with TestClient(pdf_studio.app) as client:
                upload = client.post("/api/v2/upload", content=reference, headers=action)
                self.assertEqual(upload.status_code, 200, upload.text)
                receipt = upload.json()["receipt"]

                def compare(before, after, expected, include_values="0"):
                    return client.post("/api/v2/forensics/compare", content=before + after, headers={
                        **action, "x-legitzk-baseline-length": str(len(before)),
                        "x-legitzk-expected-receipt": b64encode(canonical(expected)).decode(),
                        "x-legitzk-include-values": include_values,
                    })

                clean = compare(reference, reference, receipt)
                self.assertEqual(clean.status_code, 200, clean.text)
                self.assertTrue(clean.json()["candidate_matches_signed_bytes"])

                response = compare(reference, candidate, receipt)
                self.assertEqual(response.status_code, 200, response.text)
                changed = response.json()
                self.assertEqual(changed["attribution"], "actor_unknown")
                self.assertFalse(changed["candidate_matches_signed_bytes"])
                self.assertEqual(changed["visual"]["status"], "differences")
                field, = changed["field_analysis"]["changes"]
                self.assertEqual(field["field"], "Review code")
                self.assertNotIn("baseline_value", field)
                self.assertNotIn("candidate_value", field)

                opt_in = compare(reference, candidate, receipt, "1").json()
                field = opt_in["field_analysis"]["changes"][0]
                self.assertEqual((field["baseline_value"], field["candidate_value"]), ("ABC-01", "DEF-02"))
                self.assertEqual(compare(candidate, reference, receipt).status_code, 400)
                self.assertEqual(compare(reference, candidate, {**receipt, "signature": "00" * 64}).status_code, 400)
                self.assertEqual(compare(reference, b"invalid", receipt).status_code, 400)

    def test_proof_studio_http_round_trip(self):
        from secrets import token_hex
        from time import time
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import credential_proof as engine

        key = Ed25519PrivateKey.generate()
        expiry = int(time()) + 300
        record = engine.issue("school", {"score": {"value": 84, "unit": "points"}}, expiry, key)
        cid = record["credential"]["manifest"]["id"]
        trust = {"school": key.public_key().public_bytes_raw().hex()}
        policy = {"schema": engine.POLICY, "audience": "reviewer", "nonce": token_hex(32), "expires": expiry,
                  "clauses": [{"credential_id": cid, "issuer": "school", "attribute": "score",
                               "unit": "points", "min": 75, "max": 100}]}
        action = {"x-legitzk-action": "1"}
        with TemporaryDirectory() as home, patch.dict("os.environ", {"LEGITZK_PDF_HOME": home}):
            with TestClient(pdf_studio.app) as client:
                made = client.post("/api/v2/claims/prove", headers=action,
                                   json={"records": [record], "policy": policy, "trust": trust})
                self.assertEqual(made.status_code, 200, made.text)
                result = {"presentation": made.json(), "policy": policy, "trust": trust}
                self.assertNotIn("openings", result["presentation"]["credentials"][cid])
                checked = client.post("/api/v2/claims/verify", headers=action, json=result)
                self.assertEqual(checked.json(), {"valid": True})
                result["policy"]["audience"] = "another-reviewer"
                self.assertEqual(client.post("/api/v2/claims/verify", headers=action, json=result).json(),
                                 {"valid": False})

    def test_synthetic_field_example_changes_native_data(self):
        from base64 import b64decode
        from io import BytesIO
        from zipfile import ZipFile

        with TemporaryDirectory() as home, patch.dict("os.environ", {"LEGITZK_PDF_HOME": home}):
            with TestClient(pdf_studio.app) as client:
                response = client.post("/api/v2/forensics/field-example", json={},
                                       headers={"x-legitzk-action": "1"})
                self.assertEqual(response.status_code, 200, response.text)
                example = response.json()
                report = example["investigation"]
                self.assertFalse(report["candidate_matches_signed_bytes"])
                field, = report["field_analysis"]["changes"]
                self.assertEqual((field["field"], field["baseline_value"], field["candidate_value"]),
                                 ("Review score", "78", "96"))
                with ZipFile(BytesIO(b64decode(example["zip_base64"]))) as files:
                    candidate = files.read("synthetic-modified.pdf")
                    with fitz.open(stream=candidate, filetype="pdf") as doc:
                        extracted = doc[0].get_text()
                    self.assertIn("Review score: 96", extracted)
                    self.assertNotIn("Review score: 78", extracted)
