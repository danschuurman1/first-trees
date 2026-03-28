# bots/woodcutter.py
from __future__ import annotations
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


def chebyshev(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class WoodcutterBot(Bot):
    """
    Woodcutting bot decision tree:
      1. Inventory full?  YES → open inventory tab, drop one log, repeat
      2. Animating?       YES (only when anim_color enabled) → wait for idle
      3. Tree visible?    YES → click it, wait for its cyan to disappear
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

        # 1. Inventory full → ensure tab open, drop one log, loop back
        if self._inventory_full():
            if self._inventory_has_logs():
                self.log("Inventory full — dropping one log")
                self._open_inventory_tab()
                self._drop_one_log()
                self.random_sleep(0.8, 1.2)  # wait for drop to register
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

        # 3. Find and click a living tree, then wait for it to be cut
        tree_pos = self._nearest_living_tree()
        if tree_pos is not None:
            self.log(f"Clicking tree at {tree_pos}")
            self._mouse.move_and_click(tree_pos)
            self.micro_pause()
            # Wait for this specific tree's cyan to vanish (chop complete)
            if not self._cfg.anim_color.enabled:
                self._wait_for_tree_gone(tree_pos)
        else:
            # No trees visible — wait quietly for respawn, no camera movement
            self.log("No living trees — waiting for respawn")
            self.random_sleep(3.0, 6.0)

        self.random_sleep(self._cfg.min_delay, self._cfg.max_delay)

    def _open_inventory_tab(self) -> None:
        """Click the inventory (backpack) tab to make sure it is open."""
        self._mouse.move_and_click(INVENTORY_TAB)
        self.random_sleep(0.2, 0.4)

    def _inventory_full(self) -> bool:
        if not self._cfg.log_color.enabled:
            return False
        inv_region = self._screen.grab((548, 205, 190, 260))
        clusters = self._color.find_clusters(inv_region, self._cfg.log_color)
        return len(clusters) >= 10

    def _inventory_has_logs(self) -> bool:
        if not self._cfg.log_color.enabled:
            return True
        inv_region = self._screen.grab((548, 205, 190, 260))
        return len(self._color.find_clusters(inv_region, self._cfg.log_color)) > 0

    def _drop_one_log(self) -> None:
        if not self._cfg.log_color.enabled:
            return
        inv_region = self._screen.grab((548, 205, 190, 260))
        cluster = self._color.best_cluster(
            inv_region, self._cfg.log_color, region_offset=(548, 205)
        )
        if cluster:
            self._mouse.move_and_click(cluster)
            self.micro_pause()
            self.random_sleep(0.3, 0.6)
            drop_pos = (cluster[0], cluster[1] + 40)
            self._mouse.move_and_click(drop_pos)
            self.micro_pause()

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

    def _wait_for_tree_gone(self, pos: Tuple[int, int]) -> None:
        """Poll until the tree color near pos disappears (chop complete) or timeout."""
        self.log("Waiting for tree to be cut...")
        deadline = time.monotonic() + 35.0
        while time.monotonic() < deadline and self._running.is_set():
            viewport = self._screen.grab((4, 4, 512, 334))
            clusters = self._color.find_clusters(
                viewport, self._cfg.tree_color, region_offset=(4, 4)
            )
            # Tree still present near original click position?
            still_there = any(
                max(abs(c[0] - pos[0]), abs(c[1] - pos[1])) < 25
                for c in clusters
            )
            if not still_there:
                self.log("Tree cut — looking for next")
                return
            self.random_sleep(0.5, 1.0)
        self.log("Tree chop wait timed out")

    def _nearest_living_tree(self) -> Optional[Tuple[int, int]]:
        if not self._cfg.tree_color.enabled:
            return None
        viewport = self._screen.grab((4, 4, 512, 334))
        # Check priority override (Color 2)
        if self._cfg.color2.enabled:
            best = self._color.best_cluster(viewport, self._cfg.color2, region_offset=(4, 4))
            if best:
                return best
        clusters = self._color.find_clusters(viewport, self._cfg.tree_color, region_offset=(4, 4))
        if not clusters:
            return None
        center = (4 + 512 // 2, 4 + 334 // 2)
        return min(clusters, key=lambda c: max(abs(c[0] - center[0]), abs(c[1] - center[1])))


# Auto-register on import
WoodcutterBot.register()
