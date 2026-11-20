"""Local single-user PDF redaction studio. Run with Uvicorn on loopback."""
import base64
from collections import OrderedDict
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
import os
from secrets import token_hex
from threading import Lock
from time import monotonic
import zlib
from zipfile import ZIP_DEFLATED, ZipFile

import fitz
from PIL import Image
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

import adaptive_mask as planner
import adaptive_proof as adaptive
import credential_proof
import disclosure_bundle as bundle
import disclosure_compare
import field_detector
import forensic_review
import revision_test
import privacy_review
import field_equality
from exposure import ExposureHistory
import pdf_redaction as core
from protocol import canonical, parse_json, shape, valid_hex

BASE = Path(__file__).resolve().parent
WORKSPACES = OrderedDict()
LOCK = Lock()
MINUTES = 20


@asynccontextmanager
async def lifespan(app):
    home = Path(os.environ.get("LEGITZK_PDF_HOME", BASE / ".legitzk-pdf"))
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    keyfile = home / "ingestion.key"
    try:
        with os.fdopen(os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
            stream.write(Ed25519PrivateKey.generate().private_bytes_raw())
    except FileExistsError:
        pass
    app.state.key = Ed25519PrivateKey.from_private_bytes(keyfile.read_bytes())
    app.state.public = app.state.key.public_key().public_bytes_raw().hex()
    reviewer_key = os.environ.get("LEGITZK_PDF_TRUSTED_KEY", "").lower()
    if reviewer_key:
        valid_hex(reviewer_key, 32)
    app.state.trusted_keys = tuple(dict.fromkeys(filter(None, (app.state.public, reviewer_key))))
    app.state.exposure = ExposureHistory(home / "exposure.sqlite3", app.state.key.private_bytes_raw())
    yield
    with LOCK:
        WORKSPACES.clear()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
app.mount("/assets", StaticFiles(directory=BASE / "pdf_web"), name="pdf-assets")


@app.middleware("http")
async def guards(req, call_next):
    if req.method == "POST" and (req.headers.get("x-legitzk-action") != "1"
                                 or req.headers.get("sec-fetch-site") == "cross-site"):
        return JSONResponse({"detail": "Invalid request origin."}, 403)
    response = await call_next(req)
    response.headers.update({
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'self'; img-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        "Referrer-Policy": "no-referrer",
    })
    return response


async def read(req, limit):
    data = bytearray()
    async for chunk in req.stream():
        if len(data) + len(chunk) > limit:
            raise HTTPException(413, "The file or package is too large.")
        data.extend(chunk)
    return bytes(data)


def prune():
    now = monotonic()
    for item, (deadline, _, _) in list(WORKSPACES.items()):
        if deadline < now:
            del WORKSPACES[item]


def session(req):
    token = req.headers.get("x-legitzk-workspace")
    with LOCK:
        prune()
        if token not in WORKSPACES:
            raise HTTPException(404, "Workspace expired. Upload the original PDF again.")
        return WORKSPACES[token][1]


@app.exception_handler(ValueError)
@app.exception_handler(TypeError)
@app.exception_handler(KeyError)
@app.exception_handler(zlib.error)
@app.exception_handler(RecursionError)
async def invalid(req, err):
    return JSONResponse({"detail": str(err) if type(err) is ValueError and err.args
                         else "Invalid or malformed document evidence."}, 400)


@app.get("/")
def home():
    return FileResponse(BASE / "pdf_web" / "index.html")


@app.get("/api/key")
def public_key():
    return {"public_key": app.state.public}


@app.post("/api/upload")
async def upload(req: Request):
    original = await read(req, core.MAX_SOURCE)
    try:
        source = await run_in_threadpool(core.issue_source, original, app.state.key)
    except fitz.FileDataError as exc:
        raise HTTPException(400, "The source is unreadable as a PDF.") from exc
    return register(source)


def register(source):
    token = token_hex(32)
    with LOCK:
        prune()
        if len(WORKSPACES) >= 2:
            WORKSPACES.popitem(last=False)
        WORKSPACES[token] = (monotonic() + MINUTES * 60, source, {})
    return {"workspace": token, "receipt": source[0], "tile": core.TILE}


def adaptive_source(req):
    source = session(req)
    if source[0]["manifest"]["profile"] != adaptive.PROFILE:
        raise ValueError("Upload a source using the adaptive studio.")
    return source


@app.post("/api/v2/claims/verify")
async def verify_claims(req: Request):
    data = parse_json(await read(req, 6_000_000))
    shape(data, ("presentation", "policy", "trust"))
    valid = await run_in_threadpool(credential_proof.verify, data["presentation"], data["policy"], data["trust"])
    return {"valid": valid}


@app.post("/api/v2/claims/prove")
async def prove_claims(req: Request):
    data = parse_json(await read(req, 6_000_000))
    shape(data, ("records", "policy", "trust"))
    records = data["records"]
    if not isinstance(records, list) or not 1 <= len(records) <= credential_proof.MAX_CLAUSES:
        raise ValueError("Provide a holder record for each requested credential.")
    indexed = {record["credential"]["manifest"]["id"]: record for record in records}
    if len(indexed) != len(records):
        raise ValueError("Duplicate holder credential.")
    try:
        return await run_in_threadpool(credential_proof.prove, indexed, data["policy"], data["trust"])
    except InvalidSignature as exc:
        raise ValueError("A holder credential signature failed verification.") from exc


@app.post("/api/v2/upload")
async def upload_adaptive(req: Request):
    original = await read(req, core.MAX_SOURCE)
    try:
        def ingest():
            pages = core.render_source(original)
            lines = field_detector.native_lines(original, pages)
            return (*adaptive.issue(original, app.state.key, pages), lines)
        source = await run_in_threadpool(ingest)
    except fitz.FileDataError as exc:
        raise HTTPException(400, "The source is unreadable as a PDF.") from exc
    return register(source)


@app.post("/api/v2/detect")
async def detect(req: Request):
    source = adaptive_source(req)
    data = parse_json(await read(req, 32_000))
    has_profile = isinstance(data, dict) and "financial" in data
    shape(data, ("custom", "ocr", "financial") if has_profile else ("custom", "ocr"))
    financial = data.get("financial", False)
    if type(data["ocr"]) is not bool or type(financial) is not bool:
        raise ValueError("OCR and financial settings must be true or false.")
    return await run_in_threadpool(field_detector.find, source[-1], source[1], data["custom"], data["ocr"],
                                   financial=financial)


@app.post("/api/v2/request")
async def request_adaptive(req: Request):
    source = adaptive_source(req)
    receipt = source[0]
    data = parse_json(await read(req, 256_000))
    if isinstance(data, dict) and "max_percent" in data:
        shape(data, ("audience", "max_percent", "hide", "keep", "tile_limit"))
        budget, limit = data["max_percent"], data["tile_limit"]
    else:
        shape(data, ("audience", "hide", "keep"))
        budget, limit = 100, planner.MAX_CUT
    request = await run_in_threadpool(adaptive.request, receipt, data["audience"], budget,
                                      data["hide"], data["keep"], limit)
    cut, metrics = await run_in_threadpool(adaptive.plan, request, receipt["manifest"])
    masked = [planner.rectangle(node, receipt["manifest"]["pages"]) for node, hidden in cut if hidden]
    groups = await run_in_threadpool(privacy_review.protected_groups, source[-1], masked)
    exposure = await run_in_threadpool(app.state.exposure.evaluate, receipt["manifest"], request, masked, groups=groups)
    inference = await run_in_threadpool(privacy_review.plan_review, source[-1], masked)
    return {"request": request, "metrics": metrics, "masked": masked, "exposure": exposure, "inference": inference}


@app.post("/api/v2/prove")
async def prove_adaptive(req: Request):
    source = adaptive_source(req)
    data = parse_json(await read(req, 256_000))
    shape(data, ("request",))
    package, pdf, metrics = await run_in_threadpool(adaptive.prove, source[:-1], data["request"])
    return {"proof_package": package, "pdf_base64": base64.b64encode(pdf).decode(), "metrics": metrics}


@app.post("/api/v2/export")
async def export_adaptive(req: Request):
    source = adaptive_source(req)
    data = parse_json(await read(req, 256_000))
    if not isinstance(data, dict) or "request" not in data or data.keys() - {"request", "record_exposure", "scan_export", "provable_fields"}:
        raise ValueError("Invalid export request.")
    record = data.get("record_exposure", False)
    scan = data.get("scan_export", False)
    if type(record) is not bool or type(scan) is not bool:
        raise ValueError("Export options must be true or false.")

    def export():
        request = data["request"]
        package, pdf, metrics = adaptive.prove(source[:-1], request)
        audit = core.audit_export(pdf)
        manifest = source[0]["manifest"]
        if scan or record:
            cut, _ = adaptive.plan(request, manifest)
            masked = [planner.rectangle(node, manifest["pages"]) for node, hidden in cut if hidden]
        leak_report = privacy_review.leak_scan(pdf, source[-1], masked, source[1]) if scan else None
        if leak_report and leak_report["status"] == "findings":
            return {"leak_scan": leak_report}
        fields, witnesses = field_equality.issue(
            data.get("provable_fields", []), source[0], request, package["pdf_sha256"], app.state.key)
        archive = bundle.pack(package, pdf, app.state.key, app.state.public, fields)
        if witnesses:
            with LOCK:
                prune()
                entry = WORKSPACES.get(req.headers.get("x-legitzk-workspace"))
                if entry is None or entry[1] is not source:
                    raise ValueError("The owner workspace expired during export.")
                if len(entry[2]) + len(witnesses) > 256:
                    raise ValueError("This workspace has reached its private field limit.")
                entry[2].update(witnesses)
        response = {"zip_base64": base64.b64encode(archive).decode(),
                    "pdf_base64": base64.b64encode(pdf).decode(), "metrics": metrics, "sanitization": audit,
                    "leak_scan": leak_report}
        if record:
            response["exposure"] = app.state.exposure.evaluate(
                manifest, request, masked, record=True, groups=privacy_review.protected_groups(source[-1], masked))
        return response

    return await run_in_threadpool(export)


def receipt_signer(expected, trusted_keys):
    shape(expected, ("manifest", "signature"))
    manifest = expected["manifest"]
    shape(manifest, ("profile", "id", "source_sha256", "pages", "merkle_root"))
    if manifest["profile"] != adaptive.PROFILE:
        raise ValueError("Use a source receipt from the adaptive Studio.")
    signature = valid_hex(expected["signature"], 64)
    message = core.framed(adaptive.RECEIPT, manifest)
    for key in trusted_keys:
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(key)).verify(signature, message)
        except InvalidSignature:
            continue
        return key
    raise ValueError("The expected source receipt signature could not be verified with this Studio’s trusted keys.")


