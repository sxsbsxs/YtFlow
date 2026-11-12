import time

from app.security import AuthConfig, SessionAuth


def make_auth(ttl=3600):
    return SessionAuth(AuthConfig(
        admin_username="owner",
        admin_password="a-very-long-test-password",
        secret_key="test-secret-key-that-is-at-least-32-chars",
        session_ttl_seconds=ttl,
        cookie_secure=True,
    ))


def test_credentials_are_verified():
    auth = make_auth()
    assert auth.verify_credentials("owner", "a-very-long-test-password")
    assert not auth.verify_credentials("other", "a-very-long-test-password")
    assert not auth.verify_credentials("owner", "wrong-password")


def test_signed_session_round_trip():
    auth = make_auth()
    token, csrf = auth.issue(now=1000)
    session = auth.read(token, now=1001)
    assert session is not None
    assert session["sub"] == "owner"
    assert session["csrf"] == csrf


def test_session_expires():
    auth = make_auth(ttl=300)
    token, _ = auth.issue(now=1000)
    assert auth.read(token, now=1299) is not None
    assert auth.read(token, now=1300) is None


def test_tampered_session_is_rejected():
    auth = make_auth()
    token, _ = auth.issue(now=1000)
    encoded, signature = token.split(".", 1)
    bad = encoded + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
    assert auth.read(bad, now=1001) is None


def test_session_is_bound_to_configured_username():
    auth = make_auth()
    token, _ = auth.issue(username="someone-else", now=1000)
    assert auth.read(token, now=1001) is None
