# Security and public-preview limits

RetroRelay v0.1.0 is an **early source-code preview for testers**, not a production-ready public multiplayer service. No public server or hosted accounts are provided.

- The hub lacks IP/account rate limiting, email verification, account recovery, anti-spam protections, moderation/reporting, production monitoring and a complete security audit. **Do not open registration to the general public yet.**
- Run local testing on your own PC or a trusted private LAN. If you host remotely for a small group, use HTTPS and monitor your deployment; never forward an unencrypted login endpoint to the internet.
- Never commit `.env` files, live SQLite databases, credentials, tokens, VPN secrets, or user data. `.gitignore` protects typical names but verify before every upload.
- Do not upload or distribute copyrighted game ROMs, BIOS images, firmware, proprietary emulator executables or paid content.
- Parsec, Hamachi and emulator network features are **external software** with their own accounts, permissions and compatibility constraints. The lobby server does not stream games or emulate networking protocols.
- ROM/game hashes and emulator version strings are self-reported by clients and cannot independently prove compatibility or game ownership.

For security problems, use a private message to the repository owner rather than including exploit details or personal data in a public issue.
