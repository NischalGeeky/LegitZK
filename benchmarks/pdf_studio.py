"""Synthetic 96 DPI PDF measurements; run as python -m benchmarks.pdf_studio."""
import json
from pathlib import Path
from statistics import median
from time import perf_counter

import fitz
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import pdf_redaction as p
from protocol import canonical


def letter(count):
    with fitz.open() as pdf:
        for index in range(count):
            page = pdf.new_page(width=595, height=842)
            page.insert_text((72, 72), f"Example records office | Page {index + 1}", fontsize=18)
            page.insert_text((72, 125), "Confidential reference 123-456-789")
            page.insert_text((72, 240), "Public account status: active")
        return pdf.tobytes()


def run(count):
    key = Ed25519PrivateKey.generate()
    trusted = key.public_key().public_bytes_raw().hex()
    raw = letter(count)
    rows = []
    for trial in range(11):
        start = perf_counter()
        source = p.issue_source(raw, key)
        ingest_time = perf_counter()
        request = p.new_request(source[0], 25, [], "Benchmark reviewer")
        sites = p.tile_sites(source[0]["manifest"]["pages"])
        mask = [i for i, (_, x, y, _, _) in enumerate(sites) if 64 <= x < 384 and 128 <= y < 192]
        pkg, pdf = p.present(source, request, mask)
        prove_time = perf_counter()
        assert p.verify(pkg, source[0], request, trusted, pdf)["valid"]
        verify_time = perf_counter()
        row = {"ingest_ms": (ingest_time - start)*1000, "prove_ms": (prove_time - ingest_time)*1000,
               "verify_ms": (verify_time - prove_time)*1000, "pdf_bytes": len(pdf),
               "bundle_bytes": len(canonical(pkg)), "proof_bytes": len(bytes.fromhex(pkg["proof"])),
               "tiles": len(sites), "redacted_tiles": len(mask)}
        if trial:
            rows.append(row)
    return {"samples": len(rows), "medians": {key: round(median(row[key] for row in rows), 3)
                                             for key in rows[0]}, "raw": rows}


if __name__ == "__main__":
    outputs = {}
    for count in (1, 3):
        outputs[count] = run(count)
        name = Path(f"fixtures/sample-{count}-page.pdf")
        name.write_bytes(letter(count))
        print(count, outputs[count]["medians"])
    Path("benchmarks/pdf-results.json").write_text(json.dumps(outputs, indent=2) + "\n")
