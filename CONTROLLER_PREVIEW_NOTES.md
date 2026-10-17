# RetroRelay v0.2.0 — Controller registration preview (planned October 20, 2026)

## New in this preview
- Dedicated Controllers tab: scan local SDL2 input gamepads, including compatible Xbox, Sony PlayStation, Nintendo and generic controllers detected by the OS; keyboard/mouse input options always included.
- Register selected device profile to your logged-in lobby-server account; switch between profiles, refresh or remove registration.
- New lobby rooms require each player to select a registered input profile before they can enter and mark ready; legacy rooms continue working.
- Waiting rooms show players' selected input names.
- Optional `pygame` installation included in desktop launch scripts, and database migrations for existing v0.1 server installs.
- More server/API test coverage, no game files or emulator binaries included.

## Important limitations
- This is **a source-code early preview**, not a native Windows/macOS/Linux installer. Requires Python, networking configuration, compatible emulator and game.
- No automatic gamepad remapping/driver setup or input relay. SDL must recognize controllers, and emulators still control game input.
- Device registration and labels do **not** prove genuine/official hardware, prevent spoofing or detect/block cheats/macros. Accessible and generic gamepads remain supported.
- Account server still requires security hardening before exposure to strangers. Multiplayer game support remains game/emulator-dependent.

## New: Artwork and host-streamed controller guests

- Optional licensed/original image upload for any hosted game and Unicode title; thumbnails appear in game discovery and waiting room.
- Host controls uploads; server validates and converts artwork to a limited-size PNG.
- In Parsec mode, guests only need a registered controller (no game copy or emulator matching). The host provides their own game and Parsec streaming connection, which remains separately configured and approved by the host.
- Native emulator netplay still requires matching game files and versions. No ROM/ISO downloading or automatic copyrighted cover scraping is provided.
- For details and licensing limits see `ARTWORK_AND_PLAY_MODES.md`.

## October addition: Social Accounts
Added a private Social Accounts tab allowing users to save strictly validated, **unverified** HTTPS Twitch/YouTube/TikTok/Facebook/Instagram profile URLs. No OAuth connection, verification, or platform-specific posting/streaming is enabled. Planning tracked in GitHub Issue #6; Twitch live stream integration remains for January.

## October account protection: phone authenticator MFA (preview)

- Optional phone authenticator **TOTP** after username/password. Two-phase server login ensures MFA is checked before a normal session token exists.
- Setup requires password re-entry and verification of a six-digit rotating phone code; server shows eight **single-use offline recovery codes** only after successful enrollment.
- TOTP secrets are encrypted with a **persistent operator-managed** `RETRORELAY_MFA_KEY` outside the database. Unconfigured MFA setup fails with a clear error; already-enrolled users are **not** allowed to bypass phone verification when the key is missing.
- Per-account password/code attempt throttling and OTP replay prevention are included; these do not replace a production security audit.
- No SMS provider, phone-number registration, or optional app PIN in this preview; PIN + password is not MFA. The security checklist in GitHub Issue #9 must pass before October release.
