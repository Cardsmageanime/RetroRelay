"""Controller account and room policy tests; SDL is mocked for deterministic CI."""
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controllers import controller_family, detect_input_devices
from server import create_app, init_db
from test_app import PASS, room_data, join_data, signup_login


def app_client(tmp_path):
    return TestClient(create_app(str(tmp_path / 'hub.sqlite3')))


def add_input(client, headers, kind='gamepad', name='Xbox Wireless Controller', guid='a' * 32):
    if kind != 'gamepad':
        guid = ''
    return client.post('/devices', json={'kind': kind, 'name': name, 'guid': guid}, headers=headers)


def test_devices_require_login_belong_to_user_and_are_idempotent(tmp_path):
    c = app_client(tmp_path)
    assert c.get('/devices').status_code == 401
    a, b = signup_login(c, 'PlayerAlpha'), signup_login(c, 'PlayerBravo')
    result = add_input(c, a)
    assert result.status_code == 201, result.text
    device = result.json()
    assert device['verification'] == 'self-reported / not authenticated'
    assert device['family'] == 'Xbox-style'
    assert add_input(c, a).json()['id'] == device['id']
    assert len(c.get('/devices', headers=a).json()) == 1
    assert c.get('/devices', headers=b).json() == []
    assert c.delete(f'/devices/{device["id"]}', headers=b).status_code == 404
    assert add_input(c, a, 'keyboard', 'Keyboard (system input)', 'ignored').status_code == 201
    assert add_input(c, a, 'gamepad', 'Invalid GUID', 'not hex').status_code == 422
    assert c.delete(f'/devices/{device["id"]}', headers=a).status_code == 200
    assert len(c.get('/devices', headers=a).json()) == 1


def test_registered_device_enforced_in_new_room(tmp_path):
    c = app_client(tmp_path)
    host = signup_login(c, 'ControllerHost')
    guest = signup_login(c, 'ControllerGuest')
    other = signup_login(c, 'ControllerOther')
    device_id = add_input(c, host).json()['id']
    guest_id = add_input(c, guest, 'keyboard', 'Keyboard (system input)').json()['id']
    req = room_data(controller_required=True, controller_id=device_id)
    assert c.post('/rooms', json=room_data(controller_required=True), headers=host).status_code == 409
    assert c.post('/rooms', json={**req, 'controller_id': guest_id}, headers=host).status_code == 409
    room = c.post('/rooms', json=req, headers=host)
    assert room.status_code == 201, room.text
    room_id = room.json()['id']
    assert c.get('/rooms', headers=other).json()[0]['controller_required'] is True
    assert c.post(f'/rooms/{room_id}/join', json=join_data(), headers=guest).status_code == 409
    assert c.post(f'/rooms/{room_id}/join', json=join_data(controller_id=device_id), headers=guest).status_code == 409
    assert c.post(f'/rooms/{room_id}/join', json=join_data(controller_id=guest_id), headers=guest).status_code == 200
    members = c.get(f'/rooms/{room_id}', headers=host).json()['members']
    assert {m['controller'] for m in members} == {'Xbox Wireless Controller', 'Keyboard (system input)'}
    assert c.post(f'/rooms/{room_id}/ready', json={'ready': True}, headers=guest).status_code == 200
    assert c.delete(f'/devices/{guest_id}', headers=guest).status_code == 200
    assert c.post(f'/rooms/{room_id}/ready', json={'ready': True}, headers=guest).status_code == 409
    members = c.get(f'/rooms/{room_id}', headers=host).json()['members']
    assert next(m for m in members if m['username']=='ControllerGuest')['ready'] is False


def test_legacy_server_database_migrates(tmp_path):
    path = str(tmp_path / 'old.sqlite3')
    init_db(path)
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE rooms DROP COLUMN controller_required')
        db.execute('ALTER TABLE members DROP COLUMN controller_id')
    init_db(path)
    with sqlite3.connect(path) as db:
        rooms = {r[1] for r in db.execute('PRAGMA table_info(rooms)')}
        members = {r[1] for r in db.execute('PRAGMA table_info(members)')}
    assert 'controller_required' in rooms and 'controller_id' in members


def test_classification_is_not_authentication():
    assert controller_family('Wireless Controller') == 'PlayStation-style'
    assert controller_family('Nintendo Switch Pro Controller') == 'Nintendo-style'
    assert controller_family('USB Gamepad') == 'Generic / other gamepad'
    assert controller_family('mouse', 'mouse') == 'PC input'


def test_mocked_sdl_discovery():
    class FakeJoystick:
        def init(self): pass
        def get_name(self): return 'DUALSHOCK 4 Wireless Controller'
        def get_guid(self): return 'a'*32
    class FakeJoyModule:
        def init(self): pass
        def quit(self): pass
        def get_count(self): return 1
        def Joystick(self, index): return FakeJoystick()
    class FakePygame:
        joystick = FakeJoyModule()
    devices = detect_input_devices(FakePygame)
    assert [d['kind'] for d in devices] == ['keyboard', 'mouse', 'gamepad']
    assert devices[2]['family'] == 'PlayStation-style'
