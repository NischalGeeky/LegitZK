"""Offline field suggestions from local PDF text or optional Tesseract OCR."""
from collections import defaultdict
import csv
from functools import lru_cache
from io import BytesIO, StringIO
from math import ceil, floor
import re
import shutil
import subprocess

import fitz
from PIL import Image
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

CANDIDATE = re.compile(r"(?<!\w)(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\+?\d(?:[ .()-]*\d){6,19}|[A-Z]{2,6}[- ]?\d{5,15})(?!\w)")
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
RULES = {
    "account": r"bank account|account (?:no\.?|number|id)|acct\b",
    "tax_id": r"taxpayer|tax (?:id|number)|social security|\bssn\b|\btin\b",
    "phone": r"telephone|\bphone\b|\bmobile\b|contact number|\bfax\b",
    "public_reference": r"invoice|transaction|order|tracking|case (?:id|number)|reference",
}
LABELS = {
    "account": ("bank account", "account number", "beneficiary account", "acct no", "deposit account"),
    "tax_id": ("taxpayer identification number", "tax id", "social security number", "federal tax number", "TIN"),
    "phone": ("telephone", "mobile phone", "phone number", "contact number", "fax"),
    "public_reference": ("invoice number", "purchase order", "transaction reference", "tracking id", "case number"),
    "other": ("record value", "summary data", "statement total", "sequence", "balance"),
}


def features(label, value):
    return f"{label.lower()} shape {re.sub(r'[0-9]', '0', value.lower())}"


@lru_cache(maxsize=1)
def classifier():
    examples, labels = [], []
    formats = ("123456789", "123-45-6789", "123 456 7890", "+1 (234) 555-0123", "AB-1234567")
    for category, contexts in LABELS.items():
        for context in contexts:
            for sample in formats:
                examples.append(features(context, sample))
                labels.append(category)
    model = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), token_pattern=r"\b\w+\b"),
                          LogisticRegression(max_iter=500, C=8.0, random_state=0))
    return model.fit(examples, labels)


def classify(context, value, use_model=True):
    if EMAIL.fullmatch(value):
        return "email", "rule"
    for label, rule in RULES.items():
        if re.search(rule, context, re.I):
            return label, "rule"
    if use_model and context.strip():
        weights = classifier().predict_proba([features(context, value)])[0]
        index = int(weights.argmax())
        if weights[index] >= 0.55:
            return str(classifier().classes_[index]), "model"
    return "unclassified", "review"


def native_lines(raw, rasters):
    result = []
    with fitz.open(stream=raw, filetype="pdf") as pdf:
        for page, (w, h, _) in zip(pdf, rasters):
            by_line = defaultdict(list)
            for x, y, right, bottom, token, block, line, _ in page.get_text("words", sort=True):
                p = fitz.Rect(x, y, right, bottom) * page.rotation_matrix * fitz.Matrix(4 / 3, 4 / 3)
                rect = (max(0, floor(p.x0)), max(0, floor(p.y0)), min(w, ceil(p.x1)), min(h, ceil(p.y1)))
                if rect[0] < rect[2] and rect[1] < rect[3]:
                    by_line[block, line].append((token, rect))
            result.append(list(by_line.values()))
    return result


def ocr_lines(raster, minimum_confidence=0):
    binary = shutil.which("tesseract")
    if not binary:
        raise ValueError("Tesseract is not on PATH. Install it or inspect scanned pages manually.")
    w, h, rgb = raster
    stream = BytesIO()
    Image.frombytes("RGB", (w, h), rgb).save(stream, format="PNG")
    try:
        result = subprocess.run([binary, "stdin", "stdout", "--dpi", "96", "tsv"],
                                input=stream.getvalue(), capture_output=True, timeout=35, check=True)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as exc:
        raise ValueError("Local OCR could not read a page.") from exc
    lines = defaultdict(list)
    for row in csv.DictReader(StringIO(result.stdout.decode("utf-8", errors="replace")), delimiter="\t"):
        if row["level"] != "5" or not row["text"].strip() or float(row["conf"]) < minimum_confidence:
            continue
        x, y, width, height = (int(row[key]) for key in ("left", "top", "width", "height"))
        if 0 <= x < w and 0 <= y < h and width > 0 and height > 0:
            lines[tuple(row[key] for key in ("block_num", "par_num", "line_num"))].append(
                (row["text"].strip(), (x, y, min(w, x + width), min(h, y + height))))
    return list(lines.values())


