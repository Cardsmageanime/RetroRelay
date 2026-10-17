"""RetroRelay desktop companion: account, discovery, matching, chat and launch helpers.

Uses the PC's existing Internet/Wi-Fi connection; it does not create wireless hardware
or magically add a network stack to an emulator.
"""
from __future__ import annotations

import hashlib
import base64
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
from tkinter import filedialog, messagebox, ttk

from catalog import MODES, PLATFORMS, compatible_mode
from controllers import detect_input_devices

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


    def image_bytes(self, room_id: str) -> bytes:
        if not re.fullmatch(r"[A-Fa-f0-9]{8}", room_id):
            raise APIError("Invalid room ID")
        req = urllib.request.Request(self.base + "/rooms/" + room_id + "/artwork")
        req.add_header("Authorization", "Bearer " + (self.token or ""))
        with urllib.request.urlopen(req, timeout=12) as response:
            data = response.read(410_000)
        if len(data) > 400_000 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise APIError("Artwork is not a valid-sized PNG thumbnail")
        return data


class RetroRelayApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RetroRelay • Classic Multiplayer Hub")
        self.geometry("1120x780")
        self.minsize(900, 660)
        self.configure(bg=BG)
        self.settings = read_settings()
        self.api = API(self.settings.get("server") or DEFAULT_CONFIG["server"])
        self.username = None
        self.current_room = None
        self.rooms = {}
        self.cover_cache = {}
        self.cover_photo = None
        self.detected_devices = []
        self.registered_devices = []
        self.controller_labels = {}
        self.last_msg_id = 0
        self.current_ready = False
        self.room_polling = False
        self.lobby_polling = False
        self.status_var = tk.StringVar(value="Offline • log in to connect to the lobby server")
        self.setup_style()
        self.build_ui()
        self.after(5000, self.poll)

    def setup_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG, font=("Arial", 10))
        style.configure("Header.TLabel", background=BG, foreground=FG, font=("Arial", 18, "bold"))
        style.configure("Small.TLabel", background=BG, foreground=SUBTLE, font=("Arial", 10))
        style.configure("TButton", font=("Arial", 10), padding=(12, 7))
        style.configure("Accent.TButton", background="#1da994", foreground="#ffffff", font=("Arial", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#188777")])
        style.configure("TEntry", padding=5)
        style.configure("TCombobox", padding=5)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(20, 11), background=PANEL, foreground=FG)
        style.map("TNotebook.Tab", background=[("selected", "#28415a")], foreground=[("selected", "white")])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=31, borderwidth=0)
        style.configure("Treeview.Heading", background="#263c54", foreground=FG, font=("Arial", 10, "bold"))
        style.map("Treeview", background=[("selected", "#275867")], foreground=[("selected", "white")])
        style.configure("TSpinbox", padding=5)

    def label(self, parent, text, r, c=0, sticky="w", width=None):
        lbl = ttk.Label(parent, text=text)
        lbl.grid(row=r, column=c, sticky=sticky, padx=7, pady=7)
        return lbl

    def entry(self, parent, variable, r, c=1, width=52, show=None):
        ent = ttk.Entry(parent, textvariable=variable, width=width, show=show or "")
        ent.grid(row=r, column=c, sticky="ew", padx=7, pady=7)
        return ent

    def section(self, parent, text):
        ttk.Label(parent, text=text, style="Header.TLabel").pack(anchor="w", pady=(8, 14))

    def build_ui(self):
        hero = ttk.Frame(self)
        hero.pack(fill="x", padx=20, pady=(15, 10))
        ttk.Label(hero, text="RETRORELAY", style="Header.TLabel").pack(side="left")
        ttk.Label(hero, text="  Classic multiplayer • your games, your emulators, your lobby", style="Small.TLabel").pack(side="left")
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=10)
        self.account_tab = ttk.Frame(self.notebook, padding=18)
        self.setup_tab = ttk.Frame(self.notebook, padding=18)
        self.controller_tab = ttk.Frame(self.notebook, padding=18)
        self.host_tab = ttk.Frame(self.notebook, padding=18)
        self.discover_tab = ttk.Frame(self.notebook, padding=18)
        self.room_tab = ttk.Frame(self.notebook, padding=18)
        for name, tab in [
            ("1 • Account", self.account_tab), ("2 • Emulator Setup", self.setup_tab),
            ("3 • Controllers", self.controller_tab), ("4 • Host Game", self.host_tab),
            ("5 • Find Games", self.discover_tab), ("6 • Waiting Room", self.room_tab),
        ]:
            self.notebook.add(tab, text=name)
        self.build_account()
        self.build_setup()
        self.build_controllers()
        self.build_host()
        self.build_discover()
        self.build_room()
        ttk.Label(self, textvariable=self.status_var, style="Small.TLabel").pack(anchor="w", padx=23, pady=(0, 14))

    def build_account(self):
        t = self.account_tab
        self.section(t, "Connect to your community")
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

    def build_controllers(self):
        t = self.controller_tab
        self.section(t, "Detect and register your input devices")
        ttk.Label(t, text="Connect a gamepad via USB/Bluetooth, then choose Scan. Standard keyboard and mouse\n"
                  "can also be registered. Your device must be registered before joining new controller-required rooms.",
                  style="Small.TLabel", justify="left").pack(anchor="w", pady=(0, 12))
        detected_controls = ttk.Frame(t)
        detected_controls.pack(fill="x", pady=5)
        ttk.Button(detected_controls, text="Scan connected devices", command=self.scan_controllers).pack(side="left", padx=(0, 10))
        ttk.Button(detected_controls, text="Register selected", style="Accent.TButton",
                   command=self.register_controller).pack(side="left")
        self.detected_tree = ttk.Treeview(t, columns=("kind", "name", "family"), show="headings", height=5)
        for key, title, width in (("kind", "Input", 110), ("name", "Operating-system device name", 480),
                                  ("family", "Detected family (unverified)", 240)):
            self.detected_tree.heading(key, text=title)
            self.detected_tree.column(key, width=width)
        self.detected_tree.pack(fill="x", pady=(4, 15))
        ttk.Label(t, text="Registered to your account", style="Header.TLabel").pack(anchor="w", pady=(0, 7))
        ttk.Button(t, text="Refresh registered list", command=self.load_registered_controllers).pack(anchor="w", pady=5)
        self.registered_tree = ttk.Treeview(t, columns=("kind", "name", "family"), show="headings", height=5)
        for key, title, width in (("kind", "Input", 110), ("name", "Registered name", 480),
                                  ("family", "Type (not authenticated)", 240)):
            self.registered_tree.heading(key, text=title)
            self.registered_tree.column(key, width=width)
        self.registered_tree.pack(fill="x", pady=5)
        ttk.Button(t, text="Remove selected registration", command=self.remove_controller).pack(anchor="w", pady=8)
        ttk.Label(t, text="Use this input for game rooms:", style="Small.TLabel").pack(anchor="w", pady=(8, 3))
        self.selected_controller_label = tk.StringVar()
        self.registered_combo = ttk.Combobox(t, textvariable=self.selected_controller_label,
                                            state="readonly", width=68)
        self.registered_combo.pack(anchor="w")
        ttk.Label(t, text="Important: device names and SDL GUIDs can be faked. Registration records your chosen\n"
                  "input, but cannot verify official hardware, block macros, or police inputs inside emulators.",
                  style="Small.TLabel", justify="left").pack(anchor="w", pady=(12, 0))

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
        self.h_cover_file = tk.StringVar()
        self.h_cover_rights = tk.BooleanVar(value=False)
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
        self.label(form, "Optional lobby cover art", 8)
        self.entry(form, self.h_cover_file, 8)
        ttk.Button(form, text="Image", command=lambda: self.pick_art_file()).grid(row=8, column=2, padx=4)
        ttk.Checkbutton(t, text="I made this artwork or have permission to publish it publicly",
                        variable=self.h_cover_rights).pack(anchor="w", pady=(8, 0))
        ttk.Button(t, text="Create room + check my game", style="Accent.TButton", command=self.host_game).pack(anchor="w", pady=(10, 10))
        self.host_note = tk.StringVar(value="For RetroArch, give friends your reachable IP or VPN IP (e.g. 10.0.0.5:55435).")
        ttk.Label(t, textvariable=self.host_note, style="Small.TLabel", wraplength=850).pack(anchor="w")
        self.h_mode.trace_add("write", lambda *_: self.host_note.set(MODES.get(self.h_mode.get(), "")))

    def build_discover(self):
        t = self.discover_tab
        self.section(t, "Find people playing your games")
        ttk.Button(t, text="Refresh available rooms", command=self.refresh_lobbies).pack(anchor="w", pady=(0, 10))
        columns = ("game", "console", "emulator", "mode", "players")
        self.lobby_tree = ttk.Treeview(t, columns=columns, show="headings", height=11)
        for col, header, width in [
            ("game", "Game", 240), ("console", "Platform", 170),
            ("emulator", "Emulator / version", 190), ("mode", "Play method", 140), ("players", "Players", 75),
        ]:
            self.lobby_tree.heading(col, text=header)
            self.lobby_tree.column(col, width=width, minwidth=70)
        self.lobby_tree.pack(fill="both", expand=True, pady=(0, 9))
        self.lobby_tree.bind("<<TreeviewSelect>>", self.choose_lobby)
        details = ttk.Frame(t)
        details.pack(fill="x", pady=7)
        self.cover_widget = ttk.Label(details, text="Select a lobby to preview its artwork",
                                      width=36, anchor="center", background=PANEL)
        self.cover_widget.pack(side="left", padx=(0, 15))
        self.lobby_desc = tk.StringVar(value="Select a lobby to read the requirements.")
        ttk.Label(details, textvariable=self.lobby_desc, style="Small.TLabel",
                  wraplength=730, justify="left").pack(side="left", fill="x", expand=True)

        join_form = ttk.Frame(t)
        join_form.pack(fill="x", pady=7)
        join_form.columnconfigure(1, weight=1)
        self.join_path = tk.StringVar()
        self.label(join_form, "Your game file / folder (not needed for Parsec)", 0)
        self.entry(join_form, self.join_path, 0)
        ttk.Button(join_form, text="File", command=lambda: self.pick_file(self.join_path)).grid(row=0,column=2,padx=4)
        ttk.Button(join_form, text="Folder", command=lambda: self.pick_folder(self.join_path)).grid(row=0,column=3,padx=4)
        row = ttk.Frame(t)
        row.pack(anchor="w")
        ttk.Button(row, text="Join selected lobby", style="Accent.TButton", command=self.join_game).pack(side="left", padx=(0, 10))
        ttk.Button(row, text="Set up selected emulator", command=self.setup_selected).pack(side="left")

    def build_room(self):
        t = self.room_tab
        self.section(t, "Your waiting room")
        self.room_heading = tk.StringVar(value="No active room. Host a game or join an existing lobby.")
        ttk.Label(t, textvariable=self.room_heading, wraplength=950).pack(anchor="w", pady=5)
        self.room_cover_label = ttk.Label(t, text="No custom artwork selected", width=36,
                                         anchor="center", background=PANEL)
        self.room_cover_label.pack(anchor="w", pady=5)
        self.members_heading = tk.StringVar(value="Players: —")
        ttk.Label(t, textvariable=self.members_heading).pack(anchor="w", pady=5)
        self.connect_heading = tk.StringVar(value="Connection: —")
        ttk.Label(t, textvariable=self.connect_heading, style="Small.TLabel", wraplength=970).pack(anchor="w", pady=5)
        tools = ttk.Frame(t)
        tools.pack(anchor="w", pady=(10, 5))
        ttk.Button(tools, text="I'm ready / not ready", command=self.toggle_ready).pack(side="left", padx=(0, 8))
        ttk.Button(tools, text="Launch emulator / play", style="Accent.TButton", command=self.start_play).pack(side="left", padx=(0, 8))
        ttk.Button(tools, text="Host: change artwork", command=self.update_room_art).pack(side="left", padx=(0, 8))
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
                                 highlightthickness=0, wrap="word", font=("Arial", 10))
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
        return self.api

    def login(self):
        try:
            api = self.rebase_api()
        except ValueError as exc:
            return self.report_error(str(exc))
        def done(res):
            api.token = res["token"]
            self.username = res["username"]
            self.status_var.set("Online • logged in as " + self.username)
            self.notebook.select(self.discover_tab)
            self.refresh_lobbies()
            self.scan_controllers()
            self.load_registered_controllers()
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
                lambda _: self.status_var.set("Lobby server is reachable • Internet/network OK"),
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
        self.registered_devices = []
        self.controller_labels = {}
        self.registered_combo["values"] = []
        self.selected_controller_label.set("")
        self.status_var.set("Offline • log in to connect to the lobby server")
        self.notebook.select(self.account_tab)

    def scan_controllers(self):
        def done(devices):
            self.detected_devices = devices
            for item in self.detected_tree.get_children():
                self.detected_tree.delete(item)
            for i, device in enumerate(devices):
                self.detected_tree.insert("", "end", iid=str(i),
                                          values=(device["kind"], device["name"], device["family"]))
            self.status_var.set(f"Found {len(devices)} input options (including keyboard/mouse)")
        self.bg(detect_input_devices, done, "Scanning local input devices...")

    def load_registered_controllers(self):
        if not self.api.token:
            return self.report_error("Log in to see account registrations")
        def done(devices):
            previous_id = self.selected_controller_id()
            self.registered_devices = devices
            self.controller_labels = {}
            for item in self.registered_tree.get_children():
                self.registered_tree.delete(item)
            for device in devices:
                self.registered_tree.insert("", "end", iid=device["id"],
                    values=(device["kind"], device["name"], device["family"]))
                label = f'{device["kind"]}: {device["name"]} [{device["id"][:8]}]'
                self.controller_labels[label] = device["id"]
            self.registered_combo["values"] = list(self.controller_labels)
            selected_label = next((label for label, did in self.controller_labels.items()
                                   if did == previous_id), None)
            self.selected_controller_label.set(selected_label or next(iter(self.controller_labels), ""))
        self.bg(lambda: self.api.call("GET", "/devices"), done, "Fetching registered devices...")

    def selected_controller_id(self):
        return self.controller_labels.get(self.selected_controller_label.get())

    def register_controller(self):
        if not self.api.token:
            return self.report_error("Log in before registering controllers")
        items = self.detected_tree.selection()
        if not items:
            return self.report_error("Scan and select a device first")
        device = self.detected_devices[int(items[0])]
        self.bg(lambda: self.api.call("POST", "/devices",
                {"kind": device["kind"], "name": device["name"], "guid": device["guid"]}),
                lambda _: self.load_registered_controllers(), "Registering your input choice...")

    def remove_controller(self):
        if not self.api.token:
            return self.report_error("Log in first")
        selection = self.registered_tree.selection()
        if not selection:
            return self.report_error("Select a registered device to remove")
        if not messagebox.askyesno("Remove controller", "Remove this controller registration?"):
            return
        did = selection[0]
        self.bg(lambda: self.api.call("DELETE", "/devices/" + did),
                lambda _: self.load_registered_controllers(), "Removing device registration...")

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

    def pick_art_file(self):
        path = filedialog.askopenfilename(title="Choose artwork you may publish",
                                          filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        if path:
            self.h_cover_file.set(path)

    def host_game(self):
        if not self.api.token:
            return self.report_error("Log in first")
        if self.current_room:
            return self.report_error("Leave your current room before hosting another")
        controller_id = self.selected_controller_id()
        if not controller_id:
            self.notebook.select(self.controller_tab)
            return self.report_error("Register and select a controller/keyboard/mouse in the Controllers tab")
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
        cover_path = self.h_cover_file.get().strip()
        if cover_path and not self.h_cover_rights.get():
            return self.report_error("Confirm you have permission to publish the selected artwork")
        if cover_path and (not Path(cover_path).is_file() or Path(cover_path).stat().st_size > 800_000):
            return self.report_error("Choose an image under 800 KB before creating a room")
        def operation():
            hashcode = game_fingerprint(path)
            room = self.api.call("POST", "/rooms", {
                "platform": platform, "emulator": emulator, "emulator_version": profile["version"],
                "core_name": profile.get("core_name", ""), "core_version": profile.get("core_version", ""),
                "game_title": title, "game_sha256": hashcode,
                "mode": mode, "connection_hint": hint,
                "notes": notes, "max_players": max_players,
                "controller_required": True, "controller_id": controller_id,
            })
            if cover_path:
                try:
                    self.api.call("PUT", "/rooms/" + room["id"] + "/artwork", {
                        "image_base64": base64.b64encode(Path(cover_path).read_bytes()).decode("ascii"),
                        "rights_confirmed": True,
                    })
                except (APIError, OSError, ValueError) as exc:
                    room["art_warning"] = str(exc)
            return room
        def done(result):
            self.current_room = {"id": result["id"], "is_host": True, "platform": platform,
                                 "emulator": emulator, "mode": mode, "connection_hint": hint}
            self.game_path_for_room = path
            self.last_msg_id = 0
            self.clear_chat()
            self.notebook.select(self.room_tab)
            self.refresh_room()
            self.status_var.set("Room " + result["id"] + " created • " +
                                ("Cover upload failed: " + result['art_warning']
                                 if result.get('art_warning') else "waiting for friends"))
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
            selected = self.selected_lobby_id()
            for item in self.lobby_tree.get_children():
                self.lobby_tree.delete(item)
            for r in rows:
                self.lobby_tree.insert("", "end", iid=r["id"], values=(
                    r["game_title"], r["platform"], r["emulator"] + " " + r["emulator_version"],
                    r["mode"], str(r["players"]) + "/" + str(r["max_players"])))
            if selected and selected in self.rooms:
                self.lobby_tree.selection_set(selected)
                self.choose_lobby()
            else:
                self.cover_widget.configure(image="", text="Select a lobby to preview its artwork")
                self.cover_photo = None
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
        if room_id and room_id in self.rooms:
            room = self.rooms[room_id]
            self.lobby_desc.set(
                f"{room['game_title']}  •  hosted by {room['host']}  •  Room ID {room_id}\n"
                f"Required: {room['emulator']} {room['emulator_version']}"
                + (f"  |  Core: {room['core_name']} {room['core_version']}" if room["core_name"] else "")
                + f"\nMode: {MODES.get(room['mode'], room['mode'])}  •  {room['notes']}"
                + ("\nThis room requires a registered input profile." if room.get("controller_required") else "")
                + ("\nGuests only need Parsec and a controller; no local game copy required."
                   if room["mode"] == "parsec" else "\nGuests must supply their own matching game copy.")
            )
            self.preview_art(room_id, room.get("artwork", False))

    def preview_art(self, room_id, has_artwork):
        if not has_artwork:
            self.cover_widget.configure(image="", text="No cover uploaded\n" +
                                        self.rooms[room_id]["platform"])
            self.cover_photo = None
            return
        if room_id in self.cover_cache:
            self.apply_cover(room_id, self.cover_cache[room_id])
            return
        self.cover_widget.configure(image="", text="Loading game artwork...")
        self.cover_photo = None
        def fetch():
            try:
                data = self.api.image_bytes(room_id)
                self.cover_cache[room_id] = data
                self.after(0, lambda: self.apply_cover(room_id, data))
            except Exception:
                self.after(0, lambda: self.cover_widget.configure(text="Artwork unavailable"))
        threading.Thread(target=fetch, daemon=True).start()

    def apply_cover(self, room_id, data):
        if self.selected_lobby_id() != room_id:
            return
        try:
            self.cover_photo = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))
            self.cover_widget.configure(image=self.cover_photo, text="")
        except tk.TclError:
            self.cover_widget.configure(image="", text="Artwork unavailable")

    def preview_room_cover(self, room_id):
        if room_id in self.cover_cache:
            self.apply_room_cover(room_id, self.cover_cache[room_id])
            return
        def fetch():
            try:
                data = self.api.image_bytes(room_id)
                self.cover_cache[room_id] = data
                self.after(0, lambda: self.apply_room_cover(room_id, data))
            except Exception:
                self.after(0, lambda: self.room_cover_label.configure(text="Artwork unavailable"))
        threading.Thread(target=fetch, daemon=True).start()

    def apply_room_cover(self, room_id, data):
        if not self.current_room or self.current_room['id'] != room_id:
            return
        try:
            self.room_cover_photo = tk.PhotoImage(data=base64.b64encode(data).decode('ascii'))
            self.room_cover_label.configure(image=self.room_cover_photo, text="")
        except tk.TclError:
            self.room_cover_label.configure(image="", text="Artwork unavailable")

    def setup_selected(self):
        room_id = self.selected_lobby_id()
        if not room_id or room_id not in self.rooms:
            return self.report_error("Select a room first")
        room = self.rooms[room_id]
        controller_id = self.selected_controller_id()
        if room.get("controller_required") and not controller_id:
            self.notebook.select(self.controller_tab)
            return self.report_error("Select a registered controller/keyboard/mouse before joining")
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
        controller_id = self.selected_controller_id()
        if room.get("controller_required") and not controller_id:
            self.notebook.select(self.controller_tab)
            return self.report_error("Register and select an input device before joining")
        is_remote_guest = room["mode"] == "parsec"
        profile = {}
        path = ""
        if not is_remote_guest:
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
            digest = "" if is_remote_guest else game_fingerprint(path)
            self.api.call("POST", "/rooms/" + room_id + "/join", {
                "emulator": "" if is_remote_guest else room["emulator"],
                "emulator_version": "" if is_remote_guest else profile["version"],
                "core_name": profile.get("core_name", ""), "core_version": profile.get("core_version", ""),
                "game_sha256": digest,
                "controller_id": controller_id,
            })
            return room_id
        def done(result):
            self.current_room = {**room, "is_host": False}
            self.game_path_for_room = path
            self.last_msg_id = 0
            self.clear_chat()
            self.notebook.select(self.room_tab)
            self.refresh_room()
            self.status_var.set("Joined " + result + (" • connect using Parsec to play"
                if is_remote_guest else " • game hash and versions matched"))
        self.bg(operation, done, "Joining controller-only room..." if is_remote_guest
                else "Verifying full game SHA-256 and joining...")

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
        self.room_heading.set(f"{room['game_title']}  •  {room['platform']}  •  {room['emulator']} {room['emulator_version']}  •  Room {room_id}")
        if room.get("artwork"):
            self.preview_room_cover(room_id)
        else:
            self.room_cover_label.configure(image="", text=f"{room['platform']} • {room['game_title'][:35]}")
        self.members_heading.set("Players: " + "    |    ".join(
            m["username"] + (" ✓ READY" if m["ready"] else " • waiting") +
            (" [" + m["controller"][:28] + "]" if m.get("controller") else "")
            for m in room["members"]))
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

    def update_room_art(self):
        if not self.current_room or not self.current_room.get('is_host'):
            return self.report_error("Only the host can change lobby artwork")
        if not messagebox.askyesno("Artwork rights", "Do you own this image or have explicit permission to publish it publicly?"):
            return
        path = filedialog.askopenfilename(title="Select artwork you may publish",
                                           filetypes=[("Artwork", "*.png *.jpg *.jpeg *.webp")])
        if not path:
            return
        if Path(path).stat().st_size > 800_000:
            return self.report_error("Artwork must be under 800 KB")
        room_id = self.current_room['id']
        def operation():
            encoded = base64.b64encode(Path(path).read_bytes()).decode('ascii')
            self.api.call('PUT', f'/rooms/{room_id}/artwork',
                          {'image_base64': encoded, 'rights_confirmed': True})
            return True
        def done(_):
            self.cover_cache.pop(room_id, None)
            self.refresh_room()
            self.status_var.set("Lobby artwork updated")
        self.bg(operation, done, "Uploading artwork...")

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
            self.members_heading.set("Players: —")
            self.connect_heading.set("Connection: —")
            self.clear_chat()
            self.notebook.select(self.discover_tab)
            self.refresh_lobbies()
        self.bg(lambda: self.api.call("POST", "/rooms/" + room_id + "/leave"), done, "Leaving room...")

    def copy_room_id(self):
        if not self.current_room:
            return
        self.clipboard_clear()
        self.clipboard_append(self.current_room["id"])
        self.status_var.set("Room ID copied • friends can find it using the same lobby server")

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
