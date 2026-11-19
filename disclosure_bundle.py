"""Signed export inventory and bounded proof ZIP handling."""
from hashlib import sha256
from io import BytesIO
from zipfile import BadZipFile, ZIP_STORED, ZIP_DEFLATED, ZipFile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from pdf_redaction import framed
from protocol import canonical, parse_json, shape, valid_hex

DOMAIN = "LegitZK/pdf/export-inventory/v1"
FILES = {"package": "proof-package.json", "receipt": "source-receipt.json",
         "request": "verification-request.json", "key": "ingestion-key.json"}
PDF = "redacted.pdf"
MANIFEST = "export-manifest.json"
MAX_ZIP = 48_000_000
MAX_JSON = 72_000_000
MAX_PDF = 36_000_000


def digest(raw):
    return sha256(raw).hexdigest()


def pack(package, pdf, signing_key, public_key):
    values = {"package": package, "receipt": package["receipt"], "request": package["request"],
              "key": {"public_key": public_key}}
    files = {name: canonical(values[field]) for field, name in FILES.items()}
    hashes = {name: digest(raw) for name, raw in files.items()}
    hashes[PDF] = digest(pdf)
    manifest = {"files": hashes, "signature": signing_key.sign(framed(DOMAIN, hashes)).hex()}
    files[MANIFEST] = canonical(manifest)
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    return buffer.getvalue()


def unpack(raw, pdf, trusted_keys):
    expected = {*FILES.values(), MANIFEST}
    try:
        with ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if (len(entries) != len(names) or not names <= expected or MANIFEST not in names
                    or sum(entry.file_size for entry in entries) > MAX_JSON
                    or any(entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED)
                           or entry.flag_bits & 1 for entry in entries)):
                raise ValueError("The proof ZIP has an invalid file inventory.")
            files = {entry.filename: archive.read(entry) for entry in entries}
    except (BadZipFile, RuntimeError, EOFError) as exc:
        raise ValueError("The proof ZIP is invalid or damaged.") from exc
    manifest = parse_json(files[MANIFEST])
    shape(manifest, ("files", "signature"))
    hashes = manifest["files"]
    shape(hashes, (*FILES.values(), PDF))
    for value in hashes.values():
        valid_hex(value, 32)
    signature = valid_hex(manifest["signature"], 64)
    message = framed(DOMAIN, hashes)
    for trusted_key in trusted_keys:
        try:
            Ed25519PublicKey.from_public_bytes(valid_hex(trusted_key, 32)).verify(signature, message)
        except InvalidSignature:
            continue
        break
    else:
        raise ValueError("The export manifest could not be authenticated with this Studio's trusted keys.")
    files[PDF] = pdf
    checks = {name: ("missing" if name not in files else
                     "match" if digest(files[name]) == value else "changed")
              for name, value in hashes.items()}
    if any(checks[name] != "match" for name in FILES.values()):
        return None, checks, trusted_key
    return {field: parse_json(files[name]) for field, name in FILES.items()}, checks, trusted_key
