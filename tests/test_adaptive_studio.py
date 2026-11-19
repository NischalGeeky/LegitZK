import base64
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
import fitz

import adaptive_mask as mask
import adaptive_proof as zk
import field_detector as ai
import pdf_redaction as core
import pdf_studio


def document_pdf():
    with fitz.open() as pdf:
        page = pdf.new_page(width=240, height=200)
        page.insert_text((20, 35), "Account Number: 123456789")
        page.insert_text((20, 55), "Deposit routing record: 928374651")
        page.insert_text((20, 90), "Settlement Amount: USD 7,500")
        page.insert_text((20, 125), "disclosure@example.test")
        return pdf.tobytes()


class PlannerTests(unittest.TestCase):
    def test_adaptive_reduces_cost_at_same_precision(self):
        dims = [[70, 43]]
        boxes = [[0, 4, 5, 12, 15]]
        keep = [[0, 20, 5, 25, 15]]
        cut, stats = mask.compile_cut(dims, boxes, keep, 55, 100)
        _, fine = mask.compile_cut(dims, boxes, keep, 55, 100, "fixed8")
        self.assertEqual(stats["redacted_pixels"], fine["redacted_pixels"])
        self.assertLess(stats["tiles"], fine["tiles"])
        self.assertEqual(sum((r-x)*(b-y) for _,x,y,r,b in
                             (mask.rectangle(node, dims) for node, _ in cut)), 70*43)
        with self.assertRaisesRegex(ValueError, "share a 32px"):
            mask.compile_cut(dims, boxes, keep, 55, 100, "fixed32")
        with self.assertRaisesRegex(ValueError, "tile limit"):
            mask.compile_cut(dims, boxes, keep, 55, 1)
        with self.assertRaisesRegex(ValueError, "area budget"):
            mask.compile_cut(dims, boxes, keep, 1, 100)

    def test_fine_conflict_and_protocol_shape(self):
        with self.assertRaisesRegex(ValueError, "share a 8px"):
            mask.compile_cut([[64,64]], [[0,0,0,2,2]], [[0,3,3,6,6]], 90, 100)
        with self.assertRaises(ValueError):
            mask.regions([[0,0,0,True,6]], [[64,64]])


class AdaptiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = Ed25519PrivateKey.generate()
        cls.source = zk.issue(document_pdf(), key)
        cls.receipt = cls.source[0]
        cls.key = key.public_key().public_bytes_raw().hex()
        cls.req = zk.request(cls.receipt, "Auditor", 25, [[0,128,29,190,49]], [[0,0,0,64,24]])
        cls.pkg, cls.pdf, _ = zk.prove(cls.source, cls.req)

    def test_round_trip_and_signed_frontier(self):
        self.assertTrue(zk.verify(self.pkg, self.receipt, self.req, self.key, self.pdf)["valid"])
        forged = deepcopy(self.pkg)
        layer = next(layer for layer in forged["siblings"] if layer)
        layer[0] = "00" * 32
        with self.assertRaisesRegex(ValueError, "commitments"):
            zk.verify(forged, self.receipt, self.req, self.key, self.pdf)

    def test_exact_pdf_and_other_request(self):
        with self.assertRaisesRegex(ValueError, "canonical export"):
            zk.verify(self.pkg, self.receipt, self.req, self.key, self.pdf + b"x")
        change = {**self.req, "audience": "Another auditor"}
        with self.assertRaisesRegex(ValueError, "proof does not verify"):
            zk.verify({**self.pkg, "request":change}, self.receipt, change, self.key, self.pdf)

    def test_change_public_pixels_with_updated_transcript(self):
        import base64
        import hashlib
        import zlib

        package = deepcopy(self.pkg)
        pages = core.read_pages(package["pages"], self.receipt["manifest"]["pages"])
        w, h, rgb = pages[0]
        changed = bytes([rgb[0] ^ 1]) + rgb[1:]
        pages[0] = (w, h, changed)
        pdf = core.render_export(pages)
        package["pdf_sha256"] = hashlib.sha256(pdf).hexdigest()
        package["pages"] = [base64.b64encode(zlib.compress(changed)).decode()]
        cut, _ = zk.plan(self.req, self.receipt["manifest"])
        _, hidden = zk.geometry(cut, self.receipt["manifest"]["pages"])
        openings = [self.source[4][self.source[2][node]] for node, _ in cut]
        header = {k:v for k,v in package.items() if k != "proof"}
        package["proof"] = core.make_proof(core.transcript(header,pages), package["commits"], openings, hidden)
        with self.assertRaisesRegex(ValueError, "proof does not verify"):
            zk.verify(package, self.receipt, self.req, self.key, pdf)

    def test_detector_finds_custom_phrase_without_exporting_text(self):
        raw = document_pdf()
        result = ai.find(ai.native_lines(raw, self.source[1]), self.source[1], ["Settlement Amount =>"])
        names = {item["category"] for item in result["suggestions"]}
        self.assertTrue({"custom_field", "account", "email"} <= names)
        self.assertNotIn("123456789", str(result))
        self.assertNotIn("7,500", str(result))
        self.assertEqual(ai.classify("deposit account", "123456789"), ("account", "model"))


