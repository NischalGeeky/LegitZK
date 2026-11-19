from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as service
from protocol import canonical, parse_json

ACTION = {"X-LegitZK-Action": "1"}
PASSWORD = "synthetic-test-password"


class ApiTests(TestCase):
    def test_role_workflow_and_replay(self):
        with TemporaryDirectory() as temp, patch.object(service, "DATA", Path(temp)), TestClient(service.app) as c:
            def login(email):
                self.assertEqual(c.post("/api/session", headers=ACTION,
                                        json={"email": email, "password": PASSWORD}).status_code, 200)

            def register(email, role):
                self.assertEqual(c.post("/api/register", headers=ACTION,
                                        json={"email": email, "password": PASSWORD, "role": role}).status_code, 201)

            self.assertEqual(c.post("/api/register", json={}).status_code, 403)
            self.assertEqual(c.post("/api/register", headers=ACTION, content=b"x" * 200000).status_code, 413)
            self.assertEqual(c.post("/api/register", headers=ACTION, json={}).status_code, 422)
            with service.db() as con:
                con.execute("INSERT INTO users VALUES (?,?,?)",
                            ("issuer@example.test", service.generate_password_hash(PASSWORD), "issuer"))
            register("owner@example.test", "owner")
            register("auditor@example.test", "auditor")
            register("other@example.test", "auditor")
            contract = parse_json(Path("fixtures/contract.json").read_bytes())
            contract["owner"] = "owner@example.test"
            login("owner@example.test")
            self.assertEqual(c.post("/api/documents", json=contract, headers=ACTION).status_code, 403)
            login("issuer@example.test")
            issued = c.post("/api/documents", json=contract, headers=ACTION)
            self.assertEqual(issued.status_code, 201)
            doc = issued.json()["id"]
            root = "/api/documents/" + doc
            login("auditor@example.test")
            self.assertEqual(c.get(root + "/source.pdf").status_code, 403)
            request = c.post("/api/requests", json={
                "document_id": doc, "threshold": 7000000, "include_service": False}, headers=ACTION)
            self.assertEqual(request.status_code, 201)
            r = request.json()
            path = "/api/requests/" + r["id"]
            login("owner@example.test")
            source = c.get(root + "/source.pdf")
            self.assertEqual(source.status_code, 200)
            self.assertEqual(c.post(root + "/match", content=source.content, headers=ACTION).status_code, 200)
            self.assertEqual(c.post(root + "/match", content=source.content + b"extra", headers=ACTION).status_code, 400)
            self.assertEqual(c.get(path + "/preview.pdf").status_code, 200)
            self.assertEqual(c.post(path + "/publish", json={}, headers=ACTION).status_code, 200)
            self.assertEqual(c.post(path + "/publish", json={}, headers=ACTION).status_code, 200)
            login("other@example.test")
            self.assertEqual(c.get(path + "/package").status_code, 404)
            login("auditor@example.test")
            package = c.get(path + "/package").json()
            trust = c.get("/api/trust").json()
            self.assertTrue(c.post(path + "/verify", json={}, headers=ACTION).json()["valid"])
            self.assertEqual(c.post(path + "/verify", json={}, headers=ACTION).status_code, 409)
            self.assertEqual(c.get(path + "/disclosure.pdf").status_code, 200)
            self.assertEqual(c.post("/api/logout", json={}, headers=ACTION).status_code, 200)
            self.assertEqual(c.get(path + "/package").status_code, 401)
            independent = {k: canonical(v).decode() for k, v in
                           {"package": package, "request": r["request"], "trust": trust}.items()}
            self.assertTrue(c.post("/api/verify", json=independent, headers=ACTION).json()["valid"])
            login("owner@example.test")
            self.assertEqual(c.post(path + "/revoke", json={}, headers=ACTION).status_code, 200)
            login("auditor@example.test")
            self.assertEqual(c.get(path + "/package").status_code, 410)