def line_text(words):
    tokens = []
    offset = 0
    for token, box in words:
        tokens.append((offset, offset + len(token), token, box))
        offset += len(token) + 1
    return " ".join(word for _, _, word, _ in tokens), tokens


CLINICAL_LABEL = re.compile(
    r"^\s*(?P<label>patient(?:['’]s)? name|full name|name|d\.?o\.?b\.?|date of birth|birth date|"
    r"medical record(?: number| no\.?| id)?|mrn|hospital id|patient id|"
    r"social security(?: number)?|ssn)\s*[:=]\s*(?P<value>.*?)\s*$",
    re.I,
)
DATE = re.compile(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}")
SSN = re.compile(r"\d{3}[- ]\d{2}[- ]\d{4}")


FINANCIAL_LABELS = (
    ("account", r"(?:bank\s+)?(?:account|acct)\s*(?:number|no\.?|id|#)|account"),
    ("routing", r"(?:aba\s+)?routing(?:\s+(?:number|no\.?|#))?|ifsc(?:\s+code)?|sort code"),
    ("iban", r"iban|international bank account number"),
    ("card_number", r"(?:credit |debit |payment )?card (?:number|no\.?|#)|pan"),
    ("card_security_code", r"cvv2?|cvc2?|card security code"),
    ("tax_id", r"tax(?:payer)? (?:id|number|identification number)|tin|ein|national id"),
    ("government_id", r"passport(?: number| no\.?)?|driver['’]?s? licen[cs]e(?: number| no\.?)?"),
    ("financial_reference", r"(?:loan|policy|transaction|invoice|control) (?:id|number|no\.?|reference|#)"),
    ("person_name", r"account holder(?: name)?|customer name|beneficiary name"),
    ("residential_address", r"(?:mailing|billing|residential|home) address"),
    ("email", r"(?:personal |contact )?e-?mail(?: address)?"),
    ("phone", r"(?:personal |contact )?phone(?: number)?|mobile(?: number)?"),
)
FINANCIAL_PATTERNS = tuple((category, re.compile(
    rf"^\s*(?:{label})\s*[:=]\s*(?P<value>.*?)\s*$", re.I
)) for category, label in FINANCIAL_LABELS)


def financial_seed(text):
    for kind, pattern in FINANCIAL_PATTERNS:
        match = pattern.fullmatch(text)
        if not match:
            continue
        value = match["value"]
        compact = re.sub(r"[ -]", "", value).upper()
        if kind == "iban":
            valid = re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", compact)
        elif kind == "card_number":
            valid = compact.isdigit() and 13 <= len(compact) <= 19
        elif kind == "card_security_code":
            valid = re.fullmatch(r"[0-9]{3,4}", value)
        elif kind in {"person_name", "residential_address"}:
            valid = 5 <= len(value) <= 120 and len(value.split()) >= 2
        elif kind == "email":
            valid = EMAIL.fullmatch(value)
        elif kind == "phone":
            valid = re.fullmatch(r"\+?[0-9(). -]{7,25}", value) and sum(c.isdigit() for c in value) >= 7
        else:
            valid = re.fullmatch(r"(?=[A-Z0-9]*[0-9])[A-Z0-9]{4,34}", compact)
        if valid:
            return value, kind
    return None


