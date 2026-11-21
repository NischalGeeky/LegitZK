# LegitZK project scope and implementation status

The primary project is a local PDF redaction and verification studio. The practical goal is to let an owner share a masked PDF with evidence that the visible pixels and redaction policy agree with a trusted ingestion receipt.

| Area | Shipped behavior |
|---|---|
| Ingestion | A local Studio key signs a source fingerprint, raster profile and tile-commitment root for a supported PDF. |
| Redaction | A reviewer approves hide and keep regions using page previews and optional detection. The planner coalesces uniform tiles at a fixed fine-grid coverage. |
| Release | A fresh image-only PDF and signed proof ZIP carry the disclosed raster and its verification evidence. |
| Verification and forensics | The verifier checks the exact PDF and ZIP, optionally checks an expected source, and reports byte or visible differences. |
| Private financial example | A local owner can register a settlement amount and prove an exact comparison or range over that commitment. The UI also offers whole numbers, dates and code/text. |
| Privacy review | Optional OCR and export history provide heuristic leakage checks and geometric exposure checks. |

## Acceptance and research

The central experiments compare adaptive, fixed-8 and fixed-32 cuts on identical synthetic layouts. Separate fixtures cover proof binding, evidence file attribution, source revisions, and exposure across releases. The [evaluation guide](docs/README_PUBLIC_PDF_TESTING.md) links the recorded data and explains how to reproduce the measurements.

The earlier role-based contract app and issuer-backed numeric CLI are retained as separate experiments. Their designs and results are documented in the [contract protocol](docs/protocol.md), [paper draft](docs/paper.md), and [numeric claims guide](docs/README_NUMERIC_CLAIMS.md).

## Open research questions

- How well does the adaptive layout perform on independent document families and rendering environments?
- How reliable are detection and optional question interpretation on human-written, independently annotated examples?
- What issuer or extraction process could give a third party stronger assurance that a registered value matches the source?
- How should disclosure history account for collusion, transformed sources and information inferred from repeated claims?

The implementation is research code. Independent cryptographic and PDF handling review, browser and accessibility evaluation, and a defined deployment threat model would be needed for broader use.
