# core/geographic_leash.py
from __future__ import annotations
import numpy as np
from core.screen import ScreenCapture
from config import ColorProfile

# Viewport area to check for grid lines (approximate for fixed mode)
# Draynor bank area is usually within the main viewport
VIEWPORT_REGION = (4, 4, 512, 334) 

class GeographicLeash:
    def __init__(self, screen: ScreenCapture, profile: ColorProfile) -> None:
        self._screen = screen
        self._profile = profile

    def is_out_of_bounds(self) -> bool:
        """Return True if the grid lines are not visible in the viewport."""
        if not self._profile.enabled:
            return False
            
        frame = self._screen.grab(VIEWPORT_REGION)
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
        
        # If no grid pixels found, assume out of bounds
        return matches < 10
