import os

os.environ.setdefault("YTFLOW_ADMIN_USERNAME", "ci-admin")
os.environ.setdefault("YTFLOW_ADMIN_PASSWORD", "ci-test-password-which-is-long-enough")
os.environ.setdefault("YTFLOW_SECRET_KEY", "ci-signing-secret-which-is-longer-than-32-characters")
# TestClient uses HTTP; production Docker forces Secure cookies behind Caddy/HTTPS.
os.environ["YTFLOW_COOKIE_SECURE"] = "false"

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def login():
    return client.post("/api/auth/login", json={
        "username": os.environ["YTFLOW_ADMIN_USERNAME"],
        "password": os.environ["YTFLOW_ADMIN_PASSWORD"],
    })


def test_api_is_protected_before_login():
    client.post("/api/auth/logout")  # clear any cookie left by an earlier test
    assert client.get("/api/downloads").status_code == 401
    assert client.get("/api/files").status_code == 401


def test_login_sets_http_only_session_cookie():
    response = login()
    assert response.status_code == 200
    assert response.json()["csrf_token"]
    cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert client.get("/api/auth/status").json()["authenticated"] is True


def test_mutating_api_requires_csrf_token():
    login()
    response = client.post("/api/downloads", json={})
    assert response.status_code == 403
    status = client.get("/api/auth/status").json()
    allowed = client.post("/api/auth/logout", headers={"X-CSRF-Token": status["csrf_token"]})
    assert allowed.status_code == 200
    assert client.get("/api/auth/status").json()["authenticated"] is False


def test_login_rejects_wrong_password():
    response = client.post("/api/auth/login", json={
        "username": os.environ["YTFLOW_ADMIN_USERNAME"],
        "password": "incorrect-password",
    })
    assert response.status_code == 401
