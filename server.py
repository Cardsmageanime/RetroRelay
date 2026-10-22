"""RetroRelay lobby/account server. It coordinates play; it is NOT a game-data relay."""
from __future__ import annotations

import hashlib
import base64
import hmac
import os
import re
import secrets
import sqlite3
import time
from typing import Literal
from pathlib import Path
from contextlib import contextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from catalog import PLATFORMS, MODES, compatible_mode
from controllers import controller_family
from artwork import clean_artwork
from social import SOCIAL_PROVIDERS, validate_social_url
from mfa import (create_secret, encrypt_secret, decrypt_secret, provisioning_uri,
                 match_counter, new_recovery_codes, recovery_hash, encryption_key)

USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{2,23}$")
HEX_RE = re.compile(r"^[a-f0-9]{64}$")


class Credentials(BaseModel):
    username: str
    password: str


class RoomCreate(BaseModel):
    platform: str
    emulator: str
    emulator_version: str = Field(min_length=1, max_length=100)
    core_name: str = Field(default="", max_length=120)
    core_version: str = Field(default="", max_length=100)
    game_title: str = Field(min_length=1, max_length=120)
    game_sha256: str
    mode: str
    connection_hint: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=400)
    max_players: int = Field(default=2, ge=2, le=16)
    controller_required: bool = False
    controller_id: str | None = None

    @field_validator("game_sha256")
    @classmethod
    def hash_format(cls, v):
        if not HEX_RE.fullmatch(v):
            raise ValueError("Must be a lowercase SHA-256 hex digest")
        return v


class JoinRoom(BaseModel):
    emulator: str = ""
    emulator_version: str = ""
    core_name: str = ""
    core_version: str = ""
    game_sha256: str = ""
    controller_id: str | None = None


class ArtworkUpload(BaseModel):
    image_base64: str = Field(min_length=1, max_length=1_100_000)
    rights_confirmed: bool = False



class SocialLink(BaseModel):
    url: str = Field(min_length=10, max_length=280)


