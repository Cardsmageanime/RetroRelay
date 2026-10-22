# RetroRelay — Development Roadmap (2026–2028)

**Project:** [RetroRelay](https://github.com/Cardsmageanime/RetroRelay)  
**Roadmap last consolidated:** October 22, 2026  
**Status convention:** **Published** = verified GitHub Release; **In review** = code proposed in a pull request but not released; **Planned** = feature requirements exist, but shipping has not been verified.  
**Release policy:** Dates below are *reviews/targets*, not guaranteed release dates. Ship meaningful changes only after testing, security review, documentation, and honest compatibility notes.

## Mission

RetroRelay is a beginner-friendly, self-hostable hub connecting players of classic emulated games through compatible emulator netplay, game-specific multiplayer services or host-streamed controller-only sessions. It is also planned to support communities, streaming and achievement showcases. A lobby does **not** make every emulator or game automatically online-capable.

### Platform scope

- Nintendo: **Super Nintendo (SNES) through Wii U**, excluding Switch / Switch 2.
- PlayStation: **PS1 through PS3**, excluding PS4 / PS5.
- Sega: **Genesis through Dreamcast**.
- Xbox: **original Xbox through Xbox 360**, excluding Xbox One/Series.
- Supported emulator/core versions and games vary by mode. Computer Internet/Wi-Fi hardware supplies the network; RetroRelay cannot create an independent Wi-Fi radio.

## Releases and target milestones

| Date | Version | Milestone | Verified status | Tracker |
|---|---|---|---|---|
| October 2026 | v0.1.0 | Source-code starter with accounts, compatible-game lobbies, chat, match checks and emulator launch helpers | **Published early preview** | [Release v0.1.0](https://github.com/Cardsmageanime/RetroRelay/releases/tag/v0.1.0) |
| **October 20, 2026** | **v0.2.0** | Social profile links, controller discovery/registration, lobby artwork, Parsec controller-only guest rooms and phone-authenticator MFA security preview | **In review** (not published) | [PR #2](https://github.com/Cardsmageanime/RetroRelay/pull/2), [MFA Issue #9](https://github.com/Cardsmageanime/RetroRelay/issues/9), [Issue #6](https://github.com/Cardsmageanime/RetroRelay/issues/6) |
| **January 16, 2027** | **v0.3.0** | Twitch account authorization, OBS-assisted broadcasting, separate Twitch and RetroRelay lobby chats, streamer dashboard | **Planned** | [Issue #3](https://github.com/Cardsmageanime/RetroRelay/issues/3) |
| **April 16, 2027** | **v0.4.0** | Low-latency netplay/rollback where emulator supports it, network diagnostics and controller input test/remapping wizard | **Planned** | [Issue #4](https://github.com/Cardsmageanime/RetroRelay/issues/4) |
| **August 16, 2027** | **v0.5.0** | Social gaming profiles, app/room themes, licensed or user-owned images, free Relay Store, OBS controller-display overlays | **Planned** | [Issue #5](https://github.com/Cardsmageanime/RetroRelay/issues/5) |
| **November 16, 2027** | **v0.6.0** | Arcade Network: compatibility-aware Quick Match, tournaments/leaderboards, friends/parties/clubs, spectating, moderation and fair-play | **Planned** | [Issue #7](https://github.com/Cardsmageanime/RetroRelay/issues/7) |
| **February 16, 2028** | **v0.7.0** | Opt-in Steam and **GOG GALAXY** and Epic Games library/achievement showcases, plus RetroAchievements points and badges | **Planned** | [Issue #8](https://github.com/Cardsmageanime/RetroRelay/issues/8) |
| **March 2028** | **Version TBD** | Cross-platform achievement/trophy sharing hub for Sony PlayStation, Xbox, Nintendo goals and Steam, where provider data is available and authorized | **Planned** | [Issue #12](https://github.com/Cardsmageanime/RetroRelay/issues/12) |

## Phase-by-phase acceptance goals

### 2026 — Foundation and October feature preview

**v0.1.0 — published starter:** Accounts, rooms, chat, matching game fingerprints and emulator versions, launch helpers, basic self-hosted server. This is a **source-code preview**, not a finished installer or hardened global hosting service.

**v0.2.0 — October 20 target:**
- **Account security:** Optional phone TOTP MFA with password verification, encrypted setup secrets, one-use recovery codes, login attempt throttling, and step-up requirements for disabling MFA. A PIN alone does not count as independent MFA; SMS delivery is not part of the October preview. Pending security/CI validation before release ([Issue #9](https://github.com/Cardsmageanime/RetroRelay/issues/9)).

- Social Accounts tab starts with **private, unverified** Twitch/YouTube/TikTok/Facebook/Instagram profile URLs. Direct OAuth account connections require separate developer apps, authorization flows and, sometimes, provider review. Do not call a pasted URL a connected account.
- Discover SDL-supported PlayStation/Xbox/Nintendo/generic gamepads, and offer keyboard/mouse registration; users choose an input profile. Controller name/GUID does **not** certify official hardware or stop cheating.
- Rights-cleared host-supplied artwork previews, international titles, and lobby images; no bundled unlicensed game art library.
- Native emulator multiplayer requires compatible ROM/game hashes and emulator/core versions. Parsec mode permits controller-only guests but **Parsec handles the stream**; hosts must configure it separately. No unauthorized commercial ROM sharing.
- Validate CI plus real desktop and hardware testing, then decide whether to merge [PR #2](https://github.com/Cardsmageanime/RetroRelay/pull/2) and publish a source-only prerelease.

### January 2027 — v0.3.0 Streaming & dual chat

- Twitch OAuth access with secure tokens and minimum necessary permissions.
- Streamer dashboard (game, console, emulator, lobby, broadcast status).
- **Twitch viewer chat** and **RetroRelay player lobby chat**, separate and access-controlled.
- OBS-assisted game capture and Twitch broadcasting, with viewer embedding only where Twitch requirements allow.
- Preserve player privacy; check rate limits, disconnect/reconnect, moderation and Windows/Linux usability.
- **Not a built-from-scratch Twitch-scale video streaming service.** Details: [Issue #3](https://github.com/Cardsmageanime/RetroRelay/issues/3).

### April 2027 — v0.4.0 Low latency & advanced input

- Begin with compatible emulator-native rewind/rollback; evaluate dedicated rollback architecture only where deterministic cores have input, save-state and resimulation hooks.
- Measured ping, jitter, packet loss, rollback events and clear fallback modes; improve responsiveness rather than promise **zero lag**.
- Input verification wizard: face buttons, shoulders, triggers, D-pad, stick axes/clicks, Start/Options/Share/Guide where exposed.
- Profiles for PlayStation, Xbox, Switch Pro, Nintendo Switch Online N64-style and generic controllers; hotplug, USB/Bluetooth support where OS/hardware allow.
- Use OS/SDL mappings, not unauthorized driver installations; tests on real devices required.
- Details: [Issue #4](https://github.com/Cardsmageanime/RetroRelay/issues/4).

### August 2027 — v0.5.0 Community Customization

- Editable avatar, banner, bio, favorite games/consoles/controllers, online status and privacy.
- MySpace-inspired profile/page personality without allowing arbitrary executable user scripts.
- Custom room themes, banners, icons, colors, game art; accessible built-in themes.
- **Free Relay Store** containing original or licensed theme packs, background art, decorations and OBS controller-input overlays, including original/licensed skins for controller families.
- User image upload **does not waive copyright**: permitted/licensed images only for public redistributing, plus reporting, takedowns, size/type validation and privacy controls.
- Chat/room polish and compatibility with earlier network and streaming improvements.
- Details: [Issue #5](https://github.com/Cardsmageanime/RetroRelay/issues/5).

### November 2027 — v0.6.0 Arcade Network

All five owner-approved tracks:
1. **Quick Match:** match by game fingerprint, emulator/core version, supported mode and network quality; explain mismatches.
2. **Tournaments & rankings:** single-elimination MVP, brackets, check-in, verified scores, disputes and opt-in leaderboards.
3. **Friends, parties and gaming clubs:** requests, invites, friend visibility, private parties, clubs and member/host roles.
4. **Spectator mode:** use actual emulator spectator support or consented broadcasts; never promise universal native spectating.
5. **Community safety & fair play:** reports, blocking, muting, room moderation, abuse controls, privacy, verified tournament outcomes; device registration is not cheat-proof.

Details: [Issue #7](https://github.com/Cardsmageanime/RetroRelay/issues/7).

### February 2028 — v0.7.0 Gaming Library & Achievement Showcase

- **Steam:** opt-in games and per-game achievements using supported APIs and user library visibility.
- **GOG GALAXY:** the owner confirmed this is the intended “GG Galaxy” library. Investigate authorized library and achievement visibility; manual/local fallback if official comprehensive APIs are not available.
- **Epic Games:** approved account and achievement access where APIs permit; mark unsupported synchronization accurately.
- **RetroAchievements:** read-only earned badges, completion data and points with documented API authorization.
- Gaming profile cards with favorite games, pinned showcases and per-source points/achievement labels. **No invented unified official gamer score**.
- Secure provider permissions, no passwords/scraped private sessions, private-by-default visibility and disconnect/deletion settings.
- Details: [Issue #8](https://github.com/Cardsmageanime/RetroRelay/issues/8).

### March 2028 — Cross-Platform Achievements, Trophies & Goals Hub

- **One RetroRelay profile** to showcase earned PlayStation trophies, Xbox achievements, Nintendo missions/goals and Steam achievements across supported generations, with optional online sharing.
- **Sony PlayStation:** pursue authorized PSN trophy read access for supported consoles, including PS3/PS4/PS5 where permitted. Older systems without trophies or available API data must not be represented as synced.
- **Xbox:** pursue authorized earned achievements from Xbox 360, Xbox One, Xbox Series and supported PC titles. The original Xbox had no platform-wide achievements; any RetroRelay-created goals must be labeled separately.
- **Nintendo:** show authorized Nintendo Switch Online Missions & Rewards/My Nintendo activity only if suitable access is available. Nintendo does not offer a universal systemwide achievements service across all consoles; provide separately labeled optional RetroRelay goals for unsupported generations.
- **Steam:** build on the February 2028 integration and supported Steam achievement APIs. Preserve GOG GALAXY, Epic Games and RetroAchievements where feasible.
- Display game, source platform, earned badge/trophy, official source score or tier (where applicable), earned date and verification status. **Never fabricate a unified official gamer score or claim to unlock official achievements.**
- **Privacy and security:** accounts connected only with consent and authorized interfaces; profiles private by default, per-source sharing controls, revocation/deletion, token protection, API rate limits, honest unsupported status.
- This is a **cross-platform achievements showcase**, not a change to RetroRelay's emulator/platform-play support list above. It does not grant multiplayer or game-launch support for all PlayStation, Xbox and Nintendo consoles.
- Acceptance criteria, dependencies and feasibility review: [Issue #12](https://github.com/Cardsmageanime/RetroRelay/issues/12).

## Engineering work that cuts across every release

1. **Installer & accessibility:** beginner-friendly Windows executable/installer and tested Linux packages (Mint/Fedora/Bazzite) are still desired; don't claim they exist until packaged and checked.
2. **Security:** rate limiting, auth/session hardening, token lifecycle, content moderation, privacy, abuse reporting and network safety before unrestricted public hosting.
3. **Compatibility truthfulness:** provide a per-game, per-emulator mode matrix. A listed console is not blanket native-netplay or rollback support.
4. **Testing:** automated tests, Windows/Linux launch checks, two-PC multiplayer sessions, physical input devices, real streaming accounts when consented and latency measurements for network claims.
5. **IP rights:** don't bundle/distribute commercial game ROMs, copyrighted characters, firmware or other content without redistribution permission. Homebrew and appropriately licensed art are separate.

## Development and release policy

- Put incoming features into an issue before coding; prefer small scoped pull requests, tests and documentation.
- A scheduled quarterly review is a **check-in and opportunity to act**, not continuous background development or proof a future release will occur automatically.
- Release an honest early preview only when the feature is implemented, testable and documented. Defer incomplete integrations.
- Main source of truth: [Master Roadmap Issue #1](https://github.com/Cardsmageanime/RetroRelay/issues/1), this file and each linked feature issue.
