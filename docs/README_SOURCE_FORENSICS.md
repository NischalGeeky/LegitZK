# Source investigation and Proof Studio

## Launch on Windows

Extract to a fresh folder. Place the official x64 `libsodium.dll` next to `rangeproof.py`. With Python 3.12 installed, run `start-windows.cmd` from the extracted folder. It creates the local virtual environment and installs dependencies if necessary. Open http://127.0.0.1:8001.

## Investigate a candidate PDF

1. Upload the baseline PDF in **Redact** and download its signed source receipt.
2. In **Integrity lab**, upload the baseline, the candidate PDF and the independently retained baseline receipt.
3. Choose whether to include field values. The comparison authenticates the baseline and reports whether the candidate has the same bytes, shows changed areas on the first changed page, and lists structural indicators and native-field differences.
4. Download a JSON report. This report is an unsigned record of the investigation. Keep the input hashes and original inputs for reproducibility.

A signed source receipt links the baseline version identifier and source hash to a trusted Studio key. It does not establish the candidate editor's identity. A changed candidate has unknown attribution. The tool does not infer an actor from document metadata. Structural observations cover object counts, embedded files, annotations, signature flags and the names of changed metadata keys. PDF signature coverage and revision chain parsing are outside this release. Native field comparison pairs unique colon-delimited labels within a page. The comparison can miss unlabeled or scanned values, same-label duplicates, or layout changes. Visual comparison uses the existing raster profile and excludes annotations.

The older disclosure-integrity tools still provide the marked visible and metadata-only test cases and verification with a proof ZIP. They run on your exported test copies.

## Proof Studio

Issue a numeric holder record using the local CLI in [Private numeric claims](README_NUMERIC_CLAIMS.md). In **Proof Studio** supply one or more holder records, the verifier's expected policy and trusted issuer keys. Download the public presentation and verify it under **Verify private numeric claims** with the expected policy and trusted keys. Holder records go to the local Studio process. The exported presentation omits private openings.

## Status and research

The implementation adds authenticated baseline investigation, field and visual localization, structural observations, proof generation through the website, and a Windows launcher. It reuses the existing signed disclosure, OCR and private numeric claim implementations. The complete revised brief still requires authenticated editor identities and signed version chains, hosted access, contextual AI, broader semantic and revision analysis, and full adversarial coverage and evaluation.

A cryptographic hash comparison provides the integrity baseline. Unique-label field comparison tests whether a native text change can be assigned to a field. Visual localization identifies changed raster regions. These measure different aspects of forensic detection. The synthetic API tests exercise a matching baseline, a changed field, invalid signatures and privacy-conscious reporting. They do not establish real-world accuracy or novelty. See the [PDF Association's forensic analysis guidance](https://pdfa.org/challenges-in-the-forensic-analysis-of-pdf-files/) for context about revision and signature coverage analysis.

Reproduce the three fixture measurements with `python benchmarks/source_forensics.py`. The [raw data](../benchmarks/source-forensics-results.json) records ten runs for each fixture.

### Synthetic field-change test

In **Integrity lab**, run **Run synthetic field-change test** to compare two generated native-text records. The signed baseline contains `Review score: 78` and the modified test copy contains `Review score: 96`. The field difference comes from extracting text from both PDFs. The downloadable test ZIP has both files and the signed baseline receipt. The overlay test separately demonstrates a change in rendered appearance.

### Demonstrate a hash mismatch with your own PDF

In **Integrity lab → Change a value in a test copy**, upload a supported PDF that you own. Use **Replace extractable text** for native PDF text and enter a value that appears once on the selected page. Use **Replace visible pixels** for a redacted raster export. Preview its page and drag around the visible value. Enter a short ASCII replacement and download the edited test copy. The panel reports the SHA-256 fingerprints of the unchanged input and the edited output.

For an original source, compare the test copy against the original PDF and its saved source receipt in **Investigate a source revision**. For a redacted export, upload the edited copy in **Verify** with the original proof ZIP. The signed reference hash remains the one recorded before the edit. A mismatch identifies changed bytes. The visual comparison identifies affected page regions, and the native field comparison is limited to comparable extracted text. Redacted pixels cannot be recovered from a LegitZK export.
