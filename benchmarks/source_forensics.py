"""Measure signed-baseline comparison on clean, field-change and metadata fixtures."""
import json
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter

import fitz
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import adaptive_proof
import disclosure_compare
import forensic_review


def fixture(code):
    with fitz.open() as doc:
        page = doc.new_page(width=250, height=250)
        page.insert_text((20, 50), f"Review code: {code}")
        return doc.tobytes()


def main():
    baseline = fixture("ABC-01")
    key = Ed25519PrivateKey.generate()
    receipt = adaptive_proof.issue(baseline, key)[0]
    signer = key.public_key().public_bytes_raw().hex()
    from pdf_studio import receipt_signer
    cases = [("clean", baseline, False, 0), ("field", fixture("DEF-02"), True, 1),
             ("metadata", disclosure_compare.metadata_demo(baseline), True, 0)]
    results = []
    for name, candidate, changed, expected_fields in cases:
        samples = []
        for _ in range(10):
            start = perf_counter()
            checked = receipt_signer(receipt, [signer])
            report = forensic_review.investigate(baseline, candidate, receipt, checked)
            samples.append((perf_counter() - start) * 1000)
        results.append({"fixture": name, "expected_byte_change": changed,
                        "detected_byte_change": not report["candidate_matches_signed_bytes"],
                        "expected_field_changes": expected_fields,
                        "detected_field_changes": len(report["field_analysis"]["changes"]),
                        "visual_status": report["visual"]["status"], "attribution": report["attribution"],
                        "median_ms": median(samples), "samples_ms": samples})
    print(json.dumps({"platform": platform.platform(), "python": platform.python_version(),
                      "pymupdf": fitz.VersionBind, "results": results}, indent=2))


if __name__ == "__main__":
    main()
