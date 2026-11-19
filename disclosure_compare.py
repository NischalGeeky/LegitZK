"""Locate visible differences against a verified disclosure, using its raster profile."""
import base64
from io import BytesIO

import fitz
import numpy as np
from PIL import Image, ImageDraw

import pdf_redaction as core

CELL = 16
MAX_REGIONS = 80


def demo_pdf(reference):
    with fitz.open(stream=reference, filetype="pdf") as document:
        page = document[0]
        width, height = page.rect.width, page.rect.height
        box = fitz.Rect(width * .13, height * .12, width * .53, max(height * .17, min(height, height * .12 + 1)))
        page.draw_rect(box, color=(.68,.06,.13), fill=(.98,.86,.88), overlay=True)
        if width >= 150 and height >= 240:
            page.insert_text((box.x0 + 4, box.y0 + 9), "DEMO EDIT", fontsize=8, color=(.6,.05,.1))
        return document.tobytes(garbage=4, deflate=True)


def metadata_demo(reference):
    """Produce a clearly labeled byte-only test fixture."""
    with fitz.open(stream=reference, filetype="pdf") as document:
        document.set_metadata({**document.metadata, "subject": "LegitZK metadata-only test fixture"})
        return document.tobytes(garbage=4, deflate=True)


def blocks(diff):
    """Group touching changed cells and return bounds of the actual changed pixels."""
    h, w = diff.shape
    rows = np.logical_or.reduceat(diff, np.arange(0, h, CELL), axis=0)
    ys, xs = np.nonzero(np.logical_or.reduceat(rows, np.arange(0, w, CELL), axis=1))
    active = set(zip(xs.tolist(), ys.tolist()))
    result = []
    while active:
        x, y = min(active, key=lambda p: (p[1], p[0]))
        active.remove((x, y))
        stack = [(x, y)]
        cells = []
        while stack:
            cx, cy = stack.pop()
            cells.append((cx, cy))
            for neighbor in ((cx-1,cy), (cx+1,cy), (cx,cy-1), (cx,cy+1)):
                if neighbor in active:
                    active.remove(neighbor)
                    stack.append(neighbor)
        left, top = w, h
        right = bottom = 0
        for cx, cy in cells:
            x0, y0 = cx*CELL, cy*CELL
            dy, dx = np.nonzero(diff[y0:y0+CELL, x0:x0+CELL])
            left, top = min(left, x0+int(dx.min())), min(top, y0+int(dy.min()))
            right, bottom = max(right, x0+int(dx.max())+1), max(bottom, y0+int(dy.max())+1)
        result.append([left, top, right, bottom])
        if len(result) > MAX_REGIONS:
            ys, xs = np.nonzero(diff)
            return [[int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1]], True
    return result, False


def compare(reference, candidate, request, receipt, *, expected=None, actual=None):
    if candidate == reference:
        return {"status": "identical", "changes": [], "dimensions": []}
    if expected is None:
        expected = core.render_source(reference, max_bytes=36_000_000)
    if actual is None:
        actual = core.render_source(candidate, max_bytes=36_000_000)
    dimensions = [[w, h] for w, h, _ in actual]
    changes = []
    preview = None
    for i in range(max(len(expected), len(actual))):
        if i >= len(actual) or i >= len(expected):
            changes.append({"page": i+1, "status": "missing page" if i >= len(actual) else "extra page"})
            continue
        w, h, rgb = actual[i]
        if (w, h) != expected[i][:2]:
            changes.append({"page": i+1, "status": "page dimensions changed"})
            continue
        pixels = np.frombuffer(rgb, dtype=np.uint8).reshape(h, w, 3)
        base = np.frombuffer(expected[i][2], dtype=np.uint8).reshape(h, w, 3)
        diff = (pixels != base).any(axis=2)
        if not diff.any():
            continue
        regions, merged = blocks(diff)
        protected = []
        for number, (page,x,y,right,bottom) in enumerate(request.get("keep", []), 1):
            if page != i:
                continue
            original_w, original_h = receipt["manifest"]["pages"][i]
            x0, y0 = x*w//original_w, y*h//original_h
            x1 = (right*w+original_w-1)//original_w
            y1 = (bottom*h+original_h-1)//original_h
            if diff[y0:y1, x0:x1].any():
                protected.append(number)
        if preview is None:
            image = Image.frombytes("RGB", (w, h), rgb)
            draw = ImageDraw.Draw(image)
            for x, y, right, bottom in regions:
                draw.rectangle((max(0,x-2),max(0,y-2),min(w-1,right+1),min(h-1,bottom+1)),
                               outline=(210,28,64), width=3)
            image.thumbnail((900,900))
            stream = BytesIO()
            image.save(stream, format="PNG")
            preview = {"page": i+1, "png": base64.b64encode(stream.getvalue()).decode()}
        changes.append({"page": i+1, "status": "visible pixels changed", "regions": regions,
                        "changed_pixels": int(diff.sum()), "protected_regions": protected, "merged": merged})
    return {"status":"differences" if changes else "byte_difference_only", "changes":changes,
            "dimensions":dimensions, "preview":preview}
