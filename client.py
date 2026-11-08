"""RetroRelay desktop companion: account, discovery, matching, chat and launch helpers.

Uses the PC's existing Internet/Wi-Fi connection; it does not create wireless hardware
or magically add a network stack to an emulator.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from urllib.parse import urlsplit
from pathlib import Path
from tkinter import filedialog, messagebox, ttk, font as tkfont

from catalog import MODES, PLATFORMS, compatible_mode

CONFIG_DIR = Path.home() / ".retrorelay_client"
CONFIG_FILE = CONFIG_DIR / "settings.json"
DEFAULT_CONFIG = {"server": "http://127.0.0.1:8751", "profiles": {}}
BG = "#0f1724"
PANEL = "#162132"
FG = "#e7eef9"
SUBTLE = "#a3b3ca"
ACCENT = "#55d6be"


def game_fingerprint(path_string: str) -> str:
    """Exact SHA-256 bytes for a file, or stable entire-tree SHA-256 for a folder.

    For multi-file PS3 game folders or BIN/CUE disc folders, select the folder.
    This can take a long time for large games because it checks every byte.
    """
    if not path_string or not path_string.strip():
        raise ValueError("Choose your game file or folder first")
    path = Path(path_string).expanduser()
    if not path.exists():
        raise ValueError("Game file/folder not found")
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as inp:
            for chunk in iter(lambda: inp.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
    elif path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file() and not p.is_symlink())
        if not files:
            raise ValueError("Game folder is empty")
        digest.update(b"RETRORELAY-TREE-V1\0")
        for f in files:
            rel = f.relative_to(path).as_posix().encode("utf-8")
            digest.update(len(rel).to_bytes(8, "big"))
            digest.update(rel)
            digest.update(f.stat().st_size.to_bytes(8, "big"))
            with f.open("rb") as inp:
                for chunk in iter(lambda: inp.read(4 * 1024 * 1024), b""):
                    digest.update(chunk)
    else:
        raise ValueError("Select a normal file or directory")
    return digest.hexdigest()


def read_settings():
    if CONFIG_FILE.is_file():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and isinstance(cfg.get("profiles"), dict):
                return cfg
        except (ValueError, OSError):
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_settings(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Settings contain emulator paths and version strings; no account passwords/tokens.
    CONFIG_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def profile_key(platform: str, emulator: str) -> str:
    return platform + "::" + emulator


def launch_commands(room: dict, profile: dict, game_path: str, is_host: bool):
    """Return a subprocess argument list. Never invoke a shell or evaluate user text."""
    executable = profile.get("executable", "").strip()
    if not executable:
        raise ValueError("Set your emulator executable in Setup first")
    if not (Path(executable).is_file() or shutil.which(executable)):
        raise ValueError("Emulator executable not found: " + executable)
    mode = room["mode"]
    if mode == "retroarch":
        core_path = profile.get("core_path", "").strip()
        if not core_path or not Path(core_path).is_file():
            raise ValueError("Select the installed RetroArch .dll/.so core in Setup")
        command = [executable, "-L", core_path]
        if is_host:
            command += ["--host"]
        else:
            address = room.get("connection_hint", "").strip()
            # Public DNS or VPN IP, optionally :port. Do not allow arbitrary CLI flags.
            if not re.fullmatch(r"[A-Za-z0-9.\-\[\]:]+", address) or address.startswith("-"):
                raise ValueError("Host must set a safe IP/hostname[:port] connection address")
            parts = address.rsplit(":", 1)
            if len(parts) == 2 and parts[-1].isdigit():
                address, port = parts[0], int(parts[-1])
            else:
                port = 55435
            if port < 1 or port > 65535:
                raise ValueError("Invalid network port")
            command += ["--connect", address, "--port", str(port)]
        if is_host:
            address = room.get("connection_hint", "").strip()
            parts = address.rsplit(":", 1)
            if len(parts) == 2 and parts[-1].isdigit():
                port = int(parts[-1])
                if 1 <= port <= 65535:
                    command += ["--port", str(port)]
        command.append(game_path)
        return command
    # Other emulators vary in CLI options. Starting their GUI is safe and correct;
    # they need their own manual online game/netplay setup.
    return [executable]


class APIError(Exception):
    pass


class API:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.token = None

    def call(self, method, route, body=None):
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + route, data=encoded, method=method)
        req.add_header("Accept", "application/json")
        if encoded is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            try:
                detail = json.loads(err.read().decode("utf-8")).get("detail", "Request failed")
                if isinstance(detail, list):
                    detail = "; ".join(str(e.get("msg", e)) for e in detail)
            except Exception:
                detail = str(err)
            raise APIError(str(detail)) from err
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise APIError("Cannot reach the lobby server. Check Wi-Fi/Internet and server URL. " + str(err)) from err


class RetroRelayApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RetroRelay | Classic Multiplayer Hub")
        self.geometry(f"{min(1672, max(1180, self.winfo_screenwidth() - 48))}x{min(890, max(780, self.winfo_screenheight() - 80))}")
        self.minsize(1180, 780)
        self.configure(bg=BG)
        self.settings = read_settings()
        self.api = API(self.settings.get("server") or DEFAULT_CONFIG["server"])
        self.username = None
        self.current_room = None
        self.rooms = {}
        self.last_msg_id = 0
        self.current_ready = False
        self.room_polling = False
        self.lobby_polling = False
        self.status_var = tk.StringVar(value="Offline | log in to connect to the lobby server")
        self.setup_style()
        self.build_ui()
        self.after(5000, self.poll)

    def setup_style(self):
        families = set(tkfont.families(self))
        self.ui_font = next((name for name in ("Segoe UI", "Liberation Sans", "Arial", "Noto Sans", "Noto Sans Display", "DejaVu Sans")
                             if name in families), "Arial")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG, font=(self.ui_font, 11))
        style.configure("Header.TLabel", background=BG, foreground=FG, font=(self.ui_font, 21, "bold"))
        style.configure("Small.TLabel", background=BG, foreground="#bdcbe0", font=(self.ui_font, 10))
        style.configure("TButton", font=(self.ui_font, 10, "bold"), padding=(12, 7), background="#263c54",
                        foreground=FG, borderwidth=0, relief="flat", bordercolor="#263c54",
                        lightcolor="#263c54", darkcolor="#263c54")
        style.map("TButton", background=[("active", "#34536e")], foreground=[("disabled", SUBTLE)])
        style.configure("Accent.TButton", background="#1da994", foreground="#ffffff", font=(self.ui_font, 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#188777")])
        style.configure("TEntry", padding=7, fieldbackground=PANEL, foreground=FG,
                        insertcolor=FG, bordercolor="#34536e", lightcolor=PANEL, darkcolor=PANEL)
        style.configure("TCombobox", padding=7, fieldbackground=PANEL, background="#263c54", arrowcolor=FG)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", FG)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(20, 11), background=PANEL, foreground=FG)
        style.map("TNotebook.Tab", background=[("selected", "#28415a")], foreground=[("selected", "white")])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=31, borderwidth=0)
        style.configure("Treeview.Heading", background="#263c54", foreground=FG, font=(self.ui_font, 10, "bold"))
        style.map("Treeview", background=[("selected", "#275867")], foreground=[("selected", "white")])
        style.configure("TSpinbox", padding=5)
        style.layout("Sidebar.TNotebook.Tab", [])
        style.configure("Sidebar.TNotebook", background=BG, borderwidth=0)
        style.layout("Sidebar.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
        style.configure("Nav.TButton", font=(self.ui_font, 16, "bold"), anchor="w", padding=(14, 12), background=PANEL, foreground=FG)
        style.map("Nav.TButton", background=[("pressed", "#275867"), ("active", "#263c54")])
        style.configure("Selected.Nav.TButton", font=(self.ui_font, 16, "bold"), anchor="w", padding=(14, 12), background="#21616d", foreground="#ffffff")
        style.configure("Title.TLabel", background=BG, foreground="#f6f8fc", font=(self.ui_font, 36, "bold"))
        style.configure("Brand.TLabel", background=BG, foreground="#f6f8fc", font=(self.ui_font, 34, "bold"))
        style.configure("Subtitle.TLabel", background=BG, foreground=FG, font=(self.ui_font, 14))
        style.configure("Discover.TButton", font=(self.ui_font, 13, "bold"), padding=(12, 7))
        style.configure("Discover.Accent.TButton", font=(self.ui_font, 13, "bold"), padding=(16, 7))
        style.configure("Discover.Field.TLabel", font=(self.ui_font, 13, "bold"))
        style.configure("Discover.Treeview", rowheight=68, font=(self.ui_font, 12, "bold"))
        style.configure("Discover.Treeview.Heading", font=(self.ui_font, 12, "bold"), padding=(8, 9))
        style.configure("Discover.TEntry", padding=6, font=(self.ui_font, 13), bordercolor="#8fa8bf")
        style.configure("Discover.TCombobox", padding=6, font=(self.ui_font, 12, "bold"), bordercolor="#c1cedb")
        style.map("Discover.Accent.TButton", background=[("disabled", "#1ba99e"), ("active", "#159e95")],
                  foreground=[("disabled", "#a0d4d1")])
        style.configure("Card.TLabel", background=PANEL, foreground=FG, font=(self.ui_font, 14, "bold"))
        style.configure("CardTitle.TLabel", background=PANEL, foreground=FG, font=(self.ui_font, 28, "bold"))
        style.configure("CardMuted.TLabel", background=PANEL, foreground=FG, font=(self.ui_font, 14))
        style.configure("Treeview", rowheight=68, font=(self.ui_font, 11, "bold"))
        style.configure("Treeview.Heading", padding=(8, 12), font=(self.ui_font, 10, "bold"))
        style.configure("Field.TLabel", background=BG, foreground=FG, font=(self.ui_font, 10, "bold"))
        style.configure("TEntry", font=(self.ui_font, 11))
        style.configure("TCombobox", font=(self.ui_font, 10))
        self.option_add("*TCombobox*Listbox.font", (self.ui_font, 10))

    def label(self, parent, text, r, c=0, sticky="w", width=None):
        lbl = ttk.Label(parent, text=text, style="Field.TLabel")
        lbl.grid(row=r, column=c, sticky=sticky, padx=7, pady=7)
        return lbl

    def entry(self, parent, variable, r, c=1, width=52, show=None):
        ent = ttk.Entry(parent, textvariable=variable, width=width, show=show or "")
        ent.grid(row=r, column=c, sticky="ew", padx=7, pady=7)
        return ent

    def section(self, parent, text):
        ttk.Label(parent, text=text, style="Header.TLabel").pack(anchor="w", pady=(8, 14))

    def build_ui(self):
        header = ttk.Frame(self, padding=(30, 8))
        header.pack(fill="x")
        brand = ttk.Frame(header)
        brand.pack(side="left")
        ttk.Label(brand, text="RETRORELAY", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(brand, text="Classic Multiplayer Hub", style="Subtitle.TLabel").pack(anchor="w")
        self.identity_var = tk.StringVar(value="Not signed in")
        ttk.Label(header, textvariable=self.identity_var, style="Subtitle.TLabel").pack(side="right", padx=12)
        ttk.Separator(self).pack(fill="x")
        footer = ttk.Frame(self, padding=(24, 10))
        footer.pack(side="bottom", fill="x")
        ttk.Label(footer, textvariable=self.status_var, style="Subtitle.TLabel").pack(side="left")
        shell = ttk.Frame(self)
        shell.pack(fill="both", expand=True)
        sidebar = ttk.Frame(shell, style="Panel.TFrame", width=270, padding=(12, 22))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self.notebook = ttk.Notebook(shell, style="Sidebar.TNotebook", takefocus=False)
        self.notebook.pack(side="left", fill="both", expand=True, padx=(16, 16), pady=16)
        self.account_tab = ttk.Frame(self.notebook, padding=12)
        self.setup_tab = ttk.Frame(self.notebook, padding=12)
        self.host_tab = ttk.Frame(self.notebook, padding=12)
        self.discover_tab = ttk.Frame(self.notebook, padding=(16, 0, 12, 12))
        self.room_tab = ttk.Frame(self.notebook, padding=12)
        self.library_tab = ttk.Frame(self.notebook, padding=12)
        self.nav_buttons = {}
        for name, page in [
            ("Find Games", self.discover_tab), ("Host Game", self.host_tab),
            ("Waiting Room", self.room_tab), ("Emulator Setup", self.setup_tab),
            ("Library &\nAchievements", self.library_tab), ("Account & Security", self.account_tab),
        ]:
            self.notebook.add(page, text=name)
            button = ttk.Button(sidebar, text=name, style="Nav.TButton",
                                command=lambda target=page: self.show_page(target))
            button.pack(fill="x", pady=5)
            self.nav_buttons[page] = button
        self.notebook.bind("<<NotebookTabChanged>>", self.sync_navigation)
        self.build_account()
        self.build_setup()
        self.build_host()
        self.build_discover()
        self.build_room()
        self.build_library()
        self.show_page(self.discover_tab)

    def show_page(self, page):
        self.notebook.select(page)
        self.sync_navigation()

    def sync_navigation(self, _event=None):
        for page, button in self.nav_buttons.items():
            button.configure(style="Selected.Nav.TButton" if self.notebook.select() == str(page) else "Nav.TButton")

    def update_identity(self):
        self.identity_var.set(self.username if self.username and self.api.token else "Not signed in")

    def build_library(self):
        self.section(self.library_tab, "Library & Achievements")
        ttk.Label(self.library_tab, text="Planned for December 2026 | provider connections are not implemented yet.",
                  style="Small.TLabel", wraplength=780).pack(anchor="w", pady=(0, 24))
        for provider in ("Steam", "GOG GALAXY", "Epic Games", "RetroAchievements"):
            card = ttk.Frame(self.library_tab, style="Panel.TFrame", padding=18)
            card.pack(fill="x", pady=6)
            ttk.Label(card, text=provider, style="Card.TLabel").pack(side="left")
            ttk.Label(card, text="Planned | not connected", style="CardMuted.TLabel").pack(side="right")

    def build_account(self):
        t = self.account_tab
        self.section(t, "Account & Security")
        ttk.Label(t, text="Passwords are not saved by this desktop client. Public servers require HTTPS.\n"
                  "Phone authenticator setup is not available in this build.", style="Small.TLabel").pack(anchor="w", pady=(0, 16))
        ttk.Label(t, text="Your account lives on the RetroRelay lobby server. No game files are uploaded.",
                  style="Small.TLabel").pack(anchor="w", pady=(0, 16))
        form = ttk.Frame(t)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.server_var = tk.StringVar(value=self.api.base)
        self.login_user = tk.StringVar()
        self.login_pass = tk.StringVar()
        self.label(form, "Lobby server URL", 0)
        self.entry(form, self.server_var, 0)
        self.label(form, "Username", 1)
        self.entry(form, self.login_user, 1)
        self.label(form, "Password", 2)
        self.entry(form, self.login_pass, 2, show="*")
        buttons = ttk.Frame(t)
        buttons.pack(anchor="w", pady=20)
        ttk.Button(buttons, text="Log in", style="Accent.TButton", command=self.login).pack(side="left", padx=(0, 10))
        ttk.Button(buttons, text="Create account", command=self.register).pack(side="left", padx=(0, 10))
        ttk.Button(buttons, text="Test server", command=self.test_connection).pack(side="left", padx=(0, 10))
        ttk.Button(buttons, text="Log out", command=self.logout).pack(side="left")
        ttk.Label(t, text="First test: run the hub server on your own PC and keep http://127.0.0.1:8751.\n"
                  "For friends over the Internet, deploy the hub with HTTPS and use its public URL.\n"
                  "Every player uses the same lobby server URL.", style="Small.TLabel", justify="left").pack(anchor="w", pady=10)

    def make_combos(self, parent, platform_var, emu_var, row):
        self.label(parent, "Console / platform", row)
        platform = ttk.Combobox(parent, textvariable=platform_var, values=list(PLATFORMS), state="readonly", width=38)
        platform.grid(row=row, column=1, sticky="ew", padx=7, pady=7)
        self.label(parent, "Emulator", row+1)
        emu = ttk.Combobox(parent, textvariable=emu_var, values=[], state="readonly", width=38)
        emu.grid(row=row+1, column=1, sticky="ew", padx=7, pady=7)

        def update_emus(*_):
            options = PLATFORMS.get(platform_var.get(), [])
            emu["values"] = options
            if emu_var.get() not in options:
                emu_var.set(options[0] if options else "")
        platform_var.trace_add("write", update_emus)
        if not platform_var.get():
            platform_var.set("Nintendo SNES")
        update_emus()
        return platform, emu

    def build_setup(self):
        t = self.setup_tab
        self.section(t, "Choose your installed emulator")
        ttk.Label(t, text="Players must use identical emulator versions and game files. RetroArch users also match core versions.",
                  style="Small.TLabel").pack(anchor="w", pady=(0, 12))
        form = ttk.Frame(t)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.sp_platform = tk.StringVar(value="Nintendo SNES")
        self.sp_emu = tk.StringVar(value="RetroArch")
        self.make_combos(form, self.sp_platform, self.sp_emu, 0)
        self.sp_exe = tk.StringVar()
        self.sp_version = tk.StringVar()
        self.sp_core = tk.StringVar()
        self.sp_core_version = tk.StringVar()
        self.sp_core_path = tk.StringVar()
        self.label(form, "Emulator executable", 2)
        self.entry(form, self.sp_exe, 2)
        ttk.Button(form, text="Browse", command=lambda: self.pick_file(self.sp_exe)).grid(row=2,column=2,padx=7)
        self.label(form, "Installed emulator version", 3)
        self.entry(form, self.sp_version, 3)
        self.label(form, "RetroArch core name", 4)
        self.entry(form, self.sp_core, 4)
        self.label(form, "RetroArch core version", 5)
        self.entry(form, self.sp_core_version, 5)
        self.label(form, "RetroArch core .dll / .so", 6)
        self.entry(form, self.sp_core_path, 6)
        ttk.Button(form, text="Browse", command=lambda: self.pick_file(self.sp_core_path)).grid(row=6,column=2,padx=7)
        self.sp_platform.trace_add("write", lambda *_: self.load_profile())
        self.sp_emu.trace_add("write", lambda *_: self.load_profile())
        buttons = ttk.Frame(t)
        buttons.pack(anchor="w", pady=12)
        ttk.Button(buttons, text="Save emulator profile", style="Accent.TButton", command=self.save_profile).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Auto-find executable", command=self.autofind).pack(side="left")
        ttk.Label(t, text="Tip: Emulator version is entered manually in this starter. Read it in your emulator's About screen.\n"
                  "RetroArch netplay also requires the EXACT same core (name, build and settings).\n"
                  "No ROMs, BIOS files or paid games are included in the project.", style="Small.TLabel", justify="left").pack(anchor="w", pady=15)
        self.load_profile()

    def build_host(self):
        t = self.host_tab
        self.section(t, "Create a game waiting room")
        form = ttk.Frame(t)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.h_platform = tk.StringVar(value="Nintendo SNES")
        self.h_emu = tk.StringVar(value="RetroArch")
        self.make_combos(form, self.h_platform, self.h_emu, 0)
        self.h_title = tk.StringVar()
        self.h_path = tk.StringVar()
        self.h_mode = tk.StringVar(value="retroarch")
        self.h_hint = tk.StringVar()
        self.h_notes = tk.StringVar()
        self.h_max = tk.IntVar(value=2)
        self.label(form, "Game name", 2)
        self.entry(form, self.h_title, 2)
        self.label(form, "My matching game file / folder", 3)
        self.entry(form, self.h_path, 3)
        pickers = ttk.Frame(form)
        pickers.grid(row=3,column=2,sticky="w")
        ttk.Button(pickers, text="File", command=lambda: self.pick_file(self.h_path)).pack(side="left")
        ttk.Button(pickers, text="Folder", command=lambda: self.pick_folder(self.h_path)).pack(side="left")
        self.label(form, "Play method", 4)
        modes = ttk.Combobox(form, values=list(MODES), textvariable=self.h_mode, state="readonly")
        modes.grid(row=4, column=1, sticky="ew", padx=7, pady=7)
        self.label(form, "Connect info (IP, code, or link)", 5)
        self.entry(form, self.h_hint, 5)
        self.label(form, "Room description", 6)
        self.entry(form, self.h_notes, 6)
        self.label(form, "Maximum players", 7)
        ttk.Spinbox(form, from_=2, to=16, textvariable=self.h_max, width=6).grid(row=7,column=1,sticky="w",padx=7,pady=7)
        ttk.Button(t, text="Create room + check my game", style="Accent.TButton", command=self.host_game).pack(anchor="w", pady=(20, 10))
        self.host_note = tk.StringVar(value="For RetroArch, give friends your reachable IP or VPN IP (e.g. 10.0.0.5:55435).")
        ttk.Label(t, textvariable=self.host_note, style="Small.TLabel", wraplength=850).pack(anchor="w")
        self.h_mode.trace_add("write", lambda *_: self.host_note.set(MODES.get(self.h_mode.get(), "")))

    def build_discover(self):
        t = self.discover_tab
        ttk.Label(t, text="Find Games", style="Title.TLabel").pack(anchor="w")
        ttk.Label(t, text="Find a compatible lobby and play together.", style="Subtitle.TLabel").pack(anchor="w", pady=(4, 16))
        toolbar = ttk.Frame(t)
        toolbar.pack(fill="x", pady=(0, 16))
        toolbar.columnconfigure(0, weight=1)
        self.search_var = tk.StringVar()
        self.platform_filter = tk.StringVar(value="All platforms")
        self.mode_filter = tk.StringVar(value="All play methods")
        search = ttk.Entry(toolbar, textvariable=self.search_var, width=20, style="Discover.TEntry", font=(self.ui_font, 13))
        search.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        # Visible label remains available to keyboard and screen-reader users.
        ttk.Label(toolbar, text="Search games or hosts", style="Discover.Field.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(toolbar, textvariable=self.platform_filter, values=["All platforms", *PLATFORMS],
                     state="readonly", width=17, style="Discover.TCombobox", font=(self.ui_font, 12, "bold")).grid(row=0, column=1, padx=4)
        ttk.Combobox(toolbar, textvariable=self.mode_filter, values=["All play methods", *MODES],
                     state="readonly", width=17, style="Discover.TCombobox", font=(self.ui_font, 12, "bold")).grid(row=0, column=2, padx=4)
        ttk.Button(toolbar, text="Refresh", style="Discover.Accent.TButton", command=self.refresh_lobbies).grid(row=0, column=3, padx=(8, 0))
        body = ttk.Frame(t)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=340, weight=0)
        body.rowconfigure(0, weight=1)
        listing = ttk.Frame(body)
        listing.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        listing.rowconfigure(0, weight=1)
        listing.columnconfigure(0, weight=1)
        columns = ("game", "console", "mode", "players")
        self.lobby_tree = ttk.Treeview(listing, columns=columns, show="headings", selectmode="browse", height=6, style="Discover.Treeview")
        for col, label, width in [("game", "GAME / ROOM", 280), ("console", "PLATFORM", 180),
                                  ("mode", "METHOD", 120), ("players", "PLAYERS", 95)]:
            self.lobby_tree.heading(col, text=label)
            self.lobby_tree.column(col, width=width, minwidth=width, stretch=col in ("game", "console"))
        self.lobby_tree.tag_configure("alternate", background="#1b2b3d")
        self.lobby_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.lobby_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.lobby_tree.configure(yscrollcommand=scroll.set)
        horizontal = ttk.Scrollbar(listing, orient="horizontal", command=self.lobby_tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.lobby_tree.configure(xscrollcommand=horizontal.set)
        self.results_var = tk.StringVar(value="Log in through Account & Security to discover live lobbies.")
        results_label = ttk.Label(listing, textvariable=self.results_var, style="Subtitle.TLabel", wraplength=900)
        results_label.grid(row=2, column=0, sticky="w", pady=12)
        listing.bind("<Configure>", lambda event: results_label.configure(wraplength=max(180, event.width - 20)))
        self.lobby_tree.bind("<<TreeviewSelect>>", self.choose_lobby)
        detail_shell = ttk.Frame(body, style="Panel.TFrame")
        detail_shell.grid(row=0, column=1, sticky="nsew")
        detail_canvas = tk.Canvas(detail_shell, background=PANEL, highlightthickness=0, width=370)
        detail_scroll = ttk.Scrollbar(detail_shell, orient="vertical", command=detail_canvas.yview)
        detail_scroll.pack(side="right", fill="y")
        detail_canvas.pack(side="left", fill="both", expand=True)
        detail_canvas.configure(yscrollcommand=detail_scroll.set)
        detail = ttk.Frame(detail_canvas, style="Panel.TFrame", padding=(16, 10))
        detail_window = detail_canvas.create_window(0, 0, window=detail, anchor="nw")
        detail.bind("<Configure>", lambda _: detail_canvas.configure(scrollregion=detail_canvas.bbox("all")))
        detail_canvas.bind("<Configure>", lambda event: detail_canvas.itemconfigure(detail_window, width=event.width))
        self.detail_title = tk.StringVar(value="Select a lobby")
        ttk.Label(detail, textvariable=self.detail_title, style="CardTitle.TLabel", wraplength=338).pack(anchor="w", pady=(0, 8))
        self.lobby_desc = tk.StringVar(value="Choose a room to view its platform and emulator requirements.")
        ttk.Label(detail, textvariable=self.lobby_desc, style="Card.TLabel", wraplength=338, justify="left").pack(anchor="w")
        ttk.Separator(detail).pack(fill="x", pady=10)
        ttk.Label(detail, text="Select your local game to check compatibility.", style="CardMuted.TLabel", wraplength=338).pack(anchor="w", pady=(0, 8))
        self.join_path = tk.StringVar()
        ttk.Entry(detail, textvariable=self.join_path, width=26, style="Discover.TEntry", font=(self.ui_font, 13)).pack(fill="x", pady=(0, 8))
        pickers = ttk.Frame(detail, style="Panel.TFrame")
        pickers.pack(fill="x")
        ttk.Button(pickers, text="Choose file", style="Discover.TButton", command=lambda: self.pick_file(self.join_path)).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(pickers, text="Folder", style="Discover.TButton", command=lambda: self.pick_folder(self.join_path)).pack(side="left")
        self.join_button = ttk.Button(detail, text="Verify & Join", style="Discover.Accent.TButton", command=self.join_game, state="disabled")
        self.join_button.pack(fill="x", pady=8)
        self.profile_status = tk.StringVar(value="Select a lobby to check your emulator profile.")
        ttk.Label(detail, text="Your emulator", style="Card.TLabel").pack(anchor="w", pady=(10, 6))
        ttk.Label(detail, textvariable=self.profile_status, style="CardMuted.TLabel", wraplength=338).pack(anchor="w")
        ttk.Button(detail, text="Manage setup", style="Discover.TButton", command=self.setup_selected).pack(fill="x", pady=(8, 0))
        for variable in (self.search_var, self.platform_filter, self.mode_filter):
            variable.trace_add("write", lambda *_: self.render_lobbies())

    def render_lobbies(self):
        selected = self.selected_lobby_id()
        query = self.search_var.get().strip().casefold()
        platform = self.platform_filter.get()
        mode = self.mode_filter.get()
        self.lobby_tree.delete(*self.lobby_tree.get_children())
        for room_id, room in self.rooms.items():
            if query and query not in (room["game_title"] + " " + room["host"]).casefold():
                continue
            if platform != "All platforms" and platform != room["platform"]:
                continue
            if mode != "All play methods" and mode != room["mode"]:
                continue
            self.lobby_tree.insert("", "end", iid=room_id, values=(room["game_title"], room["platform"],
                room["mode"], f"{room['players']} / {room['max_players']}"),
                tags=("alternate",) if len(self.lobby_tree.get_children()) % 2 else ())
        if selected and self.lobby_tree.exists(selected):
            self.lobby_tree.selection_set(selected)
        self.choose_lobby()
        count = len(self.lobby_tree.get_children())
        self.results_var.set(f"{count} matching lobby/lobbies" if count else
                            ("No matching lobbies. Adjust filters or host a game." if self.api.token else
                             "Log in through Account & Security to discover live lobbies."))

    def build_room(self):
        t = self.room_tab
        self.section(t, "Your waiting room")
        self.room_heading = tk.StringVar(value="No active room. Host a game or join an existing lobby.")
        ttk.Label(t, textvariable=self.room_heading, wraplength=950).pack(anchor="w", pady=5)
        self.members_heading = tk.StringVar(value="Players: -")
        ttk.Label(t, textvariable=self.members_heading).pack(anchor="w", pady=5)
        self.connect_heading = tk.StringVar(value="Connection: -")
        ttk.Label(t, textvariable=self.connect_heading, style="Small.TLabel", wraplength=970).pack(anchor="w", pady=5)
        tools = ttk.Frame(t)
        tools.pack(anchor="w", pady=(10, 5))
        ttk.Button(tools, text="I'm ready / not ready", command=self.toggle_ready).pack(side="left", padx=(0, 8))
        ttk.Button(tools, text="Launch emulator / play", style="Accent.TButton", command=self.start_play).pack(side="left", padx=(0, 8))
        ttk.Button(tools, text="Copy room ID", command=self.copy_room_id).pack(side="left", padx=(0, 8))
        ttk.Button(tools, text="Leave / close room", command=self.leave_game).pack(side="left")
        hint = ttk.Frame(t)
        hint.pack(fill="x", pady=(6, 8))
        hint.columnconfigure(1, weight=1)
        self.connection_edit = tk.StringVar()
        self.label(hint, "Host connect details", 0)
        self.entry(hint, self.connection_edit, 0)
        ttk.Button(hint, text="Host: update", command=self.update_connection).grid(row=0,column=2,padx=5)
        self.chat_view = tk.Text(t, height=14, bg=PANEL, fg=FG, insertbackground=FG,
                                 highlightthickness=0, wrap="word", font=(self.ui_font, 11))
        self.chat_view.pack(fill="both", expand=True)
        self.chat_view.configure(state="disabled")
        chat_row = ttk.Frame(t)
        chat_row.pack(fill="x", pady=9)
        self.chat_entry = tk.StringVar()
        chat_row.columnconfigure(0, weight=1)
        ttk.Entry(chat_row, textvariable=self.chat_entry).grid(row=0,column=0,sticky="ew",padx=(0,8))
        ttk.Button(chat_row, text="Send message", style="Accent.TButton", command=self.send_message).grid(row=0,column=1)
        self.bind("<Return>", self.enter_event)

    def enter_event(self, event):
        if self.notebook.select() == str(self.room_tab):
            self.send_message()

    def pick_file(self, variable):
        path = filedialog.askopenfilename(title="Choose an installed emulator, core or game file")
        if path:
            variable.set(path)

    def pick_folder(self, variable):
        path = filedialog.askdirectory(title="Select a game directory (all files are hashed)")
        if path:
            variable.set(path)

    def bg(self, operation, on_success, description):
        self.status_var.set(description)
        def work():
            try:
                result = operation()
                self.after(0, lambda: on_success(result))
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda: self.report_error(message))
        threading.Thread(target=work, daemon=True).start()

    def report_error(self, message):
        self.status_var.set("Error: " + message)
        messagebox.showerror("RetroRelay", message)

    def rebase_api(self):
        url = self.server_var.get().strip().rstrip("/")
        parsed = urlsplit(url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or
                parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError("Enter a valid http:// or https:// server address without a path")
        try:
            local_host = ipaddress.ip_address(parsed.hostname).is_private
        except ValueError:
            local_host = parsed.hostname in ("localhost", "localhost.localdomain")
        if parsed.scheme == "http" and not local_host:
            raise ValueError("Public lobby servers must use HTTPS to protect passwords")
        self.settings["server"] = url
        save_settings(self.settings)
        if self.api.base != url:
            self.api = API(url)
            self.username = None
            self.current_room = None
            self.rooms = {}
            self.render_lobbies()
            self.update_identity()
        return self.api

    def login(self):
        try:
            api = self.rebase_api()
        except ValueError as exc:
            return self.report_error(str(exc))
        def done(res):
            api.token = res["token"]
            self.username = res["username"]
            self.update_identity()
            self.login_pass.set("")
            self.status_var.set("Online | logged in as " + self.username)
            self.notebook.select(self.discover_tab)
            self.refresh_lobbies()
        username, password = self.login_user.get(), self.login_pass.get()
        self.bg(lambda: api.call("POST", "/login", {"username": username,
                   "password": password}), done, "Signing in...")

    def register(self):
        try:
            api = self.rebase_api()
        except ValueError as exc:
            return self.report_error(str(exc))
        username, password = self.login_user.get(), self.login_pass.get()
        self.bg(lambda: api.call("POST", "/register", {"username": username,
                   "password": password}),
                lambda _: messagebox.showinfo("Account created", "Account created. Click Log in."),
                "Creating account...")

    def test_connection(self):
        try:
            api = self.rebase_api()
        except ValueError as exc:
            return self.report_error(str(exc))
        self.bg(lambda: api.call("GET", "/health"),
                lambda _: self.status_var.set("Lobby server is reachable | Internet/network OK"),
                "Checking server connection...")

    def logout(self):
        if not self.api.token:
            return
        self.bg(lambda: self.api.call("POST", "/logout"),
                lambda _: self.logout_local(), "Logging out...")

    def logout_local(self):
        self.api.token = None
        self.username = None
        self.current_room = None
        self.rooms = {}
        self.render_lobbies()
        self.update_identity()
        self.login_pass.set("")
        self.status_var.set("Offline | log in to connect to the lobby server")
        self.notebook.select(self.account_tab)

    def load_profile(self):
        p = self.settings.get("profiles", {}).get(profile_key(self.sp_platform.get(), self.sp_emu.get()), {})
        self.sp_exe.set(p.get("executable", ""))
        self.sp_version.set(p.get("version", ""))
        self.sp_core.set(p.get("core_name", ""))
        self.sp_core_version.set(p.get("core_version", ""))
        self.sp_core_path.set(p.get("core_path", ""))

    def save_profile(self):
        if not self.sp_version.get().strip():
            return self.report_error("Enter the installed emulator version in Setup")
        if self.sp_emu.get() == "RetroArch" and (
            not self.sp_core.get().strip() or not self.sp_core_version.get().strip()
        ):
            return self.report_error("RetroArch needs a core name and core version")
        self.settings.setdefault("profiles", {})[profile_key(self.sp_platform.get(), self.sp_emu.get())] = {
            "executable": self.sp_exe.get().strip(),
            "version": self.sp_version.get().strip(),
            "core_name": self.sp_core.get().strip() if self.sp_emu.get() == "RetroArch" else "",
            "core_version": self.sp_core_version.get().strip() if self.sp_emu.get() == "RetroArch" else "",
            "core_path": self.sp_core_path.get().strip() if self.sp_emu.get() == "RetroArch" else "",
        }
        save_settings(self.settings)
        self.status_var.set("Saved emulator profile: " + self.sp_emu.get())
        messagebox.showinfo("Saved", "Emulator profile saved. You can host or join games now.")

    def autofind(self):
        emulator = self.sp_emu.get()
        search = {
            "RetroArch": ["retroarch", "retroarch.exe"], "Dolphin": ["dolphin-emu", "Dolphin.exe"],
            "Cemu": ["Cemu.exe", "cemu"], "PCSX2": ["pcsx2-qt", "pcsx2.exe"],
            "RPCS3": ["rpcs3", "rpcs3.exe"], "PPSSPP": ["PPSSPPSDL", "PPSSPPWindows64.exe"],
            "Flycast": ["flycast", "flycast.exe"], "xemu": ["xemu", "xemu.exe"],
            "DuckStation": ["duckstation-qt", "duckstation.exe"],
            "Xenia": ["xenia.exe"], "Xenia Canary": ["xenia_canary.exe"],
        }.get(emulator, [emulator.lower().replace(" ", "")])
        for name in search:
            result = shutil.which(name)
            if result:
                self.sp_exe.set(result)
                self.status_var.set("Found: " + result)
                return
        messagebox.showinfo("Not in PATH", "Use Browse to locate the emulator on your computer.")

    def selected_profile(self, platform, emulator):
        profile = self.settings.get("profiles", {}).get(profile_key(platform, emulator))
        if not profile or not profile.get("version"):
            raise ValueError("First configure " + emulator + " for " + platform + " under Emulator Setup")
        return profile

    def host_game(self):
        if not self.api.token:
            return self.report_error("Log in first")
        if self.current_room:
            return self.report_error("Leave your current room before hosting another")
        platform = self.h_platform.get()
        emulator = self.h_emu.get()
        mode = self.h_mode.get()
        if not compatible_mode(platform, emulator, mode):
            return self.report_error("That mode does not work with the selected console/emulator")
        try:
            profile = self.selected_profile(platform, emulator)
        except ValueError as exc:
            return self.report_error(str(exc))
        path = self.h_path.get().strip()
        if Path(path).suffix.lower() in (".cue", ".m3u"):
            return self.report_error("For CUE/BIN or multi-disc sets, select the containing FOLDER, not only the playlist")
        title = self.h_title.get().strip()
        if not title:
            return self.report_error("Enter the name of the game")
        try:
            max_players = int(self.h_max.get())
        except Exception:
            return self.report_error("Maximum players must be from 2 to 16")

        hint, notes = self.h_hint.get(), self.h_notes.get()
        def operation():
            hashcode = game_fingerprint(path)
            return self.api.call("POST", "/rooms", {
                "platform": platform, "emulator": emulator, "emulator_version": profile["version"],
                "core_name": profile.get("core_name", ""), "core_version": profile.get("core_version", ""),
                "game_title": title, "game_sha256": hashcode,
                "mode": mode, "connection_hint": hint,
                "notes": notes, "max_players": max_players,
            })
        def done(result):
            self.current_room = {"id": result["id"], "is_host": True, "platform": platform,
                                 "emulator": emulator, "mode": mode, "connection_hint": hint}
            self.game_path_for_room = path
            self.last_msg_id = 0
            self.clear_chat()
            self.notebook.select(self.room_tab)
            self.refresh_room()
            self.status_var.set("Room " + result["id"] + " created | waiting for friends")
        self.bg(operation, done, "Hashing every byte of your game, then creating lobby...")

    def refresh_lobbies(self, quiet=False):
        if not self.api.token or self.lobby_polling:
            return
        self.lobby_polling = True
        def operation():
            return self.api.call("GET", "/rooms")
        def done(rows):
            self.lobby_polling = False
            self.rooms = {r["id"]: r for r in rows}
            self.render_lobbies()
            if not quiet:
                self.status_var.set(str(len(rows)) + " live lobby/lobbies found")
        def work():
            try:
                result = operation()
                self.after(0, lambda: done(result))
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda: self.fail_lobby(message, quiet))
        threading.Thread(target=work, daemon=True).start()

    def fail_lobby(self, message, quiet):
        self.lobby_polling = False
        if not quiet:
            self.report_error(message)
        else:
            self.status_var.set("Connection interrupted: " + message)

    def selected_lobby_id(self):
        selection = self.lobby_tree.selection()
        return selection[0] if selection else None

    def choose_lobby(self, _event=None):
        room_id = self.selected_lobby_id()
        if not room_id or room_id not in self.rooms:
            self.detail_title.set("Select a lobby")
            self.lobby_desc.set("Choose a room to view its platform and emulator requirements.")
            self.profile_status.set("Select a lobby to check your emulator profile.")
            self.join_button.state(["disabled"])
            return
        room = self.rooms[room_id]
        self.detail_title.set(room["game_title"])
        self.lobby_desc.set(
            f"Hosted by {room['host']}\n\nPlatform: {room['platform']}\n"
            f"Play method: {room['mode']}\nPlayers: {room['players']} of {room['max_players']}\n"
            f"Emulator: {room['emulator']} {room['emulator_version']}"
            + (f"\nCore: {room['core_name']} {room['core_version']}" if room.get("core_name") else "")
            + "\nGame match: Not checked"
            + ("\n\n" + room["notes"] if room.get("notes") else ""))
        profile = self.settings.get("profiles", {}).get(profile_key(room["platform"], room["emulator"]))
        self.profile_status.set(f"{room['emulator']} profile saved" if profile else "Emulator setup required")
        self.join_button.state(["!disabled"] if self.api.token and room['players'] < room['max_players'] else ["disabled"])

    def setup_selected(self):
        room_id = self.selected_lobby_id()
        if not room_id or room_id not in self.rooms:
            return self.report_error("Select a room first")
        room = self.rooms[room_id]
        self.sp_platform.set(room["platform"])
        self.sp_emu.set(room["emulator"])
        self.notebook.select(self.setup_tab)

    def join_game(self):
        if not self.api.token:
            return self.report_error("Log in first")
        if self.current_room:
            return self.report_error("Leave your current room before joining another")
        room_id = self.selected_lobby_id()
        if not room_id or room_id not in self.rooms:
            return self.report_error("Select a room first")
        room = self.rooms[room_id]
        try:
            profile = self.selected_profile(room["platform"], room["emulator"])
        except ValueError as exc:
            return self.report_error(str(exc))
        for field, key in [("version", "emulator_version"), ("core_name", "core_name"),
                           ("core_version", "core_version")]:
            if profile.get(field, "") != room[key]:
                return self.report_error(f"Emulator profile mismatch ({field}). Host requires {room[key]!r}.")
        path = self.join_path.get().strip()
        if Path(path).suffix.lower() in (".cue", ".m3u"):
            return self.report_error("Select the containing FOLDER for CUE/BIN or multi-disc games")

        def operation():
            digest = game_fingerprint(path)
            self.api.call("POST", "/rooms/" + room_id + "/join", {
                "emulator": room["emulator"], "emulator_version": profile["version"],
                "core_name": profile.get("core_name", ""), "core_version": profile.get("core_version", ""),
                "game_sha256": digest,
            })
            return room_id
        def done(result):
            self.current_room = {**room, "is_host": False}
            self.game_path_for_room = path
            self.last_msg_id = 0
            self.clear_chat()
            self.notebook.select(self.room_tab)
            self.refresh_room()
            self.status_var.set("Joined room " + result + " | game hash and versions matched")
        self.bg(operation, done, "Verifying full game SHA-256 and joining...")

    def clear_chat(self):
        self.chat_view.configure(state="normal")
        self.chat_view.delete("1.0", "end")
        self.chat_view.configure(state="disabled")

    def refresh_room(self):
        if not self.api.token or not self.current_room or self.room_polling:
            return
        self.room_polling = True
        room_id = self.current_room["id"]
        after = self.last_msg_id
        def operation():
            room = self.api.call("GET", "/rooms/" + room_id)
            messages = self.api.call("GET", f"/rooms/{room_id}/chat?after_id={after}")
            return room, messages
        def work():
            try:
                result = operation()
                self.after(0, lambda: self.room_updated(room_id, result))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: self.room_failed(room_id, msg))
        threading.Thread(target=work, daemon=True).start()

    def room_updated(self, room_id, result):
        self.room_polling = False
        if not self.current_room or self.current_room["id"] != room_id:
            return
        room, messages = result
        self.current_room = room
        self.room_heading.set(f"{room['game_title']}  |  {room['platform']}  |  {room['emulator']} {room['emulator_version']}  |  Room {room_id}")
        self.members_heading.set("Players: " + "    |    ".join(
            m["username"] + (" READY: READY" if m["ready"] else " | waiting") for m in room["members"]))
        self.current_ready = next((m["ready"] for m in room["members"] if m["username"] == self.username), False)
        self.connect_heading.set("Method: " + MODES.get(room["mode"], room["mode"]) +
                                 "\nConnect info (room members only): " + (room["connection_hint"] or "Host has not posted details yet"))
        if self.connection_edit.get() != room["connection_hint"] and not self.connection_edit.get():
            self.connection_edit.set(room["connection_hint"])
        if messages:
            self.chat_view.configure(state="normal")
            for msg in messages:
                moment = time.strftime("%H:%M", time.localtime(msg["created_at"]))
                self.chat_view.insert("end", f"[{moment}] {msg['username']}: {msg['message']}\n")
                self.last_msg_id = max(self.last_msg_id, msg["id"])
            self.chat_view.see("end")
            self.chat_view.configure(state="disabled")

    def room_failed(self, room_id, message):
        self.room_polling = False
        if "Room was closed" in message and self.current_room and self.current_room["id"] == room_id:
            self.current_room = None
            self.room_heading.set("This room has closed. Return to Find Games.")
        self.status_var.set(message)

    def post_room(self, path, body, success="Saved"):
        if not self.current_room:
            return self.report_error("You are not in a room")
        room_id = self.current_room["id"]
        self.bg(lambda: self.api.call("POST", "/rooms/" + room_id + path, body),
                lambda _: (self.status_var.set(success), self.refresh_room()), success + "...")

    def toggle_ready(self):
        self.post_room("/ready", {"ready": not self.current_ready}, "Ready state updated")

    def send_message(self):
        if not self.current_room:
            return
        message = self.chat_entry.get().strip()
        if not message:
            return
        self.chat_entry.set("")
        self.post_room("/chat", {"message": message}, "Message sent")

    def update_connection(self):
        if not self.current_room:
            return self.report_error("You are not in a room")
        if not self.current_room.get("is_host"):
            return self.report_error("Only the host may update connection instructions")
        room_id = self.current_room["id"]
        connect_info = self.connection_edit.get()
        self.bg(lambda: self.api.call("PUT", "/rooms/" + room_id + "/connection",
                    {"connection_hint": connect_info}),
                lambda _: (self.status_var.set("Connect info updated"), self.refresh_room()),
                "Updating connection details...")

    def leave_game(self):
        if not self.current_room:
            return
        if not messagebox.askyesno("Leave room", "Leave the room? If you are hosting, this will close it for everyone."):
            return
        room_id = self.current_room["id"]
        def done(_):
            self.current_room = None
            self.last_msg_id = 0
            self.room_heading.set("You have left the room.")
            self.members_heading.set("Players: -")
            self.connect_heading.set("Connection: -")
            self.clear_chat()
            self.notebook.select(self.discover_tab)
            self.refresh_lobbies()
        self.bg(lambda: self.api.call("POST", "/rooms/" + room_id + "/leave"), done, "Leaving room...")

    def copy_room_id(self):
        if not self.current_room:
            return
        self.clipboard_clear()
        self.clipboard_append(self.current_room["id"])
        self.status_var.set("Room ID copied | friends can find it using the same lobby server")

    def start_play(self):
        room = self.current_room
        if not room:
            return self.report_error("Join a room first")
        mode = room["mode"]
        if mode == "parsec" and not room.get("is_host"):
            self.status_var.set("Open Parsec, connect to the host and request a controller")
            hint_url = room.get("connection_hint", "").strip()
            parsed = urlsplit(hint_url)
            if parsed.scheme == "https" and (parsed.hostname == "parsec.app" or
                    (parsed.hostname or "").endswith(".parsec.app")):
                webbrowser.open(hint_url)
            else:
                webbrowser.open("https://parsec.app/")
            return
        if mode == "hamachi" and not room.get("is_host"):
            self.status_var.set("Start Hamachi and join the host's virtual LAN, then launch your emulator")
            webbrowser.open("https://support.goto.com/hamachi")
            return
        try:
            profile = self.selected_profile(room["platform"], room["emulator"])
            command = launch_commands(room, profile, self.game_path_for_room, room["is_host"])
            subprocess.Popen(command)
            if mode == "retroarch":
                note = "RetroArch launched with native netplay options. Check firewall/VPN connectivity."
            elif mode == "dolphin":
                note = "Open Dolphin > Tools > Start Netplay Session, then exchange traversal code in room chat."
            else:
                note = "Emulator started. Configure the game's network, Parsec session or VPN using room details."
            self.status_var.set(note)
            messagebox.showinfo("Play setup", note)
        except Exception as exc:
            self.report_error(str(exc))

    def poll(self):
        if self.api.token:
            if self.current_room:
                self.refresh_room()
            else:
                self.refresh_lobbies(quiet=True)
        self.after(6000, self.poll)


if __name__ == "__main__":
    app = RetroRelayApp()
    app.mainloop()
