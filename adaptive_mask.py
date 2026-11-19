"""Compile approved pixel regions into a canonical minimum-loss quadtree cut."""
from collections import defaultdict

import numpy as np

from protocol import integer

MIN_TILE = 8
ROOT_TILE = 32
MAX_REGIONS = 512
MAX_CUT = 140_000
MODES = ("adaptive", "fixed32", "fixed8")


def roots(dimensions):
    for page, (w, h) in enumerate(dimensions):
        for y in range(0, h, ROOT_TILE):
            for x in range(0, w, ROOT_TILE):
                yield (page, x, y, ROOT_TILE)


def children(node, dimensions):
    page, x, y, size = node
    if size == MIN_TILE:
        return
    half = size // 2
    w, h = dimensions[page]
    for dy in (0, half):
        for dx in (0, half):
            if x + dx < w and y + dy < h:
                yield (page, x + dx, y + dy, half)


def rectangle(node, dimensions):
    page, x, y, size = node
    w, h = dimensions[page]
    return page, x, y, min(x + size, w), min(y + size, h)


def inventory(dimensions):
    def walk(node):
        yield node
        for child in children(node, dimensions):
            yield from walk(child)
    for node in roots(dimensions):
        yield from walk(node)


def regions(items, dimensions):
    if not isinstance(items, list) or len(items) > MAX_REGIONS:
        raise ValueError(f"Use at most {MAX_REGIONS} boxes per rule.")
    result = set()
    for item in items:
        if not isinstance(item, list) or len(item) != 5:
            raise ValueError("Invalid page region.")
        page, x, y, right, bottom = item
        integer(page, 0, len(dimensions) - 1)
        w, h = dimensions[page]
        integer(x, 0, w - 1)
        integer(y, 0, h - 1)
        integer(right, x + 1, w)
        integer(bottom, y + 1, h)
        result.add(tuple(item))
    return [list(item) for item in sorted(result)]


def coverage(boxes, dimensions, size):
    labels = defaultdict(set)
    for page, x, y, right, bottom in boxes:
        for row in range(y // size, (bottom - 1) // size + 1):
            for col in range(x // size, (right - 1) // size + 1):
                labels[page].add((col * size, row * size))
    return labels


def target_area(boxes, dimensions):
    total = 0
    by_page = defaultdict(list)
    for page, *rect in boxes:
        by_page[page].append(rect)
    for page, rects in by_page.items():
        w, h = dimensions[page]
        pixels = np.zeros((h, w), dtype=bool)
        for x, y, right, bottom in rects:
            pixels[y:bottom, x:right] = True
        total += int(pixels.sum())
    return total


def compile_cut(dimensions, hide, keep, budget, limit, mode="adaptive"):
    """First minimize collateral pixels, then merge uniform regions recursively."""
    if mode not in MODES:
        raise ValueError("Unknown planning mode.")
    if not hide:
        raise ValueError("Approve at least one region to hide.")
    size = ROOT_TILE if mode == "fixed32" else MIN_TILE
    targets = coverage(hide, dimensions, size)
    protected = coverage(keep, dimensions, size)
    for page, cells in targets.items():
        conflict = cells & protected[page]
        if conflict:
            x, y = min(conflict)
            raise ValueError(f"Hide and keep rules share a {size}px tile on page {page + 1} at ({x}, {y}).")
    areas = [0] * len(dimensions)
    for page, (w, h) in enumerate(dimensions):
        areas[page] = sum(min(size, w - x) * min(size, h - y) for x, y in targets[page])
        if 100 * areas[page] > budget * w * h:
            raise ValueError(f"Approved regions exceed the {budget}% area budget on page {page + 1}.")

    def walk(node):
        page, x, y, width = node
        if width == size:
            return [(node, (x, y) in targets[page])]
        cut = [entry for child in children(node, dimensions) for entry in walk(child)]
        if mode == "adaptive" and all(hidden == cut[0][1] for _, hidden in cut):
            return [(node, cut[0][1])]
        return cut

    cut = [entry for root in roots(dimensions) for entry in walk(root)]
    if len(cut) > limit:
        raise ValueError(f"The minimum-loss plan uses {len(cut):,} tiles, above the {limit:,}-tile limit.")
    return cut, {"tiles": len(cut), "hidden_tiles": sum(hidden for _, hidden in cut),
                 "redacted_pixels": sum(areas), "extra_pixels": sum(areas) - target_area(hide, dimensions),
                 "page_percentages": [round(100 * area / (w * h), 3)
                                      for area, (w, h) in zip(areas, dimensions)]}
