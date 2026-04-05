# bots/inventory_count_bot.py
"""
Standalone test script: Inventory Count
----------------------------------------
Grabs the full screen, finds all blobs matching log_color (the pink
Inventory Tags highlight), and shift-clicks each one to drop the logs.
"""
from __future__ import annotations
import random
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from bots.base_bot import Bot
from config import ConfigManager, BotConfig
from core.color import ColorDetector
from core.keyboard import KeyboardController
from core.mouse import MouseController
from core.screen import ScreenCapture


class InventoryCountBot(Bot):
    """
    Test script — Inventory Count.

    Each loop:
      1. Grab the full screen and find all blobs matching log_color.
      2. If blobs found, shift-click each centroid to drop the logs.
    """

    name = "Inventory Count"

    def __init__(self, config: Optional[BotConfig] = None) -> None:
        super().__init__()
        cfg_mgr = ConfigManager()
        self._cfg      = config or cfg_mgr.get_current_preset()
        self._screen   = ScreenCapture()
        self._mouse    = MouseController()
        self._kbd      = KeyboardController()
        self._detector = ColorDetector()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_loop(self) -> None:
        slots = self._find_log_slots()
        self.log(f"Log blobs found: {len(slots)}")
        if not slots:
            self.log("No logs detected — waiting 2 s")
            time.sleep(2.0)
            return
        self._drop_slots(slots)
        time.sleep(random.uniform(0.8, 1.5))

    # ------------------------------------------------------------------
    # Log detection
    # ------------------------------------------------------------------

    def _find_log_slots(self) -> List[Tuple[int, int]]:
        """Full-screen grab → pink color mask → blob centroids as logical coords."""
        profile = self._cfg.log_color
        if not profile.enabled:
            self.log("log_color is disabled — enable it in the Colors tab and set the pink color")
            return []

        frame = self._screen.grab_full()
        logical_width = self._screen._sct.monitors[1]["width"]

        slots = self._detector.find_log_slots(frame, profile, logical_width)
        for i, (cx, cy) in enumerate(slots, 1):
            self.log(f"  blob {i}: logical ({cx}, {cy})")
        return slots

    # ------------------------------------------------------------------
    # Drop
    # ------------------------------------------------------------------

    def _drop_slots(self, slots: List[Tuple[int, int]]) -> None:
        random.shuffle(slots)
        self.log(f"Dropping {len(slots)} slot(s)...")
        subprocess.run(
            ["osascript", "-e", 'tell application "RuneLite" to activate'],
            capture_output=True, timeout=2,
        )
        time.sleep(random.uniform(0.10, 0.18))  # wait for RuneLite to gain focus
        self._kbd.press_shift()
        time.sleep(random.uniform(0.08, 0.15))  # let game register shift before first click
        try:
            for i, pos in enumerate(slots, 1):
                self.log(f"  Drop {i}/{len(slots)} at {pos}")
                self._mouse.move_and_click(pos)
                time.sleep(random.uniform(0.12, 0.28))  # gap between drops
        finally:
            time.sleep(random.uniform(0.06, 0.12))  # hold shift briefly after last click
            self._kbd.release_shift()
        self.log("Drop complete")

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------

    def save_debug_screenshot(self) -> None:
        """Save the current full-screen grab to ~/Desktop/inv_count_test.png."""
        frame = self._screen.grab_full()
        out = str(Path.home() / "Desktop" / "inv_count_test.png")
        cv2.imwrite(out, frame)
        self.log(f"Debug screenshot saved → {out}")


InventoryCountBot.register_test()
