"""Versioned vendor-contract protocol and offline verification."""
import base64
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import re
from secrets import randbelow, token_hex
from time import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from reportlab.pdfgen import canvas
import rangeproof as zk

SCHEMA = "vendor-contract-usd/v1"
FIELDS = ("vendor", "buyer", "effective_date", "service", "bank_reference")
REQUIRED = {"vendor", "buyer", "effective_date"}
TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .,&()/+_-]{0,83}\Z", re.ASCII)


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(domain, value):
    return sha256(domain.encode() + b"\x00" + canonical(value)).hexdigest()


def shape(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError("Unexpected fields or data type")


def valid_hex(value, size):
    if not isinstance(value, str) or not re.fullmatch(f"[0-9a-f]{{{size * 2}}}", value):
        raise ValueError("Invalid hex encoding")
    return bytes.fromhex(value)


def integer(value, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError("Integer outside the supported range")


def validate_field(key, value):
    if key not in FIELDS or not isinstance(value, str) or not TEXT.fullmatch(value):
        raise ValueError("Invalid contract field")
    if key == "effective_date":
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("Use YYYY-MM-DD for the effective date")
        datetime.strptime(value, "%Y-%m-%d")


def render(values, document_id, original=False):
    """Fresh PDF from explicitly allowed fields. No source PDF objects are copied."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(595, 842), invariant=1, pageCompression=1)
    pdf.setTitle("Vendor contract" if original else "Vendor contract disclosure")
    pdf.setFillColorRGB(.045, .095, .16)
    pdf.rect(0, 683, 595, 159, fill=1, stroke=0)
    pdf.setFillColorRGB(.4, .9, .78)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(48, 784, "LEGITZK")
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 25)
    pdf.drawString(48, 741, "Vendor contract" if original else "Vendor contract disclosure")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(48, 711, document_id)
    labels = {"vendor": "Vendor", "buyer": "Buyer", "effective_date": "Effective date",
              "service": "Service", "bank_reference": "Bank reference", "amount": "Amount (USD cents)"}
    for i, key in enumerate((*FIELDS, "amount")):
        y = 622 - 79 * i
        pdf.setFillColorRGB(.17, .24, .33)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(48, y, labels[key])
        if key in values:
            pdf.setFont("Helvetica", 11)
            pdf.drawString(48, y - 23, str(values[key]))
        else:
            pdf.setFillColorRGB(.045, .095, .16)
            pdf.roundRect(48, y - 28, 185, 17, 3, fill=1, stroke=0)
    pdf.setFillColorRGB(.24, .3, .4)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(48, 61, "Synthetic contract record" if original else "Schema-based disclosure derived from issuer-attested claims")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def leaf(field, value, salt):
    return digest("LegitZK/field/v1", [SCHEMA, field, value, salt])


def issue(values, issuer_id, secret, now=None):
    shape(values, (*FIELDS, "amount"))
    for key in FIELDS:
        validate_field(key, values[key])
    integer(values["amount"], 0, zk.MAX)
    now = int(time()) if now is None else now
    document_id = token_hex(16)
    salts = {key: token_hex(32) for key in FIELDS}
    blind = randbelow(zk.ORDER)
    source = render(values, document_id, original=True)
    manifest = {
        "schema": SCHEMA, "id": document_id, "issuer": issuer_id,
        "source_sha256": sha256(source).hexdigest(), "issued": now, "expires": now + 86400 * 30,
        "inventory": {key: leaf(key, values[key], salts[key]) for key in FIELDS},
        "amount_commitment": zk.commit(values["amount"], blind).hex(),
    }
    return {"manifest": manifest, "signature": secret.sign(signed(manifest)).hex(),
            "values": values, "salts": salts, "blind": str(blind)}, source


def signed(manifest):
    return b"LegitZK/manifest/v1\x00" + canonical(manifest)


def validate_request(request):
    shape(request, ("policy", "context"))
    policy, context = request["policy"], request["context"]
    shape(policy, ("version", "schema", "issuer", "visible", "threshold"))
    shape(context, ("document_id", "audience", "nonce", "expires"))
    if policy["version"] != 1 or type(policy["version"]) is not int or policy["schema"] != SCHEMA:
        raise ValueError("Unsupported policy version or schema")
    visible = policy["visible"]
    if (not isinstance(visible, list) or any(type(v) is not str for v in visible)
            or visible != sorted(set(visible)) or not REQUIRED <= set(visible) <= set(FIELDS)
            or "bank_reference" in visible):
        raise ValueError("Visibility must include required fields and protect bank reference")
    integer(policy["threshold"], 0, zk.MAX)
    integer(context["expires"], 0, 2**53 - 1)
    valid_hex(context["document_id"], 16)
    valid_hex(context["nonce"], 32)
    audience = context["audience"]
    issuer = policy["issuer"]
    if (not isinstance(issuer, str) or not TEXT.fullmatch(issuer) or not isinstance(audience, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .@_+-]{0,203}", audience) is None):
        raise ValueError("Invalid audience or issuer")


def request_for(doc_id, issuer, threshold, audience, include_service, now=None):
    now = int(time()) if now is None else now
    request = {
        "policy": {"version": 1, "schema": SCHEMA, "issuer": issuer,
                   "visible": sorted(REQUIRED | ({"service"} if include_service else set())),
                   "threshold": threshold},
        "context": {"document_id": doc_id, "audience": audience, "nonce": token_hex(32), "expires": now + 3600},
    }
    validate_request(request)
    return request


def transcript(body):
    return bytes.fromhex(digest("LegitZK/presentation/v1", body))


def present(record, request):
    validate_request(request)
    manifest = record["manifest"]
    disclosure = {key: {"value": record["values"][key], "salt": record["salts"][key]}
                  for key in request["policy"]["visible"]}
    pdf = render({k: item["value"] for k, item in disclosure.items()}, manifest["id"])
    body = {"manifest": manifest, "signature": record["signature"], "request": request,
            "disclosure": disclosure, "pdf_sha256": sha256(pdf).hexdigest()}
    proof = zk.prove(record["values"]["amount"], int(record["blind"]),
                     request["policy"]["threshold"], transcript(body))
    return {**body, "proof": proof, "pdf": base64.b64encode(pdf).decode()}


def verify(package, expected, trust, now=None):
    """expected policy/context and trust are supplied independently of the package."""
    checks = []
    stage = "Package"
    try:
        if type(trust) is not dict:
            raise ValueError("Invalid trust store")
        shape(package, ("manifest", "signature", "request", "disclosure", "pdf_sha256", "proof", "pdf"))
        stage = "Policy and request"
        validate_request(expected)
        validate_request(package["request"])
        if canonical(package["request"]) != canonical(expected):
            raise ValueError("Presentation differs from the expected request")
        now = int(time()) if now is None else now
        policy, context = expected["policy"], expected["context"]
        if now >= context["expires"]:
            raise ValueError("Request has expired")
        checks.append({"check": stage, "passed": True})
        stage = "Issuer signature"
        m = package["manifest"]
        shape(m, ("schema", "id", "issuer", "source_sha256", "issued", "expires", "inventory", "amount_commitment"))
        if (m["issuer"] != policy["issuer"] or m["issuer"] not in trust or m["schema"] != SCHEMA
                or m["id"] != context["document_id"]):
            raise ValueError("Issuer, schema or document differs from request")
        integer(m["issued"], 0, now)
        integer(m["expires"], now + 1, 2**53 - 1)
        valid_hex(m["source_sha256"], 32)
        commitment = zk.point(valid_hex(m["amount_commitment"], 32))
        Ed25519PublicKey.from_public_bytes(valid_hex(trust[m["issuer"]], 32)).verify(
            valid_hex(package["signature"], 64), signed(m))
        checks.append({"check": stage, "passed": True})
        stage = "Disclosed claims"
        shape(m["inventory"], FIELDS)
        for claim_hash in m["inventory"].values():
            valid_hex(claim_hash, 32)
        disclosure = package["disclosure"]
        shape(disclosure, policy["visible"])
        for key, item in disclosure.items():
            shape(item, ("value", "salt"))
            validate_field(key, item["value"])
            valid_hex(item["salt"], 32)
            if leaf(key, item["value"], item["salt"]) != m["inventory"][key]:
                raise ValueError("Claim does not open its signed commitment")
        checks.append({"check": stage, "passed": True})
        stage = "Disclosure PDF"
        if not isinstance(package["pdf"], str) or len(package["pdf"]) > 65536:
            raise ValueError("Invalid disclosure PDF size")
        pdf = base64.b64decode(package["pdf"], validate=True)
        regenerated = render({k: v["value"] for k, v in disclosure.items()}, m["id"])
        if pdf != regenerated or package["pdf_sha256"] != sha256(pdf).hexdigest():
            raise ValueError("PDF differs from the canonical public-claims rendering")
        checks.append({"check": stage, "passed": True})
        stage = "Private threshold proof"
        body = {k: v for k, v in package.items() if k not in ("proof", "pdf")}
        if not zk.verify(package["proof"], commitment, policy["threshold"], transcript(body)):
            raise ValueError("Invalid proof for this presentation")
        checks.append({"check": stage, "passed": True})
        return {"valid": True, "checks": checks}
    except (InvalidSignature, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        checks.append({"check": stage, "passed": False})
        return {"valid": False, "checks": checks}


def parse_json(data):
    def unique(items):
        result = dict(items)
        if len(result) != len(items):
            raise ValueError("Duplicate JSON keys")
        return result
    def reject_constant(_):
        raise ValueError("Non-JSON numeric value")
    return json.loads(data, object_pairs_hook=unique, parse_constant=reject_constant)
