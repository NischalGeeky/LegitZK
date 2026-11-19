from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

import fitz

import exposure
import field_detector
import forensic_review
import pdf_redaction as core
import privacy_review


def document(score=78):
    with fitz.open() as pdf:
        page = pdf.new_page(width=440, height=250)
        for y, text in (
            (30, "Name: Avery Morgan"),
            (60, "A. Morgan attended"),
            (90, "Avery Morgan"),
            (120, "Visit date: 2025-05-15"),
            (150, "Age: 40 years and 2 months"),
            (180, f"Heart rate: {score}"),
            (210, "Account number: 450827316"),
        ):
            page.insert_text((24, y), text, fontsize=16)
        return pdf.tobytes()


class PrivacyReviewTests(unittest.TestCase):
    def test_grouping_and_inference(self):
        raw = document()
        pages = core.render_source(raw)
        lines = field_detector.native_lines(raw, pages)
        found = field_detector.find(lines, pages, [], financial=True)["suggestions"]
        people = [item for item in found if item["category"] == "person_name"]
        self.assertEqual(len(people), 3)
        self.assertEqual(len({item["group"] for item in people}), 1)
        self.assertEqual(sum(item["method"] == "possible_variant" for item in people), 1)
        self.assertTrue(any(item["category"] == "account" and item["group"] for item in found))
        self.assertEqual(privacy_review.plan_review(lines, [])[0]["estimated_month"], "1985-03")
        self.assertEqual(privacy_review.plan_review(lines, [[0, 0, 120, 600, 190]]), [])

    def test_complementary_masks(self):
        with TemporaryDirectory() as home:
            history = exposure.ExposureHistory(Path(home) / "history.sqlite", bytes(32))
            manifest = {"pages": [[80, 80]], "source_sha256": "ab", "profile": "test"}
            policy = {"audience": "Reviewer"}
            history.evaluate(manifest, policy, [[0, 0, 0, 40, 80]], record=True)
            groups = [(None, "bank_account", [[[0, 20, 20, 60, 40]]])]
            result = history.evaluate(manifest, policy, [[0, 40, 0, 80, 80]], groups=groups)
            self.assertEqual(result["reconstructed_fields"], [{"category": "bank_account", "page": 1}])

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is not installed")
    def test_real_ocr_leak_and_value_change(self):
        raw = document()
        pages = core.render_source(raw)
        native = field_detector.native_lines(raw, pages)
        matches = field_detector.find(native, pages, [])["suggestions"]
        boxes = [item["region"] for item in matches if item["method"] == "labeled_identifier"]
        first = core.render_export(core.redact(pages, boxes[:1], [0]))
        report = privacy_review.leak_scan(first, native, boxes[:1])
        self.assertEqual(report["status"], "findings", report)
        self.assertEqual(report["findings"][0]["category"], "person_name")
        fully_masked = core.render_export(core.redact(pages, boxes, range(len(boxes))))
        self.assertEqual(privacy_review.leak_scan(fully_masked, native, boxes)["status"], "no_matches")
        reference = core.render_export(pages)
        suspect = core.render_export(core.render_source(document(96)))
        visual = forensic_review.disclosure_compare.compare(reference, suspect, {}, {})
        compared = forensic_review.compare_ocr(reference, suspect, visual)
        field, = compared["changes"]
        self.assertEqual((field["field"], field["baseline_value"], field["candidate_value"]),
                         ("Heart rate", "78", "96"))

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is not installed")
    def test_export_endpoint_blocks_known_leak(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        import pdf_studio

        with TemporaryDirectory() as home, patch.dict("os.environ", {"LEGITZK_PDF_HOME": home}):
            with TestClient(pdf_studio.app) as client:
                headers = {"x-legitzk-action": "1"}
                uploaded = client.post("/api/v2/upload", content=document(), headers=headers)
                self.assertEqual(uploaded.status_code, 200, uploaded.text)
                headers["x-legitzk-workspace"] = uploaded.json()["workspace"]
                suggestions = client.post("/api/v2/detect", headers=headers,
                                          json={"custom": [], "ocr": False}).json()["suggestions"]
                names = [item["region"] for item in suggestions
                         if item["category"] == "person_name" and item["method"] == "labeled_identifier"]
                for masks, expected in ((names[:1], "findings"), (names, "no_matches")):
                    plan = client.post("/api/v2/request", headers=headers,
                                       json={"audience": "Reviewer", "hide": masks, "keep": []})
                    self.assertEqual(plan.status_code, 200, plan.text)
                    result = client.post("/api/v2/export", headers=headers,
                                         json={"request": plan.json()["request"], "scan_export": True})
                    self.assertEqual(result.status_code, 200, result.text)
                    self.assertEqual(result.json()["leak_scan"]["status"], expected)
                    self.assertEqual("pdf_base64" in result.json(), expected == "no_matches")