def source_match(expected, submitted, trusted_keys):
    receipt_signer(expected, trusted_keys)
    original = expected["manifest"]
    disclosed = submitted["manifest"]
    keys = ("source_sha256", "profile", "pages")
    return "match" if all(original[key] == disclosed[key] for key in keys) else "mismatch"


@app.post("/api/v2/forensics/edit-preview")
async def edit_preview(req: Request):
    raw = await read(req, core.MAX_SOURCE)
    page = req.headers.get("x-legitzk-page", "")
    if page not in tuple(str(i) for i in range(1, core.MAX_PAGES + 1)):
        raise ValueError("Choose an existing page.")
    try:
        preview = await run_in_threadpool(revision_test.page_preview, raw, int(page))
    except fitz.FileDataError as exc:
        raise ValueError("The source is unreadable as a PDF.") from exc
    return Response(preview, media_type="image/png")


@app.post("/api/v2/forensics/edit-copy")
async def edit_copy(req: Request):
    encoded = req.headers.get("x-legitzk-edit", "")
    if not 0 < len(encoded) <= 4096:
        raise ValueError("Supply a valid edit request.")
    edit = parse_json(base64.b64decode(encoded, validate=True))
    shape(edit, ("page", "old", "replacement", "box"))
    raw = await read(req, core.MAX_SOURCE)
    try:
        revised = await run_in_threadpool(revision_test.edit_pdf, raw, edit["page"], edit["old"],
                                          edit["replacement"], edit["box"])
    except fitz.FileDataError as exc:
        raise ValueError("The source is unreadable as a PDF.") from exc
    return Response(revised, media_type="application/pdf")


