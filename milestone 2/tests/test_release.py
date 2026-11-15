"""Focused release regression tests. Run `python -m pytest -q tests` from release root.

These tests exercise the actual FastAPI API with a temporary local SQLite database.
They do not email OTPs or access a browser microphone; validate those separately.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
sys.path.insert(0, str(APP))
os.environ.setdefault("JWT_SECRET", "regression-unique-test-key-0123456789-abcdefghijklmnopqrstuvwxyz")
os.environ.setdefault("ADMIN_PASSWORD", "ReleaseTest#2026")
os.environ.setdefault("ADMIN_EMAIL", "admin-regression@example.test")
os.environ.setdefault("APP_DATA_DIR", tempfile.mkdtemp(prefix="freightquote-release-tests-"))
os.environ["NO_WORKER"] = "1"
os.environ["APP_KIND"] = "Freight"

from server import app  # noqa: E402
from db import get_conn  # noqa: E402
import auth_service  # noqa: E402

PASSWORD = os.environ["ADMIN_PASSWORD"]

@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def login(client, identity, password, role):
    return client.post("/api/auth/login", json={"identity": identity, "password": password, "role": role})


def make_user(username, role="Customer"):
    # Provision through the supported admin workflow, without requiring real SMTP.
    success, info = auth_service.admin_create_user(
        "admin", username, f"{username}@example.test", "Customer#2026", role,
    )
    assert success, info
    with get_conn() as conn:
        conn.execute("UPDATE users SET security_answer_hash=?, email_verified=1 WHERE username=?",
                     (auth_service.hashed("sunrise"), username))
    return username


def test_health_and_original_freight_pages(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/static/landing_exact.html").status_code == 200
    admin = login(client, "admin", PASSWORD, "Admin")
    assert admin.status_code == 200, admin.text
    headers = {"Authorization": "Bearer " + admin.json()["token"]}
    for page in ("admin", "profile", "copilot", "route", "quotes", "carriers", "weather", "margin", "customs"):
        response = client.get(f"/api/page/{page}", headers=headers)
        assert response.status_code == 200, (page, response.text[:300])
    route_page = client.get("/api/page/route", headers=headers).json()
    assert "could not be calculated" not in str(route_page).lower()


def test_role_selector_is_not_privilege_escalation(client):
    make_user("roleregression")
    wrong = login(client, "roleregression", "Customer#2026", "Admin")
    assert wrong.status_code == 401
    assert "does not match" in wrong.json()["msg"].lower()
    assert "token" not in wrong.json()
    correct = login(client, "roleregression", "Customer#2026", "Customer")
    assert correct.status_code == 200
    headers = {"Authorization": "Bearer " + correct.json()["token"]}
    assert client.get("/api/page/admin", headers=headers).status_code == 403
    assert client.get("/api/page/copilot", headers=headers).status_code == 200
    assert client.post("/api/auth/unblock", json={"identity": "admin"}, headers=headers).status_code == 403


def test_five_attempt_account_lockout_and_question_visibility(client):
    user = make_user("lockregression")
    for attempt in range(1, 6):
        resp = login(client, user, "incorrect-password", "Customer")
        assert resp.status_code == (401 if attempt < 5 else 423), (attempt, resp.text)
        if attempt < 5:
            assert "invalid" in resp.json()["msg"].lower()
        else:
            assert "account locked" in resp.json()["msg"].lower()
    locked = login(client, user, "Customer#2026", "Customer")
    assert locked.status_code == 423
    assert "account locked" in locked.json()["msg"].lower()
    q = client.post("/api/auth/forgot/question", json={"identity": user})
    assert q.status_code == 200, q.text
    assert q.json()["question"] == auth_service.QUESTIONS[0]
    assert q.json()["locked"] is True
    assert "account locked" in q.json()["msg"].lower()
    verify = client.post("/api/auth/forgot/verify_answer", json={"identity": user, "answer": "Sunrise"})
    assert verify.status_code == 400
    assert "account locked" in verify.json()["msg"].lower()
    a = login(client, "admin", PASSWORD, "Admin")
    headers = {"Authorization": "Bearer " + a.json()["token"]}
    unlock = client.post("/api/auth/unblock", json={"identity": user}, headers=headers)
    assert unlock.status_code == 200, unlock.text
    q2 = client.post("/api/auth/forgot/question", json={"identity": user})
    assert q2.status_code == 200 and q2.json()["locked"] is False
    assert login(client, user, "Customer#2026", "Customer").status_code == 200


def test_copilot_sql_and_browser_voice_controls(client):
    r = login(client, "admin", PASSWORD, "Admin")
    headers = {"Authorization": "Bearer " + r.json()["token"]}
    resp = client.post("/api/copilot", json={"q": "How many shipments are on customs hold?"}, headers=headers)
    assert resp.status_code == 200
    assert "event-stream" in resp.headers["content-type"]
    assert '"ev": "final"' in resp.text or '"ev":"final"' in resp.text
    js = client.get("/static/app.js").text
    assert 'SpeechRecognition' in js and 'speechSynthesis' in js
    assert '"Assigned Role"' in js
    assert '"Show security question"' in js
