import hashlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import create_app
from client import game_fingerprint

PASS = "strongpassword123!"


def mk_client(tmp_path):
    return TestClient(create_app(str(tmp_path / "db.sqlite3")))


def signup_login(client, username):
    assert client.post("/register", json={"username": username, "password": PASS}).status_code == 201
    res = client.post("/login", json={"username": username, "password": PASS})
    assert res.status_code == 200, res.text
    return {"Authorization": "Bearer " + res.json()["token"]}


def room_data(**kwargs):
    data = {
        "platform": "Nintendo SNES", "emulator": "RetroArch", "emulator_version": "1.22.0",
        "core_name": "Snes9x", "core_version": "1.63", "game_title": "Test Homebrew",
        "game_sha256": "b" * 64, "mode": "retroarch", "max_players": 2,
        "connection_hint": "10.1.1.2:55435", "notes": "2-player local battle"
    }
    data.update(kwargs)
    return data


def join_data(**kwargs):
    data = {k: room_data()[k] for k in
            ("emulator", "emulator_version", "core_name", "core_version", "game_sha256")}
    data.update(kwargs)
    return data


def test_accounts_room_join_and_chat(tmp_path):
    client = mk_client(tmp_path)
    host = signup_login(client, "HostPlayer")
    guest = signup_login(client, "GuestPlayer")
    res = client.post("/rooms", json=room_data(), headers=host)
    assert res.status_code == 201, res.text
    rid = res.json()["id"]
    assert len(client.get("/rooms", headers=guest).json()) == 1
    public = client.get("/rooms", headers=guest).json()[0]
    assert "game_sha256" not in public
    assert "connection_hint" not in public
    assert client.get(f"/rooms/{rid}/chat", headers=guest).status_code == 403

    assert client.post(f"/rooms/{rid}/join", json=join_data(game_sha256="c"*64), headers=guest).status_code == 409
    assert client.post(f"/rooms/{rid}/join", json=join_data(emulator_version="1.21.0"), headers=guest).status_code == 409
    assert client.post(f"/rooms/{rid}/join", json=join_data(core_version="1.62"), headers=guest).status_code == 409
    assert client.post(f"/rooms/{rid}/join", json=join_data(), headers=guest).status_code == 200
    assert client.post(f"/rooms/{rid}/ready", json={"ready": True}, headers=guest).status_code == 200
    assert client.post(f"/rooms/{rid}/chat", json={"message": "Ready for battle!"}, headers=guest).status_code == 201
    messages = client.get(f"/rooms/{rid}/chat", headers=host).json()
    assert messages[0]["message"] == "Ready for battle!"
    assert client.get(f"/rooms/{rid}", headers=guest).json()["connection_hint"] == "10.1.1.2:55435"
    assert client.post(f"/rooms/{rid}/leave", headers=host).status_code == 200
    assert client.get(f"/rooms/{rid}", headers=guest).status_code == 404


def test_excluded_consoles_and_invalid_mode(tmp_path):
    client = mk_client(tmp_path)
    h = signup_login(client, "Superhost")
    for platform, emulator in [("Nintendo Switch", "Dolphin"),
                               ("PlayStation 5", "RPCS3"),
                               ("Nintendo SNES", "Dolphin")]:
        res = client.post("/rooms", json=room_data(platform=platform, emulator=emulator), headers=h)
        assert res.status_code == 400
    assert client.post("/rooms", json=room_data(mode="dolphin"), headers=h).status_code == 400
    assert client.post("/rooms", json=room_data(game_sha256="not-a-sha"), headers=h).status_code == 422


def test_room_capacity_and_host_controls(tmp_path):
    client = mk_client(tmp_path)
    host = signup_login(client, "PlayerOne")
    guest = signup_login(client, "PlayerTwo")
    other = signup_login(client, "PlayerThree")
    rid = client.post("/rooms", json=room_data(), headers=host).json()["id"]
    assert client.post(f"/rooms/{rid}/join", json=join_data(), headers=guest).status_code == 200
    assert client.post(f"/rooms/{rid}/join", json=join_data(), headers=other).status_code == 409
    assert client.put(f"/rooms/{rid}/connection", json={"connection_hint": "new"}, headers=guest).status_code == 403
    assert client.put(f"/rooms/{rid}/connection", json={"connection_hint": "new"}, headers=host).status_code == 200
    assert client.post(f"/rooms/{rid}/leave", headers=guest).status_code == 200
    assert client.post(f"/rooms/{rid}/join", json=join_data(), headers=other).status_code == 200


def test_hash_file_and_directory(tmp_path):
    rom = tmp_path / "rom.sfc"
    rom.write_bytes(b"public domain test content")
    assert game_fingerprint(str(rom)) == hashlib.sha256(rom.read_bytes()).hexdigest()
    folder = tmp_path / "game"
    folder.mkdir()
    (folder / "a.bin").write_bytes(b"aaa")
    (folder / "b.cue").write_bytes(b"bbb")
    first = game_fingerprint(str(folder))
    assert first == game_fingerprint(str(folder))
    (folder / "a.bin").write_bytes(b"changed")
    assert first != game_fingerprint(str(folder))


def test_empty_game_path_and_native_retroarch_command(tmp_path):
    from client import launch_commands
    with pytest.raises(ValueError, match="Choose"):
        game_fingerprint("")
    emu = tmp_path / "retroarch"
    emu.write_bytes(b"executable placeholder")
    core = tmp_path / "snes_libretro.so"
    core.write_bytes(b"core placeholder")
    profile = {"executable": str(emu), "core_path": str(core)}
    room = room_data()
    host = launch_commands(room, profile, str(tmp_path / "game.sfc"), True)
    assert "--host" in host and "--connect" not in host
    guest = launch_commands(room, profile, str(tmp_path / "game.sfc"), False)
    assert guest[guest.index("--connect") + 1] == "10.1.1.2"
    assert guest[guest.index("--port") + 1] == "55435"
