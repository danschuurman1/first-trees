from __future__ import annotations
import math
import random
import subprocess
import time
from typing import Optional, Tuple, List

from bots.base_bot import Bot
from config import BotConfig
from core.color import ColorDetector, ClusterRegion
from core.mouse import MouseController
from core.screen import ScreenCapture
from core.calibrate import find_runelight_origin

# OSRS fixed-mode game viewport (excludes minimap, chat, side panels).
# Client-relative offsets from the content-area origin.
_VP_X, _VP_Y = 4, 4
_VP_W, _VP_H = 508, 326

# Ignore ore blobs smaller than this many pixels (noise filter).
_MIN_ORE_PIXELS = 60

# Padding (client px) around the click point for depletion monitoring.
_MONITOR_PAD = 20

# Deposit triggers
_INV_DEPOSIT_AT = 26        # deposit when inventory ore count reaches this
_ORE_TIMEOUT_S  = 60.0      # deposit if no new ore clicked for this many seconds

# Hopper interaction timing
_DEPOSIT_WAIT_MIN = 2.0
_DEPOSIT_WAIT_MAX = 4.0
_DEPOSIT_MAX_RETRIES = 3


class MotherlodeMineBot(Bot):
    """
    Motherlode Mine bot — runs inside the shared first-try-trees GUI.

    State machine:
        FIND_ORE ──► MONITOR_DEPLETION ──► FIND_ORE …
                │                               ▲
                └──► DEPOSIT_HOPPER ────────────┘
                     (triggered by full inv or idle timeout)

    Coordinate rules:
      - All client coords (passed to MouseController) are relative to the
        765×503 OSRS content area.  MouseController adds the screen origin.
      - All ScreenCapture.grab() calls need absolute coords: (ox + cx, oy + cy).
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
        self._active_click: Optional[Tuple[int, int]] = None
        self._last_ore_time: float = 0.0

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_loop(self) -> None:
        if self.stop_if_runtime_elapsed(self._cfg):
            return

        self._origin = find_runelight_origin()
        if self._origin == (0, 0):
            self.log("RuneLite window not found — waiting...")
            self.random_sleep(2.0, 4.0)
            return

        if self._state == "FIND_ORE":
            self._do_find_ore()
        elif self._state == "MONITOR_DEPLETION":
            self._do_monitor_depletion()
        elif self._state == "DEPOSIT_HOPPER":
            self._do_deposit_hopper()

    # ------------------------------------------------------------------
    # State: FIND_ORE
    # ------------------------------------------------------------------

    def _do_find_ore(self) -> None:
        # Trigger A: inventory at or above threshold.
        if self._should_deposit_by_count():
            self.log(f"Inventory at {_INV_DEPOSIT_AT}+ ores — heading to hopper")
            self._state = "DEPOSIT_HOPPER"
            return

        # Trigger B: idle too long since last ore.
        if self._last_ore_time > 0 and (time.time() - self._last_ore_time) > _ORE_TIMEOUT_S:
            self.log("No new ore for 60 s — heading to hopper")
            self._state = "DEPOSIT_HOPPER"
            return

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
        self._last_ore_time = time.time()
        self._state = "MONITOR_DEPLETION"
        self.micro_pause()

    def _should_deposit_by_count(self) -> bool:
        count = self._count_inventory_ore()
        if count > 0:
            self.log(f"Inventory ore count: {count}")
        return count >= _INV_DEPOSIT_AT

    def _upper_level_visible(self) -> bool:
        profile = getattr(self._cfg, "ladder_descend_color", None)
        if not profile or not profile.enabled:
            return True
        return bool(self._color.find_clusters(self._grab_viewport(), profile))

    def _find_best_ore(self) -> Optional[Tuple[Tuple[int, int], int]]:
        profile = getattr(self._cfg, "ore_active_color", None)
        if not profile or not profile.enabled:
            return None

        frame = self._grab_viewport()
        regions: List[ClusterRegion] = self._color.find_cluster_regions(
            frame, profile, region_offset=(_VP_X, _VP_Y)
        )
        regions = [r for r in regions if len(r.pixels) >= _MIN_ORE_PIXELS]
        if not regions:
            return None

        vp_cx = _VP_X + _VP_W // 2
        vp_cy = _VP_Y + _VP_H // 2

        def score(r: ClusterRegion) -> float:
            dx = r.centroid[0] - vp_cx
            dy = r.centroid[1] - vp_cy
            return math.hypot(dx, dy) + random.uniform(0, 15)

        best = min(regions, key=score)
        return self._interior_click(best), len(best.pixels)

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
        active_profile = getattr(self._cfg, "ore_active_color", None)
        if not active_profile or not active_profile.enabled:
            return True

        cx, cy = self._active_click
        ox, oy = self._origin
        pad = _MONITOR_PAD
        frame = self._screen.grab((ox + cx - pad, oy + cy - pad, pad * 2, pad * 2))
        if frame is None or frame.size == 0:
            return True

        active_hits = self._color.find_clusters(frame, active_profile)
        if not active_hits:
            return True

        depleted_profile = getattr(self._cfg, "ore_depleted_color", None)
        if depleted_profile and depleted_profile.enabled:
            depleted_hits = self._color.find_clusters(frame, depleted_profile)
            if len(depleted_hits) > len(active_hits):
                return True

        return False

    # ------------------------------------------------------------------
    # State: DEPOSIT_HOPPER
    # ------------------------------------------------------------------

    def _do_deposit_hopper(self) -> None:
        """
        Find the hopper, click it, verify inventory is empty.
        Re-clicks up to _DEPOSIT_MAX_RETRIES times if ore remains.
        """
        hopper_profile = getattr(self._cfg, "hopper_color", None)
        if not hopper_profile or not hopper_profile.enabled:
            self.log("Hopper colour not configured — skipping deposit")
            self._last_ore_time = time.time()
            self._state = "FIND_ORE"
            return

        for attempt in range(1, _DEPOSIT_MAX_RETRIES + 1):
            frame = self._grab_viewport()
            regions = self._color.find_cluster_regions(
                frame, hopper_profile, region_offset=(_VP_X, _VP_Y)
            )
            if not regions:
                self.log(f"Hopper not visible (attempt {attempt}) — waiting to retry")
                self.random_sleep(1.5, 3.0)
                return  # stay in DEPOSIT_HOPPER; retry next run_loop call

            target = max(regions, key=lambda r: len(r.pixels))
            click_pt = self._interior_click(target)
            self.log(f"Clicking hopper at client {click_pt} (attempt {attempt})")
            self._mouse.move_and_click(click_pt, log_callback=self.log)

            self.random_sleep(_DEPOSIT_WAIT_MIN, _DEPOSIT_WAIT_MAX)

            # Verify inventory via full-window scan.
            inv_profile = getattr(self._cfg, "inv_ore_color", None)
            if not inv_profile or not inv_profile.enabled:
                self.log("Inventory colour not configured — assuming deposit succeeded")
                break

            remaining = self._count_inventory_ore()
            self.log(f"Post-deposit inventory count: {remaining}")
            if remaining == 0:
                self.log("Deposit confirmed — inventory empty")
                break

            if attempt < _DEPOSIT_MAX_RETRIES:
                self.log(f"{remaining} ore still in inventory — re-clicking hopper")
            else:
                self.log(f"Still {remaining} ore after {_DEPOSIT_MAX_RETRIES} attempts — resuming anyway")

        self._last_ore_time = time.time()
        self._active_click = None
        self._state = "FIND_ORE"
        self.log("Deposit complete — resuming mining")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_window_rect(self) -> Tuple[int, int, int, int]:
        """
        Return (left, top, width, height) of the OSRS content area in
        absolute screen coordinates at the window's current position/size.
        Falls back to (0, 0, 765, 503) if RuneLite is not found.
        """
        try:
            r = subprocess.run(
                ['osascript', '-e',
                 'tell application "System Events" to tell process "RuneLite" '
                 'to get {position, size} of window 1'],
                capture_output=True, text=True, timeout=3,
            )
            if r.returncode == 0:
                px, py, sw, sh = [int(v.strip()) for v in r.stdout.strip().split(',')]
                title_bar = max(sh - 503, 0)
                return (px, py + title_bar, sw, 503)
        except Exception:
            pass
        return (0, 0, 765, 503)

    def _count_inventory_ore(self) -> int:
        """
        Count inventory slots containing inv_ore_color by sampling the centre
        pixel of each of the 28 slots.

        Slot positions are derived proportionally from the current window size
        so the grid stays accurate at any RuneLite resolution or stretch factor.
        The reference layout is the OSRS fixed-mode 765×503 client:
            slot-1 centre: (563, 213), step: (42, 36), grid: 4 cols × 7 rows.

        Returns 0 if the profile is disabled. Maximum return value is 28.
        """
        profile = getattr(self._cfg, "inv_ore_color", None)
        if not profile or not profile.enabled:
            return 0

        left, top, width, height = self._get_window_rect()

        # Scale reference slot geometry to actual window dimensions.
        sx = width  / 765
        sy = height / 503
        origin_x = round(563 * sx)
        origin_y = round(213 * sy)
        step_x   = round(42  * sx)
        step_y   = round(36  * sy)

        count = 0
        for slot in range(4 * 7):
            col = slot % 4
            row = slot // 4
            abs_x = left + origin_x + col * step_x
            abs_y = top  + origin_y + row * step_y
            r, g, b = self._screen.pixel_color(abs_x, abs_y)
            dist = ((r - profile.r) ** 2 +
                    (g - profile.g) ** 2 +
                    (b - profile.b) ** 2) ** 0.5
            if dist <= profile.tolerance:
                count += 1
        return count

    def _grab_viewport(self):
        ox, oy = self._origin
        return self._screen.grab((ox + _VP_X, oy + _VP_Y, _VP_W, _VP_H))

    @staticmethod
    def _interior_click(region: ClusterRegion) -> Tuple[int, int]:
        cx, cy = region.centroid
        pixels = region.pixels
        if not pixels:
            return cx, cy
        sorted_px = sorted(pixels, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
        pool = sorted_px[: max(1, len(sorted_px) * 2 // 5)]
        return random.choice(pool)


MotherlodeMineBot.register()