@app.post("/api/v2/forensics/field-example")
async def field_example(req: Request):
    shape(parse_json(await read(req, 1024)), ())

    def build():
        fixed = [("Account reference", "TEST-001")]
        baseline = forensic_review.sample_statement(fixed + [
            ("Debit amount", "150.00"), ("Credit amount", "420.00"), ("Closing balance", "1270.00"),
        ])
        candidate = forensic_review.sample_statement(fixed + [
            ("Debit amount", "170.00"), ("Credit amount", "460.00"), ("Closing balance", "1290.00"),
        ])
        source = adaptive.issue(baseline, app.state.key)
        receipt = source[0]
        signer = receipt_signer(receipt, app.state.trusted_keys)
        report = forensic_review.investigate(baseline, candidate, receipt, signer, include_values=True)
        manifest = receipt["manifest"]
        # This rectangle covers the account-reference line in the built-in synthetic fixture.
        policy = adaptive.request(receipt, "Classroom reviewer", 100, [[0, 44, 116, 230, 140]], [])
        package, original_redacted, _ = adaptive.prove(source, policy)
        cut, _ = adaptive.plan(policy, manifest)
        sites, hidden = adaptive.geometry(cut, manifest["pages"])
        candidate_redacted = core.render_export(core.redact(core.render_source(candidate), sites, hidden))
        proof_zip = bundle.pack(package, original_redacted, app.state.key, app.state.public)
        archive = BytesIO()
        with ZipFile(archive, "w", ZIP_DEFLATED) as files:
            files.writestr("synthetic-baseline.pdf", baseline)
            files.writestr("synthetic-modified.pdf", candidate)
            files.writestr("source-receipt.json", canonical(receipt))
            files.writestr("synthetic-baseline-redacted.pdf", original_redacted)
            files.writestr("synthetic-modified-redacted.pdf", candidate_redacted)
            files.writestr("legitzk-proof.zip", proof_zip)
        return {"investigation": report, "zip_base64": base64.b64encode(archive.getvalue()).decode()}

    return await run_in_threadpool(build)


