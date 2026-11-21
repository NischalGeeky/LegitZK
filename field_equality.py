"""Source-bound proofs of equality for owner-attested redacted fields."""
from datetime import date
from hashlib import sha256
import re
from secrets import randbelow, token_hex
from unicodedata import normalize

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from pdf_redaction import absorb, framed
from protocol import canonical, shape, valid_hex
import rangeproof as group

TYPES = ("amount", "date", "code", "integer")
DOMAIN = "LegitZK/pdf/field-equality/v1"
MAX_FIELDS = 16
OFFSET = 2**31
NUMERIC = ("amount", "integer")


def typed(value, kind, unit):
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError("Enter a value of up to 128 characters.")
    value = normalize("NFKC", value).strip()
    if kind == "amount":
        if not isinstance(unit, str) or not re.fullmatch(r"[A-Z]{3}", unit):
            raise ValueError("Enter a three-letter currency code.")
        symbol = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(unit)
        if symbol:
            value = value.removeprefix(symbol).strip()
        if not re.fullmatch(r"[+-]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})*,[0-9]{3})(?:\.[0-9]{1,2})?", value):
            raise ValueError("Enter an amount with up to two decimal places.")
        value = value.replace(",", "")
        negative = value.startswith("-")
        whole, _, fraction = value.lstrip("+-").partition(".")
        return str((-1 if negative else 1) * (int(whole) * 100 + int(fraction.ljust(2, "0"))))
    if unit != "":
        raise ValueError("Only amount fields take a currency code.")
    if kind == "integer" and re.fullmatch(r"[+-]?[0-9]+", value):
        return str(int(value))
    if kind == "date" and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return date.fromisoformat(value).isoformat()
    if kind == "code" and value and value.isprintable():
        return value.upper()
    raise ValueError("Use a whole number for integers, YYYY-MM-DD for dates, or a nonempty printable code.")


def message(field, value):
    if field.get("encoding") == "bounded-integer":
        number = int(typed(value, field["type"], field["unit"]))
        if not -OFFSET <= number < OFFSET:
            raise ValueError("Number exceeds the supported 32-bit range (cents for amounts).")
        return number + OFFSET
    return absorb(DOMAIN.encode() + b"/value", canonical([
        field["id"], field["type"], field["unit"], typed(value, field["type"], field["unit"])
    ]))


def issue(items, receipt, request, pdf_hash, signer):
    if not isinstance(items, list) or len(items) > MAX_FIELDS:
        raise ValueError("Register up to 16 fields per export.")
    records, witnesses = [], {}
    for item in items:
        keys = ("label", "type", "unit", "value", "region")
        shape(item, (*keys, "description") if isinstance(item, dict) and "description" in item else keys)
        description = item.get("description", "")
        if not isinstance(description, str) or len(description) > 120 or (description and not description.isprintable()):
            raise ValueError("Use a public description of up to 120 printable characters.")
        label = item["label"]
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 80 or not label.strip().isprintable():
            raise ValueError("Enter a public field label of up to 80 printable characters.")
        if not any(canonical(box) == canonical(item["region"]) for box in request["hide"]):
            raise ValueError("Select a hide region that fully covers the field.")
        field = {
            "id": token_hex(16), "label": label.strip(), "type": item["type"], "unit": item["unit"],
            "region": item["region"], "receipt_sha256": sha256(canonical(receipt)).hexdigest(),
            "pdf_sha256": pdf_hash,
        }
        if description.strip():
            field["description"] = description.strip()
        if field["type"] in NUMERIC:
            field["encoding"] = "bounded-integer"
        value = message(field, item["value"])
        blind = randbelow(group.ORDER - 1) + 1
        field["commitment"] = group.commit(value, blind).hex()
        record = {"field": field, "signature": signer.sign(framed(DOMAIN + "/record", field)).hex()}
        witnesses[field["id"]] = (record, value, blind)
        records.append(record)
    return records, witnesses


def check_record(record, trusted_key):
    shape(record, ("field", "signature"))
    field = record["field"]
    keys = ("id", "label", "type", "unit", "region", "receipt_sha256", "pdf_sha256", "commitment")
    if "description" in field:
        keys = (*keys, "description")
    if "encoding" in field:
        shape(field, (*keys, "encoding"))
        if field["encoding"] != "bounded-integer" or field["type"] not in NUMERIC:
            raise ValueError("Unknown numeric encoding.")
    else:
        shape(field, keys)
    if field["type"] not in TYPES:
        raise ValueError("Unknown field datatype.")
    valid_hex(field["id"], 16)
    valid_hex(field["pdf_sha256"], 32)
    valid_hex(field["receipt_sha256"], 32)
    group.point(valid_hex(field["commitment"], 32))
    try:
        Ed25519PublicKey.from_public_bytes(valid_hex(trusted_key, 32)).verify(
            valid_hex(record["signature"], 64), framed(DOMAIN + "/record", field))
    except InvalidSignature:
        raise ValueError("Field record signature is not trusted.") from None
    return field


def check_request(request, record):
    shape(request, ("field_id", "record_sha256", "nonce", "candidate"))
    valid_hex(request["nonce"], 32)
    field = record["field"]
    if request["field_id"] != field["id"] or request["record_sha256"] != sha256(canonical(record)).hexdigest():
        raise ValueError("The request targets a different field or disclosure.")
    return message(field, request["candidate"])


def statement(record, value):
    return group.sub(valid_hex(record["field"]["commitment"], 32), group.mul(value, group.G))


def challenge(record, request, difference, announcement):
    return absorb(DOMAIN.encode() + b"/challenge", sha256(canonical(record)).digest(),
                  sha256(canonical(request)).digest(), difference, announcement)


def prove(witness, request):
    record, value, blind = witness
    if check_request(request, record) != value:
        return None
    difference = statement(record, value)
    nonce = randbelow(group.ORDER - 1) + 1
    announcement = group.mul(nonce, group.H)
    response = nonce + challenge(record, request, difference, announcement) * blind
    return (announcement + group.encode(response)).hex()


def verify(record, request, proof):
    difference = statement(record, check_request(request, record))
    raw = valid_hex(proof, 64)
    announcement, response = group.point(raw[:32]), group.scalar(raw[32:])
    if difference == group.ZERO or announcement == group.ZERO:
        return False
    return group.mul(response, group.H) == group.add(
        announcement, group.mul(challenge(record, request, difference, announcement), difference))
