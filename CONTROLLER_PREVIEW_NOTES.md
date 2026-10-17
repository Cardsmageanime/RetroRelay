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
