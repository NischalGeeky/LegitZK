"""Defensive comparison of a receipt-authenticated source and a supplied PDF."""
from collections import Counter, defaultdict
from hashlib import sha256
import re

import fitz

import disclosure_compare
import field_detector
import pdf_redaction as core

MAX_FINDINGS = 250
MAX_LINES = 2000


def structure(raw):
    with fitz.open(stream=raw, filetype="pdf") as doc:
        return {
            "pages": len(doc),
            "objects": doc.xref_length() - 1,
            "embedded_files": doc.embfile_count(),
            "annotations": sum(len(page.annot_xrefs()) for page in doc),
            "signature_flags": doc.get_sigflags(),
            "metadata": {key: value for key, value in (doc.metadata or {}).items() if value},
        }


def fields(lines):
    output = defaultdict(list)
    for line in lines[:MAX_LINES]:
        text, _ = field_detector.line_text(line)
        label, separator, value = text.partition(":")
        label = label.strip()
        if not separator or not value.strip() or not 1 <= len(label) <= 100:
            continue
        bounds = [box for _, box in line]
        output[re.sub(r"\s+", " ", label.casefold())].append({
            "label": label, "value": value.strip(),
            "box": [min(b[0] for b in bounds), min(b[1] for b in bounds),
                    max(b[2] for b in bounds), max(b[3] for b in bounds)],
        })
    return output


def compare_fields(original, suspect, include_values):
    changes, ambiguous = [], 0
    for page in range(max(len(original), len(suspect))):
        old = fields(original[page]) if page < len(original) else {}
        new = fields(suspect[page]) if page < len(suspect) else {}
        for key in sorted(old.keys() | new.keys()):
            before, after = old.get(key, []), new.get(key, [])
            if max(len(before), len(after)) > 1:
                if Counter(item["value"] for item in before) != Counter(item["value"] for item in after):
                    ambiguous += 1
                continue
            left = before[0] if before else None
            right = after[0] if after else None
            if left and right and left["value"] == right["value"]:
                continue
            change = {"page": page + 1, "field": (left or right)["label"],
                      "classification": "changed" if left and right else ("removed" if left else "added"),
                      "baseline_box": left["box"] if left else None,
                      "candidate_box": right["box"] if right else None,
                      "match_basis": "unique native-text label on the same page"}
            if include_values:
                change["baseline_value"] = left["value"][:500] if left else None
                change["candidate_value"] = right["value"][:500] if right else None
            changes.append(change)
    return {"changes": changes[:MAX_FINDINGS], "ambiguous_matches": ambiguous,
            "truncated": len(changes) > MAX_FINDINGS or any(len(p) > MAX_LINES for p in original + suspect)}


def investigate(reference, suspect, receipt, signer_key, include_values=False):
    reference_hash, suspect_hash = (sha256(raw).hexdigest() for raw in (reference, suspect))
    if reference_hash != receipt["manifest"]["source_sha256"]:
        raise ValueError("Baseline PDF does not match the trusted source receipt.")
    before = core.render_source(reference)
    after = core.render_source(suspect)
    if [[w, h] for w, h, _ in before] != receipt["manifest"]["pages"]:
        raise ValueError("Baseline rendering dimensions differ from the source receipt.")
    visual = disclosure_compare.compare(reference, suspect, {}, receipt, expected=before, actual=after)
    first, second = structure(reference), structure(suspect)
    first_meta, second_meta = first.pop("metadata"), second.pop("metadata")
    metadata_keys = [key for key in sorted(first_meta.keys() | second_meta.keys())
                     if first_meta.get(key) != second_meta.get(key)]
    structural = {key: {"baseline": first[key], "candidate": second[key]}
                  for key in first if first[key] != second[key]}
    same = reference_hash == suspect_hash
    field_report = compare_fields(field_detector.native_lines(reference, before),
                                  field_detector.native_lines(suspect, after), include_values)
    return {
        "schema": "legitzk/source-investigation/v1",
        "baseline_version": receipt["manifest"]["id"],
        "baseline_sha256": reference_hash, "candidate_sha256": suspect_hash,
        "baseline_receipt_valid": True, "candidate_matches_signed_bytes": same,
        "baseline_signing_key": signer_key,
        "attribution": "no_byte_change" if same else "actor_unknown",
        "visual": visual, "structure_changes": structural, "metadata_keys_changed": metadata_keys,
        "field_analysis": field_report,
        "limitations": ["Native text fields use unique colon-delimited labels within a page.",
                        "Moved, scanned, duplicate, or unlabeled fields can require manual review.",
                        "Visual comparison uses the Studio raster profile, which excludes annotations.",
                        "Structure counts are observations. Embedded PDF signatures are not validated."],
    }


def sample_revision(score):
    """Build an explicitly synthetic record with a native-text field."""
    with fitz.open() as doc:
        page = doc.new_page(width=360, height=180)
        page.insert_text((24, 32), "SYNTHETIC TEST RECORD", fontsize=14)
        page.insert_text((24, 66), "Record ID: DEMO-001", fontsize=12)
        page.insert_text((24, 91), f"Review score: {score}", fontsize=12)
        page.insert_text((24, 120), "For LegitZK verification practice only.", fontsize=11)
        return doc.tobytes()

def compare_ocr(reference, suspect, visual):
    """Compare only confidently readable, uniquely labeled fields on changed pages."""
    pages = [entry["page"] - 1 for entry in visual["changes"]
             if entry["status"] == "visible pixels changed"]
    if not pages:
        return {"changes": [], "manual_review_pages": []}
    before = core.render_source(reference, max_bytes=36_000_000)
    after = core.render_source(suspect, max_bytes=36_000_000)
    changes, manual = [], []
    for index in pages:
        try:
            left = field_detector.ocr_lines(before[index], minimum_confidence=75)
            right = field_detector.ocr_lines(after[index], minimum_confidence=75)
        except ValueError:
            manual.append(index + 1)
            continue
        report = compare_fields([left], [right], include_values=True)
        paired = [entry for entry in report["changes"] if entry["classification"] == "changed"]
        regions = next(entry["regions"] for entry in visual["changes"] if entry["page"] == index + 1)
        paired = [entry for entry in paired if any(
            b[0] < r[2] and r[0] < b[2] and b[1] < r[3] and r[1] < b[3]
            for b in (entry["baseline_box"], entry["candidate_box"]) for r in regions)]
        for entry in paired:
            entry.update(page=index + 1, match_basis="OCR and unique same-page field label")
        changes.extend(paired)
        if not paired or len(paired) != len(report["changes"]) or report["ambiguous_matches"] or report["truncated"]:
            manual.append(index + 1)
    return {"changes": changes[:MAX_FINDINGS], "manual_review_pages": manual}


def sample_statement(fields):
    """Render a labeled synthetic statement from fixture data."""
    with fitz.open() as doc:
        page = doc.new_page(width=440, height=240)
        page.insert_text((24, 37), "SYNTHETIC BANK STATEMENT", fontsize=17)
        page.insert_text((24, 60), "TEST DATA ONLY / NO ACTUAL ACCOUNT", fontsize=10)
        for index, (label, value) in enumerate(fields):
            top = 82 + 32 * index
            if index % 2 == 0:
                page.draw_rect(fitz.Rect(24, top, 416, top + 30), color=None, fill=(0.93, 0.95, 0.98))
            page.insert_text((34, top + 20), f"{label}: {value}", fontsize=12)
        return doc.tobytes()
