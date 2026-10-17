# RetroRelay v0.1.0 — Early Preview (source code)

RetroRelay is a classic-game multiplayer **lobby and launcher**, for Windows and Linux, targeting selected Nintendo (SNES–Wii U), PlayStation (PS1–PS3/PSP), Sega (Genesis–Dreamcast) and Xbox (original–360) emulator ecosystems. Newer systems are intentionally excluded.

**Included in this download**
- Python desktop interface for accounts, game discovery, room chat and waiting rooms.
- Self-hosted FastAPI lobby server with SQLite storage.
- Local SHA-256 game-file matching and version-string matching.
- RetroArch netplay launching for explicitly supported classic cores, plus guides/helpers for Dolphin, Parsec, Hamachi and game-specific networking.
- Windows/Linux launch scripts, tests, and server-deployment examples.

**Important limitations**
- This is a ZIP of source code, **not a Windows .exe installer**, hosted multiplayer service, or universal game-netplay patch.
- Users need Python and their own supported emulators. The hub does not create online play in offline-only games without an appropriate remote-play/netplay method.
- Console and game support varies by emulator and game; listing a system does not guarantee it works online.
- No ROMs, firmware or copyrighted game files are included.
- **Not ready for open public signups or untrusted hosting**. See SECURITY.md.

Start with README.md. Feedback from technically confident early testers is welcome.
