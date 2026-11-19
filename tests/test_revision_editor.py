from base64 import b64encode
from hashlib import sha256
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

import forensic_review
import pdf_redaction as core
import pdf_studio
from protocol import canonical


class RevisionEditorTests(TestCase):
    def test_native_and_raster_changes_are_detected_against_saved_receipt(self):
        baseline = forensic_review.sample_revision(78)
        raster = core.render_export(core.render_source(baseline))
        action = {"x-legitzk-action": "1"}
        with TemporaryDirectory() as home, patch.dict("os.environ", {"LEGITZK_PDF_HOME": home}):
            with TestClient(pdf_studio.app) as client:
                for original, box in ((baseline, None), (raster, [116, 105, 157, 127])):
                    with self.subTest(box=box):
                        upload = client.post("/api/v2/upload", content=original, headers=action)
                        self.assertEqual(upload.status_code, 200, upload.text)
                        saved = upload.json()["receipt"]
                        edit = {"page": 1, "old": "78", "replacement": "96", "box": box}
                        response = client.post("/api/v2/forensics/edit-copy", content=original, headers={
                            **action, "x-legitzk-edit": b64encode(canonical(edit)).decode()})
                        self.assertEqual(response.status_code, 200, response.text)
                        candidate = response.content
                        self.assertNotEqual(sha256(original).digest(), sha256(candidate).digest())
                        with fitz.open(stream=candidate, filetype="pdf") as doc:
                            text = doc[0].get_text()
                        if box is None:
                            self.assertIn("96", text)
                            self.assertNotIn("78", text)
                        else:
                            self.assertFalse(text.strip())
                        result = client.post("/api/v2/forensics/compare", content=original + candidate, headers={
                            **action, "x-legitzk-baseline-length": str(len(original)),
                            "x-legitzk-expected-receipt": b64encode(canonical(saved)).decode()})
                        self.assertEqual(result.status_code, 200, result.text)
                        self.assertFalse(result.json()["candidate_matches_signed_bytes"])
                        self.assertEqual(result.json()["visual"]["status"], "differences")
