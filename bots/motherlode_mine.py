from __future__ import annotations
import math
import random
from typing import Optional, Tuple, List

from bots.base_bot import Bot
from config import BotConfig
from core.color import ColorDetector, ClusterRegion
from core.mouse import MouseController
from core.screen import ScreenCapture
from core.calibrate import find_runelight_origin

# OSRS fixed-mode game viewport (excludes minimap, chat, side panels).
# These are client-relative offsets from the content-area origin.
_VP_X, _VP_Y = 4, 4
_VP_W, _VP_H = 508, 326

# Ignore blobs smaller than this many pixels (noise filter).
_MIN_ORE_PIXELS = 60

# Padding (client px) around the click point for depletion monitoring.
_MONITOR_PAD = 20


class MotherlodeMineBot(Bot):
    """
    Motherlode Mine bot — runs in the shared first-try-trees GUI.

    State machine:
        FIND_ORE  →  click ore  →  MONITOR_DEPLETION  →  FIND_ORE  …

    All coordinates are **client-relative** (origin = top-left of the
    765×503 OSRS content area).  MouseController handles the screen
    offset internally; ScreenCapture.grab() needs absolute coords, so
    we add self._origin before every grab.
    """

    name = "Motherlode Mine"

    def __init__(self, config: Optional[BotConfig] = None) -> None:
        super().__init__()
        self._cfg = config
        self._screen = ScreenCapture()
        self._color = ColorDetector()
        self._mouse = MouseController()
        self._origin: Tuple[int, int] = (0, 0)

        self._state = "FIND_ORE"
        self._active_click: Optional[Tuple[int, int]] = None  # client-relative

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_loop(self) -> None:
        if self.stop_if_runtime_elapsed(self._cfg):
            return

        # Re-query every iteration so a moved/resized window is handled.
        self._origin = find_runelight_origin()
        if self._origin == (0, 0):
            self.log("RuneLite window not found — waiting...")
            self.random_sleep(2.0, 4.0)
            return

        if self._state == "FIND_ORE":
            self._do_find_ore()
        elif self._state == "MONITOR_DEPLETION":
            self._do_monitor_depletion()

    # ------------------------------------------------------------------
    # State: FIND_ORE
    # ------------------------------------------------------------------

    def _do_find_ore(self) -> None:
        if not self._upper_level_visible():
            self.log("Ladder not visible — not on upper level, waiting...")
            self.random_sleep(2.0, 4.0)
            return

        result = self._find_best_ore()
        if result is None:
            self.log("No active ore found, scanning...")
            self.random_sleep(1.0, 2.5)
            return

        click_pt, area = result
        self.log(f"Ore found at client {click_pt} (area={area}px) — clicking")
        self._mouse.move_and_click(click_pt, log_callback=self.log)
        self._active_click = click_pt
        self._state = "MONITOR_DEPLETION"
        self.micro_pause()

    def _upper_level_visible(self) -> bool:
        """True when the descend-ladder colour is present in the viewport."""
        profile = getattr(self._cfg, "ladder_descend_color", None)
        if not profile or not profile.enabled:
            return True  # not configured → assume we're on the right level

        frame = self._grab_viewport()
        return bool(self._color.find_clusters(frame, profile))

    def _find_best_ore(self) -> Optional[Tuple[Tuple[int, int], int]]:
        """
        Return (client_click_point, pixel_count) for the ore closest to the
        viewport centre, or None if no ore is visible.

        click_point is an interior pixel of the blob (not the raw centroid)
        to avoid edge-jitter when the contour clips a wall/shadow.
        """
        profile = getattr(self._cfg, "ore_active_color", None)
        if not profile or not profile.enabled:
            return None

        frame = self._grab_viewport()
        # region_offset converts frame-local coords → client-relative coords.
        regions: List[ClusterRegion] = self._color.find_cluster_regions(
            frame, profile, region_offset=(_VP_X, _VP_Y)
        )

        regions = [r for r in regions if len(r.pixels) >= _MIN_ORE_PIXELS]
        if not regions:
            return None

        # Pick closest to viewport centre with a little randomness.
        vp_cx = _VP_X + _VP_W // 2
        vp_cy = _VP_Y + _VP_H // 2

        def score(r: ClusterRegion) -> float:
            dx = r.centroid[0] - vp_cx
            dy = r.centroid[1] - vp_cy
            return math.hypot(dx, dy) + random.uniform(0, 15)

        best = min(regions, key=score)
        click_pt = self._interior_click(best)
        return click_pt, len(best.pixels)

    @staticmethod
    def _interior_click(region: ClusterRegion) -> Tuple[int, int]:
        """
        Return a random pixel from the inner ~40 % of the blob
        (sorted by distance to centroid) to stay well away from edges.
        """
        cx, cy = region.centroid
        pixels = region.pixels
        if not pixels:
            return cx, cy
        sorted_px = sorted(pixels, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
        pool = sorted_px[: max(1, len(sorted_px) * 2 // 5)]
        return random.choice(pool)

    # ------------------------------------------------------------------
    # State: MONITOR_DEPLETION
    # ------------------------------------------------------------------

    def _do_monitor_depletion(self) -> None:
        if self._active_click is None:
            self._state = "FIND_ORE"
            return

        if self._ore_depleted():
            self.log("Ore depleted — returning to scan")
            self.random_sleep(0.6, 1.8)
            self._active_click = None
            self._state = "FIND_ORE"
        else:
            self.random_sleep(0.4, 0.9)

    def _ore_depleted(self) -> bool:
        """
        Grab a small region centred on the last click point and test whether
        the active-ore colour has disappeared.
        """
        active_profile = getattr(self._cfg, "ore_active_color", None)
        if not active_profile or not active_profile.enabled:
            return True  # can't check → assume depleted

        cx, cy = self._active_click
        ox, oy = self._origin
        pad = _MONITOR_PAD

        # Grab uses absolute screen coords.
        frame = self._screen.grab((ox + cx - pad, oy + cy - pad, pad * 2, pad * 2))
        if frame is None or frame.size == 0:
            return True

        active_hits = self._color.find_clusters(frame, active_profile)
        if not active_hits:
            return True

        # Secondary check: depleted colour dominant?
        depleted_profile = getattr(self._cfg, "ore_depleted_color", None)
        if depleted_profile and depleted_profile.enabled:
            depleted_hits = self._color.find_clusters(frame, depleted_profile)
            if len(depleted_hits) > len(active_hits):
                return True

        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _grab_viewport(self):
        """Grab the game viewport frame in absolute screen coords."""
        ox, oy = self._origin
        return self._screen.grab((ox + _VP_X, oy + _VP_Y, _VP_W, _VP_H))


MotherlodeMineBot.register()
