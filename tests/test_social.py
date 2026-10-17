"""Social profile link safety: not OAuth and never proof of identity."""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import create_app, init_db
from social import validate_social_url
from test_app import signup_login


def test_social_provider_catalog_and_private_crud(tmp_path):
    api = TestClient(create_app(str(tmp_path / "hub.db")))
    a, b = signup_login(api, "SocialAlice"), signup_login(api, "SocialBobby")
    p = api.get('/social/providers').json()
    assert {x['id'] for x in p} >= {'twitch', 'tiktok', 'youtube', 'facebook'}
    assert all(x['oauth_enabled'] is False for x in p)
    assert api.get('/social-links').status_code == 401
    assert api.get('/social-links', headers=a).json() == []
    good = {'url': 'https://www.youtube.com/@DemoChannel'}
    r=api.put('/social-links/youtube',json=good,headers=a)
    assert r.status_code == 200 and r.json()['verified'] is False
    assert r.json()['visibility'] == 'private'
    assert api.get('/social-links',headers=b).json() == []
    assert len(api.get('/social-links',headers=a).json()) == 1
    assert api.put('/social-links/youtube',json={'url':'https://youtube.com/channel/SomeChannel'},headers=a).status_code == 200
    assert len(api.get('/social-links',headers=a).json()) == 1
    assert api.delete('/social-links/youtube',headers=b).status_code == 200
    assert len(api.get('/social-links',headers=a).json()) == 1
    assert api.delete('/social-links/youtube',headers=a).status_code == 200
    assert api.get('/social-links',headers=a).json() == []


@pytest.mark.parametrize('url', [
    'http://twitch.tv/someuser',
    'https://twitch.tv.evil.example/streamer',
    'https://twitch.tv@evil.example/streamer',
    'https://twitch.tv:8443/streamer',
    'https://twitch.tv/streamer?token=secret',
    'https://twitch.tv/streamer#redirect',
    'https://twitch.tv/a/../../b',
    'javascript:alert(1)',
    'https://127.0.0.1/streamer',
    'https://youtube.com/@a',
    'https://twitch.tv/%0d%0afoo',
    'https://twitch.tv/streamer ',
])
def test_invalid_links_are_rejected(url):
    with pytest.raises(ValueError):
        validate_social_url('twitch', url)


def test_other_providers_and_migration(tmp_path):
    valid = {'twitch': 'https://twitch.tv/streamer123',
             'tiktok': 'https://www.tiktok.com/@streamer123',
             'youtube': 'https://youtube.com/@streamer123',
             'facebook': 'https://facebook.com/streamer123',
             'instagram': 'https://instagram.com/streamer123'}
    for provider, url in valid.items():
        assert validate_social_url(provider,url) == url
    with pytest.raises(ValueError):
        validate_social_url('spotify', 'https://spotify.com/something')
    db=str(tmp_path/'old.sqlite3')
    init_db(db)
    init_db(db)
    import sqlite3
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='social_links'").fetchone()
