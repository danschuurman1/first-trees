# core/mouse.py
from __future__ import annotations
import math
import random
import time
from typing import List, Optional, Tuple

from pynput.mouse import Button, Controller as MouseCtrl

from core.screen import ScreenCapture
from config import ColorProfile


class MouseController:
    """Bezier mouse movement with per-click jitter. Never clicks the same pixel twice consecutively."""

    def __init__(self) -> None:
        self._mouse = MouseCtrl()
        self._screen = ScreenCapture()
        self._last_click: Optional[Tuple[int, int]] = None

    def move_and_click(self, target: Tuple[int, int]) -> Tuple[int, int]:
        """Move along a Bezier curve to a jittered target, click, return actual pixel clicked."""
        dest = self._unique_jitter(target)
        path = self._bezier_path(self._current_pos(), dest, steps=random.randint(18, 30))
        for pt in path:
            self._mouse.position = pt
            time.sleep(random.uniform(0.003, 0.012))
        self._mouse.click(Button.left, 1)
        self._last_click = dest
        return dest

    def right_click(self, target: Tuple[int, int]) -> Tuple[int, int]:
        """Move along a Bezier curve to a jittered target, right-click, return actual pixel clicked."""
        dest = self._unique_jitter(target)
        path = self._bezier_path(self._current_pos(), dest, steps=random.randint(18, 30))
        for pt in path:
            self._mouse.position = pt
            time.sleep(random.uniform(0.003, 0.012))
        self._mouse.click(Button.right, 1)
        self._last_click = dest
        return dest

    def post_click_verify(
        self,
        pos: Tuple[int, int],
        profile: ColorProfile,
        delay: float = 0.3,
    ) -> bool:
        """Return True if the clicked pixel still matches the color profile after `delay` seconds."""
        time.sleep(delay)
        r, g, b = self._screen.pixel_color(pos[0], pos[1])
        dist = math.sqrt((r - profile.r) ** 2 + (g - profile.g) ** 2 + (b - profile.b) ** 2)
        return dist <= profile.tolerance

    def _jitter(self, target: Tuple[int, int]) -> Tuple[int, int]:
        """Apply random ±8–15 px offset to a target."""
        offset_x = random.choice([-1, 1]) * random.randint(8, 15)
        offset_y = random.choice([-1, 1]) * random.randint(8, 15)
        return target[0] + offset_x, target[1] + offset_y

    def _unique_jitter(self, target: Tuple[int, int]) -> Tuple[int, int]:
        """Jitter guaranteed to differ from the last click position."""
        for _ in range(20):
            pos = self._jitter(target)
            if pos != self._last_click:
                return pos
        # Fallback: force a different offset
        dx = random.randint(1, 5) if self._last_click and pos[0] == self._last_click[0] else 0
        return pos[0] + dx, pos[1] + (1 if not dx else 0)

    def _bezier_path(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        steps: int = 25,
    ) -> List[Tuple[int, int]]:
        """Cubic Bezier curve from start to end with a random arc control point."""
        x0, y0 = start
        x3, y3 = end
        mid_x = (x0 + x3) / 2
        mid_y = (y0 + y3) / 2
        dx, dy = x3 - x0, y3 - y0
        length = math.hypot(dx, dy) or 1
        perp_x, perp_y = -dy / length, dx / length
        arc = random.uniform(0.1, 0.35) * length * random.choice([-1, 1])
        x1 = mid_x + perp_x * arc + random.uniform(-10, 10)
        y1 = mid_y + perp_y * arc + random.uniform(-10, 10)
        x2 = mid_x + perp_x * arc * 0.5 + random.uniform(-10, 10)
        y2 = mid_y + perp_y * arc * 0.5 + random.uniform(-10, 10)

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
