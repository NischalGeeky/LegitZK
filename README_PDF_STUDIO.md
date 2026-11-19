# LegitZK PDF Disclosure Studio

Upload an ordinary PDF, review locally detected fields, and export a redacted PDF with verifiable evidence. Approved regions determine what to hide and what must stay visible. The Studio applies its 8-pixel proof grid and previews the resulting coverage.

## Windows quick start

1. Extract this release to a new folder. Open PowerShell where `pdf_studio.py` is located.
2. Put the same 64-bit official `libsodium.dll` used in your previous LegitZK install next to `rangeproof.py`. The app loads it automatically. If you need it again, use an official x64 MSVC release. [libsodium releases](https://download.libsodium.org/libsodium/releases/)
3. Set up Python 3.12 once, then start the server.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn pdf_studio:app --host 127.0.0.1 --port 8001 --no-access-log
```

Open [http://127.0.0.1:8001](http://127.0.0.1:8001). Keep PowerShell open while using the app. Subsequent sessions only need the Uvicorn command. Text-based detection runs offline on CPU, with no API key or issuer login. OCR is optional and requires `tesseract` on PATH with English language data. Check it with `tesseract --version`. If OCR is unavailable, text extraction and manual regions work normally.

On Linux, install the local libsodium shared library and use your virtual environment's Python to run the same Uvicorn module.

## Three-minute demo

1. Upload `fixtures/demo-vendor.pdf`.
2. Add `Settlement Amount =>` to the custom search box and choose **Detect fields**. Click **Hide** on the settlement and account-number suggestions. Use **Mark to keep visible** to draw around the reviewer-visible status on the page. Review both pages.
3. Enter a recipient and choose **Review redaction plan**. Check the shaded boundary and any conflict with keep-visible regions.
4. Choose **Generate proof and PDF**, then download **redacted.pdf** and **legitzk-proof.zip**. In **Verify**, upload those two files.
5. With the verified pair still selected, open **Integrity lab** and run the metadata-only and visible-edit tests. To inspect a suspected edit, submit that PDF alongside the original proof ZIP in **Verify**.

The Studio trusts its own key by default. On a separate reviewer installation, obtain the issuer Studio's public key independently from its `/api/key` endpoint or an authenticated channel. Set `LEGITZK_PDF_TRUSTED_KEY` to that hex key before starting the verifier. Verification uses the existing one-hour request validity window. The signed inventory authenticates each included JSON file and the PDF. The key inside the archive is an evidence file.

## Compare your own disclosures

The Integrity lab works with any supported Studio export selected in Verify. To check a suspected edit, upload your candidate redacted PDF with the original proof ZIP. To detect substitution of both files, keep an independently retained signed source receipt. Use **Save source receipt** after the original upload, then select it under **Check against an expected source** in Verify. The receipt is specific to that ingestion. Keep the original source PDF separately if you want to show its unredacted content.

## Documentation

| Guide | Contents |
|---|---|
| [Features](docs/README_FEATURES.md) | Capabilities, document limits and trust boundaries |
| [Architecture](docs/README_ARCHITECTURE.md) | Components, APIs, data flow and compatibility |
| [Working and presentation](docs/README_WORKFLOW.md) | Demo clicks, expected results and viva explanation |
| [Zero knowledge](docs/README_ZERO_KNOWLEDGE.md) | Signed commitments, Merkle authentication and Schnorr equations |
| [AI and adaptive planner](docs/README_ADAPTIVE_AI.md) | Offline detection and the research contribution |
| [Integrity research](docs/README_INTEGRITY_RESEARCH.md) | Safe fixtures, benchmark protocol and feature extensions |
| [Testing](docs/README_PUBLIC_PDF_TESTING.md) | Public PDF sources, tests and benchmark commands |

Use the bundled synthetic PDFs for your first demo. The system trusts local ingestion to link the source PDF to the committed raster, and it does not authenticate the document's real-world issuer. The proof verifies approved redactions, while reviewer inspection is necessary to catch sensitive content the detector missed.

For cumulative disclosure review and its benchmark, see [Next-generation implementation status](docs/README_NEXT_GENERATION.md).

See [Private numeric claims](docs/README_NUMERIC_CLAIMS.md) for credential issuance, proof generation, verification and range exposure review.

For the Windows launcher, source investigations and browser-based proof generation, see [Source investigations and Proof Studio](docs/README_SOURCE_FORENSICS.md).

## Clinical identifier suggestions

The Redact tab scans accessible PDF text on upload. The detector uses explicit name, birth-date, identification number, and medical-record labels as anchors. It looks for matching values across the document and suggests regions for repeated occurrences in headers and narrative. Use **Hide all labeled identifiers** to accept the visible set in bulk, or review each suggestion individually. The bulk action preserves marked keep-visible regions. Preview the mask before export.

For scanned pages, enable OCR and run **Detect fields** again with Tesseract installed. Review variation in spelling or date formats, line-wrapped names, and identifiers without labels manually. A successful proof verifies the approved mask against the source; it does not certify complete clinical de-identification.

## Financial document review

Enable **Include financial identifiers** and run **Detect fields**. Labeled account, routing, IBAN, card, tax and government IDs, references, and selected contact fields are suggested. The scan also finds repeated copies of explicitly labeled values in the same format. A short CVV/CVC is suggested only at the explicit field. Review the suggestions and use **Hide all labeled identifiers** if the set matches your disclosure purpose.

Use manual regions for signatures, photos, barcodes, labels the detector misses, or selectively retaining the last four digits. Context-dependent fields such as commercial terms should be reviewed against the disclosure request. The export is a fresh raster PDF. Structural checks reject an unexpected text layer, embedded files, annotations, forms, links, optional layers, or unexpected metadata indicators. Approved visual redactions still require review. Keep the original and any original source receipts private as appropriate.

Background: [Apryse financial redaction](https://apryse.com/blog/redaction/document-redaction-in-fintech) and [EMA clinical-trial records guidance](https://www.ema.europa.eu/en/documents/regulatory-procedural-guideline/guideline-computerised-systems-electronic-data-clinical-trials_en.pdf).

For the PDF value editor and hash demonstration, see [Source investigations](docs/README_SOURCE_FORENSICS.md).

## Privacy review and OCR forensics

- Install Tesseract with English language data and make its executable available on PATH for local OCR.
- Select **Include local OCR for scans** to search scanned regions. Exact repeats of labeled identifiers can be approved together. Initial-and-surname matches are suggestions for individual review.
- **Review redaction plan** checks the supported visit-date and precise-age pattern in visible native text. Cumulative exposure flags complementary masks for recognized fields within the exact same source and recipient label, using opted-in export history.
- **Scan final PDF for protected values using local OCR** is enabled by default in the interface. Recognized labeled identifiers touched by the mask are checked against the exported raster. Confirmed OCR matches pause delivery. Inconclusive results, including unreadable pages or an empty protected-value set, are reported separately. Review these before sharing. Exact matching can miss OCR errors and variant spellings.
- Under **Verify**, enable **Compare visible field values with OCR if the PDF changed** to analyze competing readings near detected visual changes. This opt-in includes recognized field values in the result and inspection report. Readings are heuristic, and changed pages without a confident unique field match are flagged for review. Significant page layout changes require manual review.

This release is designed for a single-user local Studio. The privacy review relies on labeled identifiers, bounded local OCR, a specific date-and-age rule, and the exposure records available locally. These checks do not certify complete de-identification or extend the original cryptographic proof statement. Public sensitive uploads and multi-tenant deployment are outside the validated scope.
