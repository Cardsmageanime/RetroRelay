# RetroRelay roadmap — from starter to full multiplayer product

## Working in version 0.1

- Python desktop UI for Windows/Linux; native Wi-Fi/Internet through the operating system.
- FastAPI + SQLite central account, room and chat server.
- SHA-256 content hash equality enforced by hub at join, emulator version and RetroArch core string equality.
- Host/join/waiting-room/readiness/room-only connection hints.
- RetroArch classic-core command line netplay host/connect launcher.
- Dolphin, emulator native networks, Parsec and Hamachi integration guides/launch helpers.
- Explicit platform allowlist: last Nintendo = Wii U, Sony = PS3, Sega = Dreamcast, Xbox = Xbox 360.

## Next implementation milestones (not provided yet)

1. **Windows/Linux installers and onboarding:** make signed Windows `.exe`/installer and Linux Flatpak/AppImage, built with PyInstaller or an equivalent. Add dependency scans and machine-readable version detection.
2. **Native integrations:** Dolphin netplay session adapter for traversal-code capture (where an official API supports it), game-specific RPCS3/PCSX2/PPSSPP/Flycast/xemu/Cemu integrations; version/corename/core-binary checks; mod/config matching. No emulator-specific ability should be advertised until tested.
3. **Remote-play:** integrate an actual low-latency streaming/control stack using its supported API and explicit host approvals. Parsec can remain an external option; alternatively implement Sunshine/Moonlight compatibility. Stream/screen controls must not accidentally expose the desktop.
4. **P2P NAT traversal / optional game packet relay:** STUN/ICE or carefully scoped VPN protocols for platform-aware networking. Our current hub relays lobby metadata and chat only; it cannot accept arbitrary old console game traffic and translate it into online play. Doing that needs a protocol bridge per console/game.
5. **Community management:** friend lists, invitations, room codes, private/public rooms, presence, game search, block/report/moderation, customizable profile and accessibility settings.
6. **Production back end:** PostgreSQL, Redis/pub-sub, WebSocket updates, password recovery, per-IP and account rate limits, abuse controls, monitoring, security review, back-ups and live deployment.
7. **Optional game/PC lobby adapters:** only compatible versions and game-specific servers; never promise that PS3, Xbox 360, PC and Wii editions of a game can crossplay unless that title and adapter truly support it.

## Architectural boundary

```
PC #1 (client + emulator)                   PC #2 (client + emulator)
        |                                            |
        |  HTTPS accounts, room discovery, chat      |
        +-----------> RetroRelay Hub <---------------+
        |                                            |
        +------ game connection via selected --------+
                native netplay / game network /
                Parsec screen/controller stream /
                optional Hamachi virtual LAN
```

The RetroRelay hub does not receive ROMs, local executable paths or game streams.