class AdaptiveApiTests(unittest.TestCase):
    def test_local_review_to_verification(self):
        headers = {"x-legitzk-action": "1"}
        with TemporaryDirectory() as temp, patch.dict("os.environ", {"LEGITZK_PDF_HOME": temp}):
            with TestClient(pdf_studio.app) as client:
                upload = client.post("/api/v2/upload", content=document_pdf(), headers=headers)
                self.assertEqual(upload.status_code, 200, upload.text)
                data = upload.json()
                headers["x-legitzk-workspace"] = data["workspace"]
                detect = client.post("/api/v2/detect", headers=headers,
                                     json={"custom": ["Settlement Amount =>"], "ocr": False})
                box = next(item["region"] for item in detect.json()["suggestions"]
                           if item["category"] == "custom_field")
                plan = client.post("/api/v2/request", headers=headers,
                                   json={"audience":"Reviewer","hide":[box],"keep":[],"tile_limit":1000,"max_percent":30})
                self.assertEqual(plan.status_code, 200, plan.text)
                req = plan.json()["request"]
                issued = client.post("/api/v2/prove", headers=headers, json={"request":req})
                self.assertEqual(issued.status_code, 200, issued.text)
                pdf = issued.json()
                checked = client.post("/api/verify", headers=headers,
                                      json={"package":pdf["proof_package"],"receipt":data["receipt"],
                                            "request":req,"key":client.get("/api/key").json(),"pdf":pdf["pdf_base64"]})
                self.assertTrue(checked.json()["valid"], checked.text)
                reference = {"package":pdf["proof_package"], "receipt":data["receipt"], "request":req,
                             "key":client.get("/api/key").json(), "pdf":pdf["pdf_base64"]}
                demo = client.post("/api/compare", headers=headers,
                                   json={"reference":reference,"candidate":None,"demo":True})
                self.assertEqual(demo.status_code, 200, demo.text)
                self.assertEqual(demo.json()["status"], "differences")
                self.assertGreater(demo.json()["changes"][0]["changed_pixels"], 0)
                self.assertTrue(demo.json()["preview"]["png"])
                candidate = demo.json()["candidate_pdf"]
                rejected = client.post("/api/verify", headers=headers, json={**reference,"pdf":candidate})
                self.assertEqual(rejected.status_code, 400)
                identical = client.post("/api/compare", headers=headers,
                                        json={"reference":reference,"candidate":reference["pdf"],"demo":False})
                self.assertEqual(identical.json()["status"], "identical")
                with fitz.open(stream=base64.b64decode(reference["pdf"]), filetype="pdf") as document:
                    document.set_metadata({"title":"Different metadata"})
                    changed_meta = base64.b64encode(document.tobytes()).decode()
                metadata = client.post("/api/compare", headers=headers,
                                       json={"reference":reference,"candidate":changed_meta,"demo":False})
                self.assertEqual(metadata.json()["status"], "byte_difference_only", metadata.text)
                failure = client.post("/api/compare", headers=headers,
                                      json={"reference":{**reference,"pdf":candidate},"candidate":None,"demo":True})
                self.assertEqual(failure.status_code, 400)
