# Policy-bound redaction of committed PDF rasters

## Research contribution and prior art

The candidate systems contribution is an evaluated workflow for ordinary PDFs that combines a verifier-retained redaction budget, mandatory visible regions and a request-bound proof over committed page tiles. The verifiable claim is intentionally narrow. For the selected raster profile, the disclosed output preserves all pixels outside the mask, every masked tile is black, and the mask obeys the exact independently retained request. The experiment tests whether a two-aggregate proof keeps the proof itself compact while preserving enforceable policy checks. It does not establish a previously unknown cryptographic primitive or publication-level novelty.

| Prior work | Relation to the prototype |
|---|---|
| Starling Lab and Stanford Applied Cryptography | Direct precedent for verifiable PDF pixel redaction in an investigation. [Project](https://starling.stanford.edu/prototypes/document-redaction/) |
| Chabanne, Hugel and Keuffer | Direct precedent for authenticated document redaction and cryptographic proof, building on PhotoProof. [Paper](https://www.eurecom.edu/publication/5311/download/sec-publi-5311.pdf) |
| ISO/IEC 23264-2:2024 | Redactable attestations and constrained redactions are established. The studio studies a specific late-bound recipient and area-budget workflow. [Standard abstract](https://webstore.iec.ch/en/publication/99496) |
| ZKPDF | Proves selected claims about signatures and PDF text. Its documented focus differs from preservation of raster pixels. [Documentation](https://privacy-ethereum.github.io/zkpdf/docs/introduction.html) |

A stronger novelty claim requires full-text citation chaining and evaluation against implementations of the closest policy-constrained image-redaction systems. The 160-byte proof result alone cannot establish an overall size or speed advantage.

## Commitment, redaction and verification

At trusted local ingestion, MuPDF rasterizes the original to RGB at 96 DPI with annotations disabled. Tiles are 32×32 pixels except at the right and bottom edges. A tile digest is a domain-separated SHA-512 reduction incorporating the source ID and exact page and coordinates. The ingester commits to it with an independent random Pedersen blinding scalar and signs a receipt containing the ordered commitment-vector hash, PDF hash, raster profile and dimensions. The recipient independently retains the receipt, its trusted signing key and the expected request. The request pins the source identifier, audience label, nonce, expiry, protected tile indices and per-page area budget.

The verifier recomputes the visible tile digests from the exported canonical raster. It subtracts each visible digest times G from its commitment and weights those differences by coefficients derived from the full public transcript. It verifies a Schnorr proof of an H-only opening of the resulting aggregate. A separate representation proof covers the aggregate of the hidden tile commitments, with witnesses consisting of the weighted digest and blinding scalars. Separation matters. A shared aggregate with a free digest coefficient would allow a change in the visible contributions to be offset by adjusting the hidden digest witness.

The proof transcript binds the receipt, request, mask, commitment vector, public raster hashes and output PDF hash. The proof payload carries two Ristretto announcements and three scalar responses. Verification also performs deterministic PDF reconstruction and compares the supplied PDF byte-for-byte. The raw tile openings, original page rasters and original PDF never enter the exported package. The verifier sees public tile positions, the redaction mask, source fingerprint, document identifier and policy. Multiple disclosures of the same receipt are linkable and may reveal complementary regions. A predictable full source hash can confirm a known candidate document.

This is a zero-knowledge Schnorr argument about aggregate commitment openings in the Fiat–Shamir random-oracle model. Visible-pixel binding depends on collision resistance, Ristretto discrete-log hardness, transcript-derived coefficients and the independently trusted receipt. The hidden argument does not prove knowledge of the raw hidden pixels or execute a PDF renderer in zero knowledge. The ingestion process is trusted to link the PDF and raster honestly. The audience is a request label, not a designated-verifier key. Anyone with the matching expected inputs can verify before expiry. The redaction policy governs locations and area and has no semantic understanding of sensitive text. Both the custom aggregation protocol and PDF handling need independent review before use with sensitive documents. The parser currently runs inside the local service without resource isolation.

## Experiments

Run `python -m benchmarks.pdf_studio` from the root. Results below are medians of ten measured iterations per size after one warm-up, on the Linux execution environment. The fixture is sparse synthetic text. Proof timings include constructing the PDF and package. Verification includes reconstructing the PDF. Results will vary with image complexity and hardware.

| Pages | Tiles | Ingest (ms) | Generate (ms) | Verify (ms) | Raw proof | JSON package |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 900 | 133.9 | 161.4 | 169.4 | 160 B | 75,236 B |
| 3 | 2,700 | 393.5 | 479.4 | 509.1 | 160 B | 224,116 B |

The raw proof size is constant in these tests. Input commitments, public raster data and verifier computation grow with document size. The [raw results](../benchmarks/pdf-results.json) record all 20 measured iterations. To rerun the positive and negative checks, install `requirements-dev.txt` and run `python -m unittest discover -s tests -v`. The suite includes a visible-pixel change tested with a freshly generated proof transcript, a non-black hidden tile, a protected region violation, an excess-area request, substituted PDF bytes, an incorrect signer and a transplanted recipient. Native Windows and a full browser session were not tested in this execution environment.
