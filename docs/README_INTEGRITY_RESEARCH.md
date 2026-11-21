# Integrity benchmark for proof-backed PDF disclosure

A PDF can change at the byte level while showing the same page at a specified rendering resolution. The bundled **metadata-only** fixture adds a clearly marked subject to an already redacted test copy. The **visible-edit** fixture changes page pixels and serves as a positive control for the visual comparison. Both retain the clean proof ZIP for the experiment. Use synthetic documents and record the affected artifact at fixture creation.

## Candidate contribution

Study **artifact attribution in proof-backed PDF disclosure**. The research question is whether a signed file inventory and a comparison against the proof-authenticated raster can jointly identify the changed artifact and indicate whether its page appearance changed. Treat the metadata-only case as a known class of byte-level changes. The prospective contribution is the evaluation of file attribution and render classification together in a selective-disclosure workflow.

Compare the workflow with visual-only comparison, a trusted PDF-only hash, and binary proof verification. A visual check establishes rendering agreement under the tested profile. A PDF-only hash detects a PDF byte mismatch. The signed inventory identifies changed or missing JSON members when its signature validates against the verifier's configured key.

| Case | Expected artifact result | Expected visual result |
|---|---|---|
| Original export | All files match | Baseline |
| Marked metadata edit | PDF changed | No changed pixels at the comparison resolution |
| Marked visible edit | PDF changed | Changed page and pixel bounds |
| Benign PDF re-save with equal render | PDF changed | No changed pixels at the comparison resolution |
| ZIP repacked with identical member bytes | All files match | Baseline |
| JSON file changed or omitted | Affected member changed or missing | Visual result unavailable if required evidence fails |
| PDF and evidence from different exports | PDF changed against the supplied ZIP | Compare against the authenticated reference if available |
| Manifest missing, malformed, or untrusted | Verification fails | Attribution unavailable |

Use a fixed split of synthetic contracts, statements, and forms with a range of page counts and coverage levels. Hold out whole source documents. Record fixture pair IDs, ground-truth changed files, rendering profile, software versions, and timing. Report document-level detection, exact-set attribution, per-file precision and recall, visible-change classification, and median and 95th-percentile latency. Include benign transformations when measuring false positives for claims of malicious intent. A byte mismatch establishes a difference from the signed export. It cannot establish who changed it or why.

Maintain a renderer-version matrix when extending the experiment. A clean bundle verifies the signed export and its embedded request. A separate verifier policy would be needed to establish that the recipient expected that specific export when multiple valid signed exports exist.

## Related work

- Mainka, Mladenov, and Rohlmann, *Shadow Attacks: Hiding and Replacing Content in Signed PDFs*, NDSS 2021. Relevant prior work on discrepancies between document presentation and integrity guarantees. [Paper](https://www.ndss-symposium.org/wp-content/uploads/ndss2021_1B-4_24117_paper.pdf)
- PDF Association, *Challenges in the forensic analysis of PDF files*. Discusses incremental updates, redundant metadata, and implementation variability. [Article](https://pdfa.org/challenges-in-the-forensic-analysis-of-pdf-files)

## Implemented controls and a follow-up

Image-only exports undergo structural checks. Optional OCR scans look for known protected values in the output. The Studio can record releases and report cumulative raster exposure for the same source and recipient. These controls are described in the [Studio guide](../README_PDF_STUDIO.md#detection-and-privacy-review).

Independent reviewer signatures on region approvals are a possible follow-up. The current signed source receipt and disclosure inventory establish Studio provenance.
