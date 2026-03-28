# bots/woodcutter.py
from __future__ import annotations
import math
import random
import time
from typing import List, Optional, Tuple

from bots.base_bot import Bot
from config import BotConfig, ConfigManager
from core.color import ColorDetector
from core.keyboard import KeyboardController
from core.mouse import MouseController
from core.screen import ScreenCapture
from core.scheduler import DowntimeScheduler


# OSRS right-panel inventory tab icon (backpack) — fixed client layout
INVENTORY_TAB = (644, 169)

# The inventory tab has a red background when open, grey when closed.
# R must be above this floor AND dominate G and B by at least this margin.
_INV_OPEN_R_MIN = 100
_INV_OPEN_BIAS = 50


def chebyshev(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class WoodcutterBot(Bot):
    """
    Woodcutting bot decision tree:
      1. Inventory full?  YES → open inventory tab, shift-drop all logs, repeat
      2. Animating?       YES (only when anim_color enabled) → wait for idle
      3. Tree visible?    YES → click it, wait for its pixel colour to disappear
                          NO  → wait for respawn (no camera movement)
    Camera is never rotated — bot operates from a fixed position.
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

    def run_loop(self) -> None:
        # Scheduled break check
        if self._scheduler.is_break_time():
            end = self._scheduler.next_break_end()
            self.log(f"Scheduled break until {end}")
            self.random_sleep(30, 60)
            return

        # 1. Inventory full → ensure tab open, shift-drop all logs, loop back
        if self._inventory_full():
            if self._inventory_has_logs():
                self.log("Inventory full — dropping all logs")
                self._drop_all_logs()
                self.random_sleep(0.8, 1.2)
                return
            else:
                self.log("HALT: inventory full but no logs found")
                self.stop()
                return

        # 2. Currently animating? (only fires if anim_color is explicitly enabled)
        if self._is_animating():
            self.log("Chopping — waiting for idle")
            self._wait_for_idle()
            self.micro_pause()
            return

        # 3. Find and click a living tree, then wait for its pixel colour to vanish
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
    # Inventory helpers
    # ------------------------------------------------------------------

    def _is_inventory_open(self) -> bool:
        """Return True when the inventory tab has a red (selected) background."""
        r, g, b = self._screen.pixel_color(INVENTORY_TAB[0], INVENTORY_TAB[1])
        return r > _INV_OPEN_R_MIN and r > g + _INV_OPEN_BIAS and r > b + _INV_OPEN_BIAS

    def _ensure_inventory_open(self) -> None:
        """Click the backpack tab only if it is currently closed."""
        if not self._is_inventory_open():
            self._mouse.move_and_click(INVENTORY_TAB)
            self.random_sleep(0.2, 0.4)

    def _inventory_full(self) -> bool:
        if not self._cfg.log_color.enabled:
            return False
        self._ensure_inventory_open()
        inv_region = self._screen.grab((548, 205, 190, 260))
        clusters = self._color.find_clusters(inv_region, self._cfg.log_color)
        return len(clusters) >= 10

    def _inventory_has_logs(self) -> bool:
        if not self._cfg.log_color.enabled:
            return True
        self._ensure_inventory_open()
        inv_region = self._screen.grab((548, 205, 190, 260))
        return len(self._color.find_clusters(inv_region, self._cfg.log_color)) > 0

    def _drop_one_log(self) -> None:
        """Right-click a log in the inventory, then left-click the Drop option."""
        if not self._cfg.log_color.enabled:
            return
        self._ensure_inventory_open()
        inv_region = self._screen.grab((548, 205, 190, 260))
        cluster = self._color.best_cluster(
            inv_region, self._cfg.log_color, region_offset=(548, 205)
        )
        if cluster:
            self._mouse.right_click(cluster)
            self.micro_pause()
            self.random_sleep(0.3, 0.5)
            drop_pos = (cluster[0], cluster[1] + 40)
            self._mouse.move_and_click(drop_pos)
            self.micro_pause()

    def _drop_all_logs(self) -> None:
        """Hold Shift and left-click every log cluster to drop the whole inventory."""
        if not self._cfg.log_color.enabled:
            return
        self._ensure_inventory_open()
        inv_region = self._screen.grab((548, 205, 190, 260))
        clusters = self._color.find_clusters(
            inv_region, self._cfg.log_color, region_offset=(548, 205)
        )
        if not clusters:
            return
        self._keyboard.press_shift()
        try:
            for pos in clusters:
                self._mouse.move_and_click(pos)
                self.micro_pause()
        finally:
            self._keyboard.release_shift()

    # ------------------------------------------------------------------
    # Tree detection
    # ------------------------------------------------------------------

    def _wait_for_tree_gone(self, pos: Tuple[int, int]) -> None:
        """Poll pos pixel until it no longer matches tree_color (chop complete) or timeout.

        Samples a single pixel at the exact clicked coordinate — O(1) and drift-free.
        """
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
        viewport = self._screen.grab((4, 4, 512, 334))
        if self._cfg.color2.enabled:
            best = self._color.best_cluster(viewport, self._cfg.color2, region_offset=(4, 4))
            if best:
                return best
        clusters = self._color.find_clusters(viewport, self._cfg.tree_color, region_offset=(4, 4))
        if not clusters:
            return None
        center = (4 + 512 // 2, 4 + 334 // 2)
        return min(clusters, key=lambda c: max(abs(c[0] - center[0]), abs(c[1] - center[1])))

    # ------------------------------------------------------------------
    # Animation detection (unchanged)
    # ------------------------------------------------------------------

    def _is_animating(self) -> bool:
        if not self._cfg.anim_color.enabled:
            return False
        orb_region = self._screen.grab((0, 0, 200, 200))
        return self._color.best_cluster(orb_region, self._cfg.anim_color) is not None

    def _wait_for_idle(self) -> None:
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline and self._running.is_set():
            if not self._is_animating():
                return
            self.random_sleep(0.5, 1.0)
        self.log("Animation wait timed out")


# Auto-register on import
WoodcutterBot.register()
