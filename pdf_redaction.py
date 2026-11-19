"""Committed PDF raster redaction with request-bound Schnorr proofs."""
import base64
from hashlib import sha256, sha512
from io import BytesIO
from secrets import randbelow, token_hex
from time import time
import zlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import fitz
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

import rangeproof as group
from protocol import canonical, integer, shape, valid_hex

PROFILE = "legitzk/rgb96-tile32/v1"
TILE = 32
MAX_PAGES = 8
MAX_DIM = 2300
MAX_PIXELS = 8_000_000
MAX_SOURCE = 16 * 1024 * 1024


def framed(domain, value):
    return domain.encode() + b"\0" + canonical(value)


def render_source(raw, max_bytes=MAX_SOURCE):
    if not raw.startswith(b"%PDF-") or len(raw) > max_bytes:
        raise ValueError("Choose a PDF within the supported file size.")
    pages = []
    pixels = 0
    with fitz.open(stream=raw, filetype="pdf") as doc:
        if doc.needs_pass or not 1 <= len(doc) <= MAX_PAGES:
            raise ValueError("Choose an unencrypted PDF with 1–8 pages.")
        for page in doc:
            rect = (page.rect * fitz.Matrix(4 / 3, 4 / 3)).irect
            w, h = rect.width, rect.height
            pixels += w * h
            if not (1 <= w <= MAX_DIM and 1 <= h <= MAX_DIM and pixels <= MAX_PIXELS):
                raise ValueError("PDF dimensions exceed the supported 96 DPI raster limits.")
            pix = page.get_pixmap(matrix=fitz.Matrix(4 / 3, 4 / 3), colorspace=fitz.csRGB,
                                  alpha=False, annots=False)
            if (pix.width, pix.height) != (w, h):
                raise ValueError("Unexpected page dimensions.")
            pages.append((w, h, pix.samples))
    return pages


def tiles(w, h):
    return [(x, y, min(x + TILE, w), min(y + TILE, h))
            for y in range(0, h, TILE) for x in range(0, w, TILE)]


def tile_sites(dimensions):
    return [(i, *rect) for i, (w, h) in enumerate(dimensions) for rect in tiles(w, h)]


def read_tile(raw, w, rect):
    x, y, right, bottom = rect
    return b"".join(raw[(r * w + x) * 3:(r * w + right) * 3] for r in range(y, bottom))


def tile_scalar(profile_id, site, raw):
    digest = sha512(framed("LegitZK/pdf/tile/v1", [profile_id, *site]) + raw).digest()
    return int.from_bytes(digest, "little") % group.ORDER


def absorb(domain, *values):
    return int.from_bytes(sha512(domain + b"\0" + b"".join(values)).digest(), "little") % group.ORDER


def issue_source(raw, key):
    pages = render_source(raw)
    source_id = token_hex(16)
    dimensions = [[w, h] for w, h, _ in pages]
    openings = []
    commits = []
    for site in tile_sites(dimensions):
        i, *rect = site
        w, _, rgb = pages[i]
        value = tile_scalar(source_id, site, read_tile(rgb, w, rect))
        blind = randbelow(group.ORDER)
        openings.append((value, blind))
        commits.append(group.commit(value, blind).hex())
    manifest = {"profile": PROFILE, "id": source_id, "source_sha256": sha256(raw).hexdigest(),
                "pages": dimensions, "commitment_sha256": sha256(framed("LegitZK/pdf/vector/v1", commits)).hexdigest()}
    receipt = {"manifest": manifest, "signature": key.sign(framed("LegitZK/pdf/receipt/v1", manifest)).hex()}
    return receipt, pages, commits, openings


def new_request(receipt, maximum_pct, protected, audience):
    if not isinstance(maximum_pct, int) or isinstance(maximum_pct, bool) or not 1 <= maximum_pct <= 99:
        raise ValueError("Choose a maximum redaction percentage from 1 through 99.")
    request = {"source_id": receipt["manifest"]["id"], "audience": audience, "nonce": token_hex(32),
               "expires": int(time()) + 3600, "max_percent": maximum_pct, "protected": protected}
    validate_request(request, receipt["manifest"])
    return request


def validate_request(req, manifest, now=None):
    shape(req, ("source_id", "audience", "nonce", "expires", "max_percent", "protected"))
    if req["source_id"] != manifest["id"]:
        raise ValueError("Request is for a different source.")
    if not isinstance(req["audience"], str) or not 1 <= len(req["audience"]) <= 100 or not req["audience"].isprintable():
        raise ValueError("Enter a printable audience name.")
    valid_hex(req["nonce"], 32)
    integer(req["expires"], (int(time()) if now is None else now) + 1, 2**53 - 1)
    integer(req["max_percent"], 1, 99)
    validate_selection(req["protected"], len(tile_sites(manifest["pages"])), required=False)


