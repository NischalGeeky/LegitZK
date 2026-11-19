"""LegitZK web workshop for issuer-attested vendor contract disclosures."""
import base64
from contextlib import asynccontextmanager, contextmanager
from hashlib import scrypt, sha256
from hmac import compare_digest
from pathlib import Path
import os
import re
from secrets import token_hex
import sqlite3
from time import time

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt
from starlette.concurrency import run_in_threadpool

from protocol import canonical, issue, parse_json, present, render, request_for, verify

BASE = Path(__file__).resolve().parent
DATA = Path(os.getenv("LEGITZK_DATA", str(BASE / "data")))
SECURE = os.getenv("LEGITZK_HTTPS") == "1"
ISSUER = "LegitZK Lab"
SESSION = "legitzk_session"
LIMIT = 192 * 1024
EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,120}\.[A-Za-z]{2,16}\Z")

DDL = """
CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, password TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, email TEXT NOT NULL REFERENCES users, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users, record BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, document TEXT NOT NULL REFERENCES documents,
 auditor TEXT NOT NULL REFERENCES users, request BLOB NOT NULL, package BLOB, consumed INTEGER, revoked INTEGER);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, actor TEXT NOT NULL, kind TEXT NOT NULL,
 ref TEXT NOT NULL, occurred INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS limits(bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL);
"""


@contextmanager
def db():
    con = sqlite3.connect(DATA / "legitzk.sqlite", timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        with con:
            yield con
    finally:
        con.close()


def password_key(password, salt):
    return scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=64 * 1024 * 1024)


def generate_password_hash(password):
    salt = os.urandom(16)
    return (salt + password_key(password, salt)).hex()


def check_password_hash(stored, password):
    raw = bytes.fromhex(stored)
    return compare_digest(raw[16:], password_key(password, raw[:16]))


def now():
    return int(time())


def audit(con, actor, kind, ref):
    con.execute("INSERT INTO events(actor,kind,ref,occurred) VALUES (?,?,?,?)", (actor, kind, ref, now()))


def secret_file(name, factory):
    path = DATA / name
    if not path.exists():
        try:
            with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as stream:
                stream.write(factory())
        except FileExistsError:
            pass
    return path.read_bytes()


def setup():
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    with db() as con:
        con.executescript(DDL)
        con.execute("BEGIN IMMEDIATE")
        cipher = Fernet(secret_file("storage.key", Fernet.generate_key))
        issuer = Ed25519PrivateKey.from_private_bytes(secret_file("issuer.key", lambda: Ed25519PrivateKey.generate().private_bytes_raw()))
    return cipher, issuer


def store(value):
    return app.state.cipher.encrypt(canonical(value))


def load(value):
    return parse_json(app.state.cipher.decrypt(value))


@asynccontextmanager
async def lifespan(app):
    app.state.cipher, app.state.issuer = setup()
    app.state.trust = {ISSUER: app.state.issuer.public_key().public_bytes_raw().hex()}
    yield


