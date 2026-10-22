"""Account MFA tests: enrollment, challenge isolation, replay defense, recovery and lockouts."""
import hashlib
import sqlite3
import sys
import time
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import create_app
from mfa import totp_code

PASSWORD = "long-test-password-2026"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RETRORELAY_MFA_KEY", Fernet.generate_key().decode())
    db_path = tmp_path / "mfa.sqlite3"
    client = TestClient(create_app(str(db_path)))
    client.post("/register", json={"username": "playerOne", "password": PASSWORD})
    login = client.post("/login", json={"username": "playerOne", "password": PASSWORD})
    assert login.status_code == 200
    assert "token" in login.json()
    auth = {"Authorization": "Bearer " + login.json()["token"]}
    return client, auth, db_path


def code_at(secret, timestamp=None):
    return totp_code(secret, int((time.time() if timestamp is None else timestamp) // 30))


def enroll(client, auth):
    setup = client.post("/mfa/setup", json={"password": PASSWORD}, headers=auth)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["uri"].startswith("otpauth://totp/")
    confirm = client.post("/mfa/confirm", json={"code": code_at(secret)}, headers=auth)
    assert confirm.status_code == 200, confirm.text
    backups = confirm.json()["recovery_codes"]
    assert len(backups) == 8
    return secret, backups


def test_totp_two_phase_login_and_replay_protection(env, monkeypatch):
    c, auth, db_path = env
    assert c.get("/mfa/status", headers=auth).json()["enabled"] is False
    secret, backups = enroll(c, auth)
    assert c.get("/mfa/status", headers=auth).json()["enabled"] is True
    with sqlite3.connect(str(db_path)) as conn:
        encrypted = conn.execute("SELECT secret_encrypted FROM mfa_accounts").fetchone()[0]
        assert encrypted != secret and secret not in encrypted
        hashes = [r[0] for r in conn.execute("SELECT code_hash FROM mfa_recovery")]
        assert hashlib.sha256(backups[0].encode()).hexdigest() in hashes

    start = c.post("/login", json={"username": "playerOne", "password": PASSWORD})
    assert start.status_code == 200
    assert start.json()["mfa_required"] is True
    assert "token" not in start.json()
    challenge = start.json()["challenge"]
    assert c.get("/me", headers={"Authorization": "Bearer " + challenge}).status_code == 401
    # Same counter used to enable MFA must not work again to log in.
    same = c.post("/mfa/login", json={"challenge": challenge, "code": code_at(secret)})
    assert same.status_code == 401
    # A fresh authenticator step can be used.
    future = time.time() + 61
    monkeypatch.setattr("mfa.time.time", lambda: future)
    next_code = code_at(secret, future)
    accepted = c.post("/mfa/login", json={"challenge": challenge, "code": next_code})
    assert accepted.status_code == 200, accepted.text
    assert c.get("/me", headers={"Authorization": "Bearer " + accepted.json()["token"]}).status_code == 200
    assert c.post("/mfa/login", json={"challenge": challenge, "code": next_code}).status_code == 401
    another = c.post("/login", json={"username": "playerOne", "password": PASSWORD}).json()
    assert c.post("/mfa/login", json={"challenge": another["challenge"], "code": next_code}).status_code == 401

    # A backup code works once, not again for any later challenge.
    session = c.post("/mfa/login", json={"challenge": another["challenge"], "code": backups[0]})
    assert session.status_code == 200, session.text
    second = c.post("/login", json={"username": "playerOne", "password": PASSWORD}).json()
    assert c.post("/mfa/login", json={"challenge": second["challenge"], "code": backups[0]}).status_code == 401


def test_manage_requires_password_and_otp_and_migration_survives_restart(env):
    c, auth, db_path = env
    bad = c.post("/mfa/setup", json={"password": "badpassword"}, headers=auth)
    assert bad.status_code == 401
    secret, backups = enroll(c, auth)
    again = c.post("/mfa/setup", json={"password": PASSWORD}, headers=auth)
    assert again.status_code == 409

    # A session alone may not remove phone-based protection.
    no_password = c.post("/mfa/disable", json={"password": "wrong", "code": backups[0]}, headers=auth)
    assert no_password.status_code == 401
    no_factor = c.post("/mfa/disable", json={"password": PASSWORD, "code": "000000"}, headers=auth)
    assert no_factor.status_code == 401
    c2 = TestClient(create_app(str(db_path)))
    login = c2.post("/login", json={"username": "playerOne", "password": PASSWORD})
    assert login.json()["mfa_required"] is True
    removal = c2.post("/mfa/disable", json={"password": PASSWORD, "code": backups[0]}, headers=auth)
    assert removal.status_code == 200, removal.text
    assert c2.get("/mfa/status", headers=auth).json()["enabled"] is False
    plain = c2.post("/login", json={"username": "playerOne", "password": PASSWORD})
    assert "token" in plain.json()


def test_rate_limit_wrong_password_and_phone_code(env):
    c, auth, _ = env
    secret, backups = enroll(c, auth)
    for _ in range(5):
        assert c.post("/login", json={"username": "playerOne", "password": "wronglongpassword"}).status_code == 401
    assert c.post("/login", json={"username": "playerOne", "password": PASSWORD}).status_code == 429

    # Another account can still log in, and throttling is per-account.
    c.post("/register", json={"username": "otherPlayer", "password": PASSWORD})
    assert "token" in c.post("/login", json={"username": "otherPlayer", "password": PASSWORD}).json()


def test_wrong_codes_rate_limit(env):
    c, auth, _ = env
    secret, backups = enroll(c, auth)
    login = c.post("/login", json={"username": "playerOne", "password": PASSWORD}).json()
    for _ in range(5):
        r = c.post("/mfa/login", json={"challenge": login["challenge"], "code": "zzzzzz"})
        assert r.status_code == 401
    locked = c.post("/mfa/login", json={"challenge": login["challenge"], "code": backups[0]})
    assert locked.status_code == 429


def test_server_without_key_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("RETRORELAY_MFA_KEY", raising=False)
    c = TestClient(create_app(str(tmp_path / "nokey.sqlite3")))
    c.post("/register", json={"username": "FreshPlayer", "password": PASSWORD})
    token = c.post("/login", json={"username": "FreshPlayer", "password": PASSWORD}).json()["token"]
    auth = {"Authorization": "Bearer " + token}
    assert c.post("/mfa/setup", json={"password": PASSWORD}, headers=auth).status_code == 503
    assert c.get("/mfa/status", headers=auth).json()["server_configured"] is False
