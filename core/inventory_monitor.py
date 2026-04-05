# core/inventory_monitor.py
from __future__ import annotations
import numpy as np
import cv2
import os
from pathlib import Path
from typing import Tuple, Optional, List
from core.screen import ScreenCapture
from config import ColorProfile

# Standard Fixed mode inventory region: (x, y, w, h)
INV_REGION = (548, 205, 172, 252) # The whole inventory grid area

# Individual slot centers (approx coordinates relative to client origin)
# 4 columns, 7 rows
SLOT_WIDTH = 42
SLOT_HEIGHT = 36
INV_START_X = 563
INV_START_Y = 213

def get_slot_coord(slot: int) -> Tuple[int, int]:
    """Returns logical (x, y) for slot 1-28."""
    idx = slot - 1
    col = idx % 4
    row = idx // 4
    return (INV_START_X + col * SLOT_WIDTH, INV_START_Y + row * SLOT_HEIGHT)

class InventoryMonitor:
    def __init__(self, screen: ScreenCapture, log_profile: ColorProfile) -> None:
        self._screen = screen
        self._log_profile = log_profile

    def count_items(self) -> int:
        """
        Scan the inventory area for items. 
        Uses the pink log highlight color profile to count blobs.
        """
        if not self._log_profile.enabled:
            return 0
            
        frame = self._screen.grab(INV_REGION)
        # BGR -> Mask
        b = frame[:, :, 0].astype(np.int32)
        g = frame[:, :, 1].astype(np.int32)
        r = frame[:, :, 2].astype(np.int32)
        
        dist = np.sqrt(
            (r - self._log_profile.r) ** 2 + 
            (g - self._log_profile.g) ** 2 + 
            (b - self._log_profile.b) ** 2
        )
        mask = (dist <= self._log_profile.tolerance).astype(np.uint8) * 255
        
        # Count distinct blobs (each represents one log)
        num_labels, _, _, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        # Background is label 0, so subtract 1
        return max(0, num_labels - 1)

    def is_slot_full(self, slot: int) -> bool:
        """Returns True if the center of a specific slot matches the log profile or isn't brown."""
        x, y = get_slot_coord(slot)
        r, g, b = self._screen.pixel_color(x, y)
        
        # 1. Matches log profile?
        dist = np.sqrt((r - self._log_profile.r)**2 + (g - self._log_profile.g)**2 + (b - self._log_profile.b)**2)
        if dist <= self._log_profile.tolerance:
            return True
            
        # 2. Not empty brown?
        is_empty_brown = (50 <= r <= 80) and (40 <= g <= 70) and (30 <= b <= 60)
        return not is_empty_brown

    def is_full(self) -> bool:
        """Robust check: is the inventory full (slot 28 filled or total count == 28)."""
        # First check the critical slot 28 (bottom right)
        if self.is_slot_full(28):
            return True
            
        # Double check with count if needed (slower but thorough)
        count = self.count_items()
        return count >= 28

    def save_debug(self) -> None:
        """Saves a screenshot of the inventory region for debugging."""
        frame = self._screen.grab(INV_REGION)
        desktop = Path.home() / "Desktop" / "debug_inventory_full.png"
        cv2.imwrite(str(desktop), frame)
