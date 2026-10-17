# Lobby art and two ways to play (v0.2.0 early preview)

## Images for any supported console or language

- Hosts can optionally select a local JPEG, PNG, or WebP **image they created or have permission to publish**. They must affirm rights to display it publicly.
- The server verifies and resizes artwork into a PNG thumbnail, strips metadata, and serves it to logged-in players. Art appears when browsing lobbies and inside the waiting room. If art is missing, the game/platform text remains visible.
- Titles use Unicode, including Japanese, Korean, Chinese, Arabic, and Latin characters. On some PCs, fonts may need to be installed for characters to render properly.
- The source bundle contains no copyrighted game artwork and does not silently scrape or redistribute third-party cover databases. To auto-populate licensed cover art across a large worldwide catalog in a later version, integrate a provider with suitable distribution rights/terms and require source attribution where appropriate. A host-uploaded image does **not** prove ownership; moderation is not yet implemented.
- Server checks: authenticated host only, decoded source under 800 KB, PNG/JPEG/WebP, <= 4 million pixels, normalized PNG no more than 400 KB. As with any public upload service, add moderation, rate limiting, antivirus/image sandboxing, and abuse reporting before wide deployment.

## Playing online

**Match my game copy:** RetroArch, Dolphin and other native networking modes still require participants to have the same game bytes, emulator versions, and required core versions. The hub is only a lobby coordinator; some emulators need manual netplay setup.

**Controller guest, no game file:** Create a `parsec`-mode room. The host runs their *own* locally installed game and runs Parsec hosting. Guests register a controller, join the RetroRelay room without selecting a ROM/emulator, then connect to the host in Parsec. The Parsec host approves the session and assigns controller access. RetroRelay itself does not encode video, relay input, or integrate Parsec's authentication; it simply displays the connection details and opens Parsec.

For Parsec host requirements and controller support see:
- https://support.parsec.app/hc/en-us/articles/32381747079572-Hosting-and-Permissions
- https://support.parsec.app/hc/en-us/articles/32381705301908-Setup-Gamepad

## Downloads and copyright

RetroRelay **does not upload, store, transmit, or distribute ROMs/ISOs**. Guests may provide their own lawful game copies. Parsec-style streaming does not send a ROM to guests. Distribution of public-domain or properly licensed homebrew games may be added in a future release with verified license information; blanket download sharing of commercial game files is not planned.

## Known limitations

This is preview source code, not a polished installer. Cover art is per lobby, not a complete built-in multi-platform cover art database. Automated test coverage does not establish physical-controller or live-Parsec compatibility. The public hub still requires authentication security hardening and content moderation.
