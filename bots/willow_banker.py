from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from bots.base_bot import Bot
from bots.helpers.banker import BankerHelper
from config import BotConfig, ColorProfile, ConfigManager
from core.color import ColorDetector
from core.mouse import MouseController
from core.screen import ScreenCapture


class WillowBankerBot(Bot):
    """
    Inventory counter based on a full RuneLite window screenshot.

    The bot captures the current RuneLite window, isolates the configured log
    color across the whole window, groups the resulting colored shapes into a
    4x7-style inventory grid dynamically, and counts occupied cells.
    """

    name = "Willow Banker"

    def __init__(self, config: Optional[BotConfig] = None) -> None:
        super().__init__()
        cfg_mgr = ConfigManager()
        self._cfg = config or cfg_mgr.get_current_preset()
        self._screen = ScreenCapture()
        self._mouse = MouseController()
        self._color = ColorDetector()
        self._banker = BankerHelper(self._cfg, self._screen, self._mouse, self._color)
        self._log_color: ColorProfile = self._cfg.log_color
        self._debug_dir = Path("tmp/willow_banker_debug")
        self._window_region = self._resolve_window_region()

    def run_loop(self) -> None:
        if not self._log_color.enabled:
            self.log("Willow log color is disabled in the Colors tab.")
            self.random_sleep(2.0, 4.0)
            return

        window = self._grab_window()
        log_count = self._count_logs_in_window(window)
        self.log(f"Willow logs in inventory: {log_count}")
        if log_count >= 27:
            self._run_banking_if_ready()
        self.random_sleep(2.0, 4.0)

    def _run_banking_if_ready(self) -> None:
        """
        Trigger the teller interaction only when inventory is effectively full.
        This leaves the existing log counting flow unchanged.
        """
        if not self._cfg.bank_booth_color.enabled:
            self.log("Inventory threshold reached, but bank booth color is disabled.")
            return

        self.log("Inventory threshold reached (>=27). Searching for bank teller color...")

        def count_inventory() -> int:
            window = self._grab_window()
            return self._count_logs_in_window(window)

        def get_log_click():
            window = self._grab_window()
            return self._find_log_click_in_window(window)

        if self._banker.run(self.log, count_inventory=count_inventory, get_log_click=get_log_click):
            self.log("Banking sequence completed.")
            return

        self.log("Banking sequence did not complete.")

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

    def _find_log_click_in_window(self, window: np.ndarray) -> Optional[tuple[int, int]]:
        """
        Return a random client-coord pixel that matches the log color,
        restricted to the right side of the window where the inventory lives.
        Reuses _log_mask so it uses the exact same logic that _count_logs_in_window does.
        """
        wx, wy, ww, wh = self._window_region
        # Title bar height = window height minus fixed OSRS client content height (503)
        title_bar = wh - 503

        raw_mask = self._log_mask(window)

        # Zero out columns outside the inventory panel and outside move_and_click's
        # accepted client range (0–765). In resizable mode the window can be wider
        # than 765px, so pixels at fx >= 765 would be rejected downstream.
        inv_x_start = max(0, ww - 235)
        raw_mask[:, :inv_x_start] = False
        raw_mask[:, 765:] = False

        ys, xs = np.where(raw_mask)
        if len(xs) == 0:
            self.log("_find_log_click_in_window: no log pixels in inventory region")
            return None

        idx = np.random.randint(len(xs))
        fx, fy = int(xs[idx]), int(ys[idx])
        client_x = fx
        client_y = fy - title_bar
        self.log(f"_find_log_click_in_window: frame=({fx},{fy}) title_bar={title_bar} client=({client_x},{client_y})")
        return (client_x, client_y)

    def _log_mask(self, img: np.ndarray) -> np.ndarray:
        """Return a binary mask of pixels matching the configured log color."""
        profile = self._log_color
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

    def _count_logs_in_window(self, window: np.ndarray) -> int:
        """
        Detect logs from the full RuneLite window without relying on fixed
        inventory coordinates. The distinct log highlight color defines the
        occupied inventory cells directly.
        """
        raw_mask = self._log_mask(window)
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
        col_bands = self._top_bands(col_bands, x_counts, limit=4)
        row_bands = self._top_bands(row_bands, y_counts, limit=7)

        count = 0
        for row_idx, (y0, y1) in enumerate(row_bands, start=1):
            for col_idx, (x0, x1) in enumerate(col_bands, start=1):
                cell_mask = raw_mask[y0:y1 + 1, x0:x1 + 1]
                matching_pixels = int(np.sum(cell_mask))
                if matching_pixels > 0:
                    count += 1

        self._save_debug_artifacts(window, raw_mask, merged_mask, col_bands, row_bands)
        return count

    def _save_debug_artifacts(
        self,
        window: np.ndarray,
        raw_mask: np.ndarray,
        merged_mask: np.ndarray,
        col_bands: list[tuple[int, int]],
        row_bands: list[tuple[int, int]],
    ) -> None:
        """Persist full-window debug overlays for geometry inspection."""
        self._debug_dir.mkdir(parents=True, exist_ok=True)

        window_path = self._debug_dir / "window.png"
        raw_mask_path = self._debug_dir / "window_mask.png"
        merged_mask_path = self._debug_dir / "window_mask_merged.png"
        overlay_path = self._debug_dir / "window_overlay.png"

        cv2.imwrite(str(window_path), window)
        cv2.imwrite(str(raw_mask_path), (raw_mask.astype(np.uint8) * 255))
        cv2.imwrite(str(merged_mask_path), (merged_mask.astype(np.uint8) * 255))

        overlay = window.copy()
        overlay[raw_mask] = (0, 0, 255)
        for x0, x1 in col_bands:
            cv2.rectangle(overlay, (x0, 0), (x1, overlay.shape[0] - 1), (255, 0, 0), 1)
        for y0, y1 in row_bands:
            cv2.rectangle(overlay, (0, y0), (overlay.shape[1] - 1, y1), (0, 255, 0), 1)
        for row_idx, (y0, y1) in enumerate(row_bands, start=1):
            for col_idx, (x0, x1) in enumerate(col_bands, start=1):
                cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 255, 255), 1)
                cv2.putText(
                    overlay,
                    f"{row_idx},{col_idx}",
                    (x0 + 2, min(y0 + 14, overlay.shape[0] - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    (0, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

        cv2.imwrite(str(overlay_path), overlay)


WillowBankerBot.register()
