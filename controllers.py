"""Local input-device discovery. Device descriptions are NOT anti-cheat attestations.

SDL controller GUIDs describe device *types*, not trustworthy serial numbers. Do
not attempt to use them for device authenticity, bans, or hardware tracking.
"""
from __future__ import annotations


def controller_family(name: str, kind: str = "gamepad") -> str:
    """User-facing family based on the OS-provided label (which can be spoofed)."""
    if kind in ("keyboard", "mouse"):
        return "PC input"
    label = name.casefold()
    if any(word in label for word in ("dualsense", "dualshock", "playstation", "sony")):
        return "PlayStation-style"
    if any(word in label for word in ("xbox", "xinput", "microsoft")):
        return "Xbox-style"
    if any(word in label for word in ("switch", "joy-con", "joycon", "nintendo", "pro controller")):
        return "Nintendo-style"
    if label.strip() == "wireless controller":
        return "PlayStation-style"  # Common SDL name for DualShock 4; unverified.
    return "Generic / other gamepad"


def detect_input_devices(pygame_module=None) -> list[dict]:
    """Enumerate SDL game controllers + ordinary keyboard/mouse options.

    Keyboard and mouse entries are system input *options*, not proof that a
    particular physical keyboard or mouse has been attached. Gamepad scanning
    needs the optional pygame package and OS-level device permission.
    """
    devices = [
        {"kind": "keyboard", "name": "Keyboard (system input)", "guid": "", "family": "PC input"},
        {"kind": "mouse", "name": "Mouse (system input)", "guid": "", "family": "PC input"},
    ]
    if pygame_module is None:
        try:
            import pygame as pygame_module
        except ImportError:
            # Make keyboard/mouse registration possible on computers without SDL.
            return devices
    pygame_module.joystick.init()
    try:
        for index in range(pygame_module.joystick.get_count()):
            joystick = pygame_module.joystick.Joystick(index)
            joystick.init()
            name = str(joystick.get_name() or f"Gamepad {index + 1}")[:100]
            guid = str(joystick.get_guid() or "")[:64]
            devices.append({"kind": "gamepad", "name": name, "guid": guid,
                            "family": controller_family(name)})
    finally:
        pygame_module.joystick.quit()
    return devices
