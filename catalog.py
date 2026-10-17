"""Supported platforms and intentionally conservative emulator integrations."""

PLATFORMS = {
    "Nintendo SNES": ["RetroArch", "Snes9x"],
    "Nintendo 64": ["RetroArch", "simple64", "Project64"],
    "Nintendo GameCube": ["Dolphin"],
    "Nintendo Wii": ["Dolphin"],
    "Nintendo Wii U": ["Cemu"],
    "Nintendo Game Boy": ["RetroArch", "mGBA"],
    "Nintendo Game Boy Color": ["RetroArch", "mGBA"],
    "Nintendo Game Boy Advance": ["RetroArch", "mGBA"],
    "Nintendo DS": ["melonDS"],
    "Nintendo 3DS": ["Azahar"],
    "PlayStation 1": ["DuckStation", "RetroArch"],
    "PlayStation 2": ["PCSX2"],
    "PlayStation 3": ["RPCS3"],
    "PlayStation Portable": ["PPSSPP"],
    "Sega Genesis": ["RetroArch", "BlastEm", "Kega Fusion"],
    "Sega CD": ["RetroArch", "Kega Fusion"],
    "Sega 32X": ["RetroArch", "PicoDrive"],
    "Sega Saturn": ["RetroArch", "Mednafen", "Kronos"],
    "Sega Dreamcast": ["Flycast", "Redream", "RetroArch"],
    "Xbox": ["xemu"],
    "Xbox 360": ["Xenia", "Xenia Canary"],
    "PC (legacy games)": ["PC Game"],
}

MODES = {
    "retroarch": "RetroArch netplay (selected classic cores only)",
    "dolphin": "Dolphin native netplay (GameCube / Wii)",
    "game_network": "Game's own networking (manual setup)",
    "parsec": "Parsec shared-controller remote play (host handles streaming)",
    "hamachi": "Hamachi VPN / LAN play (game needs LAN support)",
}

# RetroArch rewind netplay is not suitable for every core or console.
RETROARCH_NETPLAY_PLATFORMS = {
    "Nintendo SNES", "Sega Genesis", "Sega CD", "Sega 32X",
}


def compatible_mode(platform: str, emulator: str, mode: str) -> bool:
    if platform not in PLATFORMS or emulator not in PLATFORMS[platform] or mode not in MODES:
        return False
    if mode == "retroarch":
        return emulator == "RetroArch" and platform in RETROARCH_NETPLAY_PLATFORMS
    if mode == "dolphin":
        return emulator == "Dolphin" and platform in {"Nintendo GameCube", "Nintendo Wii"}
    return True
