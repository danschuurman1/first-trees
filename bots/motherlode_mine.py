from __future__ import annotations
import math
import random
import subprocess
import time
from typing import Optional, Tuple, List

import cv2
import numpy as np

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
        self._window_region: tuple = (0, 0, 765, 503)

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

    def _count_inventory_ore(self) -> int:
        """
        Count inventory slots containing inv_ore_color.

        Grabs the 172×252 inventory panel, builds a colour-distance mask,
        then divides it into a 4-col × 7-row grid and checks each cell.
        Any matching pixel anywhere in the cell counts the slot as occupied.
        This avoids dependence on exact slot-centre offsets.
        Maximum return value is 28.
        """
        profile = getattr(self._cfg, "inv_ore_color", None)
        if not profile or not profile.enabled:
            return 0

        ox, oy = self._origin
        frame = self._screen.grab((ox + 548, oy + 205, 172, 252))
        if frame is None or frame.size == 0:
            self.log("inv panel grab failed")
            return 0

        arr = frame.astype(np.int32)
        dist = np.sqrt(
            (arr[:, :, 2] - profile.r) ** 2 +
            (arr[:, :, 1] - profile.g) ** 2 +
            (arr[:, :, 0] - profile.b) ** 2
        )
        mask = dist <= profile.tolerance
        total_px = int(np.sum(mask))
        self.log(f"inv panel matched pixels: {total_px}")

        h, w = mask.shape
        slot_w = w // 4   # 43
        slot_h = h // 7   # 36

        count = 0
        for row in range(7):
            for col in range(4):
                x0 = col * slot_w
                y0 = row * slot_h
                x1 = min(w, x0 + slot_w)
                y1 = min(h, y0 + slot_h)
                if np.any(mask[y0:y1, x0:x1]):
                    count += 1

        self.log(f"inv slot count: {count}")
        return count

    def _activate_runelite(self) -> None:
        """Bring RuneLite to the front so the capture sees the real client."""
        try:
            subprocess.run(
                ["osascript", "-e", 'tell application "RuneLite" to activate'],
                capture_output=True,
                timeout=2,
            )
            time.sleep(0.25)
        except Exception as exc:
            self.log(f"RuneLite activation failed: {exc}")

    def _resolve_window_region(self) -> tuple[int, int, int, int]:
        """Get the live RuneLite window rectangle once at startup."""
        script = (
            'tell application "System Events" to tell process "RuneLite" '
            'to get {position, size} of window 1'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                px, py, win_w, win_h = [int(v.strip()) for v in result.stdout.strip().split(",")]
                region = (px, py, win_w, win_h)
                self.log(f"RuneLite window region={region}")
                return region
        except Exception as exc:
            self.log(f"RuneLite window lookup failed: {exc}")

        fallback = (0, 0, 765, 503)
        self.log(f"Falling back to default window region={fallback}")
        return fallback

    def _refresh_window_region(self) -> tuple[int, int, int, int]:
        region = self._resolve_window_region()
        if region != self._window_region:
            self.log(f"RuneLite window region updated: {self._window_region} -> {region}")
            self._window_region = region
        return self._window_region

    def _grab_window(self) -> np.ndarray:
        """Focus RuneLite, refresh its geometry, then capture the live window."""
        self._activate_runelite()
        region = self._refresh_window_region()
        return self._screen.grab(region)

    def _inv_ore_mask(self, img: np.ndarray) -> np.ndarray:
        """Return a binary mask of pixels matching the configured inv_ore_color."""
        profile = getattr(self._cfg, "inv_ore_color", None)
        if not profile or not profile.enabled:
            return np.zeros(img.shape[:2], dtype=bool)
        arr = img.astype(np.int32)
        b = arr[:, :, 0]
        g = arr[:, :, 1]
        r = arr[:, :, 2]
        dist = np.sqrt(
            (r - profile.r) ** 2 +
            (g - profile.g) ** 2 +
            (b - profile.b) ** 2
        )
        return dist <= profile.tolerance

    def _merge_mask(self, mask: np.ndarray) -> np.ndarray:
        """
        Expand thin highlighted outlines into solid per-item bands without
        merging neighboring inventory rows/columns together.
        """
        h, w = mask.shape
        kx = self._odd(max(5, int(round(w / 160))))
        ky = self._odd(max(5, int(round(h / 140))))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, ky))
        merged = cv2.dilate(mask.astype(np.uint8), kernel, iterations=1)
        self.log(f"Mask merge kernel={(kx, ky)}")
        return merged > 0

    def _odd(self, value: int) -> int:
        return value if value % 2 == 1 else value + 1

    def _find_bands(self, counts: np.ndarray, gap: int, min_span: int, min_mass: int) -> list[tuple[int, int]]:
        """Find contiguous occupied bands along one axis."""
        idx = np.where(counts > 0)[0]
        if len(idx) == 0:
            return []

        bands: list[tuple[int, int]] = []
        start = end = int(idx[0])
        for value in idx[1:]:
            value = int(value)
            if value <= end + gap + 1:
                end = value
            else:
                span = end - start + 1
                mass = int(np.sum(counts[start:end + 1]))
                if span >= min_span and mass >= min_mass:
                    bands.append((start, end))
                start = end = value
        span = end - start + 1
        mass = int(np.sum(counts[start:end + 1]))
        if span >= min_span and mass >= min_mass:
            bands.append((start, end))
        return bands

    def _top_bands(
        self,
        bands: list[tuple[int, int]],
        counts: np.ndarray,
        limit: int,
    ) -> list[tuple[int, int]]:
        """Keep the heaviest bands when extra noise bands are present."""
        if len(bands) <= limit:
            return bands
        ranked = sorted(
            bands,
            key=lambda band: int(np.sum(counts[band[0]:band[1] + 1])),
            reverse=True,
        )
        trimmed = sorted(ranked[:limit])
        return trimmed

    def _count_ore_in_window(self, window: np.ndarray) -> int:
        """
        Detect ore from the full RuneLite window without relying on fixed
        inventory coordinates. The distinct ore highlight color defines the
        occupied inventory cells directly.
        """
        raw_mask = self._inv_ore_mask(window)
        total_px = int(np.sum(raw_mask))
        self.log(f"inv_ore raw pixels matched: {total_px}")
        if total_px == 0:
            return 0

        merged_mask = self._merge_mask(raw_mask)

        x_counts = merged_mask.sum(axis=0)
        y_counts = merged_mask.sum(axis=1)

        min_x_span = max(6, window.shape[1] // 80)
        min_y_span = max(6, window.shape[0] // 90)
        min_x_mass = max(10, window.shape[0] // 4)
        min_y_mass = max(10, window.shape[1] // 4)
        gap_x = max(3, window.shape[1] // 220)
        gap_y = max(3, window.shape[0] // 180)

        col_bands = self._find_bands(x_counts, gap_x, min_x_span, min_x_mass)
        row_bands = self._find_bands(y_counts, gap_y, min_y_span, min_y_mass)
        self.log(f"col_bands before trim: {len(col_bands)}, row_bands before trim: {len(row_bands)}")
        col_bands = self._top_bands(col_bands, x_counts, limit=4)
        row_bands = self._top_bands(row_bands, y_counts, limit=7)
        self.log(f"col_bands: {col_bands}")
        self.log(f"row_bands: {row_bands}")

        count = 0
        for row_idx, (y0, y1) in enumerate(row_bands, start=1):
            for col_idx, (x0, x1) in enumerate(col_bands, start=1):
                cell_mask = raw_mask[y0:y1 + 1, x0:x1 + 1]
                matching_pixels = int(np.sum(cell_mask))
                if matching_pixels > 0:
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