def validate_selection(selection, size, *, required=True):
    if not isinstance(selection, list) or len(selection) > size or (required and not selection):
        raise ValueError("Select at least one valid redaction tile.")
    for index in selection:
        integer(index, 0, size - 1)
    if selection != sorted(set(selection)):
        raise ValueError("Tile selections must be sorted and unique.")


def check_mask(mask, manifest, req, sites):
    validate_selection(mask, len(sites))
    hidden = set(mask)
    if hidden.intersection(req["protected"]):
        raise ValueError("The mask covers a protected tile.")
    areas = [0] * len(manifest["pages"])
    for index in mask:
        i, x, y, right, bottom = sites[index]
        areas[i] += (right - x) * (bottom - y)
    for area, (w, h) in zip(areas, manifest["pages"]):
        if area * 100 > req["max_percent"] * w * h:
            raise ValueError("The mask exceeds the request's per-page redaction budget.")
    return hidden


def redact(pages, sites, hidden):
    redacted = [(w, h, bytearray(raw)) for w, h, raw in pages]
    for index in hidden:
        i, x, y, right, bottom = sites[index]
        w, _, data = redacted[i]
        black = bytes((right - x) * 3)
        for r in range(y, bottom):
            start = (r * w + x) * 3
            data[start:start + len(black)] = black
    return [(w, h, bytes(raw)) for w, h, raw in redacted]


def render_export(pages):
    result = BytesIO()
    pdf = canvas.Canvas(result, invariant=1, pageCompression=1)
    pdf.setTitle("LegitZK redacted disclosure")
    for w, h, rgb in pages:
        width, height = w * 0.75, h * 0.75
        pdf.setPageSize((width, height))
        pdf.drawImage(ImageReader(Image.frombytes("RGB", (w, h), rgb)), 0, 0, width, height)
        pdf.showPage()
    pdf.save()
    return result.getvalue()


def audit_export(raw):
    """Check the raster-only export before it leaves the studio."""
    with fitz.open(stream=raw, filetype="pdf") as doc:
        checks = {
            "no_embedded_files": doc.embfile_count() == 0,
            "no_optional_layers": not doc.get_ocgs(),
            "no_xml_metadata": not doc.get_xml_metadata(),
            "no_source_metadata": (
                not doc.metadata.get("keywords")
                and doc.metadata.get("subject") in ("", "unspecified")
                and doc.metadata.get("title") == "LegitZK redacted disclosure"
                and doc.metadata.get("author") in ("", "anonymous")
                and doc.metadata.get("creator") in ("", "anonymous")
            ),
            "no_text_layer": True,
            "no_annotations_forms_or_links": True,
        }
        for page in doc:
            checks["no_text_layer"] &= not page.get_text().strip()
            checks["no_annotations_forms_or_links"] &= not page.annot_xrefs() and not page.get_links()
    if not all(checks.values()):
        raise ValueError("The redacted PDF failed the raster-only export checks.")
    return checks


def read_pages(encoded, dimensions):
    if not isinstance(encoded, list) or len(encoded) != len(dimensions):
        raise ValueError("Wrong number of disclosure pages.")
    result = []
    for value, (w, h) in zip(encoded, dimensions):
        size = w * h * 3
        if not isinstance(value, str) or len(value) > size * 2 + 1024:
            raise ValueError("Invalid disclosure raster encoding.")
        zdata = base64.b64decode(value, validate=True)
        decompressor = zlib.decompressobj()
        pixels = decompressor.decompress(zdata, size + 1)
        if len(pixels) != size or not decompressor.eof or decompressor.unused_data:
            raise ValueError("Invalid disclosure raster size.")
        result.append((w, h, pixels))
    return result


def transcript(body, pages):
    header = {k: value for k, value in body.items() if k != "pages"}
    header["page_hashes"] = [sha256(raw).hexdigest() for _, _, raw in pages]
    return sha256(framed("LegitZK/pdf/presentation/v1", header)).digest()


def weighted_points(context, commits, values, hidden):
    visible_point = group.ZERO
    hidden_point = group.ZERO
    weights = []
    for i, commit in enumerate(commits):
        coefficient = absorb(b"LegitZK/pdf/coefficient/v1", context, i.to_bytes(4, "big")) or 1
        cpoint = group.point(valid_hex(commit, 32))
        if i in hidden:
            hidden_point = group.add(hidden_point, group.mul(coefficient, cpoint))
        else:
            difference = group.sub(cpoint, group.mul(values[i], group.G))
            visible_point = group.add(visible_point, group.mul(coefficient, difference))
        weights.append(coefficient)
    return visible_point, hidden_point, weights


