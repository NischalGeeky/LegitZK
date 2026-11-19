# Architecture and operations

## Components

- `web/` contains a responsive dependency-free ES module, stylesheet and HTML shell. The browser uses same-origin requests and its native PDF viewer.
- `app.py` implements FastAPI, SQLite persistence and authorization. Keys are initialized locally and private records are encrypted before storing them.
- `protocol.py` implements the schema validator, issuer manifest, PDF renderer, presentation formatter and verifier. `rangeproof.py` uses libsodium group arithmetic through a narrow binding.
- `verify.py` is the offline verifier. It works with a public trust mapping and has no code or database dependency on the web service.

| Table | Data |
|---|---|
| `users` | Unique normalized email, salted scrypt verifier, role |
| `sessions` | SHA-256 token hash, account, expiry |
| `documents` | Immutable contract reference, owner, encrypted issuer manifest and source record |
| `requests` | Document reference, recipient account, encrypted request and evidence, consumption and revocation timestamps |
| `events` | Actor, event, reference, timestamp |
| `limits` | Short-lived rate limit counters |

## API

FastAPI serves an OpenAPI description at `/openapi.json`. JSON actions require the `X-LegitZK-Action: 1` header. Authentication uses an HttpOnly session cookie.

| Routes | Operation |
|---|---|
| GET `/api/health`, `/api/trust`, `/api/benchmarks` | Readiness, local issuer mapping and benchmark summary |
| POST `/api/register`, `/api/session`, `/api/logout` | Owner/auditor registration, login, logout |
| GET `/api/dashboard` | Recent account-specific documents, disclosure requests and events |
| POST `/api/documents` | Issuer assigns a newly signed document to a registered owner |
| GET `/api/documents/{id}/source.pdf` | Owner-only original PDF |
| POST `/api/documents/{id}/match` | Raw PDF fingerprint check against that owner's record |
| POST `/api/requests` | Auditor creates a versioned request with threshold and service visibility |
| GET `/api/requests/{id}/preview.pdf` | Owner-only preview against the active policy |
| POST `/api/requests/{id}/publish`, `/revoke` | Owner generates/publishes evidence or revokes access |
| GET `/api/requests/{id}/package`, `/disclosure.pdf` | Active, designated-recipient downloads |
| POST `/api/requests/{id}/verify` | Designated recipient checks and consumes successfully verified online request |
| POST `/api/verify` | Independent evaluation from three JSON strings named package, request and trust |

Verification is fail-closed per check. The web API does not echo witness data or submitted private form inputs in error messages.

## Docker development deployment

```bash
docker compose up --build -d
docker compose exec legitzk python app.py issuer@example.test
```

Open `http://127.0.0.1:8000`. The service listens on loopback from the host and uses a volume mounted at `/data`. Development uses HTTP on loopback. Docker was unavailable in the implementation environment, so the image and Compose launch were not executed there.

For a controlled HTTPS evaluation, terminate TLS at a trusted reverse proxy with a signed certificate. Keep the application bound to loopback and set `LEGITZK_HTTPS=1` in the service environment so the app sets the Secure cookie flag and HSTS. Use one worker, a private data directory and restricted writable volumes. Do not configure a proxy to trust arbitrary forwarding headers.

## Data and operational boundaries

SQLite stores metadata in cleartext and Fernet encrypts source records, requests and packages. The storage secret and issuer key are mode-0600 local files. Backups require treating the data volume and both key files as sensitive. Removing a key is destructive and defeats verification or decryption as applicable. The app uses owner/auditor/issuer roles and object-level authorization, CSRF request headers, SameSite cookies, rate limits, body size limits and a content security policy. Shares expire automatically for access purposes and may be revoked. Expired records persist for research reproducibility. Audit records are ordinary application data.

This release omits password recovery, email verification, OIDC or MFA, tenant administration, managed secret storage, automated record retention, key rotation and a separate worker network. External users, sensitive inputs and internet-facing deployment require an independent review and production controls.
