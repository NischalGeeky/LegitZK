# Run the PDF Disclosure Studio

## Windows

1. Install 64-bit Python 3.12 and open PowerShell in the folder containing `start-windows.cmd`.
2. Place the official x64 MSVC `libsodium.dll` next to `rangeproof.py`. [libsodium releases](https://download.libsodium.org/libsodium/releases/)
3. Run the launcher and open [http://127.0.0.1:8001](http://127.0.0.1:8001). Keep PowerShell open.

```powershell
.\start-windows.cmd
```

The launcher creates `.venv` and installs the main requirements when needed. On Linux, install the system libsodium shared library, create a Python 3.12 virtual environment, install `requirements.txt`, and run `python -m uvicorn pdf_studio:app --host 127.0.0.1 --port 8001 --no-access-log` from the project root.

### Optional local tools

- **OCR.** Install Tesseract with English language data on PATH. Check with `tesseract --version`. Text-layer detection and manual selection are available without it.
- **Natural-language questions.** After the launcher creates the environment, stop the server with Ctrl+C and run the following. Setup downloads roughly 300 MB of FLAN-T5 Small base weights separately from the dependencies. The fine-tuned adapter is already in `claim-model/`. Manual comparisons work without this setup.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-nlp.txt
.\.venv\Scripts\python.exe setup_claim_model.py
.\start-windows.cmd
```

The model interprets the question using public field metadata. On the included synthetic evaluation, it matched 41 of 78 structured conditions and produced the expected clarification on 0 of 18 clarification cases. Review its field, operator and threshold before proving. See [evaluation details](docs/README_PUBLIC_PDF_TESTING.md).

## First disclosure

1. Open **Redact**, upload `fixtures/demo-vendor.pdf`, and select **Upload and commit**.
2. Search for `Settlement Amount =>`, select **Detect fields**, and mark the matching settlement regions **Hide**. Review both pages. Use the keep-visible tool where you want to protect visible content from the mask.
3. Enter a recipient label and select **Review redaction plan**. Inspect the grid-aligned coverage, including any extra pixels masked.
4. Choose **Generate proof and PDF**. Download the redacted PDF and its matching proof ZIP.
5. In **Verify**, select both files and click **Verify disclosure**. For a comparison against a specific source, use a signed receipt saved at ingestion under **Check against an expected source**.

For a field proof or integrity demonstration, follow the [walkthrough](docs/README_WORKFLOW.md).

## Detection and privacy review

- The detector suggests labeled clinical identifiers and repeated matches in accessible text. Enable **Include financial identifiers** for additional account, routing, payment, government and reference fields. Confirm each mask, especially repeated values, scans, and multiline content. Manual regions are suitable for unsupported visual content such as signatures and barcodes.
- **Review redaction plan** checks supported age/date inferences and reports cumulative exposure from opt-in exports of the same source to the same literal recipient label.
- The default **Scan final PDF for protected values using local OCR** option looks for recognized protected values in the output. Findings pause export. An inconclusive scan can occur when OCR is missing, some pages are unreadable, or there are no tracked values. Review coverage before sharing.

## Verification on another installation

Obtain the source Studio's public key independently. The issuer can display it at `/api/key`. In the verifier's PowerShell session set `$env:LEGITZK_PDF_TRUSTED_KEY = "trusted-public-key-in-hex"`, then restart the verifier. Each installation also trusts its own ingestion key. Verification uses the bundled request's one-hour validity window.

The service is designed for a trusted, single-user loopback environment. See [architecture and storage](docs/README_ARCHITECTURE.md) before handling evidence or configuration files.
