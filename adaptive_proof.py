"""Adaptive raster presentation with Merkle-authenticated commitment cuts."""
import base64
from hashlib import sha256
from secrets import randbelow, token_hex
from time import time
import zlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

import adaptive_mask as planner
import pdf_redaction as core
from protocol import integer, shape, valid_hex

PROFILE = "legitzk/rgb96-quadtree32-8/v2"
RECEIPT = "LegitZK/pdf/receipt/v2"
EMPTY = sha256(b"LegitZK/pdf/tree/padding/v2").digest()


def leaf(index, commitment):
    return sha256(b"LegitZK/pdf/tree/leaf/v2\0" + index.to_bytes(4, "big") + commitment).digest()


def branch(left, right):
    return sha256(b"LegitZK/pdf/tree/branch/v2\0" + left + right).digest()


def merkle_levels(commits):
    leaves = [leaf(i, value) for i, value in enumerate(commits)]
    leaves.extend([EMPTY] * ((1 << (len(leaves) - 1).bit_length()) - len(leaves)))
    levels = [leaves]
    while len(levels[-1]) > 1:
        previous = levels[-1]
        levels.append([branch(previous[i], previous[i + 1]) for i in range(0, len(previous), 2)])
    return levels


def auxiliary_levels(indices, depth):
    active = set(indices)
    for _ in range(depth):
        yield sorted({i ^ 1 for i in active} - active)
        active = {i // 2 for i in active}


def authenticate(indices, commits, auxiliary, count, root):
    depth = (count - 1).bit_length()
    if not isinstance(auxiliary, list) or len(auxiliary) != depth:
        raise ValueError("Invalid Merkle proof depth.")
    active = {i: leaf(i, valid_hex(c, 32)) for i, c in zip(indices, commits)}
    for items, expected in zip(auxiliary, auxiliary_levels(indices, depth)):
        if not isinstance(items, list) or len(items) != len(expected):
            raise ValueError("Invalid Merkle sibling inventory.")
        active.update((i, valid_hex(value, 32)) for i, value in zip(expected, items))
        active = {i // 2: branch(active[i], active[i + 1]) for i in active if not i % 2}
    if active.get(0) != root:
        raise ValueError("Adaptive tile commitments do not match the signed source.")


def issue(raw, key, pages=None):
    pages = core.render_source(raw) if pages is None else pages
    dimensions = [[w, h] for w, h, _ in pages]
    source_id = token_hex(16)
    nodes = list(planner.inventory(dimensions))
    openings = []
    for node in nodes:
        page, *rect = planner.rectangle(node, dimensions)
        w, _, pixels = pages[page]
        value = core.tile_scalar(source_id, node, core.read_tile(pixels, w, rect))
        openings.append((value, randbelow(core.group.ORDER)))
    commits = [core.group.commit(*opening) for opening in openings]
    levels = merkle_levels(commits)
    manifest = {"profile": PROFILE, "id": source_id, "source_sha256": sha256(raw).hexdigest(),
                "pages": dimensions, "merkle_root": levels[-1][0].hex()}
    receipt = {"manifest": manifest, "signature": key.sign(core.framed(RECEIPT, manifest)).hex()}
    return receipt, pages, {node: i for i, node in enumerate(nodes)}, commits, openings, levels


def request(receipt, audience, budget, hide, keep, limit=planner.MAX_CUT, mode="adaptive"):
    m = receipt["manifest"]
    req = {"source_id": m["id"], "audience": audience, "nonce": token_hex(32), "expires": int(time()) + 3600,
           "max_percent": budget, "hide": planner.regions(hide, m["pages"]),
           "keep": planner.regions(keep, m["pages"]), "tile_limit": limit, "mode": mode}
    plan(req, m)
    return req


def plan(req, manifest):
    shape(req, ("source_id", "audience", "nonce", "expires", "max_percent", "hide", "keep", "tile_limit", "mode"))
    if req["source_id"] != manifest["id"]:
        raise ValueError("Request belongs to a different source.")
    if not isinstance(req["audience"], str) or not 1 <= len(req["audience"]) <= 100 or not req["audience"].isprintable():
        raise ValueError("Enter a printable recipient name.")
    valid_hex(req["nonce"], 32)
    integer(req["expires"], 1, 2**53 - 1)
    if req["expires"] <= int(time()):
        raise ValueError("The disclosure request expired. Export a fresh redacted PDF and proof ZIP from the original source.")
    integer(req["max_percent"], 1, 100)
    integer(req["tile_limit"], 1, planner.MAX_CUT)
    for key in ("hide", "keep"):
        if planner.regions(req[key], manifest["pages"]) != req[key]:
            raise ValueError("Request regions must be canonical.")
    return planner.compile_cut(manifest["pages"], req["hide"], req["keep"], req["max_percent"],
                               req["tile_limit"], req["mode"])


def geometry(cut, dimensions):
    return ([planner.rectangle(node, dimensions) for node, _ in cut],
            {i for i, (_, hidden) in enumerate(cut) if hidden})


def prove(source, req):
    receipt, pages, index, all_commits, all_openings, levels = source
    dimensions = receipt["manifest"]["pages"]
    cut, metrics = plan(req, receipt["manifest"])
    sites, hidden = geometry(cut, dimensions)
    indices = [index[node] for node, _ in cut]
    commits = [all_commits[i].hex() for i in indices]
    auxiliary = [[level[i].hex() for i in siblings]
                 for level, siblings in zip(levels, auxiliary_levels(indices, len(levels) - 1))]
    disclosed = core.redact(pages, sites, hidden)
    pdf = core.render_export(disclosed)
    package = {"receipt": receipt, "request": req, "commits": commits, "siblings": auxiliary,
               "pages": [base64.b64encode(zlib.compress(raw)).decode() for _, _, raw in disclosed],
               "pdf_sha256": sha256(pdf).hexdigest()}
    package["proof"] = core.make_proof(core.transcript(package, disclosed), commits,
                                        [all_openings[i] for i in indices], hidden)
    return package, pdf, metrics


def verify(pkg, receipt, req, key, pdf):
    shape(pkg, ("receipt", "request", "commits", "siblings", "pages", "pdf_sha256", "proof"))
    if pkg["receipt"] != receipt or pkg["request"] != req:
        raise ValueError("Evidence does not match the independently retained receipt and request.")
    shape(receipt, ("manifest", "signature"))
    m = receipt["manifest"]
    shape(m, ("profile", "id", "source_sha256", "pages", "merkle_root"))
    if m["profile"] != PROFILE:
        raise ValueError("Unsupported adaptive profile.")
    try:
        Ed25519PublicKey.from_public_bytes(valid_hex(key, 32)).verify(
            valid_hex(receipt["signature"], 64), core.framed(RECEIPT, m))
    except InvalidSignature as exc:
        raise ValueError("Ingestion signature is invalid.") from exc
    valid_hex(m["id"], 16)
    valid_hex(m["source_sha256"], 32)
    root = valid_hex(m["merkle_root"], 32)
    dimensions = m["pages"]
    if not isinstance(dimensions, list) or not 1 <= len(dimensions) <= core.MAX_PAGES:
        raise ValueError("Invalid page inventory.")
    total = 0
    for pair in dimensions:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("Invalid page dimensions.")
        w, h = pair
        integer(w, 1, core.MAX_DIM)
        integer(h, 1, core.MAX_DIM)
        total += w * h
    integer(total, 1, core.MAX_PIXELS)
    cut, metrics = plan(req, m)
    sites, hidden = geometry(cut, dimensions)
    index = {node: i for i, node in enumerate(planner.inventory(dimensions))}
    indices = [index[node] for node, _ in cut]
    commits = pkg["commits"]
    if not isinstance(commits, list) or len(commits) != len(indices):
        raise ValueError("Incorrect adaptive commitment count.")
    authenticate(indices, commits, pkg["siblings"], len(index), root)
    pages = core.read_pages(pkg["pages"], dimensions)
    values = []
    for i, (page, *rect) in enumerate(sites):
        pixels = core.read_tile(pages[page][2], pages[page][0], rect)
        if i in hidden and any(pixels):
            raise ValueError("A required redaction is not entirely black.")
        values.append(0 if i in hidden else core.tile_scalar(m["id"], cut[i][0], pixels))
    header = {k: v for k, v in pkg.items() if k != "proof"}
    if not core.check_proof(pkg["proof"], core.transcript(header, pages), commits, values, hidden):
        raise ValueError("The proof does not verify for these pages and this request.")
    expected = core.render_export(pages)
    if pdf != expected or sha256(expected).hexdigest() != pkg["pdf_sha256"]:
        raise ValueError("The redacted PDF differs from the verified canonical export.")
    return {"valid": True, "pages": len(pages), "redacted_tiles": len(hidden), "pdf_checked": True,
            "audience": req["audience"], "metrics": metrics}
