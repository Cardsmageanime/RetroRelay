# AGENTS.md — running RetroRelay in the Base44 sandbox

Notes that are not obvious from the manifests. RetroRelay is a Python **hub server**
(`server.py`, FastAPI + SQLite, port 8751) plus a **Tkinter desktop client** (`client.py`).

## Sandbox dev environment

```bash
docker compose -f docker-compose.base44.yml up -d --build   # start (host port 3000 -> hub 8751)
docker compose -f docker-compose.base44.yml logs -f hub      # follow logs
docker compose -f docker-compose.base44.yml exec hub python -m pytest -q   # tests
```

- `docker-compose.base44.yml` + `Dockerfile.base44` are **sandbox-only**. `Dockerfile.base44`
  installs dependencies only; the source is bind-mounted at `/app` and uvicorn runs with
  `--reload` (its polling `StatReload`, which sees sandbox-side edits on the bind mount), so
  source edits appear without rebuilding. There are no `BASE44_PREVIEW_MODE`-gated code paths
  in this repo — the stack runs identically with the flag set or unset.
- The sandbox image also installs the Tk shared libraries: `tests/test_app.py` imports
  `client.py`, which imports `tkinter`, so the suite fails to collect without them.
- The repo's own `Dockerfile`/`compose.yaml` are the **public deployment** path (prebuilt
  image + Caddy HTTPS on ports 80/443 with a `DOMAIN` from `.env`). Do not use them for the
  sandbox: that image bakes the source in, so edits would never show.
- **No external credentials are required.** Accounts, rooms and chat live in SQLite at
  `/appdata/lobbies.sqlite3` (the `hub_data` named volume, outside the repo). `DOMAIN` in
  `.env.example` is only for the optional public Caddy deployment.
- The **desktop client cannot be previewed in a browser**: it is a Tkinter GUI that needs a
  display and locally installed emulators. Preview the hub instead. The hub has no root route
  in the original source, so `landing.py` serves a read-only status page at `/` (health,
  catalog, database location, links to `/docs`); it changes no lobby behaviour.
- Live check that the served frontend is the working tree, not a bundle: after editing
  `landing.py`, the page text at `/` changes without a rebuild.

## Verifying the hub

`/health` returns `{"online": true, ...}`. `/docs` is the FastAPI Swagger UI, which can drive
`/register`, `/login`, `/rooms`, `/rooms/{id}/join`, `/rooms/{id}/chat` etc. by hand.
`tests/test_app.py` covers the account/room/chat flow and the client's file hashing; it needs
`requirements-dev.txt` (installed in `Dockerfile.base44`).
