# Zero knowledge in LegitZK v2

## The statement

Given a trusted ingestion receipt, an expected request and the redacted PDF, the verifier checks that every visible tile matches its committed source, all required hidden tiles are black, protected regions stay visible, budgets hold and the received PDF equals the canonical image-only export.

## Ingestion and authenticated tiles

The ingester renders pages, enumerates their 32→16→8 quadtrees in fixed depth-first order, and assigns each node a position in the inventory. For the original RGB pixels of each node it computes a domain-separated scalar mᵢ that includes the source ID and tile location. It samples a fresh random scalar rᵢ, then computes a Ristretto255 Pedersen commitment:

**Cᵢ = mᵢG + rᵢH**

A Merkle leaf hashes its deterministic index and commitment. Internal Merkle hashes have a separate domain from leaves. The signed source receipt pins the Merkle root, source PDF hash, raster profile, dimensions and randomly generated source ID. A single multi-resolution receipt can be used for multiple disclosure requests.

The recipient retains an approved request. Sender and verifier independently recompute the same canonical adaptive cut. The sender presents the commitments selected by the cut and a Merkle multiproof. The verifier recomputes the indices and requires the correct number of sibling hashes at each level. Unselected tile commitments and their openings are unnecessary for verification.

## Two Schnorr relations

For a visible tile the verifier computes m′ᵢ from the disclosed pixels. If they match, **Cᵢ − m′ᵢG = rᵢH**. If pixels changed, the extra G term cannot efficiently be expressed as a known multiple of H. For batching, the verifier derives transcript-dependent weights wᵢ and builds two separate aggregate statements:

- Visible relation **V = ∑visible wᵢ(Cᵢ − m′ᵢG) = RᵥH**.
- Hidden relation **W = ∑hidden wᵢCᵢ = MₕG + RₕH**.

The witnesses Rᵥ and Rₕ are the corresponding weighted sums of blindings. Mₕ is the weighted sum of the hidden tile digests. A free digest coefficient exists only in the hidden relation. Combining the two would let a party compensate a visible discrepancy by changing that hidden coefficient. Transcript-derived weights defend against cancellation between altered visible tiles under the random-oracle model.

The prover samples fresh scalars a, b and c. It sends **A = aH**, **B = bG + cH**, and three responses **zᵥ = a + eRᵥ**, **zₘ = b + eMₕ**, **zₕ = c + eRₕ**. The challenge e is derived by Fiat–Shamir from the public transcript and group points. The verifier recomputes e and checks:

- **zᵥH = A + eV**
- **zₘG + zₕH = B + eW**

The transcript covers the signed receipt, exact expected request, selected commitments and sibling hashes, public raster hashes and export PDF hash. Generating new responses requires knowledge of valid aggregate openings. The raw proof contains two 32-byte points and three 32-byte scalars, or 160 bytes. The complete evidence also carries commitments, Merkle siblings and compressed public page pixels.

## What zero knowledge hides

Fresh randomness hides the witness openings. In the idealized Schnorr simulation, choosing responses and a challenge first permits construction of announcements that satisfy the same equations. The noninteractive argument uses the Fiat–Shamir random-oracle model. Hidden tile content and individual openings stay out of the export. The public request, geometry, source hash, visible tiles and report metadata remain public. Multiple disclosures from one source are linkable and may reveal complementary content.

The hidden relation demonstrates knowledge of an aggregate opening to tile digests. It does not prove possession of every raw hidden tile in an independent PDF renderer. Source-to-raster association relies on the trusted local signature. The policy constraints, signature, Merkle membership, blacking-out and exact PDF bytes are deterministic verifier checks alongside the Schnorr proof. AI output is neither an authenticity signal nor evidence that every sensitive field was found. The custom protocol and ingestion path have not received independent security review.

For a presentation, show the visible equation first and the [proof tampering demo](README_WORKFLOW.md) second.
