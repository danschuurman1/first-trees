# bots/woodcutter.py
from __future__ import annotations
import math
import random
import time
from typing import List, Optional, Set, Tuple

import numpy as np

from bots.base_bot import Bot
from config import BotConfig, ConfigManager
from core.calibrate import find_runelight_origin
from core.color import ColorDetector
from core.keyboard import KeyboardController
from core.mouse import MouseController
from core.screen import ScreenCapture

# OSRS fixed client inventory grid (all coords relative to client origin)
_INV_TAB_X = 644      # backpack tab icon x (client-relative)
_INV_TAB_Y = 169      # backpack tab icon y (client-relative)
_INV_GRID_X = 548     # left edge of inventory grid (client-relative)
_INV_GRID_Y = 205     # top edge of inventory grid (client-relative)
_INV_SLOT_W = 42      # horizontal pitch between slot centres
_INV_SLOT_H = 36      # vertical pitch between slot centres
_INV_COLS = 4
_INV_ROWS = 7

# Inventory tab: red (active/open) vs grey (inactive/closed)
_INV_OPEN_R_MIN = 100
_INV_OPEN_BIAS  = 50

# A slot is "filled" when its centre pixel has max(R,G,B) above this level.
# Empty slot background is ~rgb(55, 52, 48); any item is brighter.
_SLOT_FILLED_THRESHOLD = 65

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
        self._cfg = config or cfg_mgr.config
        self._screen = ScreenCapture()
        self._color = ColorDetector()
        self._mouse = MouseController()
        self._keyboard = KeyboardController()
        self._origin: Tuple[int, int] = find_runelight_origin()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_loop(self) -> None:
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
            self.log("No trees found — dropping logs and waiting for respawn")
            self._drop_all_logs()
            self.random_sleep(2.0, 4.0)

    # ------------------------------------------------------------------
    # Inventory helpers
    # ------------------------------------------------------------------

    def _slot_positions(self) -> List[Tuple[int, int]]:
        """Return screen (x, y) centres for all 28 inventory slots."""
        ox, oy = self._origin
        positions: List[Tuple[int, int]] = []
        for row in range(_INV_ROWS):
            for col in range(_INV_COLS):
                x = ox + _INV_GRID_X + col * _INV_SLOT_W + _INV_SLOT_W // 2
                y = oy + _INV_GRID_Y + row * _INV_SLOT_H + _INV_SLOT_H // 2
                positions.append((x, y))
        return positions

    def _is_slot_filled(self, pos: Tuple[int, int]) -> bool:
        """Empty slots are ~rgb(55,52,48). Any item raises max(R,G,B) above threshold."""
        r, g, b = self._screen.pixel_color(pos[0], pos[1])
        return max(r, g, b) > _SLOT_FILLED_THRESHOLD

    def _is_slot_log(self, pos: Tuple[int, int]) -> bool:
        """Return True if the slot centre pixel matches the log_color profile."""
        if not self._cfg.log_color.enabled:
            return False
        profile = self._cfg.log_color
        r, g, b = self._screen.pixel_color(pos[0], pos[1])
        dist = math.sqrt(
            (r - profile.r) ** 2 + (g - profile.g) ** 2 + (b - profile.b) ** 2
        )
        return dist <= profile.tolerance

    def _count_filled_slots(self) -> int:
        return sum(1 for pos in self._slot_positions() if self._is_slot_filled(pos))

    def _is_inventory_open(self) -> bool:
        """Red tab background = open; grey = closed."""
        ox, oy = self._origin
        r, g, b = self._screen.pixel_color(ox + _INV_TAB_X, oy + _INV_TAB_Y)
        return r > _INV_OPEN_R_MIN and r > g + _INV_OPEN_BIAS and r > b + _INV_OPEN_BIAS

    def _ensure_inventory_open(self) -> None:
        """Click the backpack tab only when it is currently closed."""
        if not self._is_inventory_open():
            ox, oy = self._origin
            self._mouse.move_and_click((ox + _INV_TAB_X, oy + _INV_TAB_Y))
            self.random_sleep(0.2, 0.4)

    def _inventory_full(self) -> bool:
        self._ensure_inventory_open()
        return self._count_filled_slots() >= 28

    def _inventory_has_logs(self) -> bool:
        self._ensure_inventory_open()
        return self._count_filled_slots() > 0

    def _drop_all_logs(self) -> None:
        """Hold Shift and left-click every log slot in a randomized order."""
        self._ensure_inventory_open()
        if self._cfg.log_color.enabled:
            log_slots = [pos for pos in self._slot_positions() if self._is_slot_log(pos)]
        else:
            log_slots = [pos for pos in self._slot_positions() if self._is_slot_filled(pos)]
        if not log_slots:
            return
        random.shuffle(log_slots)
        if random.random() < 0.30:
            mid = random.randint(1, len(log_slots))
            log_slots = log_slots[mid:] + log_slots[:mid]
        self._keyboard.press_shift()
        try:
            for pos in log_slots:
                self._mouse.move_and_click(pos)
                self.micro_pause()
        finally:
            self._keyboard.release_shift()

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