def identifier_seeds(rows, financial):
    """Learn document-specific identifiers from explicit labels."""
    seeds = {}
    for page_rows in rows:
        for index, (text, _) in enumerate(page_rows):
            if financial and len(seeds) < 128:
                seed = financial_seed(text)
                if seed and seed[1] != "card_security_code":
                    seeds.setdefault(seed[0].casefold(), seed)
            match = CLINICAL_LABEL.fullmatch(text)
            if not match:
                continue
            label = re.sub(r"\.", "", match["label"].casefold())
            value = match["value"]
            if not value and index + 1 < len(page_rows) and "name" not in label:
                value = page_rows[index + 1][0]
            if "name" in label:
                words = value.split()
                valid = 2 <= len(words) <= 7 and all(
                    re.fullmatch(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", word) for word in words)
                kind = "person_name"
            elif label in {"dob", "date of birth", "birth date"}:
                valid = DATE.fullmatch(value)
                kind = "birth_date"
            elif label.startswith("social security") or label == "ssn":
                valid = SSN.fullmatch(value) or re.fullmatch(r"\d{9}", value)
                kind = "tax_id"
            else:
                valid = re.fullmatch(r"(?=[A-Za-z0-9 -]*\d)[A-Za-z0-9-]{4,30}", value)
                kind = "medical_id"
            if valid and len(seeds) < 128:
                seeds.setdefault(value.casefold(), (value, kind))
    return list(seeds.values())


def literal_pattern(value):
    return re.compile(r"(?<!\w)" + re.escape(value) + r"(?!\w)", re.I)


def identifier_patterns(pages, financial):
    for group, (value, kind) in enumerate(identifier_seeds(pages, financial), 1):
        yield literal_pattern(value), kind, group, "labeled_identifier"
        words = value.split()
        if kind == "person_name" and len(words) == 2:
            yield literal_pattern(f"{words[0][0]}. {words[1]}"), kind, group, "possible_variant"



def find(lines, rasters, custom, ocr=False, use_model=True, financial=False):
    if not isinstance(custom, list) or len(custom) > 12 or any(
            not isinstance(value, str) or not 1 <= len(value.strip()) <= 120 for value in custom):
        raise ValueError("Enter up to 12 non-empty custom search phrases of at most 120 characters.")
    queries = [value.strip() for value in custom]
    matches = {}
    warnings = []
    pages = []
    for page, (native, raster) in enumerate(zip(lines, rasters)):
        available = native
        if ocr:
            try:
                available = native + ocr_lines(raster)
            except ValueError as exc:
                warnings.append(f"Page {page + 1}: {exc}")
        if not available:
            warnings.append(f"Page {page + 1} has no accessible text. Try local OCR or review manually.")
        pages.append([line_text(row) for row in available])
    identifiers = list(identifier_patterns(pages, financial))
    for page, (rows, raster) in enumerate(zip(pages, rasters)):
        w, h, _ = raster
        for text, tokens in rows:
            items = [(*found.span(), category, method, group)
                     for pattern, category, group, method in identifiers for found in pattern.finditer(text)]
            scoped = financial_seed(text) if financial else None
            if scoped and scoped[1] == "card_security_code":
                items.append((text.rfind(scoped[0]), len(text), scoped[1], "labeled_identifier", None))
            for candidate in CANDIDATE.finditer(text):
                left_context = re.split(r"[;|]", text[max(0, candidate.start()-90):candidate.start()])[-1]
                kind, origin = classify(left_context, candidate.group(), use_model)
                items.append((candidate.start(), candidate.end(), kind, origin, None))
            for query in queries:
                if query.endswith("=>"):
                    label = query[:-2].strip()
                    found = re.search(re.escape(label) + r"\s*[:=–-]?\s*(\S.*)$", text, re.I) if label else None
                    if found:
                        items.append((*found.span(1), "custom_field", "custom", None))
                else:
                    items.extend((*found.span(), "custom_text", "custom", None)
                                 for found in re.finditer(re.escape(query), text, re.I))
            for start, end, kind, origin, group in items:
                boxes = [box for lo, hi, _, box in tokens if lo < end and hi > start]
                if not boxes:
                    continue
                region = (page, max(0, min(b[0] for b in boxes)-1), max(0, min(b[1] for b in boxes)-1),
                          min(w, max(b[2] for b in boxes)+1), min(h, max(b[3] for b in boxes)+1))
                key = (region, kind)
                if key not in matches or origin == "labeled_identifier":
                    matches[key] = {"region": list(region), "category": kind, "method": origin, "group": group}
    ordered = sorted(matches.values(), key=lambda item: (item["region"], item["category"]))
    if len(ordered) > 512:
        warnings.append("Only the first 512 suggestions are shown. Review the full document.")
    return {"suggestions": ordered[:512], "warnings": warnings}
