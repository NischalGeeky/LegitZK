"""Issue, prove and independently verify signed numeric credentials."""
import argparse
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import credential_proof as engine
from protocol import parse_json

MAX_INPUT = 4 << 20


def load(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_INPUT + 1)
    if len(data) > MAX_INPUT:
        raise ValueError("Input exceeds the CLI size limit")
    return parse_json(data)


def write(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
        stream.write(data + "\n")


def output(path, obj):
    write(path, json.dumps(obj, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    keygen = commands.add_parser("keygen", help="Create a new private issuer key and separate public trust file")
    for name in ("issuer", "private_key", "trust"):
        keygen.add_argument(name)
    issue = commands.add_parser("issue", help="Sign private numeric attributes")
    for name in ("issuer", "private_key", "attributes", "holder_record"):
        issue.add_argument(name)
    issue.add_argument("--expires", required=True, type=int)
    issue.add_argument("--source-sha256")
    prove = commands.add_parser("prove", help="Generate a public proof for an independently supplied policy")
    for name in ("policy", "trust", "presentation"):
        prove.add_argument(name)
    prove.add_argument("holder_records", nargs="+")
    verify = commands.add_parser("verify", help="Check a proof against an independently supplied policy and trust file")
    for name in ("policy", "trust", "presentation"):
        verify.add_argument(name)
    review = commands.add_parser("review", help="Intersect public range bounds for one recipient's prior disclosures")
    review.add_argument("policy")
    review.add_argument("trust")
    review.add_argument("history", nargs="+")
    args = parser.parse_args()
    try:
        if args.command == "keygen":
            engine.identifier(args.issuer)
            if Path(args.trust).exists() or Path(args.private_key).exists():
                raise ValueError("Choose new output paths")
            key = Ed25519PrivateKey.generate()
            write(args.private_key, key.private_bytes_raw().hex())
            output(args.trust, {args.issuer: key.public_key().public_bytes_raw().hex()})
        elif args.command == "issue":
            key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(Path(args.private_key).read_text().strip()))
            record = engine.issue(args.issuer, load(args.attributes), args.expires, key,
                                  source_sha256=args.source_sha256)
            output(args.holder_record, record)
            print(json.dumps(record["credential"]["manifest"], indent=2))
        elif args.command == "prove":
            records = {}
            for path in args.holder_records:
                record = load(path)
                credential = record["credential"]["manifest"]["id"]
                if credential in records:
                    raise ValueError("Duplicate holder credential")
                records[credential] = record
            output(args.presentation, engine.prove(records, load(args.policy), load(args.trust)))
        elif args.command == "review":
            result = engine.interval_review(load(args.policy), (load(path) for path in args.history), load(args.trust))
            print(json.dumps(result, indent=2))
        else:
            valid = engine.verify(load(args.presentation), load(args.policy), load(args.trust))
            print(json.dumps({"valid": valid}))
            return 0 if valid else 1
    except (OSError, InvalidSignature, ValueError, KeyError, TypeError, RecursionError) as exc:
        parser.exit(2, f"{exc or 'Invalid issuer signature'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
