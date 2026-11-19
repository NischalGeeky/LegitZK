# Private numeric claims

LegitZK signs commitments to named, unit-tagged unsigned 32-bit integers. Applications can choose attribute and unit identifiers independently of document type. A policy is an ordered conjunction of inclusive ranges, potentially over credentials from multiple issuers. A lower or upper bound is a range with one endpoint at the domain limit. A singleton range verifies an exact value and makes that value public.

## Run with the existing Studio Python environment

For PowerShell, create an example attribute file and issue a credential. Keep the issuer key and holder record private.

```powershell
'{"measure":{"value":84,"unit":"points"}}' | Set-Content -Encoding ascii attributes.json
$expires = [DateTimeOffset]::UtcNow.AddHours(2).ToUnixTimeSeconds()
.\.venv\Scripts\python.exe claims_cli.py keygen school issuer.key trust.json
.\.venv\Scripts\python.exe claims_cli.py issue school issuer.key attributes.json holder.json --expires $expires
```

The verifier prepares a policy from the credential ID printed by issuance, using a fresh challenge. Save it independently as `policy.json`. Replace the ID, nonce and expiration in the example before running.

```json
{
  "schema": "legitzk/range-policy/v1",
  "audience": "reviewer",
  "nonce": "<32 random bytes in lowercase hex>",
  "expires": 0,
  "clauses": [
    {
      "credential_id": "<credential ID>",
      "issuer": "school",
      "attribute": "measure",
      "unit": "points",
      "min": 75,
      "max": 100
    }
  ]
}
```

The verifier can generate the nonce with `.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"` and use the PowerShell expiry expression above to choose a future expiration. To combine issuers, add their public keys to the independently managed trust JSON, add clauses and pass their holder records to the prove command.

```powershell
.\.venv\Scripts\python.exe claims_cli.py prove policy.json trust.json presentation.json holder.json
.\.venv\Scripts\python.exe claims_cli.py verify policy.json trust.json presentation.json
.\.venv\Scripts\python.exe claims_cli.py review next-policy.json trust.json presentation.json
```

The Verify tab also accepts the public presentation, independently retained policy, and trusted public keys. Review computes the intersection of a proposed policy with valid, unexpired presentations supplied for the same audience. A singleton intersection exposes an exact value if the proposed policy also holds. The report covers the supplied history and public interval constraints.

## Proof and trust model

For each clause with endpoints (L,U), an Ed25519-signed commitment (C = vG+rH) is taken from the issuer manifest. Existing Ristretto255 bit proofs show the openings for (C-LG) and (UG-C) are unsigned 32-bit values. Their sum is (U-L), so there is no scalar-field wraparound under these bounds. The transcript commits to the ordered policy, credential manifests and signatures, audience, expiration, nonce and clause index. Verification uses the independently held policy and trust anchors. The issuer is responsible for validating the real-world attributes. An optional signed source hash attests only the issuer's association between source bytes and credential.

Presentations reveal issuer names, attribute names, units, public ranges, credential identifiers and commitment metadata. They are linkable and can be copied within the policy validity window. The verifier should issue a fresh nonce per transaction and manage nonce consumption externally. Issuer key and witness files use exclusive creation and mode 0600 on POSIX. Use OS-level access controls and secure storage on Windows.

This is an unaudited extension of the existing range-proof implementation. It does not implement standardized credential envelopes, credential revocation, arbitrary field relationships, cross-credential holder equality, selective hiding of credential metadata or unlinkable presentations.

To reproduce the claim benchmark, run `python benchmarks/claims.py --clauses 1 2 4 --trials 10`. See [measurements](../benchmarks/claims-results.json) for raw samples. This benchmark isolates numeric proof generation and verification under one issuer.