app = FastAPI(title="LegitZK", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/assets", StaticFiles(directory=BASE / "web"), name="assets")


@app.middleware("http")
async def security(req, next_handler):
    if req.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if req.headers.get("x-legitzk-action") != "1" or req.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Action header required"}, 403)
        chunks = bytearray()
        async for block in req.stream():
            chunks.extend(block)
            if len(chunks) > LIMIT:
                return JSONResponse({"detail": "Request is too large"}, 413)
        req._body = bytes(chunks)
    response = await next_handler(req)
    response.headers.update({
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "no-referrer", "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'self'",
    })
    if SECURE:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.exception_handler(ValueError)
async def validation_error(req, err):
    return JSONResponse({"detail": "Invalid input or the contract does not satisfy the policy"}, 400)


@app.exception_handler(RequestValidationError)
async def request_error(req, err):
    return JSONResponse({"detail": "Check the required fields and their types"}, 422)


def rate(key, limit, span=60):
    expires = (now() // span + 1) * span
    bucket = f"{expires}:{key}"
    with db() as con:
        con.execute("DELETE FROM limits WHERE expires <= ?", (now(),))
        row = con.execute("""INSERT INTO limits VALUES (?,1,?)
            ON CONFLICT(bucket) DO UPDATE SET count=count+1 RETURNING count""", (bucket, expires)).fetchone()
    if row[0] > limit:
        raise HTTPException(429, "Too many attempts. Try again shortly.")


def account(req, *roles):
    token = req.cookies.get(SESSION, "")
    with db() as con:
        row = con.execute("""SELECT users.email,role FROM sessions JOIN users USING(email)
            WHERE token=? AND expires>?""", (sha256(token.encode()).hexdigest(), now())).fetchone()
    if not row:
        raise HTTPException(401, "Sign in to continue")
    if roles and row["role"] not in roles:
        raise HTTPException(403, "This action requires a different role")
    return row["email"], row["role"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(Input):
    email: str
    password: str


class Registration(Credentials):
    role: str


class Contract(Input):
    owner: str
    vendor: str
    buyer: str
    effective_date: str
    service: str
    bank_reference: str
    amount: StrictInt


class PolicyForm(Input):
    document_id: str
    threshold: StrictInt
    include_service: StrictBool


@app.get("/")
@app.get("/verify")
@app.get("/share/{share_id}")
def home():
    return FileResponse(BASE / "web" / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ready"}


@app.get("/api/trust")
def trust():
    return app.state.trust


@app.post("/api/register", status_code=201)
def register(data: Registration, request: Request):
    rate("register:" + request.client.host, 8)
    email = data.email.lower()
    if not EMAIL.fullmatch(email) or not 12 <= len(data.password) <= 128 or data.role not in ("owner", "auditor"):
        raise HTTPException(400, "Use a valid email, a password of 12–128 characters and a supported role")
    try:
        with db() as con:
            con.execute("INSERT INTO users VALUES (?,?,?)", (email, generate_password_hash(data.password), data.role))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Account is unavailable") from None
    return {"registered": True}


@app.post("/api/session")
def login(data: Credentials, req: Request, response: Response):
    rate("login:" + req.client.host, 15)
    if len(data.password) > 128 or not EMAIL.fullmatch(data.email):
        raise HTTPException(401, "Invalid credentials")
    with db() as con:
        row = con.execute("SELECT * FROM users WHERE email=?", (data.email.lower(),)).fetchone()
        if not check_password_hash(row["password"] if row else "00" * 48, data.password) or not row:
            raise HTTPException(401, "Invalid credentials")
        token = token_hex(32)
        previous = sha256(req.cookies.get(SESSION, "").encode()).hexdigest()
        con.execute("DELETE FROM sessions WHERE token=? OR expires<=?", (previous, now()))
        con.execute("INSERT INTO sessions VALUES (?,?,?)",
                    (sha256(token.encode()).hexdigest(), row["email"], now() + 28800))
    response.set_cookie(SESSION, token, max_age=28800, httponly=True, samesite="strict", secure=SECURE)
    return {"email": row["email"], "role": row["role"]}


@app.post("/api/logout")
def logout(req: Request, response: Response):
    with db() as con:
        con.execute("DELETE FROM sessions WHERE token=?", (sha256(req.cookies.get(SESSION, "").encode()).hexdigest(),))
    response.delete_cookie(SESSION)
    return {"signed_out": True}


@app.get("/api/dashboard")
def dashboard(req: Request):
    email, role = account(req)
    with db() as con:
        docs = con.execute("SELECT * FROM documents WHERE owner=? ORDER BY rowid DESC LIMIT 100", (email,))
        docs = [{"id": row["id"], "vendor": load(row["record"])["values"]["vendor"]} for row in docs]
        requests = con.execute("""SELECT requests.* FROM requests JOIN documents ON documents.id=requests.document
            WHERE auditor=? OR owner=? ORDER BY requests.rowid DESC LIMIT 100""", (email, email))
        requests = [{"id": row["id"], "request": load(row["request"]), "shared": row["package"] is not None,
                     "consumed": row["consumed"], "revoked": row["revoked"], "auditor": row["auditor"]}
                    for row in requests]
        events = [dict(row) for row in con.execute("SELECT kind,ref,occurred FROM events WHERE actor=? ORDER BY id DESC LIMIT 20", (email,))]
    return {"email": email, "role": role, "documents": docs, "requests": requests, "events": events}


@app.post("/api/documents", status_code=201)
def create_document(data: Contract, req: Request):
    email, _ = account(req, "issuer")
    rate("issue:" + email, 12)
    values = data.model_dump(exclude={"owner"})
    record, original = issue(values, ISSUER, app.state.issuer)
    record["source"] = base64.b64encode(original).decode()
    doc_id = record["manifest"]["id"]
    with db() as con:
        owner = data.owner.lower()
        if not con.execute("SELECT 1 FROM users WHERE email=? AND role='owner'", (owner,)).fetchone():
            raise HTTPException(404, "No owner account with that email")
        con.execute("INSERT INTO documents VALUES (?,?,?)", (doc_id, owner, store(record)))
        audit(con, email, "Contract issued", doc_id)
        audit(con, owner, "Signed contract received", doc_id)
    return {"id": doc_id}


def owned_record(con, doc_id, email):
    row = con.execute("SELECT record FROM documents WHERE id=? AND owner=?", (doc_id, email)).fetchone()
    if not row:
        raise HTTPException(404, "Contract unavailable")
    return load(row["record"])


@app.get("/api/documents/{doc_id}/source.pdf")
def source(doc_id: str, req: Request):
    email, _ = account(req, "owner")
    with db() as con:
        record = owned_record(con, doc_id, email)
    return Response(base64.b64decode(record["source"]), media_type="application/pdf")


@app.post("/api/documents/{doc_id}/match")
async def match_source(doc_id: str, req: Request):
    email, _ = account(req, "owner")
    with db() as con:
        record = owned_record(con, doc_id, email)
    original = await req.body()
    if len(original) > 65536 or not original.startswith(b"%PDF-") or sha256(original).hexdigest() != record["manifest"]["source_sha256"]:
        raise HTTPException(400, "File does not match the signed PDF fingerprint")
    with db() as con:
        audit(con, email, "Source PDF matched", doc_id)
    return {"matched": True}


@app.post("/api/requests", status_code=201)
def create_request(data: PolicyForm, req: Request):
    email, _ = account(req, "auditor")
    rate("request:" + email, 15)
    result = request_for(data.document_id, ISSUER, data.threshold, email, data.include_service)
    request_id = result["context"]["nonce"]
    with db() as con:
        if not con.execute("SELECT 1 FROM documents WHERE id=?", (data.document_id,)).fetchone():
            raise HTTPException(404, "Unknown contract reference")
        con.execute("INSERT INTO requests(id,document,auditor,request) VALUES (?,?,?,?)",
                    (request_id, data.document_id, email, store(result)))
        audit(con, email, "Audit request created", request_id)
    return {"id": request_id, "request": result}


def owner_request(con, request_id, email):
    row = con.execute("""SELECT requests.* FROM requests JOIN documents ON document=documents.id
        WHERE requests.id=? AND owner=?""", (request_id, email)).fetchone()
    if not row:
        raise HTTPException(404, "Request unavailable")
    return row


def active(row):
    request = load(row["request"])
    if row["revoked"] or now() >= request["context"]["expires"]:
        raise HTTPException(410, "Request expired or was revoked")
    return request


@app.get("/api/requests/{request_id}/preview.pdf")
def preview(request_id: str, req: Request):
    email, _ = account(req, "owner")
    with db() as con:
        row = owner_request(con, request_id, email)
        request = active(row)
        record = owned_record(con, row["document"], email)
    return Response(render({k: record["values"][k] for k in request["policy"]["visible"]}, row["document"]),
                    media_type="application/pdf")


@app.post("/api/requests/{request_id}/publish")
def publish(request_id: str, req: Request):
    email, _ = account(req, "owner")
    rate("prove:" + email, 12)
    with db() as con:
        row = owner_request(con, request_id, email)
        request = active(row)
        if row["package"] is not None:
            return {"share": "/share/" + request_id}
        record = owned_record(con, row["document"], email)
    package = present(record, request)
    if not verify(package, request, app.state.trust)["valid"]:
        raise HTTPException(409, "Presentation failed its verification checks")
    with db() as con:
        active(owner_request(con, request_id, email))
        updated = con.execute("""UPDATE requests SET package=? WHERE id=?
            AND revoked IS NULL AND package IS NULL""", (store(package), request_id))
        if updated.rowcount:
            audit(con, email, "Disclosure shared", request_id)
        else:
            active(owner_request(con, request_id, email))
    return {"share": "/share/" + request_id}


@app.post("/api/requests/{request_id}/revoke")
def revoke(request_id: str, req: Request):
    email, _ = account(req, "owner")
    with db() as con:
        owner_request(con, request_id, email)
        updated = con.execute("UPDATE requests SET revoked=?,package=NULL WHERE id=? AND revoked IS NULL", (now(), request_id))
        if updated.rowcount:
            audit(con, email, "Shared access revoked", request_id)
    return {"revoked": True}


def auditor_row(con, request_id, email):
    row = con.execute("SELECT * FROM requests WHERE id=? AND auditor=?", (request_id, email)).fetchone()
    if not row:
        raise HTTPException(404, "Request unavailable")
    return row


@app.get("/api/requests/{request_id}/package")
def download(request_id: str, req: Request):
    email, _ = account(req, "auditor")
    with db() as con:
        row = auditor_row(con, request_id, email)
        active(row)
        if row["package"] is None:
            raise HTTPException(404, "Disclosure is not ready")
        return Response(canonical(load(row["package"])), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="disclosure.json"'})

@app.get("/api/requests/{request_id}/disclosure.pdf")
def disclosed_pdf(request_id: str, req: Request):
    email, _ = account(req, "auditor")
    with db() as con:
        row = auditor_row(con, request_id, email)
        active(row)
        if row["package"] is None:
            raise HTTPException(404, "Disclosure is not ready")
        return Response(base64.b64decode(load(row["package"])["pdf"]), media_type="application/pdf")



@app.post("/api/requests/{request_id}/verify")
def consume(request_id: str, req: Request):
    email, _ = account(req, "auditor")
    rate("consume:" + email, 20)
    with db() as con:
        row = auditor_row(con, request_id, email)
        expected = active(row)
        if row["consumed"]:
            raise HTTPException(409, "This audit request was already verified")
        if row["package"] is None:
            raise HTTPException(404, "Disclosure is not ready")
    report = verify(load(row["package"]), expected, app.state.trust)
    if report["valid"]:
        with db() as con:
            active(auditor_row(con, request_id, email))
            updated = con.execute("""UPDATE requests SET consumed=? WHERE id=? AND consumed IS NULL
                AND revoked IS NULL AND package IS NOT NULL""", (now(), request_id))
            if not updated.rowcount:
                raise HTTPException(409, "This audit request was consumed or revoked")
            audit(con, email, "Disclosure verified", request_id)
    return report


@app.post("/api/verify")
async def independent(req: Request):
    await run_in_threadpool(rate, "verify:" + req.client.host, 30)
    try:
        body = parse_json(await req.body())
        inputs = [parse_json(body[key]) for key in ("package", "request", "trust")]
        return await run_in_threadpool(verify, *inputs)
    except (ValueError, TypeError, KeyError, RecursionError):
        return {"valid": False, "checks": [{"check": "Input files", "passed": False}]}


@app.get("/api/benchmarks")
def benchmarks():
    return FileResponse(BASE / "benchmarks" / "summary.json", media_type="application/json")


if __name__ == "__main__":
    import argparse
    from getpass import getpass

    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    args = parser.parse_args()
    password = getpass("Issuer password: ")
    if not EMAIL.fullmatch(args.email) or not 12 <= len(password) <= 128:
        parser.error("Use a valid email and a password of 12–128 characters.")
    setup()
    with db() as con:
        con.execute("INSERT INTO users VALUES (?,?, 'issuer')", (args.email.lower(), generate_password_hash(password)))
