"""Desktop interaction checks; run with an X display (e.g. xvfb-run)."""
import os
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from client import RetroRelayApp

pytestmark = pytest.mark.skipif(not os.environ.get('DISPLAY'), reason='Requires an X display')

@pytest.fixture
def app(monkeypatch, tmp_path):
    import client
    monkeypatch.setattr(client, 'CONFIG_FILE', tmp_path / 'settings.json')
    monkeypatch.setattr(client, 'CONFIG_DIR', tmp_path)
    ui = RetroRelayApp()
    ui.update()
    yield ui
    ui.destroy()

def room(name, platform='Nintendo SNES', mode='retroarch'):
    return dict(game_title=name, platform=platform, mode=mode, emulator='RetroArch',
                emulator_version='1.22', players=1, max_players=2, host='Host',
                core_name='Snes9x', core_version='1', notes='Test lobby')

def test_filtering_clears_hidden_selection(app):
    app.rooms = {'one': room('Pixel Rally'), 'two': room('Ocean', 'Nintendo GameCube', 'dolphin')}
    app.render_lobbies()
    app.lobby_tree.selection_set('one')
    app.choose_lobby()
    assert 'Pixel Rally' in app.detail_title.get()
    app.search_var.set('ocean')
    app.update()
    assert app.lobby_tree.get_children() == ('two',)
    assert app.selected_lobby_id() is None
    assert app.detail_title.get() == 'Select a lobby'
    assert not app.join_button.instate(['!disabled'])

def test_filters_and_navigation(app):
    app.rooms = {'one': room('Pixel Rally'), 'two': room('Ocean', 'Nintendo GameCube', 'dolphin')}
    app.platform_filter.set('Nintendo SNES')
    app.mode_filter.set('dolphin')
    app.render_lobbies()
    assert not app.lobby_tree.get_children()
    app.mode_filter.set('All play methods')
    app.render_lobbies()
    assert app.lobby_tree.get_children() == ('one',)
    for page in app.nav_buttons:
        app.show_page(page)
        app.update()
        assert app.notebook.select() == str(page)
    assert app.identity_var.get() == 'Not signed in'
    app.username = 'Player'
    app.api.token = 'test-session'
    app.update_identity()
    assert 'Player' in app.identity_var.get()
    app.logout_local()
    assert app.identity_var.get() == 'Not signed in'

def test_selected_room_disappears_and_signout_clears_join_data(app):
    app.api.token = 'session'
    app.rooms = {'one': room('Pixel Rally')}
    app.render_lobbies()
    app.lobby_tree.selection_set('one')
    app.choose_lobby()
    assert app.join_button.instate(['!disabled'])
    app.rooms = {}
    app.render_lobbies()
    assert app.detail_title.get() == 'Select a lobby'
    assert app.join_button.instate(['disabled'])
    app.rooms = {'one': room('Pixel Rally')}
    app.render_lobbies()
    app.logout_local()
    assert not app.lobby_tree.get_children()
    assert app.notebook.select() == str(app.account_tab)
