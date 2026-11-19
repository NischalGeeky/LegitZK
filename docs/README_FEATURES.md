# LegitZK PDF Disclosure Studio | Features

| Capability | Current behavior |
|---|---|
| Open and preview real PDFs | Preview any eligible, unencrypted PDF of up to eight pages and 16 MiB, up to 2,300 pixels per edge and eight million total pixels at 96 DPI. |
| Local field detection | Uses rule-based candidate extraction and an offline TF-IDF/logistic-regression fallback for familiar field categories. Detected regions are suggestions. |
| Custom document search | Find literal phrases or same-line label/value fields using input such as `Settlement Amount =>`. Works without model retraining. |
| Optional OCR | Local Tesseract can analyze scanned and mixed PDF pages. The Studio reports unavailable OCR and pages without accessible text. |
| Review and manual edits | Mark suggestions as hide or keep, dismiss them, drag arbitrary pixel rectangles, enter bounds manually, and remove approved regions. |
| Per-request disclosure policy | Set hide and keep boxes and a recipient label. Preview the grid-aligned plan. The one-hour request travels in the proof ZIP. |
| Adaptive redaction | Uses 8-pixel leaves around boundaries and merges uniform regions into 16- or 32-pixel tiles. Rejects conflicts and infeasible budgets. Previews the exact mask. |
| Source receipt | Ed25519 signature binds the uploaded PDF fingerprint, raster profile, page dimensions and Merkle root of the tile commitments. |
| Image-only export | Downloads a new PDF made from masked pixels. The source text layer, attachments, annotations and source metadata objects are excluded. |
| Independent verification | Upload the redacted PDF and proof ZIP to verify the signed inventory, source receipt, bundled request, adaptive tile commitments, Schnorr proof and exact PDF. The earlier verification API supports independently retained requests and fixed-grid packages. |
| Single-user local workspace | No paid API, GPU or issuer login. Workspace access expires after 20 minutes and may be closed manually. Private raster and extracted text stay in process memory during normal operation. |

The recipient label scopes the proof to the expected request; anyone who has that request and the public artifacts can verify it before expiry. Approved box coordinates and redaction geometry are disclosed in the request. The model does not determine document authenticity or detect every sensitive field. A human still approves the redaction and checks unchecked pages.

**Disclosure comparison.** The verifier identifies changed or missing evidence members against the signed inventory. If the PDF differs and the proof is valid, it can distinguish a byte-only difference from a visible edit and highlight the first changed page. The Integrity lab includes both test cases.
