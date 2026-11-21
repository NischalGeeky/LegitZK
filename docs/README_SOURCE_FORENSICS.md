# Investigate a PDF revision

## Compare a candidate with a signed baseline

1. In **Redact**, upload the baseline PDF and select **Save source receipt**. Retain the original PDF and receipt independently of the candidate.
2. In **Integrity lab → Investigate a source revision**, select the baseline, candidate and receipt. If the candidate is a redacted export, supply the proof ZIP from that export to account for authorized redactions.
3. Choose **Compare source PDFs**. Review the signature and provenance, native field differences, visual findings and structural observations. **Include field values in results and report** is optional and can expose values in the displayed and exported results.
4. Download the unsigned investigation report if needed. Retain input digests and original files for reproduction.

A byte mismatch establishes that a candidate differs from the retained baseline. An authenticated reference and a raster comparison help localize the change. Native-field matching relies on unique colon-delimited labels on corresponding pages. It can miss duplicates and scanned fields. Structural findings include counts and metadata indicators. They do not identify the editor or validate a PDF signature's full coverage.

## Generate a synthetic test copy

Choose **Run synthetic field-change test** for an example with generated source PDFs and a signed baseline receipt. You can download the test files after the run.

To edit your own test input, choose **Edit a PDF test copy**. Use **Replace extractable text** for unique native text on the selected page, or **Replace visible pixels** for a raster export. Preview the page and select a box in raster mode. Apply each edit to the working copy and download it when finished. The displayed hashes refer to the original input and the current edited copy.

Use **Verify** with the original proof ZIP to inspect an edited disclosure. Use the baseline investigation form for a candidate source revision. See the [integrity research notes](README_INTEGRITY_RESEARCH.md) for experimental controls.

## Reproduce source comparison measurements

Run `python -m benchmarks.source_forensics` from the project root. The [saved measurements](../benchmarks/source-forensics-results.json) contain per-fixture timing samples. These synthetic results do not establish real-world forensic accuracy.
