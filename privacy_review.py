"""Local, scoped reviews of disclosure plans and exported page images."""
from collections import defaultdict
from datetime import date
import re

import field_detector as detector
import pdf_redaction as core

AGE = re.compile(r"\b(\d{1,3})\s*(?:years?|yrs?)\s+(?:and\s+)?(\d{1,2})\s*months?\b", re.I)
VISIT = re.compile(r"\b(?:visit|consultation|appointment) date\s*:\s*(\d{4}-\d{2}-\d{2})\b", re.I)


def rows(lines):
    return [[detector.line_text(row) for row in page] for page in lines]


def overlaps(region, mask):
    return region[0] == mask[0] and region[1] < mask[3] and mask[1] < region[3] and region[2] < mask[4] and mask[2] < region[4]


def plan_review(lines, masks):
    visible = []
    for index, page in enumerate(rows(lines)):
        page_masks = [mask for mask in masks if mask[0] == index]
        for text, tokens in page:
            if not any(overlaps([index, *box], mask) for _, _, _, box in tokens for mask in page_masks):
                visible.append((index + 1, text))
    ages = [(p, m) for p, text in visible if (m := AGE.search(text))]
    visits = [(p, m) for p, text in visible if (m := VISIT.search(text))]
    if len(ages) != 1 or len(visits) != 1:
        return []
    age_page, age = ages[0]
    visit_page, visit = visits[0]
    try:
        dt = date.fromisoformat(visit[1])
        years, months = map(int, age.groups())
        if months > 11 or years > 130:
            return []
        month_index = dt.year * 12 + dt.month - 1 - years * 12 - months
        year, month = divmod(month_index, 12)
        inferred = date(year, month + 1, 1)
    except ValueError:
        return []
    return [{"age_page": age_page, "visit_page": visit_page, "estimated_month": inferred.strftime("%Y-%m"),
             "assumption": "The exact age belongs to the person and visit shown. The preceding month is also possible."}]


def protected_groups(lines, masks, financial=True):
    source_rows = rows(lines)
    masks_by_page = defaultdict(list)
    for mask in masks:
        masks_by_page[mask[0]].append(mask)
    groups = []
    for value, category in detector.identifier_seeds(source_rows, financial):
        pattern = detector.literal_pattern(value)
        occurrences = []
        for page, page_rows in enumerate(source_rows):
            for text, tokens in page_rows:
                for match in pattern.finditer(text):
                    occurrences.append([[page, *box] for start, end, _, box in tokens
                                        if start < match.end() and end > match.start()])
        if any(overlaps(box, mask) for occurrence in occurrences for box in occurrence
               for mask in masks_by_page[box[0]]):
            groups.append((pattern, category, occurrences))
    return groups


def leak_scan(pdf, lines, masks, source_pages=None):
    source_unreadable = []
    if source_pages is not None:
        # Recover identifiers on scanned pages with no accessible source text.
        lines = list(lines)
        for index, raster in enumerate(source_pages):
            if lines[index]:
                continue
            try:
                lines[index] = detector.ocr_lines(raster)
            except ValueError:
                pass
            if not lines[index]:
                source_unreadable.append(index + 1)
    patterns = [(pattern, category) for pattern, category, _ in protected_groups(lines, masks)]
    if not patterns:
        return {"status": "inconclusive", "tracked_values": 0, "findings": [], "unreadable_pages": [],
                "unreadable_source_pages": source_unreadable}
    pages = core.render_source(pdf, max_bytes=36_000_000)
    findings, unreadable = [], []
    for index, page in enumerate(pages):
        try:
            extracted = detector.ocr_lines(page)
        except ValueError:
            unreadable.append(index + 1)
            continue
        if not extracted:
            unreadable.append(index + 1)
        for text, tokens in (detector.line_text(line) for line in extracted):
            for pattern, category in patterns:
                for match in pattern.finditer(text):
                    boxes = [box for start, end, _, box in tokens if start < match.end() and end > match.start()]
                    findings.append({"category": category, "page": index + 1, "box": [
                        min(b[0] for b in boxes), min(b[1] for b in boxes),
                        max(b[2] for b in boxes), max(b[3] for b in boxes)]})
                    if len(findings) >= 200:
                        return {"status": "findings", "tracked_values": len(patterns), "findings": findings,
                                "unreadable_pages": unreadable, "unreadable_source_pages": source_unreadable, "truncated": True}
    status = "findings" if findings else ("inconclusive" if unreadable or source_unreadable else "no_matches")
    return {"status": status, "tracked_values": len(patterns), "findings": findings, "unreadable_pages": unreadable,
            "unreadable_source_pages": source_unreadable}