@app.post("/api/v2/forensics/compare")
async def compare_sources(req: Request):
    size_text = req.headers.get("x-legitzk-baseline-length", "")
    encoded = req.headers.get("x-legitzk-expected-receipt", "")
    values = req.headers.get("x-legitzk-include-values", "0")
    if not size_text.isascii() or not size_text.isdecimal() or len(size_text) > 8:
        raise ValueError("Supply a baseline PDF.")
    size = int(size_text)
    if not 0 < size <= core.MAX_SOURCE or not 0 < len(encoded) <= 4096 or values not in ("0", "1"):
        raise ValueError("Invalid baseline size, receipt or comparison option.")
    raw = await read(req, size + core.MAX_SOURCE)
    if len(raw) <= size:
        raise ValueError("Supply a candidate PDF.")
    receipt = parse_json(base64.b64decode(encoded, validate=True))
    signer = receipt_signer(receipt, app.state.trusted_keys)
    try:
        return await run_in_threadpool(forensic_review.investigate, raw[:size], raw[size:], receipt,
                                       signer, values == "1")
    except (fitz.FileDataError, RuntimeError) as exc:
        raise ValueError("A PDF could not be inspected.") from exc


def inspect_bundle(raw, pdf, demo, expected=None, ocr=False):
    evidence, files, trusted_key = bundle.unpack(raw, pdf, app.state.trusted_keys)
    result = {"schema": "legitzk/inspection-report/v1", "valid": False, "files": files,
              "inputs": {"pdf_sha256": bundle.digest(pdf), "proof_zip_sha256": bundle.digest(raw)}}
    if evidence is None:
        return result
    package, receipt, request = (evidence[key] for key in ("package", "receipt", "request"))
    if receipt["manifest"]["profile"] != adaptive.PROFILE:
        raise ValueError("Unsupported proof ZIP profile.")
    try:
        reference = pdf
        if files[bundle.PDF] != "match":
            pages = core.read_pages(package["pages"], receipt["manifest"]["pages"])
            reference = core.render_export(pages)
        verified = adaptive.verify(package, receipt, request, trusted_key, reference)
    except ValueError as exc:
        result["verification_error"] = str(exc)
        return result
    if expected is not None:
        result["source_match"] = source_match(expected, receipt, app.state.trusted_keys)
    if demo:
        if files[bundle.PDF] != "match":
            raise ValueError("Start with a verified redacted PDF to run the demo.")
        candidate = disclosure_compare.metadata_demo(reference) if demo == "metadata" else disclosure_compare.demo_pdf(reference)
        result["candidate_pdf"] = base64.b64encode(candidate).decode()
        result["files"][bundle.PDF] = "changed" if bundle.digest(candidate) != bundle.digest(reference) else "match"
        pdf = candidate
    if result["files"][bundle.PDF] != "match":
        try:
            result["comparison"] = disclosure_compare.compare(reference, pdf, request, receipt)
            if ocr and not demo:
                result["ocr_fields"] = forensic_review.compare_ocr(reference, pdf, result["comparison"])
        except (fitz.FileDataError, ValueError, RuntimeError):
            result["comparison"] = {"status": "unreadable", "changes": []}
        return result
    if "fields" in evidence:
        fields = evidence["fields"]
        if not isinstance(fields, list) or len(fields) > field_equality.MAX_FIELDS:
            raise ValueError("Invalid signed field inventory.")
        receipt_hash = bundle.digest(canonical(receipt))
        for record in fields:
            field = field_equality.check_record(record, trusted_key)
            if (field["receipt_sha256"] != receipt_hash or field["pdf_sha256"] != result["inputs"]["pdf_sha256"]
                    or field["region"] not in request["hide"]):
                raise ValueError("A field record belongs to a different disclosure.")
        result["provable_fields"] = fields
        result["field_issuer"] = trusted_key
    return {**verified, **result, "proof_valid": True, "valid": result.get("source_match") != "mismatch"}


