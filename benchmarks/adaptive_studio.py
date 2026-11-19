"""Reproduce the v2 planner/detector results on synthetic document layouts."""
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import fitz

import adaptive_mask as planner
import adaptive_proof as zk
import field_detector as ai
from protocol import canonical

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
FAMILIES = {
    "lease": [
        ("Beneficiary account details", "781746392", "account"),
        ("Federal tax registry", "315-48-6201", "tax_id"),
        ("Representative inbox", "leasing@example.test", "email"),
        ("Docket reference", "783061492", "public_reference"),
        ("Settlement Amount", "USD 7,500", "custom_field"),
        ("Premises code", "812437561", "other"),
    ],
    "vendor": [
        ("Account Number", "719438564", "account"),
        ("Vendor contact line", "000-732-1818", "phone"),
        ("National tax register", "773-21-2648", "tax_id"),
        ("Invoice Number", "739628421", "public_reference"),
        ("Settlement Amount", "USD 5,230", "custom_field"),
        ("Warehouse shipment token", "AA-4926105", "other"),
    ],
    "statement": [
        ("Bank account", "579438231", "account"),
        ("Email", "accounts@example.test", "email"),
        ("Mobile for notices", "000-635-0302", "phone"),
        ("Case filing", "930263184", "public_reference"),
        ("Payment batch", "526301749", "other"),
        ("Routing identifier", "549831026", "account"),
    ],
}
SENSITIVE = {"account", "tax_id", "email", "phone"}
PAGES = {"lease": 1, "vendor": 2, "statement": 3}


def generate(name, entries):
    with fitz.open() as pdf:
        for page in range(PAGES[name]):
            p = pdf.new_page(width=360, height=505)
            p.insert_text((29, 38), "Sample " + name.capitalize(), fontsize=19)
            p.insert_text((29, 58), "SYNTHETIC TEST RECORD — NO REAL IDENTIFIERS", fontsize=10)
            for i, (label, value, _) in enumerate(entries):
                p.insert_text((29, 120 + 33*i), f"{label}: {value}", fontsize=12)
            p.insert_text((29, 390), "Reviewer-visible status: active", fontsize=12)
            p.insert_text((29, 478), f"Page {page + 1}", fontsize=10)
        raw = pdf.tobytes()
    (FIXTURES / f"demo-{name}.pdf").write_bytes(raw)
    return raw


def region_for(page, value):
    from math import ceil, floor
    rect, = page.search_for(value)
    scale = 4 / 3
    return [page.number, floor(rect.x0*scale), floor(rect.y0*scale), ceil(rect.x1*scale), ceil(rect.y1*scale)]


def overlap(a, b):
    if a[0] != b[0]:
        return 0
    area = max(0, min(a[3], b[3])-max(a[1], b[1])) * max(0, min(a[4], b[4])-max(a[2], b[2]))
    return area / ((b[3]-b[1]) * (b[4]-b[2]))


def score(truth, suggestions):
    selected = [item for item in suggestions if item["category"] in SENSITIVE]
    targets = [box for box, category in truth if category in SENSITIVE]
    true_hits = sum(any(overlap(item["region"], target) > 0.7 for item in selected) for target in targets)
    false_hits = sum(not any(overlap(item["region"], target) > 0.7 for target in targets) for item in selected)
    return {"targets": len(targets), "covered": true_hits, "false_suggestions": false_hits,
            "suggestions": len(selected)}


def evaluate(name, entries):
    raw = generate(name, entries)
    key = Ed25519PrivateKey.generate()
    trusted = key.public_key().public_bytes_raw().hex()
    start = perf_counter()
    source = zk.issue(raw, key)
    ingest_ms = (perf_counter() - start)*1000
    with fitz.open(stream=raw) as pdf:
        truth = [(region_for(page, value), category) for page in pdf for _, value, category in entries]
        keep = [region_for(page, "Reviewer-visible status: active") for page in pdf]
    lines = ai.native_lines(raw, source[1])
    detections = {mode: score(truth, ai.find(lines, source[1], [], use_model=use)["suggestions"])
                  for mode, use in (("rules", False), ("rules_plus_model", True))}
    custom = ai.find(lines, source[1], ["Settlement Amount =>"])["suggestions"]
    detections["custom_fields_located"] = sum(item["category"] == "custom_field" for item in custom)
    hide = [box for box, category in truth if category in SENSITIVE or category == "custom_field"]
    results = {}
    for mode in planner.MODES:
        request = zk.request(source[0], "Benchmark", 35, hide, keep, mode=mode)
        observations = []
        for trial in range(4):
            start = perf_counter()
            pkg, pdf, metrics = zk.prove(source, request)
            middle = perf_counter()
            assert zk.verify(pkg, source[0], request, trusted, pdf)["valid"]
            end = perf_counter()
            if trial:
                observations.append({"generation_ms": (middle-start)*1000,
                                     "verification_ms": (end-middle)*1000,
                                     "proof_bytes": len(bytes.fromhex(pkg["proof"])),
                                     "json_bytes": len(canonical(pkg)), "pdf_bytes": len(pdf)})
        results[mode] = {**metrics, "trials": observations, "medians": {
            k:round(median(row[k] for row in observations), 3) for k in observations[0]}}
    return {"pages": PAGES[name], "ingest_ms": round(ingest_ms, 3), "detection": detections, "planner": results}


if __name__ == "__main__":
    output = {name: evaluate(name, entries) for name, entries in FAMILIES.items()}
    (ROOT / "benchmarks" / "adaptive-results.json").write_text(json.dumps(output,indent=2) + "\n", encoding="utf-8")
    for name, data in output.items():
        print(name, data["detection"])
        for mode, metrics in data["planner"].items():
            print(mode, metrics["tiles"], metrics["extra_pixels"], metrics["medians"])
