# core/calibrate.py
from __future__ import annotations
import subprocess
from typing import Tuple


def find_runelight_origin() -> Tuple[int, int]:
    """Return (left, top) of the OSRS client content area in screen coordinates.

    Uses AppleScript to query the RuneLite window position and size.
    The OSRS fixed client is 765x503. Any excess window height is title bar chrome.
    Falls back to (0, 0) if detection fails.
    """
    try:
        # Single query avoids the intermittent "Invalid index" error from two
        # separate AppleScript calls racing against each other.
        r = subprocess.run(
            ['osascript', '-e',
             'tell application "System Events" to tell process "RuneLite" '
             'to get {position, size} of window 1'],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0:
            parts = [int(v.strip()) for v in r.stdout.strip().split(',')]
            px, py, _sw, sh = parts
            title_bar = sh - 503  # OSRS fixed client content height is always 503
            return (px, py + max(title_bar, 0))
    except Exception:
        pass
    return (0, 0)
