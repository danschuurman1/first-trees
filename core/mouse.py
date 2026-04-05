# core/mouse.py
from __future__ import annotations
import math
import random
import time
from typing import List, Optional, Tuple

from pynput.mouse import Button, Controller as MouseCtrl

from core.screen import ScreenCapture
from core.calibrate import find_runelight_origin
from config import ColorProfile


class MouseController:
    """Bezier mouse movement with per-click jitter and client-area boundary enforcement."""

    def __init__(self) -> None:
        self._mouse = MouseCtrl()
        self._screen = ScreenCapture()
        self._last_click: Optional[Tuple[int, int]] = None
        # Client origin: (left, top)
        self._origin = find_runelight_origin()

    def move_and_click(self, target: Tuple[int, int], log_callback: Optional[callable] = None) -> Tuple[int, int]:
        """Move to a target (logical client coords), verify it is valid, and click."""
        if target is None or (target[0] == 0 and target[1] == 0):
            if log_callback: log_callback("[Warning] Attempted to click (0,0) or None target. Aborting.")
            return (0, 0)
        
        # OSRS Fixed Client boundaries
        if not (0 <= target[0] <= 765 and 0 <= target[1] <= 503):
            if log_callback: log_callback(f"[Warning] Click {target} is outside client bounds (765x503). Aborting.")
            return (0, 0)

        # Convert to screen logical coordinates
        ox, oy = self._origin
        screen_target = (ox + target[0], oy + target[1])
        
        dest = self._unique_jitter(screen_target)
        path = self._bezier_path(self._current_pos(), dest, steps=random.randint(28, 45))
        
        for pt in path:
            self._mouse.position = pt
            time.sleep(random.uniform(0.008, 0.018))
        
        time.sleep(random.uniform(0.04, 0.09))
        self._mouse.click(Button.left, 1)
        self._last_click = dest
        return dest

    def move_and_click_precise(self, target: Tuple[int, int], radius: int = 1, log_callback: Optional[callable] = None) -> Tuple[int, int]:
        """Move to a target with minimal jitter for small UI controls."""
        if target is None or (target[0] == 0 and target[1] == 0):
            if log_callback:
                log_callback("[Warning] Attempted to click (0,0) or None target. Aborting.")
            return (0, 0)

        if not (0 <= target[0] <= 765 and 0 <= target[1] <= 503):
            if log_callback:
                log_callback(f"[Warning] Click {target} is outside client bounds (765x503). Aborting.")
            return (0, 0)

        ox, oy = self._origin
        screen_target = (ox + target[0], oy + target[1])
        if radius > 0:
            dest = (
                screen_target[0] + random.randint(-radius, radius),
                screen_target[1] + random.randint(-radius, radius),
            )
            if dest == self._last_click:
                dest = (screen_target[0], screen_target[1])
        else:
            dest = screen_target

        path = self._bezier_path(self._current_pos(), dest, steps=random.randint(24, 36))
        for pt in path:
            self._mouse.position = pt
            time.sleep(random.uniform(0.006, 0.014))

        time.sleep(random.uniform(0.03, 0.06))
        self._mouse.click(Button.left, 1)
        self._last_click = dest
        return dest

    def right_click(self, target: Tuple[int, int]) -> Tuple[int, int]:
        """Move to a target (logical client coords) and right-click."""
        ox, oy = self._origin
        screen_target = (ox + target[0], oy + target[1])
        dest = self._unique_jitter(screen_target)
        path = self._bezier_path(self._current_pos(), dest, steps=random.randint(18, 30))
        for pt in path:
            self._mouse.position = pt
            time.sleep(random.uniform(0.003, 0.012))
        self._mouse.click(Button.right, 1)
        self._last_click = dest
        return dest

    def _jitter(self, target: Tuple[int, int]) -> Tuple[int, int]:
        offset_x = random.choice([-1, 1]) * random.randint(2, 5) # Smaller jitter to stay on target
        offset_y = random.choice([-1, 1]) * random.randint(2, 5)
        return target[0] + offset_x, target[1] + offset_y

    def _unique_jitter(self, target: Tuple[int, int]) -> Tuple[int, int]:
        for _ in range(20):
            pos = self._jitter(target)
            if pos != self._last_click:
                return pos
        return target

    def _bezier_path(self, start: Tuple[int, int], end: Tuple[int, int], steps: int = 25) -> List[Tuple[int, int]]:
        x0, y0 = start
        x3, y3 = end
        mid_x = (x0 + x3) / 2
        mid_y = (y0 + y3) / 2
        dx, dy = x3 - x0, y3 - y0
        length = math.hypot(dx, dy) or 1
        perp_x, perp_y = -dy / length, dx / length
        arc = random.uniform(0.1, 0.25) * length * random.choice([-1, 1])
        x1 = mid_x + perp_x * arc
        y1 = mid_y + perp_y * arc
        x2 = mid_x + perp_x * arc * 0.5
        y2 = mid_y + perp_y * arc * 0.5

        pts: List[Tuple[int, int]] = []
        for i in range(steps):
            t = i / (steps - 1)
            mt = 1 - t
            x = mt**3 * x0 + 3*mt**2*t * x1 + 3*mt*t**2 * x2 + t**3 * x3
            y = mt**3 * y0 + 3*mt**2*t * y1 + 3*mt*t**2 * y2 + t**3 * y3
            pts.append((int(x), int(y)))
        return pts

    def _current_pos(self) -> Tuple[int, int]:
        pos = self._mouse.position
        return int(pos[0]), int(pos[1])
