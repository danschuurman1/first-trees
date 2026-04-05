# bots/helpers/banker.py
from __future__ import annotations
import time
import random
import numpy as np
from typing import Callable, Tuple, Optional
import cv2
from core.calibrate import find_runelight_origin
from core.screen import ScreenCapture
from core.mouse import MouseController
from core.color import ClusterRegion, ColorDetector
from config import BotConfig

# Viewport used for booth detection (Standard Fixed mode)
VIEWPORT_REGION_CLIENT = (4, 4, 512, 334)
# Inventory panel offset from the RuneLite client origin — matches willow_chopper
INVENTORY_REGION_CLIENT = (548, 205, 186, 253)  # x, y, w, h


class BankerHelper:
    def __init__(self, config: BotConfig, screen: ScreenCapture, mouse: MouseController, detector: ColorDetector) -> None:
        self._cfg = config
        self._screen = screen
        self._mouse = mouse
        self._detector = detector
        self._last_booth_click: Optional[Tuple[int, int]] = None

    def run(
        self,
        log_callback: Optional[callable] = None,
        count_inventory: Optional[Callable[[], int]] = None,
        get_log_click: Optional[Callable[[], Optional[Tuple[int, int]]]] = None,
    ) -> bool:
        """Run the full banking sequence. Returns True on success."""
        def log(msg):
            if log_callback: log_callback(msg)

        log("Starting banking sequence...")

        # 1. Find and click bank booth.
        booth_pos = self._acquire_booth_target(log)
        if not booth_pos:
            log("Bank booth color could not be confirmed. Stopping banking sequence.")
            return False

        log(f"Clicking bank booth at {booth_pos}")
        self._mouse.move_and_click(booth_pos)

        # 2. Wait 10 seconds for the character to travel to the bank.
        log("Waiting 10 seconds for character to arrive at bank...")
        time.sleep(10.0)

        # 3. Deposit & verification loop.
        while True:
            log("Depositing inventory — clicking a log in inventory...")
            time.sleep(random.uniform(0.5, 0.9))
            log_target = get_log_click() if get_log_click is not None else None
            if log_target:
                self._mouse.move_and_click(log_target)
                time.sleep(random.uniform(0.08, 0.15))
                self._mouse.move_and_click(log_target)
            else:
                log("No log click target returned.")
            time.sleep(random.uniform(1.0, 1.4))

            # Verify inventory using the caller-supplied counter.
            log_count = count_inventory() if count_inventory is not None else 0
            log(f"Inventory check after deposit: {log_count} logs remaining.")

            if log_count == 0:
                log("Banking complete.")
                return True

            # Logs still present — attempt recovery.
            log(f"{log_count} logs still detected. Searching for bank booth...")
            booth_pos = self._acquire_booth_target(log)
            if booth_pos:
                log(f"Booth found at {booth_pos}. Clicking and retrying deposit.")
                self._mouse.move_and_click(booth_pos)
                time.sleep(random.uniform(1.5, 2.5))
            else:
                log("Booth not visible; retrying deposit immediately (UI may still be open).")

    # ------------------------------------------------------------------
    # Booth detection
    # ------------------------------------------------------------------

    def _client_origin(self) -> Tuple[int, int]:
        return find_runelight_origin()

    def _viewport_screen_region(self) -> Tuple[int, int, int, int]:
        ox, oy = self._client_origin()
        vx, vy, vw, vh = VIEWPORT_REGION_CLIENT
        return (ox + vx, oy + vy, vw, vh)

    def _matches_profile(self, rgb: Tuple[int, int, int]) -> bool:
        profile = self._cfg.bank_booth_color
        r, g, b = rgb
        dist = float(np.sqrt(
            (r - profile.r) ** 2 +
            (g - profile.g) ** 2 +
            (b - profile.b) ** 2
        ))
        return dist <= profile.tolerance

    def _pick_cluster_click(self, cluster: ClusterRegion) -> Optional[Tuple[int, int]]:
        return self._pick_point_from_pixels(cluster.centroid, cluster.bounds, cluster.pixels, self._last_booth_click)

    def _pick_point_from_pixels(
        self,
        centroid: Tuple[int, int],
        bounds: Tuple[int, int, int, int],
        pixels: list[Tuple[int, int]],
        last_click: Optional[Tuple[int, int]],
    ) -> Optional[Tuple[int, int]]:
        if not pixels:
            return None

        centroid_x, centroid_y = centroid
        left, top, width, height = bounds
        right = left + width - 1
        bottom = top + height - 1

        def score(point: Tuple[int, int]) -> tuple[int, int, int]:
            px, py = point
            edge_margin = min(px - left, right - px, py - top, bottom - py)
            center_distance = abs(px - centroid_x) + abs(py - centroid_y)
            repeat_penalty = 1 if point == last_click else 0
            return (repeat_penalty, -edge_margin, center_distance)

        ordered = sorted(pixels, key=score)
        if len(ordered) == 1:
            return ordered[0]

        best_margin = min(
            ordered[0][0] - left,
            right - ordered[0][0],
            ordered[0][1] - top,
            bottom - ordered[0][1],
        )
        safe_pool = [
            point
            for point in ordered
            if point != last_click
            and min(point[0] - left, right - point[0], point[1] - top, bottom - point[1]) >= best_margin - 1
        ]
        if safe_pool:
            return random.choice(safe_pool[: min(8, len(safe_pool))])

        for point in ordered:
            if point != last_click:
                return point
        return ordered[0]

    def _cluster_score(self, cluster: ClusterRegion) -> tuple[int, int]:
        center = (
            VIEWPORT_REGION_CLIENT[0] + VIEWPORT_REGION_CLIENT[2] // 2,
            VIEWPORT_REGION_CLIENT[1] + VIEWPORT_REGION_CLIENT[3] // 2,
        )
        distance = max(abs(cluster.centroid[0] - center[0]), abs(cluster.centroid[1] - center[1]))
        area = len(cluster.pixels)
        return (-area, distance)

    def _clusters_from_mask(
        self,
        mask: np.ndarray,
        region_offset: Tuple[int, int],
        min_area: int = 20,
    ) -> list[ClusterRegion]:
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        clusters: list[ClusterRegion] = []
        for label in range(1, num_labels):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < min_area:
                continue
            left = int(stats[label, cv2.CC_STAT_LEFT]) + region_offset[0]
            top = int(stats[label, cv2.CC_STAT_TOP]) + region_offset[1]
            width = int(stats[label, cv2.CC_STAT_WIDTH])
            height = int(stats[label, cv2.CC_STAT_HEIGHT])
            cx = int(centroids[label, 0]) + region_offset[0]
            cy = int(centroids[label, 1]) + region_offset[1]
            ys, xs = np.where(labels == label)
            pixels = [
                (int(x) + region_offset[0], int(y) + region_offset[1])
                for y, x in zip(ys, xs)
            ]
            clusters.append(
                ClusterRegion(
                    centroid=(cx, cy),
                    bounds=(left, top, width, height),
                    pixels=pixels,
                )
            )
        return clusters

    def _purple_fallback_clusters(self, frame: np.ndarray) -> list[ClusterRegion]:
        """
        Fallback detector for RuneLite purple highlights when the configured RGB
        sample does not exactly exist in the captured frame.
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower = np.array([135, 80, 40], dtype=np.uint8)
        upper = np.array([170, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        return self._clusters_from_mask(
            mask,
            region_offset=(VIEWPORT_REGION_CLIENT[0], VIEWPORT_REGION_CLIENT[1]),
            min_area=30,
        )

    def _find_booth_cluster(self) -> Optional[ClusterRegion]:
        """Search the RuneLite viewport for booth clusters and return the best candidate."""
        region = self._viewport_screen_region()
        frame = self._screen.grab(region)
        clusters = self._detector.find_cluster_regions(
            frame,
            self._cfg.bank_booth_color,
            region_offset=(VIEWPORT_REGION_CLIENT[0], VIEWPORT_REGION_CLIENT[1]),
        )
        if not clusters:
            clusters = self._purple_fallback_clusters(frame)
        if not clusters:
            return None

        cluster = min(clusters, key=self._cluster_score)
        return cluster

    def _find_booth(self, log: Optional[Callable[[str], None]] = None) -> Optional[Tuple[int, int]]:
        """Return a validated click point inside the best booth cluster."""
        cluster = self._find_booth_cluster()
        if not cluster:
            return None
        target = self._pick_cluster_click(cluster)
        if not target:
            return None

        ox, oy = self._client_origin()
        screen_target = (ox + target[0], oy + target[1])
        rgb = self._screen.pixel_color(screen_target[0], screen_target[1])
        if not self._matches_profile(rgb):
            if log:
                log(f"Rejected bank booth target at client={target} screen={screen_target} rgb={rgb}")
            return None

        print(f"Detected Bank Booth at client={target} screen={screen_target} rgb={rgb}")
        if log:
            log(f"Detected bank booth at client={target} screen={screen_target} rgb={rgb}")
        self._last_booth_click = target
        return target

    def _acquire_booth_target(self, log: Optional[Callable[[str], None]] = None) -> Optional[Tuple[int, int]]:
        """
        Require two consecutive booth detections before clicking.
        This reduces one-frame misses and prevents fallback/random clicks.
        """
        confirmed_cluster: Optional[ClusterRegion] = None
        for detect_attempt in range(1, 3):
            cluster = self._find_booth_cluster()
            if not cluster:
                if log:
                    log(f"Bank booth detect pass {detect_attempt}/2: no purple booth cluster found.")
                return None
            if log:
                log(
                    f"Bank booth detect pass {detect_attempt}/2:"
                    f" centroid={cluster.centroid} bounds={cluster.bounds} pixels={len(cluster.pixels)}"
                )
            if confirmed_cluster is None:
                confirmed_cluster = cluster
                time.sleep(0.35)
                continue

            dx = abs(cluster.centroid[0] - confirmed_cluster.centroid[0])
            dy = abs(cluster.centroid[1] - confirmed_cluster.centroid[1])
            if max(dx, dy) <= 15:
                break

            if log:
                log(
                    "Booth detection shifted between passes"
                    f" first={confirmed_cluster.centroid} second={cluster.centroid}."
                )
            return None

        return self._find_booth(log)
