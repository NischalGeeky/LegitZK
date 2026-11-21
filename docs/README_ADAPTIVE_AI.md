# Local AI and the adaptive redaction algorithm

## What the libraries do and what LegitZK does

PyMuPDF renders PDF pages and extracts positioned words. Tesseract optionally recognizes text in page images. scikit-learn trains a local text classifier. libsodium provides group arithmetic. LegitZK builds the field review workflow, compiles exact hide and keep policies, chooses the adaptive layout, authenticates its tiles against the source, and checks the commitment evidence and canonical PDF. The cryptographic confidentiality comes from commitments and zero-knowledge proof, with no encryption of the published redacted artifact.

## Detection on fresh documents

1. Extract lines and word boxes. The optional OCR pass analyzes the actual displayed raster. OCR and digital text results can be redundant, so review overlapping suggestions.
2. Propose email addresses and plausible numeric or alphanumeric identifiers. Use nearby labels to identify a familiar field. An offline TF-IDF/logistic-regression model resolves some label variations when the rules do not fire. The model trains locally from a small built-in synthetic context corpus. Its confidence cutoff is a heuristic and has no calibration claim.
3. For an unfamiliar field, enter a literal phrase or type a label followed by `=>` to suggest the same-line value. For a full or multiline clause, drag a region manually. The response includes category, method and coordinates only.
4. Apply **Hide**, **Keep**, or **Dismiss**. The reviewer approves every region that enters the policy. They can still add undetected content.

This approach can generalize to familiar categories in previously unseen layouts, subject to extraction and model errors. It makes no claim to understand arbitrary legal clauses, detect all names or addresses, or recognize sensitive information absent from the candidate extraction step. Scanned images, difficult layouts, and mismatches between embedded text and visible pixels need review.

## Adaptive policy compiler and cut

An approved region is a half-open pixel rectangle `[page, x, y, right, bottom]`. The planner performs the following deterministic steps:

1. Validate and canonicalize the approved hide and keep boxes.
2. Mark every 8-pixel cell intersecting a hide box. These cells are forced by the minimum granularity. If any forced cell also touches a keep box, report the first conflicting coordinate. Compute exact pixel areas, including clipped edges, and enforce the cap per page.
3. Recursively coalesce a quadtree branch when all selected descendants have the same visibility. The resulting cut exactly covers every page, with a mixture of 8-, 16- and 32-pixel leaves. Reject if it exceeds the request's tile-count limit.

Every compatible cut must hide the forced 8-pixel cells, so this mask minimizes collateral redaction within the grid. Coalescing homogeneous subtrees minimizes selected tile count among cut representations of that fixed mask. The optimization order is first minimize hidden pixels, then minimize tile count. If a stricter tile count would require hiding additional pixels, the app reports the limit and does not look for a deliberately more destructive solution.

## Candidate research contribution

The evaluated contribution is an authenticated, verifier-reconstructable adaptive layout for post-ingestion hide/keep policies. It preserves the fine-grid minimum-loss mask while reducing the number of authenticated tiles and the size of evidence in the measured layouts. The pre-commitment inventory uses more tiles than the selected cut, so lower verification cost comes with an up-front ingestion trade-off. AI is evaluated separately from the planner against an identical field extraction stage. Neither a new cryptographic primitive nor a worldwide novelty claim is established.

See the [proof design](README_ZERO_KNOWLEDGE.md) and [measured results](README_PUBLIC_PDF_TESTING.md). For earlier related work see [the original raster research notes](pdf-studio-research.md), which describe the fixed-grid predecessor.

## Optional question interpretation

The Zero Knowledge Proof tab has a separate FLAN-T5 Small adapter for interpreting a user's question and public field metadata. It proposes a single-field comparison. Current UI flow is **Interpret question → Review condition → Prove and verify** for a current local export. The proof verifier checks the selected condition independently of the model. See the [setup guide](../README_PDF_STUDIO.md#optional-local-tools) and [evaluation](README_PUBLIC_PDF_TESTING.md).
