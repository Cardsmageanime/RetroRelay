# RetroRelay — Classic Multiplayer Hub (Starter v0.1)

> **Early preview / source code only:** this is not a standalone installer or a ready-to-run public multiplayer network. Do not expose the account server to open registration until security protections are added. See [Security](SECURITY.md) and [Release Notes](RELEASE_NOTES.md).

**A working Python desktop/client + self-hosted lobby server starter project.** Windows and Linux. The hub coordinates accounts, player matching, waiting rooms, readiness and chat; it does **not** emulate consoles itself or stream gameplay. You must install your preferred supported emulator separately.

**Your boundaries:** Nintendo SNES through Wii U (including GameCube, Wii and listed handhelds); PlayStation 1, 2, 3 and PSP; Sega Genesis/32X/CD/Saturn/Dreamcast; original Xbox and Xbox 360; plus legacy PC-game lobbies. Deliberately **no Nintendo Switch / Switch 2, PlayStation 4 / 5, Xbox One / Series**. ROMs/BIOS/firmware aren't provided.

## First play session — Windows (beginner route)

1. Install [Python 3.11+](https://www.python.org/downloads/) and check **Add python.exe to PATH** when installing. Extract this project folder.
2. Double-click **`START_HUB_WINDOWS.bat`** on the PC that will host the *lobby server*. It installs dependencies in a local virtual environment automatically. Keep the terminal running.
3. Double-click **`START_APP_WINDOWS.bat`**. On the `Account` tab, keep the default server URL `http://127.0.0.1:8751`. Create an account; then log in.
4. On `Emulator Setup`, select a console and emulator. Browse to the emulator executable, enter its **exact installed version**, and save. RetroArch users also enter the **core name, core version and installed core `.dll` file**.
5. On `Host Game`, choose game, matching file or folder, and multiplayer method. Click **Create room + check my game**. The app calculates a full SHA-256 fingerprint. For RetroArch the host should provide an address reachable by other players, typically `your-public-IP:55435` or a Hamachi VPN address; it is for the emulator netplay connection, not the lobby server.
6. On the other PC, install the app and emulator, set its **lobby server URL** to your shared HTTPS server URL (see below), register a different account and enter their own emulator profile. Go to `Find Games`, select your lobby and choose their local copy of the *exact same game*. Click **Verify game + join**.
7. Use `Waiting Room` to chat, mark ready and press **Launch emulator / play**. RetroArch classic netplay starts via command-line; Dolphin, Parsec, and game-network modes provide guided/manual setup.

## First play session — Linux / Bazzite

Requires Python 3.11+, `venv`, and the Python **Tk** GUI module. To check Tk: `python3 -m tkinter`. On immutable distributions such as Bazzite, a distrobox/container with Python/Tk and graphical access may be easier than changing the host OS. Your selected emulator must be available from that same environment.

Open two terminals from this folder:

```bash
chmod +x START_HUB_LINUX.sh START_APP_LINUX.sh
./START_HUB_LINUX.sh
# second terminal:
./START_APP_LINUX.sh
```

On both operating systems, only *the lobby host* needs to run the hub server. Other players run only the desktop client and point it at the same server URL.

## Share your lobby server with friends on the Internet

A localhost URL (`127.0.0.1`) works **only on your own PC**. To let friends from other homes use your community hub, it needs a reachable public hostname with HTTPS/TLS. A **Docker Compose + Caddy example** is included:

1. Obtain a domain or subdomain, and point its DNS to the PC/VPS that will host your hub.
2. Install Docker/Compose on that host. Copy `.env.example` to `.env` and set `DOMAIN=your-real-domain.example`.
3. Make TCP ports **80 and 443** reachable from the Internet for that host (server firewall/router as appropriate).
4. Run `docker compose up -d --build` from the project folder. Caddy requests HTTPS certificates automatically when DNS and networking are set up correctly.
5. All clients then use **`https://your-real-domain.example`** as their lobby server URL. No need to expose internal hub port 8751 publicly.

**Important:** this is a starter, not a hardened public social network. Before opening registration to strangers, add rate limits, anti-spam, reporting, moderation, recovery/verification, secure deployment logging and monitoring. HTTPS protects login data in transit. Do not post VPN credentials or remote-control links in public chat; room connection details are visible only to room members, who may still share them.

### LAN-only server for a household

You can set `RETRORELAY_HOST=0.0.0.0` when starting `server.py`, allow TCP port 8751 on your local firewall, and have clients on your *trusted private network* use `http://<LAN-host-IP>:8751`. **Do not expose an unencrypted server to the public Internet.**

## What each multiplayer method actually does

| Method | What this starter automates | What still requires setup |
| --- | --- | --- |
| `retroarch` | Launches matching classic-game core/ROM with `--host` or `--connect`, netplay port | A supported deterministic core, compatible settings, and a reachable port, VPN, or RetroArch relay. Intentionally offered only for SNES and Sega Genesis/CD/32X, not PS1/N64/Dreamcast/Wii. |
| `dolphin` | Creates and matches a Wii/GameCube lobby and opens Dolphin | Dolphin `Tools > Start Netplay Session`; host shares traversal code in room chat; players configure controllers and game. |
| `game_network` | Wait room, matching, game launch | Individual emulator and game networking: e.g., PPSSPP relay/ad hoc, some PCSX2 online services, RPCS3 RPCN-compatible games, Wii U Pretendo-compatible titles, xemu system link, Dreamcast revival servers, or legacy PC game server. **Not** a universal game-server emulator. |
| `parsec` | Creates lobby; clients can open Parsec and use host-provided invite | Host (normally a compatible Windows PC) installs and configures Parsec, explicitly approves guests, shares a controller-compatible local multiplayer game. Guests do **not** run separate synchronized ROMs in this mode, although RetroRelay still enforces the same game-file hash because that is your requested room policy. |
| `hamachi` | Creates lobby, shares private VPN/connection instructions | Each person installs Hamachi and joins same VPN. The emulator/game must separately support LAN or IP networking. Hamachi alone cannot make an offline game multiplayer. |

**Networking note:** "built-in Wi-Fi" means the app uses the existing computer Wi-Fi/Ethernet/Internet access for account/lobby/chat requests. Software cannot create a Wi-Fi adapter out of nothing. Console-specific game protocols require separate adapters. The hub doesn't relay controller inputs, video/audio or console game packets.

## Compatibility policy

A **room may exist** for any platform listed in `catalog.py`, but that is different from promising the game will work online. RetroRelay keeps the user's allowed-console list and stores a requested play method. It rejects incompatible direct-launch combos and excludes newer systems.

- **SNES and selected Sega 16-bit platforms:** RetroArch netplay for compatible cores; alternatively Parsec for local multiplayer.
- **N64 / PS1 / Saturn / Dreamcast / DS / Game Boy variants:** lobbies and emulator launch; typically Parsec or another specifically compatible network method. RetroArch's replay-netplay cannot simply be assumed to work for N64, PS1 or Dreamcast.
- **GameCube / Wii:** Dolphin native netplay. Wii remote gameplay can have controller/desync limitations.
- **Wii U:** Cemu; selected game's revived network support such as Pretendo where appropriately configured, otherwise local multi via remote play if supported.
- **PlayStation 2:** PCSX2; network-revival services only for supported games, local multiplayer using remote-play if suitable.
- **PlayStation 3:** RPCS3; RPCN and custom servers for certain tested titles only, or Parsec for games with local multiplayer.
- **PSP:** PPSSPP has ad-hoc relay and supported infrastructure paths.
- **Original Xbox:** xemu supports virtual networking and System Link / XLink Kai methods.
- **Xbox 360:** Xenia does **not** normally connect to Xbox Live and mainline lacks system link; some experimental forks may support limited online titles. Local multiplayer via host-controlled remote play is the conservative fallback.
- **Legacy PC games:** lobby listing and launching, but no automatic console-to-PC crossplay. Call of Duty / Modern Warfare PC editions depend on their own compatible game servers and version.

**ROM matching is enforced at room join:** server compares submitted SHA-256 with host's fingerprint. For one-file games, it hashes every byte of the ROM/ISO/CHD. For multi-file directories (e.g. game dump directory or BIN+CUE), it hashes every file in sorted relative-path order. Players must select the same *kind* of path on both PCs: both whole files or both equivalent game directories. **The hash is not a copyright/ownership check.** Files stay on each PC, not uploaded.

**Version matching:** clients store emulator version strings manually. The server verifies those strings, and RetroArch core name/version strings, exactly. The starter does **not** independently inspect executable binary version, core binary hash, mods/patches, BIOS, save state or game settings. Those improvements would be needed for strict end-to-end determinism. The app doesn't require an old emulator version: use the current version if all players use the same current version.

## Privacy and security notes

- Account passwords are salted and hashed with `scrypt`. Tokens are random; database stores only their SHA-256 hashes.
- No ROM/ISO, BIOS, save data, game file path or emulator path is sent to server. Only game fingerprint, platform, emulator/core version strings, game title, room notes, accounts and chat are stored on hub.
- Hub hashes are not publicly shown in the browser list; only membership can view private connection instructions. An altered client could lie about its hash: server-side equality checks are a consistency check, not cryptographic remote proof that someone owns the file.
- Chat/room invitations are private only to authenticated room members, not encrypted end-to-end.
- Don't blindly trust invitations or allow untrusted Parsec guests full desktop access; use Parsec's approved-app and permission settings.

## Architecture / files

```text
server.py                 FastAPI + SQLite accounts, secure tokens, rooms, chat, readiness
catalog.py                Deliberately allowed consoles, emulator options, play-method limits
client.py                 Desktop GUI, full game file/folder hash, discovery, launch adapters
requirements.txt          Python server dependencies
requirements-dev.txt      Tests
START_HUB_WINDOWS.bat      One-click local server setup/start
START_APP_WINDOWS.bat      One-click Windows client setup/start
START_HUB_LINUX.sh        Local hub server
START_APP_LINUX.sh        Desktop client
Dockerfile, compose.yaml   Optional public hub deployment
Caddyfile                  Optional automated HTTPS reverse proxy
.env.example               Public hostname setting
ARCHITECTURE.md            Suggested development roadmap

tests/test_app.py          Real API / matching / room / hashing tests
```

Run tests with:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Source documentation

- [RetroArch netplay FAQ](https://docs.libretro.com/guides/netplay-faq/) — exact core/ROM match, supported core constraints and port forwarding.
- [Dolphin netplay](https://dolphin-emu.org/docs/guides/netplay-guide/) — netplay rooms, traversal codes, synchronization.
- [PPSSPP multiplayer](https://www.ppsspp.org/docs/multiplayer/quickstart/) — ad hoc/infrastructure.
- [RPCS3 RPCN tested games](https://wiki.rpcs3.net/index.php?title=RPCN_Compatibility_List) — game-by-game compatibility.
- [Pretendo Cemu](https://pretendo.network/docs/install/cemu) — game-dependent Wii U networking.
- [xemu networking](https://xemu.app/docs/networking/) — system link/UDP tunneling/bridging.
- [Xenia FAQ](https://github.com/xenia-project/xenia/wiki/FAQ) — limitations of Xbox 360 online support.
- [Parsec hosting and permissions](https://support.parsec.app/hc/en-us/articles/32381747079572-Hosting-and-Permissions) — remote play permissions and hosting.
- [GoTo Hamachi support](https://support.goto.com/hamachi) — virtual private networking.

**Legal:** use your own authorized game backups, homebrew and emulator/BIOS files. This project does not offer ROM downloads or bypass game DRM or paid network services.
