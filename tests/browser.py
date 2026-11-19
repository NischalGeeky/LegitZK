"""Chromium end-to-end workflow. Run from repository root with PYTHONPATH=."""
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import sleep
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

PASSWORD = "synthetic-demo-password"
REGISTER = ["owner@example.test", "auditor@example.test"]


def seed(folder):
    code = """
import app
app.setup()
with app.db() as connection:
    connection.execute("INSERT INTO users VALUES (?,?,?)",
      ("issuer@example.test", app.generate_password_hash("synthetic-demo-password"), "issuer"))
"""
    env = {**os.environ, "LEGITZK_DATA": folder, "LEGITZK_HTTPS": "0"}
    subprocess.run([sys.executable, "-c", code], env=env, check=True)
    return env


def sign_in(page, email):
    form = page.locator("#signin")
    form.get_by_label("Email").fill(email)
    form.get_by_label("Password").fill(PASSWORD)
    form.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("heading", name="Contract assurance")).to_be_visible()


def sign_out(page):
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()


def upload_json(page, label, value):
    page.get_by_label(label).set_input_files({
        "name": "sample.json", "mimeType": "application/json", "buffer": json.dumps(value).encode()})


def exercise(browser, origin, folder):
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    page.goto(origin)
    expect(page.get_by_role("heading", name="Measured proof performance")).to_be_visible()
    expect(page.get_by_text("Median proving")).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.keyboard.press("Tab")
    expect(page.get_by_role("link", name="LegitZK")).to_be_focused()
    page.get_by_role("button", name="Dark mode").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.set_viewport_size({"width": 1350, "height": 850})
    for email, role in zip(REGISTER, ("owner", "auditor")):
        form = page.locator("#register")
        form.get_by_label("Email").fill(email)
        form.get_by_label("Password").fill(PASSWORD)
        form.get_by_label("Role").select_option(role)
        form.get_by_role("button", name="Create account").click()
        expect(page.get_by_role("status")).to_have_text("Account created. Sign in to continue.")
    sign_in(page, "issuer@example.test")
    contract = json.loads(Path("fixtures/contract.json").read_bytes())
    for key, value in contract.items():
        page.locator(f'#issue [name="{key}"]').fill(str(value))
    page.locator('#issue [name="owner"]').fill(REGISTER[0])
    page.get_by_role("button", name="Sign and issue").click()
    expect(page.get_by_role("status")).to_contain_text("Signed contract issued")
    doc = re.search(r"[0-9a-f]{32}$", page.get_by_role("status").inner_text()).group()
    sign_out(page)
    sign_in(page, REGISTER[1])
    page.get_by_label("Document reference").fill(doc)
    page.get_by_label("Minimum contract amount").fill("7000000")
    page.get_by_role("button", name="Create request").click()
    expect(page.get_by_role("status")).to_have_text("Audit request created.")
    with page.expect_download() as downloaded:
        page.get_by_role("button", name="Export request").click()
    expected = json.loads(downloaded.value.path().read_bytes())
    sign_out(page)
    sign_in(page, REGISTER[0])
    source_path = f"/api/documents/{doc}/source.pdf"
    pdf_data = bytes(page.evaluate("""async (path) => {
        const response = await fetch(path, {credentials: "same-origin"});
        if (!response.ok) {
            throw new Error(`Source PDF download failed (HTTP ${response.status}): ${await response.text()}`);
        }
        return Array.from(new Uint8Array(await response.arrayBuffer()));
    }""", source_path))
    assert pdf_data.startswith(b"%PDF-"), "The source endpoint did not return a PDF"
    source_file = Path(folder) / "source.pdf"
    source_file.write_bytes(pdf_data)
    page.get_by_label("Match a downloaded source PDF").set_input_files(source_file)
    page.get_by_role("button", name="Check signed fingerprint").click()
    expect(page.get_by_role("status")).to_contain_text("matches the signed source fingerprint")
    page.get_by_text("Open redaction studio").click()
    expect(page.locator('iframe[title="Disclosure PDF preview"]')).to_be_visible()
    page.get_by_role("button", name="Generate proof and share").click()
    expect(page.get_by_role("status")).to_contain_text("Disclosure shared")
    sign_out(page)
    sign_in(page, REGISTER[1])
    page.get_by_role("link", name="Open evidence").click()
    page.get_by_role("button", name="Verify disclosure").click()
    expect(page.get_by_role("heading", name="Disclosure verified")).to_be_visible()
    with page.expect_download() as downloaded:
        page.get_by_role("link", name="Download package").click()
    package = json.loads(downloaded.value.path().read_bytes())
    trust = page.request.get(origin + "/api/trust").json()
    page.get_by_role("link", name="Verify a package").click()
    upload_json(page, "Disclosure package", package)
    upload_json(page, "Expected audit request", expected)
    upload_json(page, "Trusted issuer keys", trust)
    page.get_by_role("button", name="Verify package").click()
    expect(page.get_by_role("heading", name="Disclosure verified")).to_be_visible()
    package["signature"] = "00" * 64
    upload_json(page, "Disclosure package", package)
    page.get_by_role("button", name="Verify package").click()
    expect(page.get_by_role("heading", name="Verification failed")).to_be_visible()
    assert not errors, errors


def run():
    with TemporaryDirectory() as folder:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        app = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--port", str(port),
                                "--no-access-log"], env=seed(folder))
        try:
            for _ in range(40):
                try:
                    with urlopen(origin, timeout=1):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Application stopped during startup")
                    sleep(0.25)
            else:
                raise RuntimeError("Application did not start")
            with sync_playwright() as playwright:
                executable = os.getenv("CHROMIUM_PATH") or shutil.which("chromium")
                browser = playwright.chromium.launch(executable_path=executable)
                exercise(browser, origin, folder)
                browser.close()
        finally:
            app.terminate()
            app.wait(10)
    print("Chromium workflow passed, including independent verification and signature rejection.")


if __name__ == "__main__":
    run()
