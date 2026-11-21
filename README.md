# LegitZK

LegitZK PDF Disclosure Studio is a local research prototype for redacting PDFs and verifying what was disclosed. It exports an image-only redacted PDF and a signed evidence ZIP. A separate private-claim workflow proves comparisons about values the document owner registers without putting the exact values in the evidence.

**Start here** [Installation and first run](README_PDF_STUDIO.md) · [Walkthrough](docs/README_WORKFLOW.md)

| Tab | Purpose |
|---|---|
| **Redact** | Review local field suggestions or draw regions, preview the adaptive mask, and generate a PDF and proof ZIP. |
| **Verify** | Check the matching PDF and ZIP, optionally compare an independently retained source receipt, and inspect differences. |
| **Integrity lab** | Edit a test copy or compare a candidate against a signed baseline. |
| **Zero Knowledge Proof** | Request a comparison against an owner-attested field. Use the current export for local proof generation and verification, or exchange files with the owner. |

The document proof checks the export against the signed ingestion raster and the bundled redaction policy. The field proof checks a condition on the committed value entered by the owner. The owner is responsible for matching that value to the source. Both workflows depend on the verifier's configured signing key. See [what the proofs establish](docs/README_ZERO_KNOWLEDGE.md).

## Documentation

- [Features and limits](docs/README_FEATURES.md)
- [Architecture and trust boundaries](docs/README_ARCHITECTURE.md)
- [Source investigation and test-copy editing](docs/README_SOURCE_FORENSICS.md)
- [Experiments and public PDF test plan](docs/README_PUBLIC_PDF_TESTING.md)
- [Project status](README_PROJECT_PLAN.md) and [literature review](README_LITERATURE_REVIEW.md)

## Tests

With the Studio virtual environment and libsodium set up:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m benchmarks.adaptive_studio
```

The [delivery report](docs/delivery.md) identifies the checks run on this archive and distinguishes them from saved benchmark results.

## Earlier prototypes

The separate `app.py` service on port 8000 demonstrates role-based disclosure for structured vendor contracts. The supplied Dockerfile and browser CI workflow target that service. The [numeric credential CLI](docs/README_NUMERIC_CLAIMS.md) implements a separate issuer-backed model. The main PDF Studio runs via `pdf_studio:app` on port 8001.
