# LegitZK project plan and implementation status

**Updated 18 November 2026.** Research prototype for Authenticated Policy-Bound Disclosure (APBD), using synthetic vendor contracts with one fixed schema.

## Goal and implemented workflow

A trusted issuer generates a signed manifest over a source PDF fingerprint and structured claims. An auditor creates a versioned policy and audience-specific challenge. The owner previews a new PDF generated from the allowed fields and produces zero-knowledge evidence that the signed private amount meets the public threshold. The auditor independently verifies the manifest, disclosed values, PDF regeneration and proof against the retained audit request.

| Area | Current implementation |
|---|---|
| Issuance and source | Ed25519 signatures, immutable document IDs, signed SHA-256 source digest, original preview and exact PDF file matching. |
| Document schema | Vendor, buyer, date, service, bank reference and bounded amount in USD cents. |
| Policy | Versioned issuer/schema/document checks, exact visible-field set, optional required service, mandatory vendor/buyer/date, threshold and challenge expiry. |
| ZK | Noninteractive Ristretto255 range argument over the same issuer-signed amount commitment. Public transcript binds the rest of the evidence. |
| Document privacy | Fresh template render from permitted claims with a byte-for-byte verifier check. |
| Product | Landing page, roles and sessions, account dashboard, issuance, source review, redaction preview, sharing and revocation, audit events, verification portal and benchmark panel. |
| Verification | Independent Python CLI and web upload portal, plus server-side single-use state for the designated auditor. |
| Development | FastAPI, SQLite and browser-native frontend. Docker/Compose and CI definitions are included. |

## Design changes from the original proposal

A fixed signed hash inventory replaces a generic Merkle tree because the first schema contains five text fields. A discrete-log range argument replaces the proposed Circom/snarkjs circuit. It uses vetted group arithmetic, requires no trusted setup and proves one bounded predicate. This makes the prototype directly runnable with the installed Python and libsodium runtime. General circuits and larger authenticated structures remain research directions. The app substitutes single-service SQLite and plain browser modules for PostgreSQL, queues, separate workers and Next.js. Contract exports are fresh PDFs generated from claims, with source association vouched for by the issuer. Pixel comparison and arbitrary source-document editing are outside the implemented guarantee.

## Acceptance evidence

- Issuer signatures, exact schema and disclosed values, threshold proofs, expiry and transplant cases exercised by the automated protocol and API suites.
- Local application started successfully. API integration exercised registration, signing, source matching, proof generation, sharing, verification, replay rejection and revocation.
- PDF extraction and object inspection exercised the generated disclosure fixtures, including rejection when attachment and annotation objects were added.
- Thirty measured benchmark trials produced raw timing and package-size data and a recipient-transplant control.
- Chromium workflow and Docker launch remain unverified in this execution environment. See the [delivery report](docs/delivery.md).

## Next research and engineering milestones

1. Independently review the protocol design, proof implementation and PDF renderer. Add formal proof review and interoperable wire-format vectors before real applications.
2. Verify Docker installation and cross-browser operation. Add accessibility auditing, PDF rendering differences, load tests and backup/restore checks.
3. Expand policy typing and schemas, compare against a Merkle-opening baseline at scale, and benchmark a reviewed succinct range-proof or general circuit backend.
4. Evaluate independent visual redaction proofs for source PDF workflows and build a dedicated sanitizer only if the product scope expands to arbitrary input.
5. Add OIDC/MFA, tenant administration, managed keys, revocation, recovery, file lifecycle controls and isolated proving workers for any future deployment handling real data.

See [Literature review](README_LITERATURE_REVIEW.md), [Protocol](docs/protocol.md), [Operations](docs/operations.md), and [Paper draft](docs/paper.md).
