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
