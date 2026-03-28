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


HOME_TILE = (3105, 3231)
CLUSTER_CENTER = (3106, 3230)
TREE_TILES: List[Tuple[int, int]] = [
    (3105, 3232), (3107, 3231), (3106, 3228), (3108, 3229)
]
BOUNDARY = 10  # Chebyshev


def chebyshev(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class WoodcutterBot(Bot):
    """
    Woodcutting bot decision tree:
      1. In expected location?   NO  → walk home, or halt
      2. Inventory full?         YES → drop log (or halt if no logs)
      3. Currently chopping?     YES (anim_color enabled) → wait for idle
      4. Tree available?         YES → click nearest tree, then wait for
                                       that tree's color to disappear
                                 NO  → wait 2-4s
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
        self._no_anim_since: Optional[float] = None

    def run_loop(self) -> None:
        # Scheduled break check
        if self._scheduler.is_break_time():
            end = self._scheduler.next_break_end()
            self.log(f"Scheduled break until {end}")
            self.random_sleep(30, 60)
            return

        # 1. Location check
        if not self._player_in_bounds():
            self.log("Out of bounds — walking to home tile")
            if not self._walk_home():
                self.log("HALT: walk home failed")
                self.stop()
                return
            self.micro_pause()
            return

        # 2. Inventory full?
        if self._inventory_full():
            if self._inventory_has_logs():
                self.log("Inventory full — dropping one log")
                self._drop_one_log()
                self.micro_pause()
                return
            else:
                self.log("HALT: inventory full but no logs found")
                self.stop()
                return

        # 3. Currently animating (chopping)?
        if self._is_animating():
            self.log("Chopping — waiting for idle")
            self._wait_for_idle()
            self.micro_pause()
            return

        # 4. Find and click a living tree
        tree_pos = self._nearest_living_tree()
        if tree_pos is not None:
            self.log(f"Clicking tree at {tree_pos}")
            clicked = self._mouse.move_and_click(tree_pos)
            self.micro_pause()
            if not self._mouse.post_click_verify(clicked, self._cfg.tree_color):
                self.log("Post-click mismatch — rotating camera and re-scanning")
                for _ in range(3):
                    self._keyboard.rotate_camera()
                    self.random_sleep(self._cfg.min_delay, self._cfg.max_delay)
                    tree_pos = self._nearest_living_tree()
                    if tree_pos:
                        self._mouse.move_and_click(tree_pos)
                        break
                else:
                    self.log("Target lost after 3 rotation attempts")
            else:
                # anim_color not configured: watch for THIS tree's cyan to disappear
                if not self._cfg.anim_color.enabled:
                    self._wait_for_tree_gone(tree_pos)
        else:
            self.log("No living trees — waiting 2-4s")
            self.random_sleep(2.0, 4.0)

        self.random_sleep(self._cfg.min_delay, self._cfg.max_delay)

    def _player_in_bounds(self) -> bool:
        if not self._cfg.player_color.enabled:
            return True
        region = self._screen.grab((0, 0, 800, 600))
        cluster = self._color.best_cluster(region, self._cfg.player_color)
        return cluster is not None

    def _walk_home(self) -> bool:
        minimap_center = (732, 108)
        self._mouse.move_and_click(minimap_center)
        self.random_sleep(2.0, 4.0)
        return True

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
