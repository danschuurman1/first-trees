# core/color.py
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

from config import ColorProfile

# Minimum blob size (pixels) to not be treated as noise.
# A real RuneLite tree highlight produces a much larger region than stray noise.
MIN_BLOB_PIXELS = 20


@dataclass
class ClusterRegion:
    centroid: Tuple[int, int]
    bounds: Tuple[int, int, int, int]
    pixels: List[Tuple[int, int]]


class ColorDetector:
    """Detects color blobs in BGR images and returns centroid positions."""

    def _mask(self, img: np.ndarray, profile: ColorProfile) -> np.ndarray:
        """Return binary mask where pixels match the profile within tolerance (sphere in RGB space)."""
        b = img[:, :, 0].astype(np.int32)
        g = img[:, :, 1].astype(np.int32)
        r = img[:, :, 2].astype(np.int32)
        dist = np.sqrt((r - profile.r) ** 2 + (g - profile.g) ** 2 + (b - profile.b) ** 2)
        mask = (dist <= profile.tolerance).astype(np.uint8) * 255
        return mask

    def find_clusters(
        self,
        img: np.ndarray,
        profile: ColorProfile,
        region_offset: Tuple[int, int] = (0, 0),
    ) -> List[Tuple[int, int]]:
        """Return list of (screen_x, screen_y) centroids for each surviving blob."""
        mask = self._mask(img, profile)
        num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

        results: List[Tuple[int, int]] = []
        for label in range(1, num_labels):  # skip background label 0
            area = stats[label, cv2.CC_STAT_AREA]
            if area < MIN_BLOB_PIXELS:
                continue
            cx = int(centroids[label, 0]) + region_offset[0]
            cy = int(centroids[label, 1]) + region_offset[1]
            results.append((cx, cy))
        return results

    def find_cluster_regions(
        self,
        img: np.ndarray,
        profile: ColorProfile,
        region_offset: Tuple[int, int] = (0, 0),
    ) -> List[ClusterRegion]:
        """Return centroid, bounding box, and member pixels for each surviving blob."""
        mask = self._mask(img, profile)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

        results: List[ClusterRegion] = []
        for label in range(1, num_labels):
            area = stats[label, cv2.CC_STAT_AREA]
            if area < MIN_BLOB_PIXELS:
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
            results.append(
                ClusterRegion(
                    centroid=(cx, cy),
                    bounds=(left, top, width, height),
                    pixels=pixels,
                )
            )
        return results

    def find_log_slots(
        self,
        frame: np.ndarray,
        profile: ColorProfile,
        logical_width: int,
    ) -> List[Tuple[int, int]]:
        """Find blobs matching profile and return their centroids as logical screen coords.

        Retina-safe: logical_width is the monitor's logical pixel width; frame.shape[1] is
        the physical pixel width. scale = physical / logical is applied to convert centroids.
        """
        scale = frame.shape[1] / logical_width
        blobs = self.find_clusters(frame, profile)
        return [(int(cx / scale), int(cy / scale)) for cx, cy in blobs]

    def best_cluster(
        self,
        img: np.ndarray,
        profile: ColorProfile,
        region_offset: Tuple[int, int] = (0, 0),
    ) -> Optional[Tuple[int, int]]:
        """Return centroid closest to image center (Chebyshev distance), or None."""
        clusters = self.find_clusters(img, profile, region_offset)
        if not clusters:
            return None
        h, w = img.shape[:2]
        center_x = w // 2 + region_offset[0]
        center_y = h // 2 + region_offset[1]
        return min(clusters, key=lambda c: max(abs(c[0] - center_x), abs(c[1] - center_y)))
