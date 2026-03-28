# bots/woodcutter.py
from __future__ import annotations
import math
import random
import time
from typing import List, Optional, Tuple

from bots.base_bot import Bot
from config import BotConfig, ConfigManager
from core.calibrate import find_runelight_origin
from core.color import ColorDetector
from core.keyboard import KeyboardController
from core.mouse import MouseController
from core.screen import ScreenCapture
from core.scheduler import DowntimeScheduler


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


def chebyshev(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class WoodcutterBot(Bot):
    """
    Woodcutting bot decision tree:
      1. Inventory full (28 slots)? -> open tab, shift-drop all filled slots
      2. Animating? (only when anim_color enabled) -> wait for idle
      3. Tree visible? -> click it, wait for pixel colour to vanish
                         NO -> wait for respawn (no camera movement)
    Camera is never rotated. All coordinates are derived from the detected
    RuneLite window origin so the bot works regardless of window position.
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
        self._scheduler = DowntimeScheduler(
            self._cfg.downtime_windows,
            enabled=self._cfg.scheduler_enabled,
        )
        self._origin: Tuple[int, int] = find_runelight_origin()

    def run_loop(self) -> None:
        if self._scheduler.is_break_time():
            end = self._scheduler.next_break_end()
            self.log(f"Scheduled break until {end}")
            self.random_sleep(30, 60)
            return

        if self._inventory_full():
            if self._inventory_has_logs():
                self.log("Inventory full — dropping all items")
                self._drop_all_logs()
                self.random_sleep(0.8, 1.2)
                return
            else:
                self.log("HALT: inventory full but no items found")
                self.stop()
                return

        if self._is_animating():
            self.log("Chopping — waiting for idle")
            self._wait_for_idle()
            self.micro_pause()
            return

        tree_pos = self._nearest_living_tree()
        if tree_pos is not None:
            self.log(f"Clicking tree at {tree_pos}")
            actual_pos = self._mouse.move_and_click(tree_pos)
            self.micro_pause()
            if not self._cfg.anim_color.enabled:
                self._wait_for_tree_gone(actual_pos)
        else:
            self.log("No living trees — waiting for respawn")
            self.random_sleep(3.0, 6.0)

        self.random_sleep(self._cfg.min_delay, self._cfg.max_delay)

    # ------------------------------------------------------------------
    # Inventory helpers — slot-based detection (no colour matching)
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
        """Hold Shift and left-click every filled inventory slot."""
        self._ensure_inventory_open()
        filled = [pos for pos in self._slot_positions() if self._is_slot_filled(pos)]
        if not filled:
            return
        self._keyboard.press_shift()
        try:
            for pos in filled:
                self._mouse.move_and_click(pos)
                self.micro_pause()
        finally:
            self._keyboard.release_shift()

    # ------------------------------------------------------------------
    # Tree detection
    # ------------------------------------------------------------------

    def _wait_for_tree_gone(self, pos: Tuple[int, int]) -> None:
        """Poll pos pixel until it no longer matches tree_color (O(1), drift-free)."""
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

    def _nearest_living_tree(self) -> Optional[Tuple[int, int]]:
        if not self._cfg.tree_color.enabled:
            return None
        ox, oy = self._origin
        viewport = self._screen.grab((ox + 4, oy + 4, 512, 334))
        if self._cfg.color2.enabled:
            best = self._color.best_cluster(
                viewport, self._cfg.color2, region_offset=(ox + 4, oy + 4)
            )
            if best:
                return best
        clusters = self._color.find_clusters(
            viewport, self._cfg.tree_color, region_offset=(ox + 4, oy + 4)
        )
        if not clusters:
            return None
        center = (ox + 4 + 512 // 2, oy + 4 + 334 // 2)
        return min(clusters, key=lambda c: max(abs(c[0] - center[0]), abs(c[1] - center[1])))

    # ------------------------------------------------------------------
    # Animation detection (unchanged)
    # ------------------------------------------------------------------

    def _is_animating(self) -> bool:
        if not self._cfg.anim_color.enabled:
            return False
        ox, oy = self._origin
        orb_region = self._screen.grab((ox, oy, 200, 200))
        return self._color.best_cluster(orb_region, self._cfg.anim_color) is not None

    def _wait_for_idle(self) -> None:
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline and self._running.is_set():
            if not self._is_animating():
                return
            self.random_sleep(0.5, 1.0)
        self.log("Animation wait timed out")


WoodcutterBot.register()
