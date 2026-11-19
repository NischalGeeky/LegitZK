"""Issuer-signed numeric credentials and portable conjunctive range presentations."""
import re
from secrets import randbelow, token_hex
from time import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from protocol import canonical, digest, integer, shape, valid_hex
import rangeproof as zk

SCHEMA = "legitzk/numeric-credential/v1"
POLICY = "legitzk/range-policy/v1"
MAX_ATTRIBUTES = 128
MAX_CLAUSES = 64
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("Invalid issuer, attribute or unit identifier")
    return value


def signed(manifest):
    return b"LegitZK/numeric-credential/v1\0" + canonical(manifest)


def issue(issuer, attributes, expires, key, *, source_sha256=None, now=None):
    now = int(time()) if now is None else now
    identifier(issuer)
    integer(expires, now + 1, 2**53 - 1)
    if source_sha256 is not None:
        valid_hex(source_sha256, 32)
    if not isinstance(attributes, dict) or not 1 <= len(attributes) <= MAX_ATTRIBUTES:
        raise ValueError("Invalid attribute inventory")
    commitments, openings = {}, {}
    for name, item in attributes.items():
        identifier(name)
        shape(item, ("value", "unit"))
        value, unit = item["value"], identifier(item["unit"])
        integer(value, 0, zk.MAX)
        blind = randbelow(zk.ORDER)
        commitments[name] = {"unit": unit, "point": zk.commit(value, blind).hex()}
        openings[name] = {"value": value, "blind": zk.encode(blind).hex()}
    manifest = {"schema": SCHEMA, "id": token_hex(16), "issuer": issuer, "issued": now,
                "expires": expires, "source_sha256": source_sha256, "attributes": commitments}
    public = {"manifest": manifest, "signature": key.sign(signed(manifest)).hex()}
    return {"credential": public, "openings": openings}


def validate_policy(policy, now):
    shape(policy, ("schema", "audience", "nonce", "expires", "clauses"))
    if policy["schema"] != POLICY:
        raise ValueError("Unsupported policy schema")
    identifier(policy["audience"])
    valid_hex(policy["nonce"], 32)
    integer(policy["expires"], now + 1, 2**53 - 1)
    clauses = policy["clauses"]
    if not isinstance(clauses, list) or not 1 <= len(clauses) <= MAX_CLAUSES:
        raise ValueError("Invalid clause inventory")
    for clause in clauses:
        shape(clause, ("credential_id", "issuer", "attribute", "unit", "min", "max"))
        valid_hex(clause["credential_id"], 16)
        for key in ("issuer", "attribute", "unit"):
            identifier(clause[key])
        integer(clause["min"], 0, zk.MAX)
        integer(clause["max"], clause["min"], zk.MAX)


def authenticate(public, trust, now):
    shape(public, ("manifest", "signature"))
    manifest = public["manifest"]
    shape(manifest, ("schema", "id", "issuer", "issued", "expires", "source_sha256", "attributes"))
    if manifest["schema"] != SCHEMA:
        raise ValueError("Unsupported credential schema")
    valid_hex(manifest["id"], 16)
    issuer = identifier(manifest["issuer"])
    if issuer not in trust:
        raise ValueError("Credential issuer is not trusted")
    integer(manifest["issued"], 0, now)
    integer(manifest["expires"], now + 1, 2**53 - 1)
    if manifest["source_sha256"] is not None:
        valid_hex(manifest["source_sha256"], 32)
    Ed25519PublicKey.from_public_bytes(valid_hex(trust[issuer], 32)).verify(
        valid_hex(public["signature"], 64), signed(manifest))
    attributes = manifest["attributes"]
    if not isinstance(attributes, dict) or not 1 <= len(attributes) <= MAX_ATTRIBUTES:
        raise ValueError("Invalid signed attribute inventory")
    for name, item in attributes.items():
        identifier(name)
        shape(item, ("unit", "point"))
        identifier(item["unit"])
        zk.point(valid_hex(item["point"], 32))
    return manifest


def resolve(policy, credentials, trust, now):
    needed = {clause["credential_id"] for clause in policy["clauses"]}
    shape(credentials, needed)
    manifests = {key: authenticate(public, trust, now) for key, public in credentials.items()}
    for clause in policy["clauses"]:
        key = clause["credential_id"]
        manifest = manifests[key]
        item = manifest["attributes"][clause["attribute"]]
        if (manifest["id"] != key or manifest["issuer"] != clause["issuer"]
                or item["unit"] != clause["unit"]):
            raise ValueError("Credential, issuer or unit differs from the requested clause")
        yield zk.point(valid_hex(item["point"], 32))


