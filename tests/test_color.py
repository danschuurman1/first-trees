# tests/test_color.py
import numpy as np
from config import ColorProfile
from core.color import ColorDetector

def _make_image(color_bgr, size=(100, 100)):
    """Solid color BGR image."""
    img = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    img[:] = color_bgr
    return img

def test_matches_exact_color():
    profile = ColorProfile(r=200, g=100, b=50, tolerance=10)
    img = _make_image((50, 100, 200))  # BGR: B=50, G=100, R=200
    detector = ColorDetector()
    clusters = detector.find_clusters(img, profile, region_offset=(0, 0))
    assert len(clusters) == 1
    cx, cy = clusters[0]
    assert 45 <= cx <= 55
    assert 45 <= cy <= 55

def test_no_match_outside_tolerance():
    profile = ColorProfile(r=200, g=100, b=50, tolerance=5)
    img = _make_image((10, 10, 10))
    detector = ColorDetector()
    clusters = detector.find_clusters(img, profile, region_offset=(0, 0))
    assert clusters == []

def test_noise_rejection_below_4_pixels():
    profile = ColorProfile(r=255, g=0, b=0, tolerance=5)
    img = _make_image((200, 200, 200))
    # Plant 2 matching pixels (below 4-pixel threshold) — BGR: R=255 means (0,0,255) in BGR
    img[10, 10] = (0, 0, 255)
    img[10, 11] = (0, 0, 255)
    detector = ColorDetector()
    clusters = detector.find_clusters(img, profile, region_offset=(0, 0))
    assert clusters == []

def test_find_log_slots_scales_to_logical_coords_at_2x():
    """find_log_slots returns logical (halved) coords when physical image is 2x the logical width."""
    # 200×200 physical image representing a 100×100 logical display (Retina 2×)
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    # Pink blob at physical pixels (80:120, 80:120) — logical centroid should be ≈ (50, 50)
    # Pink in BGR: R=220, G=20, B=105 → (B=105, G=20, R=220)
    frame[80:120, 80:120] = (105, 20, 220)

    profile = ColorProfile(r=220, g=20, b=105, tolerance=20, enabled=True)
    detector = ColorDetector()
    slots = detector.find_log_slots(frame, profile, logical_width=100)

    assert len(slots) == 1
    cx, cy = slots[0]
    assert 48 <= cx <= 52
    assert 48 <= cy <= 52


def test_find_log_slots_ignores_noise_blobs():
    """find_log_slots drops blobs smaller than MIN_BLOB_PIXELS."""
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    # Only 3 pixels — below threshold
    frame[10, 10] = (105, 20, 220)
    frame[10, 11] = (105, 20, 220)
    frame[10, 12] = (105, 20, 220)

    profile = ColorProfile(r=220, g=20, b=105, tolerance=20, enabled=True)
    detector = ColorDetector()
    slots = detector.find_log_slots(frame, profile, logical_width=200)

    assert slots == []


def test_center_priority_selection():
    profile = ColorProfile(r=255, g=0, b=0, tolerance=5)
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    # Blob near center (90-110, 90-110) — BGR: R=255 → (0, 0, 255)
    img[90:110, 90:110] = (0, 0, 255)
    # Blob far from center
    img[0:10, 0:10] = (0, 0, 255)
    detector = ColorDetector()
    best = detector.best_cluster(img, profile, region_offset=(0, 0))
    assert best is not None
    cx, cy = best
    assert 85 <= cx <= 115
    assert 85 <= cy <= 115
