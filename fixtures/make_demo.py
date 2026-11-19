"""Create a fresh source, disclosure, auditor request and trust bundle for the CLI demo."""
from pathlib import Path
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from protocol import canonical, issue, parse_json, present, request_for

out = Path(sys.argv[1] if len(sys.argv) == 2 else "demo-output")
out.mkdir(exist_ok=True)
key = Ed25519PrivateKey.generate()
issuer = "LegitZK Demo Fixture"
record, source = issue(parse_json(Path(__file__).with_name("contract.json").read_bytes()), issuer, key)
request = request_for(record["manifest"]["id"], issuer, 7000000, "demo-auditor", False)
result = present(record, request)
for name, data in (("disclosure.json", result), ("auditor-request.json", request),
                   ("trusted-issuers.json", {issuer: key.public_key().public_bytes_raw().hex()})):
    (out / name).write_bytes(canonical(data) + b"\n")
(out / "source.pdf").write_bytes(source)
print(f"Generated four synthetic demo files in {out}. The request expires in one hour.")
