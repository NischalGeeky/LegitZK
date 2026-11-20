# LegitZK

LegitZK PDF Disclosure Studio is a local research application for recipient-policy-bound redaction of uploaded PDFs. It combines offline field suggestions, a deterministic adaptive redaction algorithm and a verifier-checkable proof package.

**Start with the [Windows quick-start and demo](README_PDF_STUDIO.md).** The studio uses `pdf_studio:app` on port 8001. It requires no API key or issuer account.

## Verify the implementation

From the project folder after installing requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m benchmarks.adaptive_studio
```

The benchmark writes synthetic fixtures and [raw measurements](benchmarks/adaptive-results.json). The [testing README](docs/README_PUBLIC_PDF_TESTING.md) gives the public-PDF evaluation procedure.

## Earlier contract demonstration

The previous structured-contract demo remains available separately. Run `python app.py issuer@example.test` once to create its issuer, then start `python -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log`. Its sample inputs are in `fixtures/contract.json`. The previous project plan, literature review and benchmark notes describe that historical prototype.

## Match a hidden field

In **Redact**, mark a hide region that covers the entire value and review the
redaction plan. Open **Register fields for private matching**, select the hide
region, and enter a safe public label, datatype, and private value confirmed
against the original PDF. Add the field and generate the export. Keep this
workspace open until you have answered the request. Private openings live in
the owner process until the workspace expires, closes, or the server stops.

In **Zero Knowledge Proof**, the recipient loads the redacted PDF and proof ZIP,
selects a field, enters a candidate, and downloads a match request. Retain the
request and send a copy to the owner privately. The request contains the
candidate. The recipient's Studio must trust the issuer's public key obtained
independently. The owner loads the request in the same tab, approves the displayed
candidate, and returns the downloaded match proof. The recipient verifies the
proof with the request they retained and the verified export they loaded.

A match confirms the candidate against the owner-attested value. The proof
checks a typed commitment associated with the signed receipt and exact PDF
export. The owner checks the original text and region when registering the
field. Amounts use two decimal places and a currency code. Dates use
`YYYY-MM-DD`. Code and text matching normalize Unicode and ignore letter case.
A missing proof provides no verified answer. Share only field labels and
regions safe for the recipient to see, and approve candidates deliberately.
