# bots/woodcutter.py
from __future__ import annotations
import math
import random
import time
from pathlib import Path
from typing import List, Optional, Set, Tuple

import numpy as np

import cv2

from bots.base_bot import Bot
from config import BotConfig, ConfigManager
from core.calibrate import find_runelight_origin
from core.color import ColorDetector
from core.keyboard import KeyboardController
from core.mouse import MouseController
from core.screen import ScreenCapture

# Radius (px) scanned around the active tree position for cut signals
_SCAN_RADIUS = 80

# Movement detection
_MOVE_STABLE_THRESHOLD = 10.0
_MOVE_STABLE_COUNT = 2
_MOVE_TIMEOUT = 8.0

# Baseline: blobs within this many px of a known-existing stump are ignored
_BASELINE_EXCLUSION_RADIUS = 15

# Pre-click verification: region size and minimum cyan pixel count required
_VERIFY_RADIUS = 15          # grab a 30x30 region around the centroid
_VERIFY_MIN_PIXELS = 10      # must have at least this many cyan pixels to confirm


def chebyshev(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class WoodcutterBot(Bot):
    """
    Woodcutting bot loop:
      1. Scan viewport for cyan tree blobs
      2. Click nearest blob centroid
      3. Wait for player movement to stop
      4. Re-locate tree at new screen position after walking
      5. Snapshot existing stump blobs as baseline (pre-existing stumps ignored)
      6. Poll region for NEW stump blobs or cyan disappearing
      7. Wait 1–3 s, repeat
    """

    name = "Woodcutter"

    def __init__(self, config: Optional[BotConfig] = None) -> None:
        super().__init__()
        cfg_mgr = ConfigManager()
        self._cfg = config or cfg_mgr.get_current_preset()
        self._screen = ScreenCapture()
        self._color = ColorDetector()
        self._mouse = MouseController()
        self._keyboard = KeyboardController()
        self._origin: Tuple[int, int] = find_runelight_origin()
        from bots.inventory_count_bot import InventoryCountBot
        self._inv_bot = InventoryCountBot(config=self._cfg)
        from bots.willow_banker import WillowBankerBot
        self._banker_bot = WillowBankerBot(config=self._cfg)
        self._next_inv_poll: float = 0.0

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_loop(self) -> None:
        if self.stop_if_runtime_elapsed(self._cfg):
            return

        # Periodic inventory poll — check every 10–20 s without interrupting chops
        now = time.monotonic()
        if now >= self._next_inv_poll:
            self._next_inv_poll = now + random.uniform(10.0, 20.0)
            window = self._banker_bot._grab_window()
            log_count = self._banker_bot._count_logs_in_window(window)
            self.log(f"Inventory poll: {log_count} log(s)")
            if log_count >= 27:
                self.log("Inventory full — handing off to Willow Banker...")
                self._banker_bot._run_banking_if_ready()
                while not self._banker_bot.log_queue.empty():
                    self.log(self._banker_bot.log_queue.get_nowait())
                self.log("Banking done — resuming chopping")
                return

        tree_pos = self._nearest_living_tree()

        if tree_pos is not None:
            if not self._confirm_cyan_at(tree_pos):
                self.log("Pre-click check failed — no cyan at target, skipping")
                return
            self.log(f"Clicking tree at {tree_pos}")
            self._mouse.move_and_click(tree_pos)
            self.micro_pause()

            # Wait for player to stop walking
            self._wait_for_movement_stop()

            # Re-locate tree at its post-walk screen position
            active_pos = self._relocate_tree()
            if active_pos is None:
                self.log("Tree already gone after walking — skipping wait")
            else:
                if active_pos != tree_pos:
                    self.log(f"Tree relocated to {active_pos}")

                # Snapshot existing stumps BEFORE we start watching — these are
                # from previous cuts and must not trigger the cut signal
                baseline = self._snapshot_stump_baseline(active_pos)
                if baseline:
                    self.log(f"Baseline: {len(baseline)} existing stump(s) excluded")

                self._wait_for_cut(active_pos, baseline)

            self.random_sleep(1.0, 3.0)
        else:
            self.log("No trees found — delegating to inventory drop")
            self._inv_bot.run_loop()
            # relay inventory bot logs into the woodcutter log stream
            while not self._inv_bot.log_queue.empty():
                self.log(self._inv_bot.log_queue.get_nowait())
            self.random_sleep(2.0, 4.0)

    # ------------------------------------------------------------------
    # Tree detection
    # ------------------------------------------------------------------

    def _nearest_living_tree(self) -> Optional[Tuple[int, int]]:
        """Scan viewport for cyan tree blobs and return the nearest centroid."""
        ox, oy = self._origin
        viewport = self._screen.grab((ox + 4, oy + 4, 512, 334))
        clusters = self._color.find_clusters(
            viewport, self._cfg.tree_color, region_offset=(ox + 4, oy + 4)
        )
        if not clusters:
            return None
        center = (ox + 4 + 512 // 2, oy + 4 + 334 // 2)
        return min(
            clusters,
            key=lambda c: max(abs(c[0] - center[0]), abs(c[1] - center[1]))
        )

    def _wait_for_tree_gone(self, pos: Tuple[int, int]) -> None:
        """Poll pos pixel until it no longer matches tree_color."""
        self.log("Waiting for tree to be cut...")
        deadline = time.monotonic() + 35.0
        profile = self._cfg.tree_color
        while time.monotonic() < deadline and self._running.is_set():
            r, g, b = self._screen.pixel_color(pos[0], pos[1])
            dist = math.sqrt(
                (r - profile.r) ** 2 + (g - profile.g) ** 2 + (b - profile.b) ** 2
            )
            if dist > profile.tolerance:
                self.log("Tree cut — looking for next")
                return
            self.random_sleep(0.5, 1.0)
        self.log("Tree chop wait timed out")

    # ------------------------------------------------------------------
    # Pre-click cyan verification
    # ------------------------------------------------------------------

    def _confirm_cyan_at(self, pos: Tuple[int, int]) -> bool:
        """
        Re-grab a tight region around the centroid on a fresh screenshot and
        count cyan-matching pixels. Returns True only if the count meets the
        minimum threshold — confirms the target is genuinely cyan before clicking.
        """
        x, y = pos
        region = (
            x - _VERIFY_RADIUS,
            y - _VERIFY_RADIUS,
            _VERIFY_RADIUS * 2,
            _VERIFY_RADIUS * 2,
        )
        frame = self._screen.grab(region)
        profile = self._cfg.tree_color
        arr = np.asarray(frame, dtype=np.int32)
        # mss returns BGRA: index 2=R, 1=G, 0=B
        r = arr[:, :, 2]
        g = arr[:, :, 1]
        b = arr[:, :, 0]
        dist = np.sqrt((r - profile.r) ** 2 + (g - profile.g) ** 2 + (b - profile.b) ** 2)
        cyan_count = int(np.sum(dist <= profile.tolerance))
        self.log(f"Pre-click verify: {cyan_count} cyan px at {pos} (need {_VERIFY_MIN_PIXELS})")
        return cyan_count >= _VERIFY_MIN_PIXELS

    # ------------------------------------------------------------------
    # Movement detection
    # ------------------------------------------------------------------

    def _wait_for_movement_stop(self) -> None:
        """Wait until the viewport stops scrolling (player reached the tree)."""
        ox, oy = self._origin
        check_region = (ox + 150, oy + 80, 200, 150)
        prev = np.array(self._screen.grab(check_region), dtype=float)
        stable = 0
        deadline = time.monotonic() + _MOVE_TIMEOUT
        while time.monotonic() < deadline and self._running.is_set():
            time.sleep(0.25)
            curr = np.array(self._screen.grab(check_region), dtype=float)
            diff = float(np.mean(np.abs(curr - prev)))
            if diff < _MOVE_STABLE_THRESHOLD:
                stable += 1
                if stable >= _MOVE_STABLE_COUNT:
                    self.log("Player stopped — checking tree")
                    return
            else:
                stable = 0
            prev = curr
        self.log("Movement timeout — proceeding")

    # ------------------------------------------------------------------
    # Tree relocation
    # ------------------------------------------------------------------

    def _relocate_tree(self) -> Optional[Tuple[int, int]]:
        """Re-scan viewport for cyan tree after walking. Returns None if gone."""
        ox, oy = self._origin
        viewport = self._screen.grab((ox + 4, oy + 4, 512, 334))
        clusters = self._color.find_clusters(
            viewport, self._cfg.tree_color, region_offset=(ox + 4, oy + 4)
        )
        if not clusters:
            return None
        center = (ox + 4 + 512 // 2, oy + 4 + 334 // 2)
        return min(
            clusters,
            key=lambda c: max(abs(c[0] - center[0]), abs(c[1] - center[1]))
        )

    # ------------------------------------------------------------------
    # Baseline snapshot (Option 2)
    # ------------------------------------------------------------------

    def _snapshot_stump_baseline(self, tree_pos: Tuple[int, int]) -> List[Tuple[int, int]]:
        """
        Capture all stump-colored blobs currently visible in the scan region.
        These are pre-existing stumps from prior cuts. Any blob in this list
        will be ignored during cut detection.
        """
        x, y = tree_pos
        region = (x - _SCAN_RADIUS, y - _SCAN_RADIUS, _SCAN_RADIUS * 2, _SCAN_RADIUS * 2)
        frame = self._screen.grab(region)
        existing: List[Tuple[int, int]] = []
        if self._cfg.stump_color.enabled:
            existing += self._color.find_clusters(frame, self._cfg.stump_color)
        if self._cfg.stump_color2.enabled:
            existing += self._color.find_clusters(frame, self._cfg.stump_color2)
        return existing

    def _is_new_blob(
        self, blob: Tuple[int, int], baseline: List[Tuple[int, int]]
    ) -> bool:
        """Return True if this blob is NOT within exclusion radius of any baseline blob."""
        bx, by = blob
        for ex, ey in baseline:
            if max(abs(bx - ex), abs(by - ey)) <= _BASELINE_EXCLUSION_RADIUS:
                return False
        return True

    # ------------------------------------------------------------------
    # Cut detection (dual signal + baseline exclusion)
    # ------------------------------------------------------------------

    def _wait_for_cut(
        self, tree_pos: Tuple[int, int], baseline: List[Tuple[int, int]]
    ) -> None:
        """
        Poll scan region for cut signals, ignoring pre-existing stumps:
          Signal A  — NEW stump color blob appears (not in baseline)
          Signal A2 — NEW stump color 2 blob appears (not in baseline)
          Signal B  — cyan completely gone from region
        """
        x, y = tree_pos
        region = (x - _SCAN_RADIUS, y - _SCAN_RADIUS, _SCAN_RADIUS * 2, _SCAN_RADIUS * 2)
        use_stump = self._cfg.stump_color.enabled
        use_stump2 = self._cfg.stump_color2.enabled
        self.log("Watching for cut signal (stump + cyan scan)...")

        deadline = time.monotonic() + 35.0
        while time.monotonic() < deadline and self._running.is_set():
            frame = self._screen.grab(region)

            # Signal A: new stump color blob (not a pre-existing stump)
            if use_stump:
                for blob in self._color.find_clusters(frame, self._cfg.stump_color):
                    if self._is_new_blob(blob, baseline):
                        self.log("New stump detected — tree cut")
                        return

            # Signal A2: new stump color 2 blob
            if use_stump2:
                for blob in self._color.find_clusters(frame, self._cfg.stump_color2):
                    if self._is_new_blob(blob, baseline):
                        self.log("New stump 2 detected — tree cut")
                        return

            # Signal B: cyan completely gone from region
            if not self._color.find_clusters(frame, self._cfg.tree_color):
                self.log("Cyan cleared from region — tree cut")
                return

            self.random_sleep(0.5, 1.0)

        self.log("Chop timeout — moving on")


WoodcutterBot.register()
