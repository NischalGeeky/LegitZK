import base64
from copy import deepcopy
from hashlib import sha256
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zlib

import fitz
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

import pdf_redaction as p
import pdf_studio


def sample_pdf():
    with fitz.open() as pdf:
        for label in ("first", "second"):
            page = pdf.new_page(width=240, height=180)
            page.insert_text((32, 32), "CONFIDENTIAL reference 042")
            page.insert_text((32, 120), "Visible letter " + label)
        pdf.set_metadata({"author": "PRIVATE AUTHOR"})
        pdf.embfile_add("internal.txt", b"PRIVATE ATTACHMENT")
        pdf[0].add_text_annot((150, 140), "PRIVATE ANNOTATION")
        return pdf.tobytes()


class ProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = Ed25519PrivateKey.generate()
        cls.trust = cls.key.public_key().public_bytes_raw().hex()
        cls.source = p.issue_source(sample_pdf(), cls.key)
        cls.receipt = cls.source[0]
        cls.request = p.new_request(cls.receipt, 40, [5], "External reviewer")
        cls.package, cls.pdf = p.present(cls.source, cls.request, [0, 1, 2])
        cls.sites = p.tile_sites(cls.receipt["manifest"]["pages"])

    def test_proof_export(self):
        result = p.verify(self.package, self.receipt, self.request, self.trust, self.pdf)
        self.assertEqual(result["pages"], 2)
        self.assertTrue(result["pdf_checked"])
        self.assertEqual(len(bytes.fromhex(self.package["proof"])), 160)
        with fitz.open(stream=self.pdf) as pdf:
            self.assertFalse(pdf.embfile_names())
            self.assertNotEqual(pdf.metadata["author"], "PRIVATE AUTHOR")
            for page in pdf:
                self.assertEqual(page.get_text(), "")
                self.assertIsNone(page.first_annot)

    def test_visible_and_hidden_pixels(self):
        pages = p.read_pages(self.package["pages"], self.receipt["manifest"]["pages"])
        for index, (i, *rect) in enumerate(self.sites):
            tile = p.read_tile(pages[i][2], pages[i][0], rect)
            if index in self.package["mask"]:
                self.assertFalse(any(tile))
            else:
                self.assertEqual(tile, p.read_tile(self.source[1][i][2], pages[i][0], rect))

    def test_protected_and_budget(self):
        with self.assertRaisesRegex(ValueError, "protected"):
            p.present(self.source, self.request, [5])
        request = p.new_request(self.receipt, 1, [], "Reviewer")
        with self.assertRaisesRegex(ValueError, "budget"):
            p.present(self.source, request, [1])

    def test_request_transplant(self):
        swapped = deepcopy(self.request)
        swapped["nonce"] = "01" * 32
        swapped["audience"] = "Other reviewer"
        package = {**self.package, "request": swapped}
        with self.assertRaisesRegex(ValueError, "proof"):
            p.verify(package, self.receipt, swapped, self.trust, self.pdf)

    def test_changed_pixels_reject_even_with_fresh_transcript(self):
        for index, pattern in ((0, "solid black"), (6, "proof")):
            with self.subTest(tile=index):
                pkg = deepcopy(self.package)
                pages = p.read_pages(pkg["pages"], self.receipt["manifest"]["pages"])
                raw = bytearray(pages[0][2])
                _, x, y, _, _ = self.sites[index]
                raw[(y * pages[0][0] + x) * 3] ^= 255
                pages[0] = (*pages[0][:2], bytes(raw))
                pdf = p.render_export(pages)
                pkg["pdf_sha256"] = sha256(pdf).hexdigest()
                pkg["pages"][0] = base64.b64encode(zlib.compress(raw)).decode()
                body = {k: v for k, v in pkg.items() if k != "proof"}
                pkg["proof"] = p.make_proof(p.transcript(body, pages), pkg["commits"], self.source[3], set(pkg["mask"]))
                with self.assertRaisesRegex(ValueError, pattern):
                    p.verify(pkg, self.receipt, self.request, self.trust, pdf)

    def test_substituted_bytes_commitments_and_key(self):
        with self.assertRaisesRegex(ValueError, "canonical"):
            p.verify(self.package, self.receipt, self.request, self.trust, self.pdf + b"other")
        with self.assertRaisesRegex(ValueError, "signature"):
            key = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
            p.verify(self.package, self.receipt, self.request, key, self.pdf)
        pkg = deepcopy(self.package)
        pkg["commits"][0], pkg["commits"][1] = pkg["commits"][1], pkg["commits"][0]
        with self.assertRaisesRegex(ValueError, "inventory"):
            p.verify(pkg, self.receipt, self.request, self.trust, self.pdf)

    def test_ingress_rejects_invalid_sources(self):
        with self.assertRaises(ValueError):
            p.issue_source(b"not a PDF", self.key)
        with fitz.open() as oversized:
            oversized.new_page(width=3500, height=3500)
            with self.assertRaises(ValueError):
                p.issue_source(oversized.tobytes(), self.key)


class StudioTests(unittest.TestCase):
    def test_local_workflow(self):
        with TemporaryDirectory() as home, patch.dict("os.environ", {"LEGITZK_PDF_HOME": home}):
            with TestClient(pdf_studio.app) as client:
                self.assertEqual(client.get("/").status_code, 200)
                self.assertEqual(client.post("/api/upload", content=b"data").status_code, 403)
                headers = {"X-LegitZK-Action": "1"}
                raw = sample_pdf()
                upload = client.post("/api/upload", content=raw, headers=headers)
                self.assertEqual(upload.status_code, 200, upload.text)
                source = upload.json()
                self.assertEqual(source["receipt"]["manifest"]["source_sha256"], sha256(raw).hexdigest())
                self.assertEqual(client.get("/api/page/0").status_code, 404)
                headers["X-LegitZK-Workspace"] = source["workspace"]
                self.assertEqual(client.get("/api/page/0", headers=headers).headers["content-type"], "image/png")
                request = client.post("/api/request", headers=headers,
                                      json={"audience":"Reviewer","protected":[5],"max_percent":25}).json()
                artifact = client.post("/api/prove", headers=headers, json={"request":request,"mask":[0,1]})
                self.assertEqual(artifact.status_code, 200, artifact.text)
                proof = artifact.json()
                key = client.get("/api/key").json()
                result = client.post("/api/verify", headers=headers, json={
                    "package":proof["proof_package"],"pdf":proof["pdf_base64"],
                    "receipt":source["receipt"],"request":request,"key":key})
                self.assertTrue(result.json()["valid"], result.text)
                client.post("/api/close", headers=headers)
                self.assertEqual(client.get("/api/page/0", headers=headers).status_code, 404)
