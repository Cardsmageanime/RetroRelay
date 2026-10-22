"""Strictly validated, UNVERIFIED public social profile links.

This module does not authorize users or communicate with external platforms.
True provider account connections require OAuth and developer configuration.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

SOCIAL_PROVIDERS = {
    "twitch": {"name": "Twitch", "domains": ("twitch.tv", "www.twitch.tv")},
    "youtube": {"name": "YouTube", "domains": ("youtube.com", "www.youtube.com")},
    "tiktok": {"name": "TikTok", "domains": ("tiktok.com", "www.tiktok.com")},
    "facebook": {"name": "Facebook", "domains": ("facebook.com", "www.facebook.com")},
    "instagram": {"name": "Instagram", "domains": ("instagram.com", "www.instagram.com")},
}

SEG = r"[A-Za-z0-9._-]{2,64}"
PATHS = {
    "twitch": re.compile(rf"/{SEG}/?"),
    "youtube": re.compile(rf"/(?:@{SEG}|channel/{SEG}|user/{SEG}|c/{SEG})/?"),
    "tiktok": re.compile(rf"/@{SEG}/?"),
    "facebook": re.compile(rf"/{SEG}/?"),
    "instagram": re.compile(rf"/{SEG}/?"),
}


def validate_social_url(provider: str, url: str) -> str:
    """Require an HTTPS profile URL on a known exact provider host.

    Links are not proof of account ownership. Constrain the path and strip no
    characters, so trick URLs are refused rather than silently changed.
    """
    provider = provider.lower().strip()
    if provider not in SOCIAL_PROVIDERS:
        raise ValueError("This social platform is not supported yet")
    if not isinstance(url, str) or len(url) > 280 or url != url.strip():
        raise ValueError("Use a valid social profile URL no longer than 280 characters")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid social profile URL") from exc
    if (parsed.scheme != "https" or host not in SOCIAL_PROVIDERS[provider]["domains"]
            or port is not None or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not PATHS[provider].fullmatch(parsed.path)):
        raise ValueError("Enter a direct HTTPS profile/channel URL on the selected platform")
    if any(ord(c) < 33 or ord(c) > 126 for c in url):
        raise ValueError("The social URL must be printable ASCII; use an encoded public handle")
    return url