@app.post("/api/v2/inspect")
async def inspect(req: Request):
    length = req.headers.get("x-legitzk-zip-length", "")
    demo = req.headers.get("x-legitzk-demo", "")
    if not length.isascii() or not length.isdecimal() or len(length) > 8 or demo not in ("", "metadata", "visual"):
        raise ValueError("Invalid proof ZIP upload.")
    size = int(length)
    if not 0 < size <= bundle.MAX_ZIP:
        raise ValueError("The proof ZIP is too large or empty.")
    raw = await read(req, size + bundle.MAX_PDF)
    if len(raw) <= size:
        raise ValueError("Select a redacted PDF and its proof ZIP.")
    encoded_receipt = req.headers.get("x-legitzk-expected-receipt", "")
    if len(encoded_receipt) > 4096:
        raise ValueError("Expected source receipt is too large.")
    expected = parse_json(base64.b64decode(encoded_receipt, validate=True)) if encoded_receipt else None
    if encoded_receipt and not isinstance(expected, dict):
        raise ValueError("Expected source receipt must be a JSON object.")
    ocr = req.headers.get("x-legitzk-ocr-forensics", "0")
    if ocr not in ("0", "1"):
        raise ValueError("Invalid forensic OCR option.")
    return await run_in_threadpool(inspect_bundle, raw[:size], raw[size:], demo, expected, ocr == "1")


@app.post("/api/v2/field-equality/request")
async def request_field_equality(req: Request):
    data = parse_json(await read(req, 16_384))
    shape(data, ("record", "candidate", "issuer"))
    if data["issuer"] not in app.state.trusted_keys:
        raise ValueError("The field issuer is not trusted.")
    field = field_equality.check_record(data["record"], data["issuer"])
    request = {"field_id": field["id"], "record_sha256": bundle.digest(canonical(data["record"])),
               "nonce": token_hex(32), "candidate": data["candidate"]}
    field_equality.check_request(request, data["record"])
    return request


