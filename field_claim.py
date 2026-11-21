"""Prove a recipient-confirmed predicate over a signed field commitment."""
from hashlib import sha256

import field_equality as equality
from pdf_redaction import framed
from protocol import shape, valid_hex, canonical
import rangeproof as group

OPERATORS = ("eq", "ge", "gt", "le", "lt", "between")
SYMBOLS = dict(zip(OPERATORS, ("=", "≥", ">", "≤", "<", "between")))


def condition(field, operator, values):
    if operator not in OPERATORS or not isinstance(values, list) or len(values) != (2 if operator == "between" else 1):
        raise ValueError("Use one supported comparison and the required bounds.")
    if operator != "eq" and field.get("encoding") != "bounded-integer":
        raise ValueError("This field supports equality only. For numeric ranges, register and export it again.")
    encoded = [equality.message(field, x) for x in values]
    if operator == "between" and encoded[0] > encoded[1]:
        raise ValueError("The lower bound must precede the upper bound.")
    display = values[0] if operator != "between" else f"{values[0]} and {values[1]} (inclusive)"
    unit = field["unit"]
    return f'{field["label"]} {SYMBOLS[operator]} {display}' + (f" [{unit}]" if unit else "")


def check(record, request):
    shape(request, ("field_id", "record_sha256", "nonce", "operator", "values"))
    valid_hex(request["nonce"], 32)
    field = record["field"]
    if request["field_id"] != field["id"] or request["record_sha256"] != sha256(canonical(record)).hexdigest():
        raise ValueError("This request targets another field or export.")
    operator, values = request["operator"], request["values"]
    return condition(field, operator, values)


def interval(record, request):
    check(record, request)
    field, operator = record["field"], request["operator"]
    bounds = [equality.message(field, x) for x in request["values"]]
    t = bounds[0]
    low, high = {
        "ge": (t, group.MAX), "gt": (t + 1, group.MAX),
        "le": (0, t), "lt": (0, t - 1), "between": (t, bounds[-1]),
    }[operator]
    if not 0 <= low <= high <= group.MAX:
        raise ValueError("The comparison has no values in the supported range.")
    context = sha256(framed("LegitZK/pdf/field-range/v1", [record, request])).digest()
    return low, high, context


def equality_request(record, request):
    # The existing equality transcript binds the candidate, record and nonce.
    result = {key: request[key] for key in ("field_id", "record_sha256", "nonce")}
    result["candidate"] = request["values"][0]
    return result


def prove(witness, request):
    record, value, blind = witness
    if request["operator"] == "eq":
        check(record, request)
        return equality.prove(witness, equality_request(record, request))
    low, high, context = interval(record, request)
    if not low <= value <= high:
        return None
    return [group.prove_bits(value - low, blind, context, 0),
            group.prove_bits(high - value, -blind, context, 1)]


def verify(record, request, proof):
    if request["operator"] == "eq":
        check(record, request)
        return equality.verify(record, equality_request(record, request), proof)
    low, high, context = interval(record, request)
    if not isinstance(proof, list) or len(proof) != 2 or any(not isinstance(side, list) for side in proof):
        return False
    commitment = valid_hex(record["field"]["commitment"], 32)
    return (group.verify_bits(proof[0], group.sub(commitment, group.mul(low, group.G)), context, 0)
            and group.verify_bits(proof[1], group.sub(group.mul(high, group.G), commitment), context, 1))
