"""Run within one process. Measures hot-path latency, size and process peak RSS."""
import argparse
from pathlib import Path
import platform
import resource
import statistics
from time import perf_counter

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import protocol as p
import rangeproof as zk

ROOT = Path(__file__).resolve().parent


def timed(fn):
    start = perf_counter()
    result = fn()
    return result, (perf_counter() - start) * 1000


def run(samples):
    rows = []
    values = p.parse_json((ROOT.parent / "fixtures" / "contract.json").read_bytes())
    issuer = "Benchmark issuer"
    key = Ed25519PrivateKey.generate()
    pub = key.public_key()
    trust = {issuer: pub.public_bytes_raw().hex()}
    for index in range(samples + 1):
        (record, source), issuance = timed(lambda: p.issue(values, issuer, key))
        m = record["manifest"]
        threshold = 7000000
        request = p.request_for(m["id"], issuer, threshold, "benchmark-auditor", bool(index % 2))
        (bundle, creation) = timed(lambda: p.present(record, request))
        (result, validation) = timed(lambda: p.verify(bundle, request, trust))
        assert result["valid"]
        _, render = timed(lambda: p.render({k: values[k] for k in request["policy"]["visible"]}, m["id"]))
        _, commitments = timed(lambda: (
            [p.leaf(k, values[k], record["salts"][k]) for k in p.FIELDS], zk.commit(values["amount"], int(record["blind"]))))
        signed_pdf = {"source_sha256": p.sha256(source).hexdigest()}
        signature, sig_prove = timed(lambda: key.sign(p.canonical(signed_pdf)))
        _, sig_verify = timed(lambda: pub.verify(signature, p.canonical(signed_pdf)))
        openings, selective_prove = timed(lambda: {
            field: {"value": values[field], "salt": record["salts"][field]} for field in request["policy"]["visible"]})
        def check_openings():
            pub.verify(bytes.fromhex(record["signature"]), p.signed(m))
            assert all(p.leaf(k, v["value"], v["salt"]) == m["inventory"][k] for k, v in openings.items())
        _, selective_verify = timed(check_openings)
        # The root-and-threshold control intentionally omits the presentation transcript.
        bare_context = bytes.fromhex(p.digest("Baseline/amount", [m["amount_commitment"], threshold]))
        proof, bare_prove = timed(lambda: zk.prove(values["amount"], int(record["blind"]), threshold, bare_context))
        def check_bare():
            pub.verify(bytes.fromhex(record["signature"]), p.signed(m))
            return zk.verify(proof, bytes.fromhex(m["amount_commitment"]), threshold, bare_context)
        outcome, bare_verify = timed(check_bare)
        assert outcome
        swapped_request = p.request_for(m["id"], issuer, threshold, "alternate-auditor", bool(index % 2))
        swapped_bundle = {**bundle, "request": swapped_request}
        rejected_swap = not p.verify(swapped_bundle, swapped_request, trust)["valid"]
        # A verifier that ignores the full request gets the same bare context for either audience.
        swapped_bare = bytes.fromhex(p.digest(
            "Baseline/amount", [m["amount_commitment"], swapped_request["policy"]["threshold"]]))
        accepted_bare_swap = zk.verify(proof, bytes.fromhex(m["amount_commitment"]), threshold, swapped_bare)
        assert rejected_swap and accepted_bare_swap
        if index:
            rows.append({"service_required": bool(index % 2), "issuance_ms": issuance, "commitments_ms": commitments,
                         "render_ms": render, "prove_ms": creation, "verify_ms": validation,
                         "workflow_ms": issuance + creation + validation,
                         "proof_bytes": len(p.canonical(bundle["proof"])), "package_bytes": len(p.canonical(bundle)),
                         "source_bytes": len(source), "signed_pdf_create_ms": sig_prove, "signed_pdf_verify_ms": sig_verify,
                         "selective_create_ms": selective_prove, "selective_verify_ms": selective_verify,
                         "bare_prove_ms": bare_prove, "bare_verify_ms": bare_verify,
                         "apbd_swap_rejected": rejected_swap, "bare_swap_accepted": accepted_bare_swap})
    summary = {metric: round(statistics.median(row[metric] for row in rows), 3)
               for metric in rows[0] if type(rows[0][metric]) in (float, int)}
    summary.update({key: sum(row[key] for row in rows)
                    for key in ("apbd_swap_rejected", "bare_swap_accepted")})
    cpuinfo = Path("/proc/cpuinfo")
    cpu = next((line.split(":", 1)[1].strip() for line in cpuinfo.read_text().splitlines()
                if line.startswith("model name")), platform.processor()) if cpuinfo.exists() else platform.processor()
    summary["cpu"] = cpu
    summary.update({"samples": samples, "environment": f"{platform.system()} {platform.machine()} / Python {platform.python_version()}",
                    "ru_maxrss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    "ru_maxrss_unit": "bytes" if platform.system() == "Darwin" else "KiB"})
    for name, data in (("raw.json", rows), ("summary.json", summary)):
        (ROOT / name).write_bytes(p.canonical(data) + b"\n")
    print(summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=30)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    run(args.samples)