@app.post("/api/v2/field-equality/prove")
async def prove_field_equality(req: Request):
    data = parse_json(await read(req, 16_384))
    shape(data, ("request", "approved"))
    if data["approved"] is not True:
        raise ValueError("Approve this exact candidate before generating a proof.")
    request = data["request"]
    shape(request, ("field_id", "record_sha256", "nonce", "candidate"))
    valid_hex(request["field_id"], 16)
    with LOCK:
        prune()
        entry = WORKSPACES.get(req.headers.get("x-legitzk-workspace"))
        witness = entry[2].get(request["field_id"]) if entry else None
    if witness is None:
        raise ValueError("The private field is unavailable. Keep the original export workspace open.")
    proof = await run_in_threadpool(field_equality.prove, witness, request)
    return {"proof": proof}


@app.post("/api/v2/field-equality/verify")
async def verify_field_equality(req: Request):
    data = parse_json(await read(req, 16_384))
    shape(data, ("record", "request", "proof", "issuer"))
    if data["issuer"] not in app.state.trusted_keys:
        raise ValueError("The field issuer is not trusted.")
    field_equality.check_record(data["record"], data["issuer"])
    valid = await run_in_threadpool(
        field_equality.verify, data["record"], data["request"], data["proof"])
    return {"valid": valid}


@app.post("/api/close")
def close(req: Request):
    with LOCK:
        WORKSPACES.pop(req.headers.get("x-legitzk-workspace"), None)
    return {"closed": True}


@app.get("/api/page/{index}")
def page(index: int, req: Request):
    pages = session(req)[1]
    if not 0 <= index < len(pages):
        raise HTTPException(404, "Page not found.")
    w, h, bitmap = pages[index]
    buffer = BytesIO()
    Image.frombytes("RGB", (w, h), bitmap).save(buffer, format="PNG")
    return Response(buffer.getvalue(), media_type="image/png")


@app.post("/api/request")
async def request_policy(req: Request):
    receipt = session(req)[0]
    data = parse_json(await read(req, 256_000))
    shape(data, ("max_percent", "protected", "audience"))
    return core.new_request(receipt, data["max_percent"], data["protected"], data["audience"])


@app.post("/api/prove")
async def prove(req: Request):
    source = session(req)
    data = parse_json(await read(req, 512_000))
    shape(data, ("request", "mask"))
    package, pdf = await run_in_threadpool(core.present, source, data["request"], data["mask"])
    return {"proof_package": package, "pdf_base64": base64.b64encode(pdf).decode()}


def check_disclosure(data):
    shape(data, ("package", "receipt", "request", "key", "pdf"))
    shape(data["key"], ("public_key",))
    pdf = base64.b64decode(data["pdf"], validate=True)
    verifier = adaptive.verify if data["receipt"]["manifest"]["profile"] == adaptive.PROFILE else core.verify
    return pdf, verifier(data["package"], data["receipt"], data["request"], data["key"]["public_key"], pdf)


@app.post("/api/verify")
async def verify(req: Request):
    data = parse_json(await read(req, 76_000_000))
    _, result = await run_in_threadpool(check_disclosure, data)
    return result


def compare_disclosure(data):
    shape(data, ("reference", "candidate", "demo"))
    if type(data["demo"]) is not bool:
        raise ValueError("Invalid demo setting.")
    verified, _ = check_disclosure(data["reference"])
    if data["demo"]:
        if data["candidate"] is not None:
            raise ValueError("Choose either a demo edit or a candidate PDF.")
        candidate = disclosure_compare.demo_pdf(verified)
    else:
        candidate = base64.b64decode(data["candidate"], validate=True)
    ref = data["reference"]
    result = disclosure_compare.compare(verified, candidate, ref["request"], ref["receipt"])
    if data["demo"]:
        result["candidate_pdf"] = base64.b64encode(candidate).decode()
    return result


@app.post("/api/compare")
async def compare(req: Request):
    data = parse_json(await read(req, 100_000_000))
    try:
        return await run_in_threadpool(compare_disclosure, data)
    except fitz.FileDataError as exc:
        raise HTTPException(400, "The candidate is unreadable as a PDF.") from exc
