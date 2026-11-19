"""Measure real numeric credential proof workloads. Run from the Studio directory."""
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import credential_proof as engine
from protocol import canonical


def run(size, trials):
    key = Ed25519PrivateKey.generate()
    trust = {"benchmark": key.public_key().public_bytes_raw().hex()}
    now = 100000
    record = engine.issue("benchmark", {
        f"measure-{i}": {"value": 42 + i, "unit": "count"} for i in range(size)
    }, now + 100, key, now=now)
    cid = record["credential"]["manifest"]["id"]
    policy = {"schema": engine.POLICY, "audience": "benchmark", "nonce": "12" * 32, "expires": now + 100,
              "clauses": [{"credential_id": cid, "issuer": "benchmark", "attribute": f"measure-{i}",
                           "unit": "count", "min": 40, "max": 120} for i in range(size)]}
    prove_ms, verify_ms = [], []
    for _ in range(trials):
        start = perf_counter()
        presentation = engine.prove({cid: record}, policy, trust, now)
        built = perf_counter()
        if not engine.verify(presentation, policy, trust, now):
            raise RuntimeError("Benchmark generated an invalid proof")
        checked = perf_counter()
        prove_ms.append((built - start) * 1000)
        verify_ms.append((checked - built) * 1000)
    return {"clauses": size, "presentation_bytes": len(canonical(presentation)),
            "prove_median_ms": median(prove_ms), "verify_median_ms": median(verify_ms),
            "prove_samples_ms": prove_ms, "verify_samples_ms": verify_ms}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clauses", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--trials", type=int, default=10)
    args = parser.parse_args()
    if args.trials < 1 or any(not 1 <= size <= engine.MAX_CLAUSES for size in args.clauses):
        parser.error("Provide positive trials and a supported clause count.")
    print(json.dumps({"platform": platform.platform(), "python": platform.python_version(),
                      "cryptography": version("cryptography"), "trials": args.trials,
                      "results": [run(size, args.trials) for size in args.clauses]}, indent=2))
