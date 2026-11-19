import base64
from io import BytesIO
import json

import fitz
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile

from fastapi.testclient import TestClient

import disclosure_bundle as bundle
import pdf_studio
from test_adaptive_studio import document_pdf


class BundleTests(TestCase):
    def test_export_integrity_and_metadata_demo(self):
        with TemporaryDirectory() as home, patch.dict("os.environ", {"LEGITZK_PDF_HOME": home}):
            with TestClient(pdf_studio.app) as client:
                action = {"x-legitzk-action": "1"}
                upload = client.post("/api/v2/upload", content=document_pdf(), headers=action)
                self.assertEqual(upload.status_code, 200, upload.text)
                source = upload.json()
                w, h = source["receipt"]["manifest"]["pages"][0]
                workspace = {**action, "x-legitzk-workspace": source["workspace"]}
                plan = client.post("/api/v2/request", headers=workspace,
                                   json={"audience": "Reviewer", "hide": [[0, 0, 0, w, h]], "keep": []})
                self.assertEqual(plan.status_code, 200, plan.text)
                self.assertEqual(plan.json()["metrics"]["page_percentages"], [100])
                export = client.post("/api/v2/export", headers=workspace, json={"request": plan.json()["request"]})
                self.assertEqual(export.status_code, 200, export.text)
                self.assertTrue(all(export.json()["sanitization"].values()))
                pdf, archive = (base64.b64decode(export.json()[key]) for key in ("pdf_base64", "zip_base64"))

                def inspect(proof_zip=archive, candidate=pdf, demo="", expected=None):
                    headers = {**action, "x-legitzk-zip-length": str(len(proof_zip)), "x-legitzk-demo": demo}
                    if expected is not None:
                        headers["x-legitzk-expected-receipt"] = base64.b64encode(json.dumps(expected).encode()).decode()
                    return client.post("/api/v2/inspect", content=proof_zip + candidate, headers=headers)

                clean = inspect()
                self.assertTrue(clean.json()["valid"], clean.text)
                record_plan = client.post("/api/v2/request", headers=workspace, json={
                    "audience": "Reviewer", "hide": [[0, 0, 0, 32, 32]], "keep": []}).json()
                self.assertEqual(record_plan["exposure"]["recorded_exports"], 0)
                recorded = client.post("/api/v2/export", headers=workspace, json={
                    "request": record_plan["request"], "record_exposure": True})
                self.assertEqual(recorded.status_code, 200, recorded.text)
                new_plan = client.post("/api/v2/request", headers=workspace, json={
                    "audience": "Reviewer", "hide": [[0, 32, 32, 64, 64]], "keep": []}).json()
                self.assertEqual(new_plan["exposure"]["recorded_exports"], 1)
                self.assertEqual(new_plan["exposure"]["pages"][0]["previously_visible_but_now_hidden"], 1024)

                self.assertEqual(set(clean.json()["files"].values()), {"match"})
                match = inspect(expected=source["receipt"]).json()
                self.assertTrue(match["valid"])
                self.assertEqual(match["source_match"], "match")
                with fitz.open(stream=document_pdf(), filetype="pdf") as edited_source:
                    edited_source[0].insert_text((30, 165), "Revised protected value")
                    replacement = client.post("/api/v2/upload", content=edited_source.tobytes(), headers=action).json()
                check = inspect(expected=replacement["receipt"]).json()
                self.assertTrue(check["proof_valid"])
                self.assertFalse(check["valid"])
                self.assertEqual(check["source_match"], "mismatch")
                self.assertEqual(set(check["files"].values()), {"match"})
                forged = {**source["receipt"], "signature": "00" * 64}
                self.assertEqual(inspect(expected=forged).status_code, 400)

                metadata = inspect(demo="metadata").json()
                self.assertEqual(metadata["comparison"]["status"], "byte_difference_only")
                changed_pdf = base64.b64decode(metadata["candidate_pdf"])
                changed = inspect(candidate=changed_pdf).json()
                self.assertFalse(changed["valid"])
                self.assertEqual(changed["files"][bundle.PDF], "changed")
                self.assertEqual(changed["comparison"]["changes"], [])
                visual = inspect(demo="visual").json()
                self.assertEqual(visual["comparison"]["status"], "differences")
                self.assertTrue(visual["comparison"]["preview"])
                with ZipFile(BytesIO(archive)) as original:
                    entries = {name: original.read(name) for name in original.namelist()}
                edited = BytesIO()
                with ZipFile(edited, "w") as rebuilt:
                    for name, raw in entries.items():
                        if name != bundle.FILES["receipt"]:
                            rebuilt.writestr(name, raw + b" " if name == bundle.FILES["request"] else raw)
                changed = inspect(edited.getvalue()).json()
                self.assertFalse(changed["valid"])
                self.assertEqual(changed["files"][bundle.FILES["request"]], "changed")
                self.assertEqual(changed["files"][bundle.FILES["receipt"]], "missing")
                self.assertEqual(changed["files"][bundle.FILES["package"]], "match")
                self.assertEqual(inspect(b"not a ZIP").status_code, 400)
