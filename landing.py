"""Read-only landing page for the hub, so its status is visible in a browser.

The hub is an API for the RetroRelay desktop client; this page only reports what
the hub already knows (health, catalog, database location) and links to the
interactive API docs. It stores nothing and changes no lobby behaviour.
"""
from __future__ import annotations

from catalog import MODES, PLATFORMS

VERSION = "0.1.0"


def landing_page(db_path: str) -> str:
    platforms = len(PLATFORMS)
    modes = len(MODES)
    listed_modes = "".join(
        f"<li><code>{name}</code><span>{description}</span></li>"
        for name, description in MODES.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RetroRelay Hub</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 2.5rem 1.25rem; background: #0f1724; color: #e7eef9;
    font: 15px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }}
  main {{ max-width: 780px; margin: 0 auto; }}
  header {{ display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; }}
  h1 {{ font-size: 1.6rem; margin: 0; letter-spacing: -.01em; }}
  .pill {{
    background: rgba(85, 214, 190, .14); color: #55d6be; border: 1px solid rgba(85, 214, 190, .4);
    border-radius: 999px; padding: .15rem .7rem; font-size: .8rem; font-weight: 600;
  }}
  .lead {{ color: #a3b3ca; margin: 1rem 0 1.75rem; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: .75rem; }}
  .card {{
    background: #162132; border: 1px solid #22334b; border-radius: 12px; padding: 1rem;
  }}
  .card b {{ display: block; font-size: 1.35rem; color: #55d6be; }}
  .card span {{ color: #a3b3ca; font-size: .85rem; }}
  h2 {{ font-size: 1rem; margin: 2rem 0 .75rem; text-transform: uppercase; letter-spacing: .08em; color: #a3b3ca; }}
  ul.modes {{ list-style: none; margin: 0; padding: 0; }}
  ul.modes li {{ padding: .6rem .85rem; background: #162132; border: 1px solid #22334b; border-radius: 10px; margin-bottom: .5rem; }}
  ul.modes span {{ display: block; color: #a3b3ca; font-size: .88rem; }}
  code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #55d6be; }}
  .links {{ display: flex; flex-wrap: wrap; gap: .6rem; margin-top: .5rem; }}
  a.button {{
    display: inline-block; text-decoration: none; color: #e7eef9; background: #162132;
    border: 1px solid #2f4665; border-radius: 10px; padding: .5rem .9rem; font-weight: 600;
  }}
  a.button:hover {{ border-color: #55d6be; }}
  .note {{ margin-top: 2rem; padding: 1rem; border-left: 3px solid #55d6be; background: #162132; border-radius: 0 10px 10px 0; color: #a3b3ca; }}
  footer {{ margin-top: 2rem; color: #7d8ca5; font-size: .85rem; }}
</style>
</head>
<body>
<main>
  <header>
    <h1>RetroRelay Hub</h1>
    <span class="pill">online &middot; v{VERSION}</span>
  </header>

  <p class="lead">
    Account, room, chat and readiness server for the RetroRelay desktop client. It matches
    players and enforces game-file fingerprints; it never relays games, ROMs or traffic.
  </p>

  <section class="stats">
    <div class="card"><b>{platforms}</b><span>supported platforms</span></div>
    <div class="card"><b>{modes}</b><span>play methods</span></div>
    <div class="card"><b>SQLite</b><span>database at <code>{db_path}</code></span></div>
  </section>

  <h2>Play methods</h2>
  <ul class="modes">{listed_modes}</ul>

  <h2>Hub API</h2>
  <div class="links">
    <a class="button" href="/docs">Interactive API docs (/docs)</a>
    <a class="button" href="/health">Health (/health)</a>
    <a class="button" href="/catalog">Catalog (/catalog)</a>
  </div>

  <p class="note">
    The RetroRelay client (<code>client.py</code>) is a Tkinter desktop app for Windows and
    Linux &mdash; it runs on your own PC with an emulator installed, so it is not served in a
    browser preview. Point it at this hub to register accounts and open lobbies.
  </p>

  <footer>Starter v{VERSION} &mdash; early source preview, not hardened for open public registration.</footer>
</main>
</body>
</html>
"""
