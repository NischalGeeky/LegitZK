import base64
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

import field_equality
import pdf_studio
from test_adaptive_studio import document_pdf


class FieldEqualityTests(TestCase):
    def test_typed_matching(self):
        self.assertEqual(field_equality.typed("₹1,25,000.50", "amount", "INR"), "12500050")
        self.assertEqual(field_equality.typed("2026-11-20", "date", ""), "2026-11-20")
        self.assertEqual(field_equality.typed(" c50.9 ", "code", ""), "C50.9")
        for value, kind, unit in (("50,00", "amount", "INR"), ("2026-02-30", "date", ""),
                                  ("₹50,000", "amount", "USD")):
            with self.assertRaises(ValueError):
                field_equality.typed(value, kind, unit)

    def test_export_and_match_exchange(self):
        action = {"x-legitzk-action": "1"}
        with TemporaryDirectory() as home, patch.dict("os.environ", {"LEGITZK_PDF_HOME": home, "LEGITZK_PDF_TRUSTED_KEY": ""}):
            with TestClient(pdf_studio.app) as client:
                source = client.post("/api/v2/upload", content=document_pdf(), headers=action).json()
                owner = {**action, "x-legitzk-workspace": source["workspace"]}
                box = [0, 0, 0, 32, 32]
                plan = client.post("/api/v2/request", headers=owner,
                                   json={"audience": "Reviewer", "hide": [box], "keep": []}).json()
                item = {"label": "Private amount", "type": "amount", "unit": "INR", "value": "₹50,000.00", "region": box}
                exported = client.post("/api/v2/export", headers=owner,
                                       json={"request": plan["request"], "provable_fields": [item]})
                self.assertEqual(exported.status_code, 200, exported.text)
                pdf = base64.b64decode(exported.json()["pdf_base64"])
                archive = base64.b64decode(exported.json()["zip_base64"])
                report = client.post("/api/v2/inspect", content=archive + pdf, headers={
                    **action, "x-legitzk-zip-length": str(len(archive)),
                }).json()
                self.assertTrue(report["valid"], report)
                record, = report["provable_fields"]
                self.assertNotIn("value", record["field"])
                issuer = report["field_issuer"]
                root = "/api/v2/field-equality/"
                request = client.post(root + "request", headers=action,
                                      json={"record": record, "issuer": issuer, "candidate": "50000"}).json()
                denied = client.post(root + "prove", headers=owner, json={"request": request, "approved": False})
                self.assertEqual(denied.status_code, 400)
                response = client.post(root + "prove", headers=owner, json={"request": request, "approved": True})
                self.assertEqual(response.status_code, 200, response.text)
                proof = response.json()["proof"]
                verification = {"record": record, "issuer": issuer, "request": request, "proof": proof}
                self.assertTrue(client.post(root + "verify", headers=action, json=verification).json()["valid"])
                for modified in (dict(request, nonce="00" * 32), dict(request, candidate="50001")):
                    self.assertFalse(client.post(root + "verify", headers=action,
                                                 json=dict(verification, request=modified)).json()["valid"])
                incorrect = client.post(root + "prove", headers=owner,
                                        json={"request": dict(request, candidate="50001"), "approved": True})
                self.assertEqual(incorrect.json(), {"proof": None})
                swapped = client.post(root + "verify", headers=action, json=dict(
                    verification, record=dict(record, field=dict(record["field"], pdf_sha256="00" * 32))))
                self.assertEqual(swapped.status_code, 400)
                client.post("/api/close", headers=owner)
                self.assertEqual(client.post(root + "prove", headers=owner,
                                             json={"request": request, "approved": True}).status_code, 400)
