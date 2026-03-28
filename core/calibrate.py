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
        pos_r = subprocess.run(
            ['osascript', '-e',
             'tell application "System Events" to tell process "RuneLite" to get position of window 1'],
            capture_output=True, text=True, timeout=3,
        )
        size_r = subprocess.run(
            ['osascript', '-e',
             'tell application "System Events" to tell process "RuneLite" to get size of window 1'],
            capture_output=True, text=True, timeout=3,
        )
        if pos_r.returncode == 0 and size_r.returncode == 0:
            px, py = (int(v) for v in pos_r.stdout.strip().split(', '))
            _sw, sh = (int(v) for v in size_r.stdout.strip().split(', '))
            title_bar = sh - 503  # OSRS fixed client content height is always 503
            return (px, py + max(title_bar, 0))
    except Exception:
        pass
    return (0, 0)
