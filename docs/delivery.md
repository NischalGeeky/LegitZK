# Implementation and verification report

**18 November 2026**

The delivered source implements a one-schema vendor-contract application. The issuer, owner and auditor workflows persist in SQLite and use real Ed25519 signatures, salted openings and a Ristretto255 private amount range proof. Users can generate a public-fields disclosure PDF, share it, and check it independently through the CLI or web verifier. Audit requests are one-hour, recipient-specific, revocable, and consumed after a successful online verification. A consumed request remains downloadable until expiry or revocation so the auditor can retain the evidence. Offline checks follow the request expiry and have no single-use state.

| Check | Observed result |
|---|---|
| Local ASGI application launch | Started successfully and served the application shell. |
| `python -m unittest discover -s tests -v` | 12 tests passed. The API test traversed all roles and covered source matching, access checks, sharing, replay rejection and revocation. Protocol tests also covered boundaries, tampering, false predicates, PDF attachment/annotation changes and witness exclusion. |
| `python -m pip check` | The installed environment reported no broken requirements. |
| `node --check web/app.js` and Python byte compilation | Passed. |
| `PYTHONPATH=. python fixtures/make_demo.py` and `python verify.py …` | Synthetic package generated and verified in a separate process. |
| `PYTHONPATH=. python benchmarks/run.py --samples 30` | 30 measured trials and one warm-up completed. Both timing data and transplant controls are included. |
| `PYTHONPATH=. python tests/browser.py` | Uvicorn started. Chromium exited during startup because the execution environment denies Unix-domain socket creation. Browser steps did not execute. |
| Docker Compose and CI | Definitions included. Docker was unavailable, and there was no connected CI runner or deployment target. |

## Scope limits

The web implementation is a single service with a browser-native frontend. It provides schema-based PDF disclosure and signed-source matching. Free-form masks, arbitrary-PDF editing, independent pixel proofs, multiple predicate types, editable version history and cross-schema benchmarks are outstanding. The range proof is a setup-free alternative to the originally proposed circuits. Production prerequisites such as independently reviewed cryptography, externally managed secrets, account recovery, OIDC/MFA, retention policies and an operational audit remain outstanding. The public-facing interface has light and dark themes, responsive layout and labeled controls. Browser and accessibility conformance remain unverified.

The implementation contains no production signing key or real contract. Use the sample fixture and fresh generated local accounts. For setup and the demo, see [README](../README.md).
