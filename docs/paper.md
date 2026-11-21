# Evaluating transcript binding for privacy-preserving vendor contract disclosure

This draft reports the earlier structured-contract experiment. The [PDF Studio evaluation](README_PUBLIC_PDF_TESTING.md) covers the current adaptive-document workflow.

**Working paper — LegitZK Research Prototype**

## Abstract

Vendor contract auditing can require evidence about a concealed monetary amount while preserving the authenticity of publicly disclosed terms. This study implements Authenticated Policy-Bound Disclosure (APBD) over a fixed vendor-contract schema. The verifier checks an issuer-signed source fingerprint and claim inventory, exact openings for a verifier-selected field set, a canonical disclosure PDF, and a private range argument scoped to the audit request. The evaluation compares a complete presentation transcript with a predicate-only control. Across 30 synthetic trials, the complete verifier rejected all changes of recipient and challenge, whereas the predicate-only control accepted all of its corresponding transplanted proofs because its statement omitted the recipient and challenge. Median package generation and verification took 28.212 ms and 33.803 ms on the reported environment. These results characterize one binding failure and the costs of a reference implementation.

## Contribution and related work

Selective disclosure, signed commitments, private predicates and authenticated redaction have substantial prior art. Starling Lab studies pixel-preserving redaction, zk-creds studies authenticated private statements, and SD-JWT defines freshness and audience binding for its key-binding mode. The proposed contribution is a reproducible systems demonstration of the failure mode created by omitting the presentation transcript, with an evidence format for a narrow contract workflow. See the [literature review](../README_LITERATURE_REVIEW.md).

## Protocol

An issuer commits to five typed text fields and an unsigned 32-bit amount. The amount commitment permits a range argument formulated over two differences using Ristretto255 Pedersen commitments. An auditor issues a policy and random challenge pinned to a document and recipient. The verifier checks disclosure coverage publicly and regenerates the export from just those fields. The proof transcript includes the signed manifest, signature, expected request, claim openings and PDF digest. The [protocol specification](protocol.md) defines serialization, proof equations, assumptions, properties and leakage.

## Method

Run `PYTHONPATH=. python benchmarks/run.py --samples 30` from the root. The script uses the included contract fixture, threshold 7,000,000 USD cents, randomized commitments and fixed schema. It alternates the optional service requirement, discards one warm-up, asserts verification, and writes [per-trial data](../benchmarks/raw.json) and [summary](../benchmarks/summary.json). Timing uses a monotonic clock in a single Python process. The measurements cover in-process protocol latency. They exclude network, database, browser, queue and signing infrastructure. Peak RSS is for the complete process and all controls.

Controls include signed source hash, signed salted text openings, and a signed-commitment predicate with a transcript containing only the amount commitment and threshold. They reuse the same cryptographic library and inputs. The first two have a smaller assurance scope. The last control isolates recipient/challenge binding. For each trial, keep document, visibility and threshold fixed, replace the expected request with a new recipient and nonce, and test the original proof unchanged against each verifier.

## Results

30 measured trials on Linux x86-64, Python 3.12.14, AMD EPYC 7763.

| Variant | Median create (ms) | Median verify (ms) | Scope |
|---|---:|---:|---|
| Signed source fingerprint | 0.087 | 0.132 | Hash signature check |
| Signed salted openings | 0.002 | 0.181 | Included claims only |
| Predicate-only control | 27.064 | 32.561 | Signed amount threshold |
| Complete LegitZK evidence | 28.212 | 33.803 | Openings, PDF, policy and bound predicate |

For the signed source control, creation/verification times exclude source hashing. For selective disclosure, creation times use pre-existing commitments. Complete proof generation includes evidence and PDF assembly, and verification includes canonical PDF regeneration. Compared with the predicate-only control, the measured median verification time is about 1.24 ms higher on this run. Benchmark noise and sequential execution limit attribution of small differences.

| Other complete-presentation measurements | Median |
|---|---:|
| Commitment construction | 0.224 ms |
| Issuance including source PDF | 1.878 ms |
| Standalone disclosure render | 1.693 ms |
| Issuance, package generation and verification combined | 64.872 ms |
| JSON-encoded proof | 20,677 bytes |
| Complete JSON package | 25,336 bytes |

Peak process RSS was 25,848 KiB. The complete verifier rejected 30 of 30 transplants. The predicate-only control accepted 30 of 30 under its unchanged narrower predicate. This is a deliberately selected synthetic control, so the counts characterize a reproducible regression test, not a population attack rate.

## Limitations and follow-up

The study uses one schema, one CPU environment, deterministic layout, synthetic values and two disclosure settings. It does not estimate throughput, scale across schema widths, evaluate browser usability, compare across arbitrary-PDF processors, or validate privacy against a malicious issuer or host. The public manifest makes repeated contracts linkable. A separate review is needed for cryptographic proof soundness, side channels and PDF rendering portability. A scalable follow-up should compare a signed Merkle inventory and a reviewed succinct range system, expand the input corpus, and measure CPU and memory by stage under load. Bibliography and source classifications appear in the [literature review](../README_LITERATURE_REVIEW.md).