def make_proof(context, commits, openings, hidden):
    visible, private, weights = weighted_points(context, commits, [v for v, _ in openings], hidden)
    digest_opening = sum(weights[i] * openings[i][0] for i in hidden) % group.ORDER
    hidden_blind = sum(weights[i] * openings[i][1] for i in hidden) % group.ORDER
    visible_blind = sum(w * openings[i][1] for i, w in enumerate(weights) if i not in hidden) % group.ORDER
    a, b, c = (randbelow(group.ORDER) for _ in range(3))
    A, B = group.mul(a, group.H), group.commit(b, c)
    challenge = absorb(b"LegitZK/pdf/schnorr/v1", context, visible, private, A, B)
    return (A + B + group.encode(a + challenge * visible_blind)
            + group.encode(b + challenge * digest_opening)
            + group.encode(c + challenge * hidden_blind)).hex()


def check_proof(proof, context, commits, values, hidden):
    raw = valid_hex(proof, 160)
    A, B = group.point(raw[:32]), group.point(raw[32:64])
    a, b, c = (group.scalar(raw[i:i+32]) for i in (64, 96, 128))
    visible, private, _ = weighted_points(context, commits, values, hidden)
    challenge = absorb(b"LegitZK/pdf/schnorr/v1", context, visible, private, A, B)
    return (group.mul(a, group.H) == group.add(A, group.mul(challenge, visible))
            and group.commit(b, c) == group.add(B, group.mul(challenge, private)))


def present(source, request, mask):
    receipt, pages, commits, openings = source
    manifest = receipt["manifest"]
    sites = tile_sites(manifest["pages"])
    validate_request(request, manifest)
    hidden = check_mask(mask, manifest, request, sites)
    disclosure = redact(pages, sites, hidden)
    pdf = render_export(disclosure)
    package = {"receipt": receipt, "request": request, "mask": mask, "commits": commits,
               "pages": [base64.b64encode(zlib.compress(raw)).decode() for _, _, raw in disclosure],
               "pdf_sha256": sha256(pdf).hexdigest()}
    package["proof"] = make_proof(transcript(package, disclosure), commits, openings, hidden)
    return package, pdf


def verify(package, expected_receipt, expected_request, trusted_key, pdf=None):
    """All three expected verification inputs must arrive independently of the package."""
    shape(package, ("receipt", "request", "mask", "commits", "pages", "pdf_sha256", "proof"))
    if package["receipt"] != expected_receipt or package["request"] != expected_request:
        raise ValueError("The package does not match the independently retained receipt and request.")
    shape(expected_receipt, ("manifest", "signature"))
    manifest = expected_receipt["manifest"]
    shape(manifest, ("profile", "id", "source_sha256", "pages", "commitment_sha256"))
    if manifest["profile"] != PROFILE:
        raise ValueError("Unsupported raster profile.")
    valid_hex(manifest["id"], 16)
    valid_hex(manifest["source_sha256"], 32)
    valid_hex(manifest["commitment_sha256"], 32)
    signature = valid_hex(expected_receipt["signature"], 64)
    try:
        Ed25519PublicKey.from_public_bytes(valid_hex(trusted_key, 32)).verify(
            signature, framed("LegitZK/pdf/receipt/v1", manifest))
    except InvalidSignature as exc:
        raise ValueError("Ingestion signature is invalid.") from exc
    dimensions = manifest["pages"]
    if not isinstance(dimensions, list) or not 1 <= len(dimensions) <= MAX_PAGES:
        raise ValueError("Invalid page inventory.")
    total = 0
    for pair in dimensions:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("Invalid page dimensions.")
        w, h = pair
        integer(w, 1, MAX_DIM)
        integer(h, 1, MAX_DIM)
        total += w * h
    integer(total, 1, MAX_PIXELS)
    validate_request(expected_request, manifest)
    sites = tile_sites(dimensions)
    hidden = check_mask(package["mask"], manifest, expected_request, sites)
    commits = package["commits"]
    if not isinstance(commits, list) or len(commits) != len(sites):
        raise ValueError("Wrong commitment count.")
    if sha256(framed("LegitZK/pdf/vector/v1", commits)).hexdigest() != manifest["commitment_sha256"]:
        raise ValueError("Commitment inventory differs from the signed receipt.")
    pages = read_pages(package["pages"], dimensions)
    values = []
    for index, site in enumerate(sites):
        i, *rect = site
        w, _, raw = pages[i]
        tile = read_tile(raw, w, rect)
        if index in hidden and any(tile):
            raise ValueError("A redaction tile is not solid black.")
        values.append(0 if index in hidden else tile_scalar(manifest["id"], site, tile))
    body = {k: v for k, v in package.items() if k != "proof"}
    if not check_proof(package["proof"], transcript(body, pages), commits, values, hidden):
        raise ValueError("The proof does not verify for the disclosed pixels and request.")
    expected_pdf = render_export(pages)
    if sha256(expected_pdf).hexdigest() != package["pdf_sha256"] or (pdf is not None and pdf != expected_pdf):
        raise ValueError("The PDF differs from the verified canonical raster export.")
    return {"valid": True, "pages": len(pages), "redacted_tiles": len(hidden),
            "pdf_checked": pdf is not None, "audience": expected_request["audience"]}
