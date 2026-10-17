# Security and public-preview limits

RetroRelay v0.1.0 is an **early source-code preview for testers**, not a production-ready public multiplayer service. No public server or hosted accounts are provided.

- The hub lacks IP/account rate limiting, email verification, account recovery, anti-spam protections, moderation/reporting, production monitoring and a complete security audit. **Do not open registration to the general public yet.**
- Run local testing on your own PC or a trusted private LAN. If you host remotely for a small group, use HTTPS and monitor your deployment; never forward an unencrypted login endpoint to the internet.
- Never commit `.env` files, live SQLite databases, credentials, tokens, VPN secrets, or user data. `.gitignore` protects typical names but verify before every upload.
- Do not upload or distribute copyrighted game ROMs, BIOS images, firmware, proprietary emulator executables or paid content.
- Parsec, Hamachi and emulator network features are **external software** with their own accounts, permissions and compatibility constraints. The lobby server does not stream games or emulate networking protocols.
- ROM/game hashes and emulator version strings are self-reported by clients and cannot independently prove compatibility or game ownership.

For security problems, use a private message to the repository owner rather than including exploit details or personal data in a public issue.

## Controller registration security boundaries (October preview)

Controller names and SDL GUIDs are locally collected, self-reported descriptions. They
are **not** tamper-resistant IDs, official manufacturer authentication or proof that an
input device is free of macros/cheats. Any client can lie about the controller model,
and game input is processed by the emulator or external remote-play system, not this
hub. Never automatically ban accounts or accuse players based on these labels.

The server enforces only that selected input registrations belong to the user and
new controller-required rooms have selections before the user can join or ready up.
No input events, keyboard captures, hardware serials or controller button histories
are collected by the hub. Other room members see the chosen device label.

### Game artwork preview limitations
Hosts affirm they may publish the art. This is a self-declaration, not a license audit or content-moderation pipeline. A public production hub needs abuse reports, moderation, per-user storage/rate quotas, hardened image processing with sandboxing, and a takedown process. The server strips metadata and transcodes only small source PNG/JPEG/WebP images; do not treat that as complete security isolation. The client does not fetch arbitrary user-provided external image URLs. The lobby never transfers game ROM/ISO bytes.

## Social profile URL preview
Stored social URLs are self-reported, private per account, and unverified. Allowlisted provider hostname/path, HTTPS, and no query/fragment/port/userinfo prevent common unsafe URL forms; opening an external website is at the user's discretion. **No provider OAuth, proof of channel ownership, or access tokens are involved.** Real social connections must use official consent and server-managed token storage, revocation, state/PKCE as required, rate limiting, and platform review.

## October phone authenticator MFA (preview; not publicly security audited)

- **True two factors** are RetroRelay password plus a separately configured TOTP authenticator on the user's phone. **Password plus PIN is not MFA**. SMS/phone-number texting and standalone PIN login are **not implemented**.
- A verified 30-second TOTP or unused 128-bit recovery code is required before the API issues a new full account session. Challenge-only tokens cannot access private endpoints; TOTP steps and recovery codes are single-use. Per-account attempt limits temporarily block excessive guesses.
- MFA secrets are encrypted using a Fernet key stored in the server's `RETRORELAY_MFA_KEY` environment variable, not the database. There is **no fallback key**: missing or changed key causes MFA operations to fail closed.
- Server operators must maintain encrypted backups of the database and a **separate confidential backup of that key**. Never copy `.env` or recovery codes into the repository, logs, or chat. Losing the key can lock out enrolled accounts and require administrator intervention.
- Enabling MFA requires a current account password and a valid code. Disabling it requires the account password and an existing OTP/recovery code. Other sessions are revoked after enabling/disabling it; however, a compromised current session may remain until revoked.
- **Not yet production hardened:** IP/global traffic limiting, account recovery verification, monitoring and alerts, anti-enumeration, phishing-resistant passkeys, transparent password-breach screening and independent security audit remain outstanding. MFA greatly reduces some credential-theft risks but is not hack-proof.

Track security review and feature readiness in [Issue #9](https://github.com/Cardsmageanime/RetroRelay/issues/9).
