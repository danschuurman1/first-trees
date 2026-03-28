# core/screen.py
from __future__ import annotations
import numpy as np
import mss
import mss.tools
from typing import Tuple


class ScreenCapture:
    """Thread-safe screen region grabber. Returns BGR numpy arrays (OpenCV format)."""

    def __init__(self) -> None:
        self._sct = mss.mss()

    def grab(self, region: Tuple[int, int, int, int]) -> np.ndarray:
        """Capture region (left, top, width, height) → BGR ndarray."""
        mon = {"left": region[0], "top": region[1],
               "width": region[2], "height": region[3]}
        raw = self._sct.grab(mon)
        # mss returns BGRA; drop alpha, keep BGR
        arr = np.array(raw)[:, :, :3]
        return arr

    def grab_full(self) -> np.ndarray:
        mon = self._sct.monitors[1]
        raw = self._sct.grab(mon)
        return np.array(raw)[:, :, :3]

    def pixel_color(self, x: int, y: int) -> Tuple[int, int, int]:
        """Return (R, G, B) of a single screen pixel."""
        arr = self.grab((x, y, 1, 1))
        b, g, r = int(arr[0, 0, 0]), int(arr[0, 0, 1]), int(arr[0, 0, 2])
        return r, g, b
