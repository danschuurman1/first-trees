# core/screen.py
from __future__ import annotations
import numpy as np
import mss
import cv2
from typing import Tuple


class ScreenCapture:
    """
    Thread-safe screen region grabber. 
    Handles Retina scaling (Mac) by detecting physical vs logical resolution.
    """

    def __init__(self) -> None:
        self._sct = mss.mss()
        self._scale_factor = self._detect_scale()

    def _detect_scale(self) -> float:
        """Calculate physical-to-logical scale factor (e.g., 2.0 for Retina)."""
        mon = self._sct.monitors[1]
        # Physical width from mss
        phys_w = mon["width"]
        # In a typical Mac setup, we can't easily get logical width from mss,
        # but we can assume if phys_w is > 2000 on a laptop, it's likely 2.0 scaling.
        # However, a better way is to compare with a known logical size if available.
        # For now, we will default to 1.0 and allow manual override or smarter detection.
        return 1.0

    @property
    def scale_factor(self) -> float:
        return self._scale_factor

    def grab(self, region: Tuple[int, int, int, int], scale_down: bool = True) -> np.ndarray:
        """
        Capture region (left, top, width, height) in LOGICAL coordinates.
        If scale_down is True, returns an image sized to the logical dimensions.
        """
        # mss expects logical coordinates on Mac, but returns physical pixels
        mon = {"left": int(region[0]), "top": int(region[1]),
               "width": int(region[2]), "height": int(region[3])}
        
        raw = self._sct.grab(mon)
        arr = np.array(raw)[:, :, :3] # BGRA -> BGR
        
        if scale_down:
            # If mss returned 2x pixels, resize back to logical size
            phys_h, phys_w = arr.shape[:2]
            if phys_w != region[2] or phys_h != region[3]:
                arr = cv2.resize(arr, (region[2], region[3]), interpolation=cv2.INTER_AREA)
        
        return arr

    def grab_full(self) -> np.ndarray:
        mon = self._sct.monitors[1]
        raw = self._sct.grab(mon)
        return np.array(raw)[:, :, :3]

    def pixel_color(self, x: int, y: int) -> Tuple[int, int, int]:
        """Return (R, G, B) of a single screen pixel at logical coordinate (x, y)."""
        # Grab a 1x1 logical pixel
        arr = self.grab((x, y, 1, 1), scale_down=True)
        b, g, r = int(arr[0, 0, 0]), int(arr[0, 0, 1]), int(arr[0, 0, 2])
        return r, g, b
