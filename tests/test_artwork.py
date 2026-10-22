"""Room thumbnails and host-only-controller guest flow."""
import base64
import io
import sqlite3
import sys
from pathlib import Path

from PIL import Image
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import create_app
from test_app import signup_login, room_data, join_data
from test_controllers import add_input


def art_payload():
    im = Image.new("RGB", (640, 360), (100, 65, 140))
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return {"image_base64": base64.b64encode(buf.getvalue()).decode(), "rights_confirmed": True}


def test_international_art_and_permissions(tmp_path):
    c = TestClient(create_app(str(tmp_path / "database.sqlite")))
    host = signup_login(c, "HostArt")
    guest = signup_login(c, "GuestArt")
    room = c.post('/rooms', json=room_data(game_title="ストリートファイター II — 街頭霸王"), headers=host)
    assert room.status_code == 201, room.text
    rid = room.json()['id']
    assert c.get('/rooms', headers=guest).json()[0]['game_title'].startswith('ストリート')
    assert c.get(f'/rooms/{rid}/artwork', headers=guest).status_code == 404
    assert c.put(f'/rooms/{rid}/artwork', json=art_payload(), headers=guest).status_code == 403
    data = art_payload()
    data['rights_confirmed'] = False
    assert c.put(f'/rooms/{rid}/artwork', json=data, headers=host).status_code == 400
    res = c.put(f'/rooms/{rid}/artwork', json=art_payload(), headers=host)
    assert res.status_code == 200, res.text
    assert c.get('/rooms', headers=guest).json()[0]['artwork'] is True
    png = c.get(f'/rooms/{rid}/artwork', headers=guest)
    assert png.status_code == 200 and png.headers['content-type'] == 'image/png'
    assert png.content.startswith(b'\x89PNG')
    assert c.get(f'/rooms/{rid}/artwork').status_code == 401
    assert c.post(f'/rooms/{rid}/join', json=join_data(game_sha256='f'*64), headers=guest).status_code == 409
    assert c.post(f"/rooms/{rid}/leave", headers=host).status_code == 200


def test_parsec_controller_guest_needs_no_rom(tmp_path):
    c = TestClient(create_app(str(tmp_path / "database.sqlite")))
    host = signup_login(c, "ParsecHost")
    guest = signup_login(c, "ParsecGuest")
    host_pad = add_input(c, host).json()['id']
    guest_pad = add_input(c, guest).json()['id']
    room = c.post('/rooms', json=room_data(mode='parsec', controller_required=True,
                controller_id=host_pad), headers=host)
    assert room.status_code == 201, room.text
    rid = room.json()['id']
    summary = c.get('/rooms', headers=guest).json()[0]
    assert summary['game_copy_required'] is False
    assert c.post(f'/rooms/{rid}/join', json={}, headers=guest).status_code == 409
    assert c.post(f'/rooms/{rid}/join', json={'controller_id': guest_pad}, headers=guest).status_code == 200
    assert c.post(f'/rooms/{rid}/ready', json={'ready': True}, headers=guest).status_code == 200
    assert c.get(f'/rooms/{rid}', headers=guest).json()['members']


def test_reject_unsafe_and_oversize_art(tmp_path):
    c = TestClient(create_app(str(tmp_path / 'db.sqlite')))
    host = signup_login(c, 'ArtSafety')
    rid = c.post('/rooms', json=room_data(), headers=host).json()['id']
    ep = f'/rooms/{rid}/artwork'
    assert c.put(ep, json={'rights_confirmed': True,'image_base64': base64.b64encode(b'evil').decode()}, headers=host).status_code == 422
    huge_image = Image.new('RGB', (2200,2200))
    b = io.BytesIO(); huge_image.save(b,format='PNG')
    assert c.put(ep, json={'rights_confirmed':True,'image_base64':base64.b64encode(b.getvalue()).decode()},headers=host).status_code == 422
    assert c.put(ep, json={'rights_confirmed':True,'image_base64': 'x'*1100001}, headers=host).status_code == 422


def test_existing_database_art_table_migrates(tmp_path):
    from server import init_db
    db = str(tmp_path / 'old.sqlite3')
    init_db(db)
    init_db(db)
    with sqlite3.connect(db) as con:
        names = {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'room_artwork' in names