def context(policy, credentials, index):
    return bytes.fromhex(digest("LegitZK/numeric-presentation/v1", [policy, credentials, index]))


def prove(records, policy, trust, now=None):
    now = int(time()) if now is None else now
    validate_policy(policy, now)
    if not isinstance(records, dict):
        raise ValueError("Expected credentials indexed by ID")
    for record in records.values():
        shape(record, ("credential", "openings"))
    public = {key: record["credential"] for key, record in records.items()}
    commitments = list(resolve(policy, public, trust, now))
    proofs = []
    for index, (clause, commitment) in enumerate(zip(policy["clauses"], commitments)):
        opening = records[clause["credential_id"]]["openings"][clause["attribute"]]
        shape(opening, ("value", "blind"))
        value = opening["value"]
        integer(value, clause["min"], clause["max"])
        blind = zk.scalar(valid_hex(opening["blind"], 32))
        if zk.commit(value, blind) != commitment:
            raise ValueError("Private opening differs from the signed attribute")
        transcript = context(policy, public, index)
        proofs.append([
            zk.prove_bits(value - clause["min"], blind, transcript, 0),
            zk.prove_bits(clause["max"] - value, -blind, transcript, 1),
        ])
    return {"policy": policy, "credentials": public, "proofs": proofs}


def verify(presentation, policy, trust, now=None):
    now = int(time()) if now is None else now
    try:
        validate_policy(policy, now)
        shape(presentation, ("policy", "credentials", "proofs"))
        if canonical(presentation["policy"]) != canonical(policy):
            return False
        public, proofs = presentation["credentials"], presentation["proofs"]
        if not isinstance(proofs, list) or len(proofs) != len(policy["clauses"]):
            return False
        commitments = resolve(policy, public, trust, now)
        for index, (clause, proof, commitment) in enumerate(zip(policy["clauses"], proofs, commitments)):
            if not isinstance(proof, list) or len(proof) != 2:
                return False
            transcript = context(policy, public, index)
            if not zk.verify_bits(proof[0], zk.sub(commitment, zk.mul(clause["min"], zk.G)), transcript, 0):
                return False
            if not zk.verify_bits(proof[1], zk.sub(zk.mul(clause["max"], zk.G), commitment), transcript, 1):
                return False
        return True
    except (InvalidSignature, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False

def interval_review(proposed, history, trust, now=None):
    """Intersect past policy bounds with a proposed policy for the same signed credential ID."""
    now = int(time()) if now is None else now
    validate_policy(proposed, now)
    effective = {}
    used = {}
    identities = {}
    for presentation in history:
        old = presentation["policy"]
        # Verify at the present time. Expired history requires a separately authenticated
        # timestamp and is therefore outside the supported CLI workflow.
        if not verify(presentation, old, trust, now) or old["audience"] != proposed["audience"]:
            raise ValueError("A prior presentation is invalid, expired or scoped to another audience")
        for clause in old["clauses"]:
            cid = clause["credential_id"]
            record = canonical(presentation["credentials"][cid])
            key = (cid, clause["issuer"], clause["attribute"], clause["unit"])
            if cid in identities and identities[cid] != record:
                raise ValueError("Conflicting signed credentials share a credential ID")
            identities[cid] = record
            lower, upper = effective.get(key, (0, zk.MAX))
            effective[key] = max(lower, clause["min"]), min(upper, clause["max"])
            used[key] = used.get(key, 0) + 1
    preview = {}
    for clause in proposed["clauses"]:
        key = tuple(clause[name] for name in ("credential_id", "issuer", "attribute", "unit"))
        lower, upper = preview.get(key, effective.get(key, (0, zk.MAX)))
        preview[key] = max(lower, clause["min"]), min(upper, clause["max"])
    result = []
    for key, interval in preview.items():
        before = effective.get(key, (0, zk.MAX))
        lower, upper = interval
        result.append(dict(zip(("credential_id", "issuer", "attribute", "unit"), key), previous=before,
                           combined=interval, prior_clauses=used.get(key, 0),
                           possible_values=max(0, upper - lower + 1)))
    return result
