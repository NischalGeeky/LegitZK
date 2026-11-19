# APBD v1 protocol and threat model

## Actors and assumptions

The issuer attests five typed text fields, a USD amount in cents, and the SHA-256 fingerprint of the source PDF. The owner has the openings and amount witness. The auditor independently controls the expected policy, document ID, recipient identity, random 256-bit challenge, expiration and issuer public key. The online service is trusted with the original and witness, issues requests on the auditor's behalf, and maintains state for online replay prevention. The offline verifier consumes the package, original auditor request, and trust mapping through three distinct inputs.

The adversary controls a presentation and its PDF, knows other public presentations, and may attempt substitution or replay. The protocol relies on Ed25519 unforgeability, SHA-256 collision resistance, computational binding of Pedersen commitments in Ristretto255, and the proof's Fiat–Shamir random-oracle model. The independent Ristretto generator is derived with libsodium's `from_hash` from a domain-separated SHA-512 digest. Treat the binding and privacy argument as a design analysis pending independent review.

## Serialization and inputs

The implementation uses sorted-key compact UTF-8 JSON with ASCII escape sequences, no non-finite numbers, and duplicate-key rejection for evidence import. Protocol v1 restricts names and visible values to bounded printable ASCII and uses exact integer timestamps and thresholds. Manifest signatures are lowercase hex Ed25519 over the ASCII domain `LegitZK/manifest/v1`, a zero byte, and canonical bytes. The same domain-plus-zero convention prefixes application hashes. Each nonnumeric leaf hashes the ordered array of schema ID, field ID, validated value, and an independent 32-byte random salt encoded as lowercase hex.

The signed manifest contains the schema ID (`vendor-contract-usd/v1`), immutable 128-bit document ID, issuer ID, UNIX issuance/expiry, original SHA-256, exact field-hash inventory, and Ristretto amount commitment. The request contains policy version, schema ID, accepted issuer, sorted visible field names and public threshold, plus document ID, audience, nonce and expiration. The mandatory set consists of vendor, buyer and effective date. The auditor selects whether service must be included. The bank reference and exact amount cannot be disclosed through this schema's explicit fields.

The presentation transcript is SHA-256 over the domain-separated canonical object of signed manifest, signature, full request, disclosed openings and exported PDF hash. The full evidence wraps that object with two arrays of 32 proof records and one standard Base64 PDF. A proof record is 160 bytes encoded as hex and consists of a 32-byte Ristretto point followed by four 32-byte little-endian canonical scalars in the order challenge 0, response 0, challenge 1, response 1. The verifier checks the encoding, reconstructs Schnorr announcements and derives challenges with SHA-512, the transcript digest, side and bit position, commitment and both announcements.

## Range proof

Let `G` be the Ristretto generator, `H` the independently derived generator, `q` the prime group order, `u = 2^32 − 1`, `x` the amount and `t` the threshold. The issuer signs commitment `C = xG + rH`. The holder proves a 32-bit opening of `C − tG` and a 32-bit opening of `uG − C`.

For either target the prover creates 32 Pedersen bit commitments `B_i = b_i G + s_i H` with weighted blinding sums chosen to match the target. Each Schnorr OR proof demonstrates knowledge of the discrete log base `H` of either `B_i` or `B_i − G`. One branch is simulated and the other answered with the bit commitment's actual randomness. The verifier checks each OR proof and checks that the weighted sum of the bit commitments equals its target. If the extracted lower and upper distances are `d` and `e`, respectively, adding the two opening equations gives a commitment to both `d + e` and `u − t`. Binding makes the values agree modulo `q`; because the two distances and their sum are small relative to `q`, this gives ordinary integer equality. Acceptance then implies an opening of `C` to an amount in `[t, u]`, subject to the assumptions above.

This is a fixed-width noninteractive zero-knowledge range argument using established group operations. It uses no setup ceremony, proving key or circuit compiler. Its size grows linearly with the proof bit width. The proof composition and Python implementation are specific to LegitZK. Python scalar processing is not constant-time.

## Intended properties

| Property | Acceptance condition and failure event |
|---|---|
| Document authenticity | An accepted manifest verifies under the independently approved issuer key and pins the requested document ID and a source byte hash. A forged signed manifest would break signature unforgeability. The auditor needs the original bytes to check the association firsthand. |
| Disclosure integrity | Each visible value opens its field-specific signed hash. The accompanying PDF must equal a fresh canonical render of those opened values. A substituted visible value would require a bad opening or signature. |
| Policy correctness | The package matches the auditor's independently retained request exactly. Its openings match the exact allowed/required set. The fixed schema inventory is signed. Policy evaluation happens in the public verifier. |
| Predicate soundness | A valid range argument relates the public threshold to the same signed amount commitment in the manifest. Both range bounds matter for eliminating wraparound. |
| Confidentiality | The package contains no plaintext hidden values, private salts, or amount-opening randomness. Salted commitments and hiding group commitments support secrecy under their assumptions. Intended public leakage includes the schema, the exact visible fields, policy, successful threshold, source hash, issuer and recipient metadata and linkable document identifier. |
| Context binding | A copied proof fails for a different accepted transcript under the same commitment. A holder with the witness can legitimately prove a fresh statement. State controls online single-use for each request. An offline request remains re-verifiable through expiry. |

## PDF boundary and residual risks

The source path accepts only a byte match to a server-issued schema PDF and never runs a parser over uploads. The disclosure is generated from public values, with constant-size masks for omitted fields. Export includes no inherited PDF objects, fonts, attachments, metadata or text from the original. The verifier checks exact bytes against regeneration, so a matching self-reported checksum alone is insufficient. Public values may themselves encode correlated information. Source fingerprints may confirm a candidate original whose exact bytes are already known. Repeated threshold queries and stable identifiers can reveal information through inference or linking.

The PDF guarantee concerns the template render of authenticated claims. It gives no visual equivalence argument for arbitrary PDFs and no inference about unseen clauses. The issuer can sign inaccurate claims. A malicious service or compromised host can read private witnesses and source files. Users can resend downloaded packages beyond the web share controls. There is no public key revocation service, holder-bound wallet credential, or forward secrecy for stored records if the storage key is obtained. Audit events are mutable by an operator with write access.
