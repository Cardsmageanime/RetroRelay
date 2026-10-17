# Contributing to RetroRelay

Thanks for your interest in RetroRelay, a **work-in-progress source-code preview** for multiplayer lobbies and supported classic emulator netplay workflows.

## Before you begin

- [Read the README](README.md), including limitations and setup instructions.
- Check the [development roadmap](ROADMAP.md), [open issues](https://github.com/Cardsmageanime/RetroRelay/issues), and the [latest published preview](https://github.com/Cardsmageanime/RetroRelay/releases/tag/v0.1.0).
- **Important licensing note:** The repository is publicly readable, but no open-source license has yet been added. Public visibility is *not* permission to redistribute or reuse code outside GitHub's applicable terms. Before accepting substantive external code contributions or distributing derivative work, the maintainer should choose an appropriate license and clearly communicate contribution terms.

## How you can help now

1. **Give feedback:** Open an issue with a clear title, environment (Windows/Linux, emulator and exact version) and steps to reproduce. Never include passwords, account tokens, personal IP addresses, ROMs or copyrighted game data.
2. **Report compatibility findings:** Specify game/platform, emulator/core versions, native netplay versus host-streamed controller play, and what actually worked. A room listing doesn't guarantee game networking.
3. **Suggest UX/accessibility improvements:** Beginner-friendly setup, controller mapping, translations, clearer error messages and safety improvements are useful.
4. **Review the roadmap:** Submit suggestions for features that can be tested without violating game or platform terms. Please don't submit bundled copyrighted game images, commercial ROMs, keys, BIOS files or firmware.

## Code changes

If you wish to contribute code, first open an issue describing the change and discuss licensing/contribution terms with the maintainer. For agreed-upon changes:

- Work in a branch rather than pushing directly to `main`.
- Keep pull requests small and include tests for server, client and permission changes.
- Install developer dependencies with `python -m pip install -r requirements-dev.txt`; run `python -m pytest` and report the actual result.
- Document what you tested and what remains unverified, including OS and real controller/network hardware where relevant.
- Never commit secrets, emulator game ROMs/BIOS files, third-party credentials or private user content.

## Security

For potentially exploitable security issues, avoid publishing working exploit details or credentials in a public issue. Start by reading [SECURITY.md](SECURITY.md) and contact the maintainer through a private reporting channel if one is configured. Treat the current account and lobby server as **not hardened for open, unrestricted public hosting**.

## Project links

- [Main project](https://github.com/Cardsmageanime/RetroRelay)
- [Roadmap](ROADMAP.md)
- [Issues / feedback](https://github.com/Cardsmageanime/RetroRelay/issues)
- [Early preview release](https://github.com/Cardsmageanime/RetroRelay/releases/tag/v0.1.0)
