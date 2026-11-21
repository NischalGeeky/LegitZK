# Cumulative disclosure review

## Using the exposure panel

Upload a supported PDF, select hide regions, and review the redaction plan. Enable **Record this export locally** before generating the first proof and PDF. Select different regions on the same source while retaining the same recipient label and review the new plan. The cumulative exposure panel reports how many pixels hidden in the proposal were visible in recorded exports. You can change the mask and check again before exporting.

The analysis is exact for the actual raster masks. If Hᵢ is the hidden pixel set for export i, the hidden set after combining releases is the intersection of all Hᵢ. The previously exposed portion of a proposed mask H is H minus that intersection. This is a geometric calculation, independent of the cryptographic proof and the detector's field classification.

## Scope and threat model

The history is scoped to the exact source file hash, raster profile, dimensions and literal recipient label. It models a recipient who can combine every recorded export in that scope. The label is user supplied and carries no authority. Export recording is opt-in and records generation, so an export may be recorded even if the user never sent it. Releases outside this Studio, colluding recipients, re-encoded sources and semantic or statistical inference are outside the calculation.

SQLite creates the additive `exposure_v1` table on startup. The history stores encrypted packed masks and record counts. Recipient labels, unmasked text and private witnesses are absent from the database. A keyed digest indexes each scope. AES-GCM protects the mask and authenticates its scope and count. The owner of the local Studio and the ingestion key can access the stored history. Filesystem rollback or deletion can remove history and the record count is visible. The local service remains a single-user loopback application.

## Validation and prior work

Run from the Studio directory.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m benchmarks.exposure --trials 25 --sizes 256 1024 2048
```

The benchmark measures local preview analysis for a deterministic two-mask case. It checks the exact intersection against a known geometric result and reports every timing sample plus runtime and package versions. See [raw results](../benchmarks/exposure-results.json). It does not measure PDF parsing, proof generation, OCR or concurrent serving.

SD-JWT is a standards-track selective-disclosure mechanism and provides a comparison point for authenticated disclosed claims. The present work evaluates exact cumulative exposure for aligned PDF raster releases. This experiment does not establish scientific novelty. [RFC 9901](https://www.rfc-editor.org/rfc/rfc9901.html)

## Current capability boundary

Existing Studio functionality includes local extraction and field suggestions, proof-backed redacted PDFs, signed bundle validation, expected-source matching and visual forensics. Existing threshold proofs in the separate contract workflow establish a narrowly defined numeric predicate. Cumulative raster assessment and benchmark tooling are available. [Private numeric claims](README_NUMERIC_CLAIMS.md) adds issuer-backed numeric credentials, conjunctive range proofs across issuers, and cumulative numeric interval review. The Studio supports optional interpretation of single-field questions and a limited age/date inference check. General hidden predicates, cross-credential relations, interoperability and revocation, general semantic leakage simulation, unrestricted natural-language policy building, collaborative approvals, tenant isolation, a hosted vault, an interactive exposure graph and the full developer platform remain unimplemented.

PDF verification can export a versioned JSON inspection report with input digests, the signed file checks, source-match result when supplied, and visual comparison summary when available. The report omits page preview images and is an unsigned record of the inspection. Re-run verification with the original inputs to reproduce its findings.