class MFAPassword(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class MFACode(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class MFAChallenge(BaseModel):
    challenge: str = Field(min_length=32, max_length=256)
    code: str = Field(min_length=6, max_length=32)


class MFADisable(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=32)


class DeviceRegistration(BaseModel):
    kind: Literal["keyboard", "mouse", "gamepad"]
    name: str = Field(min_length=1, max_length=100)
    guid: str = Field(default="", max_length=64)

    @field_validator("guid")
    @classmethod
    def validate_guid(cls, value: str) -> str:
        if value and not re.fullmatch(r"[A-Fa-f0-9]{32}", value):
            raise ValueError("Gamepad SDL GUID must be 32 hex characters")
        return value.lower()


class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=600)


class ReadyChange(BaseModel):
    ready: bool


class ConnectionChange(BaseModel):
    connection_hint: str = Field(max_length=500)


def now():
    return int(time.time())


def passhash(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1).hex()


@contextmanager
def database(path: str):
    con = sqlite3.connect(path, timeout=15, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=15000")
    try:
        yield con
    finally:
        con.close()


def init_db(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with database(path) as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL,
            username_key TEXT NOT NULL UNIQUE,
            salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            host_id INTEGER NOT NULL REFERENCES users(id),
            platform TEXT NOT NULL, emulator TEXT NOT NULL, emulator_version TEXT NOT NULL,
            core_name TEXT NOT NULL, core_version TEXT NOT NULL,
            game_title TEXT NOT NULL, game_sha256 TEXT NOT NULL,
            mode TEXT NOT NULL, connection_hint TEXT NOT NULL, notes TEXT NOT NULL,
            max_players INTEGER NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS members (
            room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ready INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(room_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            message TEXT NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id,id);
        CREATE TABLE IF NOT EXISTS room_artwork (
            room_id TEXT PRIMARY KEY REFERENCES rooms(id) ON DELETE CASCADE,
            image_png BLOB NOT NULL,
            uploaded_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS social_links (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider TEXT NOT NULL, url TEXT NOT NULL, updated_at INTEGER NOT NULL,
            PRIMARY KEY(user_id,provider)
        );
        CREATE TABLE IF NOT EXISTS mfa_accounts (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            secret_encrypted TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            last_step INTEGER NOT NULL DEFAULT -1,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mfa_recovery (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,
            PRIMARY KEY(user_id,code_hash)
        );
        CREATE TABLE IF NOT EXISTS mfa_challenges (
            challenge_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mfa_challenges_user ON mfa_challenges(user_id);
        CREATE TABLE IF NOT EXISTS auth_attempts (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL,
            count INTEGER NOT NULL,
            started_at INTEGER NOT NULL,
            blocked_until INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,purpose)
        );
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL, name TEXT NOT NULL, guid TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(user_id, kind, name, guid)
        );
        """)
        # Safe, additive migration for existing v0.1 server databases.
        room_columns = {r["name"] for r in db.execute("PRAGMA table_info(rooms)")}
        if "controller_required" not in room_columns:
            db.execute("ALTER TABLE rooms ADD COLUMN controller_required INTEGER NOT NULL DEFAULT 0")
        member_columns = {r["name"] for r in db.execute("PRAGMA table_info(members)")}
        if "controller_id" not in member_columns:
            db.execute("ALTER TABLE members ADD COLUMN controller_id TEXT")


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="RetroRelay Hub", version="0.2.0-pre")
    app.state.db_path = db_path or os.getenv(
        "RETRORELAY_DB", str(Path.home() / ".retrorelay_hub" / "lobbies.sqlite3")
    )
    init_db(app.state.db_path)

    def conn(request: Request):
        return database(request.app.state.db_path)

    def current_user(request: Request, authorization: str | None = Header(default=None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Please log in")
        token = authorization[7:]
        if len(token) < 32:
            raise HTTPException(status_code=401, detail="Invalid session")
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with conn(request) as db:
            row = db.execute("""SELECT users.id, users.username FROM sessions
                JOIN users ON users.id=sessions.user_id
                WHERE token_hash=? AND sessions.created_at>=?""",
                (token_hash, now() - 14 * 24 * 60 * 60)).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Session expired; please log in")
        return {"id": row["id"], "username": row["username"], "token_hash": token_hash}

    def require_room(db, room_id: str):
        room = db.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
        if not room:
            raise HTTPException(status_code=404, detail="Room was closed or does not exist")
        return room

    def require_member(db, room_id: str, user_id: int):
        if not db.execute("SELECT 1 FROM members WHERE room_id=? AND user_id=?", (room_id,user_id)).fetchone():
            raise HTTPException(status_code=403, detail="Join this room first")

    def registered_device(db, user_id: int, device_id: str | None, required: bool):
        if not device_id:
            if required:
                raise HTTPException(409, "Register and select an input device in Controllers first")
            return None
        device = db.execute("SELECT * FROM devices WHERE id=? AND user_id=?",
                            (device_id, user_id)).fetchone()
        if not device:
            raise HTTPException(409, "Selected controller is not registered to this account")
        return device["id"]

    def device_info(row):
        return {"id": row["id"], "kind": row["kind"], "name": row["name"],
                "guid": row["guid"], "family": controller_family(row["name"], row["kind"]),
                "verification": "self-reported / not authenticated"}

    def room_summary(db, room):
        host = db.execute("SELECT username FROM users WHERE id=?", (room["host_id"],)).fetchone()
        count = db.execute("SELECT COUNT(*) c FROM members WHERE room_id=?", (room["id"],)).fetchone()["c"]
        return {
            "id": room["id"], "host": host["username"], "platform": room["platform"],
            "emulator": room["emulator"], "emulator_version": room["emulator_version"],
            "core_name": room["core_name"], "core_version": room["core_version"],
            "game_title": room["game_title"], "mode": room["mode"],
            "notes": room["notes"], "max_players": room["max_players"],
            "players": count, "created_at": room["created_at"],
            "controller_required": bool(room["controller_required"]),
            "artwork": bool(db.execute("SELECT 1 FROM room_artwork WHERE room_id=?", (room["id"],)).fetchone()),
            "game_copy_required": room["mode"] != "parsec",

        }

    @app.get("/health")
    def health():
        return {"online": True, "version": "0.2.0-pre"}

    @app.get("/catalog")
    def catalog():
        return {"platforms": PLATFORMS, "modes": MODES}

    @app.post("/register", status_code=201)
    def register(body: Credentials, request: Request):
        if not USERNAME_RE.fullmatch(body.username):
            raise HTTPException(400, "Username: 3-24 letters, numbers, - or _, starting with a letter")
        if len(body.password) < 10 or len(body.password) > 256:
            raise HTTPException(400, "Password must have 10-256 characters")
        salt = secrets.token_bytes(16)
        digest = passhash(body.password, salt)
        with conn(request) as db:
            try:
                db.execute("INSERT INTO users(username,username_key,salt,password_hash,created_at) VALUES(?,?,?,?,?)",
                           (body.username, body.username.casefold(), salt.hex(), digest, now()))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "Username is taken")
        return {"message": "Account created; log in to continue"}

    def attempts_check(db, user_id: int, purpose: str):
        row = db.execute("SELECT blocked_until FROM auth_attempts WHERE user_id=? AND purpose=?",
                         (user_id, purpose)).fetchone()
        if row and row["blocked_until"] > now():
            raise HTTPException(429, "Too many attempts. Try again later.")

    def attempts_fail(db, user_id: int, purpose: str):
        clock = now()
        row = db.execute("SELECT count,started_at FROM auth_attempts WHERE user_id=? AND purpose=?",
                         (user_id, purpose)).fetchone()
        count = row["count"] + 1 if row and clock - row["started_at"] < 600 else 1
        start = row["started_at"] if row and clock - row["started_at"] < 600 else clock
        block = clock + 300 if count >= 5 else 0
        db.execute("""INSERT INTO auth_attempts(user_id,purpose,count,started_at,blocked_until)
                      VALUES(?,?,?,?,?) ON CONFLICT(user_id,purpose) DO UPDATE SET
                      count=excluded.count,started_at=excluded.started_at,
                      blocked_until=excluded.blocked_until""",
                   (user_id, purpose, count, start, block))

    def attempts_reset(db, user_id: int, purpose: str):
        db.execute("DELETE FROM auth_attempts WHERE user_id=? AND purpose=?", (user_id, purpose))

    def check_password(row, password: str):
        expected = passhash(password, bytes.fromhex(row["salt"]))
        return hmac.compare_digest(expected, row["password_hash"])

    def totp_or_recovery(db, row, code: str):
        """Caller must have BEGIN IMMEDIATE; consuming this result is atomic."""
        try:
            secret = decrypt_secret(row["secret_encrypted"])
        except ValueError as exc:
            raise HTTPException(503, "MFA server configuration unavailable") from exc
        step = match_counter(secret, code, row["last_step"])
        if step is not None:
            db.execute("UPDATE mfa_accounts SET last_step=? WHERE user_id=?",
                       (step, row["user_id"]))
            return True
        if re.fullmatch(r"[A-Fa-f0-9]{32}", code):
            code_hash = recovery_hash(code.lower())
            used = db.execute("DELETE FROM mfa_recovery WHERE user_id=? AND code_hash=?",
                              (row["user_id"], code_hash))
            return used.rowcount == 1
        return False

    @app.post("/login")
    def login(body: Credentials, request: Request):
        with conn(request) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM users WHERE username_key=?", (body.username.casefold(),)).fetchone()
            if row:
                attempts_check(db, row["id"], "password")
            # Do not reveal if a username exists by skipping expensive verification.
            salt = bytes.fromhex(row["salt"]) if row else bytes(16)
            candidate = passhash(body.password, salt)
            if not row or not hmac.compare_digest(candidate, row["password_hash"]):
                if row:
                    attempts_fail(db, row["id"], "password")
                db.commit()
                raise HTTPException(401, "Incorrect username or password")
            attempts_reset(db, row["id"], "password")
            mfa = db.execute("SELECT enabled FROM mfa_accounts WHERE user_id=?",
                             (row["id"],)).fetchone()
            if mfa and mfa["enabled"]:
                try:
                    encryption_key()
                except ValueError as exc:
                    raise HTTPException(503, "MFA server configuration unavailable") from exc
                db.execute("DELETE FROM mfa_challenges WHERE user_id=? OR expires_at<?",
                           (row["id"], now()))
                challenge = secrets.token_urlsafe(36)
                db.execute("""INSERT INTO mfa_challenges(challenge_hash,user_id,expires_at)
                              VALUES(?,?,?)""",
                           (hashlib.sha256(challenge.encode()).hexdigest(), row["id"], now()+300))
                db.commit()
                return {"mfa_required": True, "challenge": challenge}
            token = secrets.token_urlsafe(36)
            db.execute("INSERT INTO sessions(token_hash,user_id,created_at) VALUES(?,?,?)",
                       (hashlib.sha256(token.encode()).hexdigest(), row["id"], now()))
            db.commit()
            return {"token": token, "username": row["username"]}

    @app.post("/mfa/login")
    def mfa_login(body: MFAChallenge, request: Request):
        challenge_hash = hashlib.sha256(body.challenge.encode()).hexdigest()
        with conn(request) as db:
            db.execute("BEGIN IMMEDIATE")
            challenge = db.execute("SELECT user_id,expires_at FROM mfa_challenges WHERE challenge_hash=?",
                                   (challenge_hash,)).fetchone()
            if not challenge or challenge["expires_at"] <= now():
                raise HTTPException(401, "MFA login challenge expired; sign in again")
            uid = challenge["user_id"]
            attempts_check(db, uid, "otp")
            row = db.execute("SELECT * FROM mfa_accounts WHERE user_id=? AND enabled=1",
                             (uid,)).fetchone()
            if not row:
                raise HTTPException(401, "MFA enrollment changed; sign in again")
            if not totp_or_recovery(db, row, body.code):
                attempts_fail(db, uid, "otp")
                db.commit()
                raise HTTPException(401, "Incorrect authenticator or recovery code")
            attempts_reset(db, uid, "otp")
            db.execute("DELETE FROM mfa_challenges WHERE user_id=?", (uid,))
            user = db.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
            token = secrets.token_urlsafe(36)
            db.execute("INSERT INTO sessions(token_hash,user_id,created_at) VALUES(?,?,?)",
                       (hashlib.sha256(token.encode()).hexdigest(), uid, now()))
            db.commit()
            return {"token": token, "username": user["username"]}

    @app.get("/mfa/status")
    def mfa_status(request: Request, me=Depends(current_user)):
        with conn(request) as db:
            row = db.execute("SELECT enabled FROM mfa_accounts WHERE user_id=?",
                             (me["id"],)).fetchone()
        return {"enabled": bool(row and row["enabled"]), "method": "totp",
                "server_configured": bool(os.getenv("RETRORELAY_MFA_KEY", "").strip())}

    @app.post("/mfa/setup")
    def mfa_setup(body: MFAPassword, request: Request, me=Depends(current_user)):
        try:
            encryption_key()
        except ValueError as exc:
            raise HTTPException(503, "MFA is not configured by this server operator") from exc
        with conn(request) as db:
            db.execute("BEGIN IMMEDIATE")
            user = db.execute("SELECT * FROM users WHERE id=?", (me["id"],)).fetchone()
            attempts_check(db, me["id"], "manage")
            if not check_password(user, body.password):
                attempts_fail(db, me["id"], "manage")
                db.commit()
                raise HTTPException(401, "Current password is incorrect")
            row = db.execute("SELECT enabled FROM mfa_accounts WHERE user_id=?",
                             (me["id"],)).fetchone()
            if row and row["enabled"]:
                raise HTTPException(409, "Disable existing MFA with your existing code first")
            secret = create_secret()
            db.execute("""INSERT INTO mfa_accounts(user_id,secret_encrypted,enabled,created_at,last_step)
                          VALUES(?,?,0,?,-1) ON CONFLICT(user_id) DO UPDATE SET
                          secret_encrypted=excluded.secret_encrypted,enabled=0,
                          created_at=excluded.created_at,last_step=-1""",
                       (me["id"], encrypt_secret(secret), now()))
            attempts_reset(db, me["id"], "manage")
            db.commit()
            return {"secret": secret, "uri": provisioning_uri(user["username"], secret),
                    "expires_in": 900,
                    "instruction": "Add this secret to your phone authenticator, then confirm its six-digit code."}

    @app.post("/mfa/confirm")
    def mfa_confirm(body: MFACode, request: Request, me=Depends(current_user)):
        with conn(request) as db:
            db.execute("BEGIN IMMEDIATE")
            attempts_check(db, me["id"], "otp")
            row = db.execute("SELECT * FROM mfa_accounts WHERE user_id=? AND enabled=0",
                             (me["id"],)).fetchone()
            if not row or now() - row["created_at"] > 900:
                raise HTTPException(409, "No recent pending MFA enrollment")
            if not re.fullmatch(r"[0-9]{6}", body.code):
                attempts_fail(db, me["id"], "otp")
                db.commit()
                raise HTTPException(401, "Invalid authenticator code")
            try:
                step = match_counter(decrypt_secret(row["secret_encrypted"]),
                                     body.code, row["last_step"])
            except ValueError as exc:
                raise HTTPException(503, "MFA server configuration unavailable") from exc
            if step is None:
                attempts_fail(db, me["id"], "otp")
                db.commit()
                raise HTTPException(401, "Invalid authenticator code")
            backup_codes = new_recovery_codes()
            db.execute("UPDATE mfa_accounts SET enabled=1,last_step=? WHERE user_id=?",
                       (step, me["id"]))
            db.execute("DELETE FROM mfa_recovery WHERE user_id=?", (me["id"],))
            db.executemany("INSERT INTO mfa_recovery(user_id,code_hash) VALUES(?,?)",
                           [(me["id"], recovery_hash(code)) for code in backup_codes])
            # Require all other devices to sign in with the newly enabled factor.
            db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?",
                       (me["id"], me["token_hash"]))
            attempts_reset(db, me["id"], "otp")
            db.commit()
            return {"enabled": True, "recovery_codes": backup_codes,
                    "warning": "Save these recovery codes securely; each works once and they are not shown again."}

    @app.post("/mfa/disable")
    def mfa_disable(body: MFADisable, request: Request, me=Depends(current_user)):
        with conn(request) as db:
            db.execute("BEGIN IMMEDIATE")
            attempts_check(db, me["id"], "manage")
            attempts_check(db, me["id"], "otp")
            user = db.execute("SELECT * FROM users WHERE id=?", (me["id"],)).fetchone()
            row = db.execute("SELECT * FROM mfa_accounts WHERE user_id=? AND enabled=1",
                             (me["id"],)).fetchone()
            if not row:
                raise HTTPException(409, "MFA is not enabled")
            if not check_password(user, body.password):
                attempts_fail(db, me["id"], "manage")
                db.commit()
                raise HTTPException(401, "Current password is incorrect")
            if not totp_or_recovery(db, row, body.code):
                attempts_fail(db, me["id"], "otp")
                db.commit()
                raise HTTPException(401, "Authenticator/recovery code was rejected")
            db.execute("DELETE FROM mfa_accounts WHERE user_id=?", (me["id"],))
            db.execute("DELETE FROM mfa_recovery WHERE user_id=?", (me["id"],))
            db.execute("DELETE FROM mfa_challenges WHERE user_id=?", (me["id"],))
            db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?",
                       (me["id"], me["token_hash"]))
            attempts_reset(db, me["id"], "manage")
            attempts_reset(db, me["id"], "otp")
            db.commit()
            return {"enabled": False, "ok": True}

    @app.post("/logout")
    def logout(request: Request, me=Depends(current_user)):
        with conn(request) as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (me["token_hash"],))
        return {"ok": True}

    @app.get("/me")
    def me_info(me=Depends(current_user)):
        return {"username": me["username"]}

    @app.get("/social/providers")
    def social_providers():
        return [{"id": provider, "name": entry["name"], "oauth_enabled": False}
                for provider, entry in SOCIAL_PROVIDERS.items()]

    @app.get("/social-links")
    def social_links(request: Request, me=Depends(current_user)):
        """Private-to-owner links; not proof of social account ownership."""
        with conn(request) as db:
            return [{"provider": row["provider"], "url": row["url"],
                     "verified": False, "visibility": "private"}
                    for row in db.execute(
                        "SELECT provider,url FROM social_links WHERE user_id=? ORDER BY provider",
                        (me["id"],))]

    @app.put("/social-links/{provider}")
    def save_social_link(provider: str, body: SocialLink, request: Request,
                         me=Depends(current_user)):
        try:
            url = validate_social_url(provider, body.url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        provider = provider.lower().strip()
        with conn(request) as db:
            db.execute("""INSERT INTO social_links(user_id,provider,url,updated_at)
                       VALUES (?,?,?,?) ON CONFLICT(user_id,provider)
                       DO UPDATE SET url=excluded.url,updated_at=excluded.updated_at""",
                       (me["id"],provider,url,now()))
        return {"provider": provider, "url": url, "verified": False,
                "visibility": "private"}

    @app.delete("/social-links/{provider}")
    def remove_social_link(provider: str, request: Request, me=Depends(current_user)):
        if provider not in SOCIAL_PROVIDERS:
            raise HTTPException(404, "Unknown social platform")
        with conn(request) as db:
            db.execute("DELETE FROM social_links WHERE user_id=? AND provider=?",
                       (me["id"],provider))
        return {"ok": True}

    @app.get("/devices")
    def list_devices(request: Request, me=Depends(current_user)):
        with conn(request) as db:
            return [device_info(r) for r in db.execute(
                "SELECT * FROM devices WHERE user_id=? ORDER BY created_at,id", (me["id"],))]

    @app.post("/devices", status_code=201)
    def register_device(body: DeviceRegistration, request: Request, me=Depends(current_user)):
        name = body.name.strip()
        if not name:
            raise HTTPException(422, "Device name is required")
        if body.kind != "gamepad" and body.guid:
            raise HTTPException(422, "Keyboard and mouse entries cannot have gamepad GUIDs")
        with conn(request) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM devices WHERE user_id=? AND kind=? AND name=? AND guid=?",
                                  (me["id"], body.kind, name, body.guid)).fetchone()
            if existing:
                return device_info(existing)
            count = db.execute("SELECT COUNT(*) AS n FROM devices WHERE user_id=?", (me["id"],)).fetchone()["n"]
            if count >= 16:
                raise HTTPException(409, "Maximum 16 registered input profiles per account")
            device_id = secrets.token_hex(12)
            db.execute("INSERT INTO devices(id,user_id,kind,name,guid,created_at) VALUES(?,?,?,?,?,?)",
                       (device_id, me["id"], body.kind, name, body.guid, now()))
            row = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
            db.commit()
            return device_info(row)

    @app.delete("/devices/{device_id}")
    def delete_device(device_id: str, request: Request, me=Depends(current_user)):
        with conn(request) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM devices WHERE id=? AND user_id=?",
                             (device_id, me["id"])).fetchone()
            if not row:
                raise HTTPException(404, "Controller profile not found")
            db.execute("UPDATE members SET controller_id=NULL,ready=0 WHERE user_id=? AND controller_id=?",
                       (me["id"], device_id))
            db.execute("DELETE FROM devices WHERE id=?", (device_id,))
            db.commit()
        return {"ok": True}

    @app.get("/rooms")
    def rooms(request: Request, me=Depends(current_user)):
        with conn(request) as db:
            results = db.execute("SELECT * FROM rooms ORDER BY created_at DESC LIMIT 150").fetchall()
            return [room_summary(db, r) for r in results]

    @app.post("/rooms", status_code=201)
    def create_room(body: RoomCreate, request: Request, me=Depends(current_user)):
        if not compatible_mode(body.platform, body.emulator, body.mode):
            raise HTTPException(400, "That platform/emulator/mode combination is not supported")
        if body.emulator == "RetroArch" and (not body.core_name.strip() or not body.core_version.strip()):
            raise HTTPException(400, "RetroArch rooms require matching core name and core version")
        room_id = secrets.token_hex(4).upper()
        with conn(request) as db:
            db.execute("BEGIN IMMEDIATE")
            controller_id = registered_device(db, me["id"], body.controller_id, body.controller_required)
            db.execute("""INSERT INTO rooms
               (id,host_id,platform,emulator,emulator_version,core_name,core_version,
                game_title,game_sha256,mode,connection_hint,notes,max_players,created_at,controller_required)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (room_id, me["id"], body.platform, body.emulator,
                body.emulator_version.strip(), body.core_name.strip(), body.core_version.strip(),
                body.game_title.strip(), body.game_sha256, body.mode, body.connection_hint.strip(),
                body.notes.strip(), body.max_players, now(), int(body.controller_required)))
            db.execute("INSERT INTO members(room_id,user_id,ready,controller_id) VALUES(?,?,0,?)",
                       (room_id,me["id"], controller_id))
            db.commit()
        return {"id": room_id}

    @app.put("/rooms/{room_id}/artwork")
    def put_room_artwork(room_id: str, body: ArtworkUpload, request: Request,
                         me=Depends(current_user)):
        if not body.rights_confirmed:
            raise HTTPException(400, "Confirm you own the art or have permission to publish it")
        try:
            safe_png = clean_artwork(body.image_base64)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        with conn(request) as db:
            room = require_room(db, room_id)
            if room["host_id"] != me["id"]:
                raise HTTPException(403, "Only the host may upload room artwork")
            db.execute("""INSERT INTO room_artwork(room_id,image_png,uploaded_at)
                VALUES(?,?,?) ON CONFLICT(room_id) DO UPDATE SET
                image_png=excluded.image_png,uploaded_at=excluded.uploaded_at""",
                (room_id, safe_png, now()))
        return {"ok": True, "bytes": len(safe_png)}

    @app.get("/rooms/{room_id}/artwork")
    def get_room_artwork(room_id: str, request: Request,
                         me=Depends(current_user)):
        with conn(request) as db:
            require_room(db, room_id)
            img = db.execute("SELECT image_png FROM room_artwork WHERE room_id=?",
                             (room_id,)).fetchone()
            if not img:
                raise HTTPException(404, "This lobby has no custom artwork")
        return Response(content=img["image_png"], media_type="image/png",
                        headers={"Cache-Control": "private, max-age=120", "X-Content-Type-Options": "nosniff"})

    @app.post("/rooms/{room_id}/join")
    def join_room(room_id: str, body: JoinRoom, request: Request, me=Depends(current_user)):
        with conn(request) as db:
            db.execute("BEGIN IMMEDIATE")
            room = require_room(db, room_id)
            # Remote-play guests view the host's authorized local game through Parsec.
            # They do not need an emulator or game file; other modes match exact bytes.
            require_values = () if room["mode"] == "parsec" else (
                "emulator", "emulator_version", "core_name", "core_version", "game_sha256")
            mismatches = [key for key in require_values if getattr(body, key).strip() != room[key]]
            if mismatches:
                raise HTTPException(409, "Cannot join: mismatched " + ", ".join(mismatches))
            controller_id = registered_device(db, me["id"], body.controller_id, bool(room["controller_required"]))
            if not db.execute("SELECT 1 FROM members WHERE room_id=? AND user_id=?",
                              (room_id,me["id"])).fetchone():
                count = db.execute("SELECT COUNT(*) c FROM members WHERE room_id=?", (room_id,)).fetchone()["c"]
                if count >= room["max_players"]:
                    raise HTTPException(409, "Room is full")
                db.execute("INSERT INTO members(room_id,user_id,ready,controller_id) VALUES(?,?,0,?)",
                           (room_id,me["id"],controller_id))
            else:
                db.execute("UPDATE members SET controller_id=?,ready=0 WHERE room_id=? AND user_id=?",
                           (controller_id,room_id,me["id"]))
            db.commit()
        return {"ok": True}

    @app.get("/rooms/{room_id}")
    def room_info(room_id: str, request: Request, me=Depends(current_user)):
        with conn(request) as db:
            room = require_room(db, room_id)
            require_member(db, room_id, me["id"])
            participants = db.execute("""SELECT users.username,members.ready,devices.name as device_name,
                devices.kind as device_kind FROM members
                JOIN users ON users.id=members.user_id
                LEFT JOIN devices ON devices.id=members.controller_id
                WHERE room_id=? ORDER BY users.username""",
                (room_id,)).fetchall()
            return {**room_summary(db, room), "is_host": room["host_id"] == me["id"],
                    "connection_hint": room["connection_hint"],
                    "members": [{"username": m["username"], "ready": bool(m["ready"]),
                                 "controller": m["device_name"], "device_kind": m["device_kind"]}
                                for m in participants]}

    @app.post("/rooms/{room_id}/ready")
    def set_ready(room_id: str, body: ReadyChange, request: Request, me=Depends(current_user)):
        with conn(request) as db:
            room = require_room(db, room_id)
            require_member(db, room_id, me["id"])
            if body.ready and room["controller_required"]:
                selected = db.execute("""SELECT 1 FROM members JOIN devices ON devices.id=members.controller_id
                    WHERE members.room_id=? AND members.user_id=? AND devices.user_id=?""",
                    (room_id,me["id"],me["id"])).fetchone()
                if not selected:
                    raise HTTPException(409, "Register a controller before marking ready")
            db.execute("UPDATE members SET ready=? WHERE room_id=? AND user_id=?",
                       (int(body.ready), room_id, me["id"]))
        return {"ok": True}

    @app.put("/rooms/{room_id}/connection")
    def update_connection(room_id: str, body: ConnectionChange, request: Request,
                          me=Depends(current_user)):
        with conn(request) as db:
            room = require_room(db, room_id)
            if room["host_id"] != me["id"]:
                raise HTTPException(403, "Only the host can update connection info")
            db.execute("UPDATE rooms SET connection_hint=? WHERE id=?",
                       (body.connection_hint.strip(), room_id))
        return {"ok": True}

    @app.get("/rooms/{room_id}/chat")
    def get_chat(room_id: str, request: Request, after_id: int = 0,
                 me=Depends(current_user)):
        with conn(request) as db:
            require_room(db, room_id)
            require_member(db, room_id, me["id"])
            messages = db.execute("""SELECT messages.id,users.username,messages.message,messages.created_at
                FROM messages JOIN users ON users.id=messages.user_id
                WHERE room_id=? AND messages.id>? ORDER BY messages.id ASC LIMIT 150""",
                (room_id, max(0,after_id))).fetchall()
            return [dict(m) for m in messages]

    @app.post("/rooms/{room_id}/chat", status_code=201)
    def send_chat(room_id: str, body: ChatMessage, request: Request, me=Depends(current_user)):
        with conn(request) as db:
            require_room(db, room_id)
            require_member(db, room_id, me["id"])
            db.execute("INSERT INTO messages(room_id,user_id,message,created_at) VALUES(?,?,?,?)",
                       (room_id,me["id"],body.message.strip(),now()))
        return {"ok": True}

    @app.post("/rooms/{room_id}/leave")
    def leave_room(room_id: str, request: Request, me=Depends(current_user)):
        with conn(request) as db:
            db.execute("BEGIN IMMEDIATE")
            room = require_room(db, room_id)
            require_member(db, room_id, me["id"])
            if room["host_id"] == me["id"]:
                db.execute("DELETE FROM rooms WHERE id=?", (room_id,))
            else:
                db.execute("DELETE FROM members WHERE room_id=? AND user_id=?", (room_id,me["id"]))
            db.commit()
        return {"ok": True}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("RETRORELAY_HOST", "127.0.0.1"),
                port=int(os.getenv("RETRORELAY_PORT", "8751")))
