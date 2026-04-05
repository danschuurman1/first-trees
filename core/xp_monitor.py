# core/xp_monitor.py
from __future__ import annotations
import time
import numpy as np
from core.screen import ScreenCapture
from config import ColorProfile

# Standard top-center XP drop area (approximate for fixed mode)
XP_REGION = (330, 45, 100, 40) # x, y, w, h

class XPMonitor:
    def __init__(self, screen: ScreenCapture, profile: ColorProfile) -> None:
        self._screen = screen
        self._profile = profile
        self._last_xp_time = 0.0

    def detect_xp_drop(self) -> bool:
        """Scan the XP region for the green XP drop color."""
        if not self._profile.enabled:
            return False
            
        frame = self._screen.grab(XP_REGION)
        # BGR: index 2=R, 1=G, 0=B
        b = frame[:, :, 0].astype(np.int32)
        g = frame[:, :, 1].astype(np.int32)
        r = frame[:, :, 2].astype(np.int32)
        
        dist = np.sqrt(
            (r - self._profile.r) ** 2 + 
            (g - self._profile.g) ** 2 + 
            (b - self._profile.b) ** 2
        )
        matches = np.sum(dist <= self._profile.tolerance)
        
        # If we see enough green pixels, we count it as an XP drop
        if matches > 5:
            self._last_xp_time = time.monotonic()
            return True
        return False

    def is_idle(self, timeout: float = 15.0) -> bool:
        """Return True if no XP has been detected for 'timeout' seconds."""
        # Proactively check for a drop right now
        self.detect_xp_drop()
        return (time.monotonic() - self._last_xp_time) > timeout

    def reset(self) -> None:
        """Reset the timer (e.g. after a new click)."""
        self._last_xp_time = time.monotonic()
