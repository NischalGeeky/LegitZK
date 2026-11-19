"""Usage: python verify.py package.json auditor-request.json trusted-issuers.json"""
import argparse
import json
from pathlib import Path

from protocol import parse_json, verify

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["package", "request", "trust"]:
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    try:
        result = verify(*(parse_json(path.read_bytes()) for path in (args.package, args.request, args.trust)))
    except (ValueError, OSError, RecursionError):
        result = {"valid": False, "checks": [{"check": "Input files", "passed": False}]}
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["valid"] else 1)
