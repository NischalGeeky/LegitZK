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

## Ask and verify a private claim

Apply this patch over the version with the Zero Knowledge Proof tab. For
plain-English interpretation, run this one-time setup from PowerShell in the
project folder. Use the same Python environment that starts the app.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-nlp.txt
.\.venv\Scripts\python.exe setup_claim_model.py
.\start-windows.cmd
```

The setup downloads approximately 300 MB of public FLAN-T5 Small base weights. The patch provides
the fine-tuned adapter in `claim-model/`. The app loads both locally. Only the
question and public field labels, descriptions, datatypes and currencies go to the model.
You can enter a condition directly if model setup is unavailable.

1. **Redact** the document and review the redaction plan. Open **Register fields
   for private proofs**, select a hide region that covers the value, and enter a
   descriptive label and its exact value from the original. Labels and regions
   are public. Export and keep the owner's original workspace open. The
   private openings expire with that workspace and are lost when the server stops.
2. In **Ask what you want to verify**, load the redacted PDF and its matching ZIP.
   Try “Did checking finish the month with seven grand or more?” or “Had the
   patient turned 18 by the time of the visit?” after registering the relevant field.
   Check or edit the interpretation, select **Review condition**, then confirm
   and download `claim-request.json`. Keep a copy.
3. In **Document owner**, upload the request, review and approve the exact
   condition, then download `claim-proof.json` if a proof can be generated.
   Share the proof with the recipient.
4. In **Verify your request**, upload the retained request and owner proof.
   The proof is checked against the signed field record and exact request. The
   verifier must trust the signing key through the Studio trust configuration.
   A missing proof leaves the condition unverified.

New amount and whole-number commitments support equality, strict and inclusive
thresholds, and inclusive ranges. Amounts use two decimal places and a signed
32-bit range in cents. Dates and codes support equality. Earlier exports
support equality, and must be regenerated to support numeric ranges. Use
specific labels such as `Age at visit (years)` or `Resting pulse (bpm)`.
Questions that require several fields or derived values need additional
proof operations. A verified proof establishes a condition on the
owner-attested value. The owner is responsible for checking transcription
against the document and deciding which conditions to approve.

To reproduce fine-tuning and its synthetic evaluation:

```powershell
python train_claim_model.py --output claim-model-initial --skip-evaluation
python train_claim_model.py --resume claim-model-initial --steps 95
```

The training and evaluation sets use different
field labels and phrasing templates. Evaluation counts full-claim matches and
clarification responses. Run `python train_claim_model.py --evaluate-only` to
evaluate the supplied adapter. Check the results in `claim-model/evaluation.json`.
The translator is experimental. Review and correct its drafts before sending a request.

