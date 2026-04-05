from unittest.mock import MagicMock, patch

import numpy as np

from bots.helpers.banker import (
    BankerHelper,
    DEPOSIT_BUTTON_CLICK_BOX,
    DEPOSIT_BUTTON_SEARCH_REGION,
    DEPOSIT_TEMPLATE_EXPECTED_CENTER,
    VIEWPORT_REGION_CLIENT,
)
from config import BotConfig, ColorProfile
from core.color import ClusterRegion, ColorDetector


def _make_helper() -> BankerHelper:
    cfg = BotConfig(
        bank_booth_color=ColorProfile(r=200, g=50, b=150, tolerance=10, enabled=True),
    )
    screen = MagicMock()
    mouse = MagicMock()
    detector = MagicMock(spec=ColorDetector)
    return BankerHelper(cfg, screen, mouse, detector)


def _stamp_deposit_template(helper: BankerHelper, frame: np.ndarray, top: int, left: int) -> None:
    template = helper._deposit_backpack_template()
    y1 = top + template.shape[0]
    x1 = left + template.shape[1]
    frame[top:y1, left:x1][template > 0] = (50, 120, 170)


@patch("bots.helpers.banker.find_runelight_origin", return_value=(100, 200))
def test_find_booth_uses_client_origin_for_viewport_capture(_origin):
    helper = _make_helper()
    helper._screen.grab.return_value = np.zeros((334, 512, 3), dtype=np.uint8)
    helper._screen.pixel_color.return_value = (200, 50, 150)
    helper._detector.find_cluster_regions.return_value = [
        ClusterRegion(
            centroid=(40, 50),
            bounds=(30, 40, 20, 20),
            pixels=[(40, 50), (41, 50), (42, 50)],
        )
    ]

    target = helper._find_booth()

    assert target is not None
    helper._screen.grab.assert_called_once_with((104, 204, 512, 334))
    helper._screen.pixel_color.assert_called_once()
    px, py = helper._screen.pixel_color.call_args.args
    assert (px, py) in {(140, 250), (141, 250), (142, 250)}


@patch("bots.helpers.banker.find_runelight_origin", return_value=(100, 200))
def test_find_booth_rejects_invalid_color_match(_origin):
    helper = _make_helper()
    helper._screen.grab.return_value = np.zeros((334, 512, 3), dtype=np.uint8)
    helper._screen.pixel_color.return_value = (0, 0, 0)
    helper._detector.find_cluster_regions.return_value = [
        ClusterRegion(
            centroid=(40, 50),
            bounds=(30, 40, 20, 20),
            pixels=[(40, 50), (41, 50), (42, 50)],
        )
    ]

    target = helper._find_booth()

    assert target is None


def test_pick_cluster_click_avoids_repeating_last_pixel():
    helper = _make_helper()
    helper._last_booth_click = (41, 50)
    cluster = ClusterRegion(
        centroid=(41, 50),
        bounds=(40, 49, 3, 2),
        pixels=[(40, 50), (41, 50), (42, 50)],
    )

    with patch("bots.helpers.banker.np.random.normal", side_effect=[41, 50] * 20):
        target = helper._pick_cluster_click(cluster)

    assert target in cluster.pixels
    assert target != (41, 50)


def test_pick_cluster_click_prefers_interior_pixels_over_edge_pixels():
    helper = _make_helper()
    cluster = ClusterRegion(
        centroid=(15, 15),
        bounds=(10, 10, 11, 11),
        pixels=[
            (10, 10), (10, 15), (15, 10), (20, 20),
            (14, 14), (15, 15), (16, 16),
        ],
    )

    with patch("bots.helpers.banker.random.choice", side_effect=lambda seq: seq[0]):
        target = helper._pick_cluster_click(cluster)

    assert target in {(14, 14), (15, 15), (16, 16)}


def test_wait_for_bank_ui_uses_deposit_detection_and_saves_overlay():
    helper = _make_helper()
    region = ClusterRegion(centroid=(442, 332), bounds=(430, 320, 20, 10), pixels=[(440, 330), (441, 330)])
    helper._detect_deposit_button_region = MagicMock(side_effect=[region, region])
    helper._save_bank_ui_overlay = MagicMock()

    assert helper._wait_for_bank_ui(timeout=1.0) is True
    helper._detect_deposit_button_region.assert_called()
    helper._save_bank_ui_overlay.assert_called_once_with(region, "open")


def test_viewport_region_client_constant_matches_expected_area():
    assert VIEWPORT_REGION_CLIENT == (4, 4, 512, 334)


def test_wait_for_bank_ui_times_out_when_deposit_button_is_never_detected():
    helper = _make_helper()
    helper._detect_deposit_button_region = MagicMock(return_value=None)
    helper._save_bank_ui_overlay = MagicMock()

    assert helper._wait_for_bank_ui(timeout=0.31) is False
    helper._save_bank_ui_overlay.assert_called_once_with(None, "timeout")


def test_run_stops_without_clicking_when_booth_cannot_be_confirmed():
    helper = _make_helper()
    helper._acquire_booth_target = MagicMock(return_value=None)

    assert helper.run() is False
    helper._mouse.move_and_click.assert_not_called()


def test_run_retries_booth_click_once_after_10_second_wait_failure():
    helper = _make_helper()
    helper._acquire_booth_target = MagicMock(side_effect=[(100, 100), (102, 101)])
    helper._wait_for_bank_ui = MagicMock(side_effect=[False, True])
    helper._find_deposit_button_target = MagicMock(return_value=(442, 332))

    assert helper.run() is True
    assert helper._mouse.move_and_click.call_args_list[0].args[0] == (100, 100)
    assert helper._mouse.move_and_click.call_args_list[1].args[0] == (102, 101)
    helper._mouse.move_and_click_precise.assert_called_once_with((442, 332), radius=1)
    helper._wait_for_bank_ui.assert_any_call(timeout=10.0)


def test_acquire_booth_target_requires_two_consistent_cluster_detections():
    helper = _make_helper()
    first = ClusterRegion(centroid=(100, 120), bounds=(90, 110, 20, 20), pixels=[(100, 120), (101, 120)])
    second = ClusterRegion(centroid=(108, 125), bounds=(98, 115, 20, 20), pixels=[(108, 125), (109, 125)])
    helper._find_booth_cluster = MagicMock(side_effect=[first, second])
    helper._find_booth = MagicMock(return_value=(108, 125))

    with patch("bots.helpers.banker.time.sleep"):
        target = helper._acquire_booth_target()

    assert target == (108, 125)
    helper._find_booth.assert_called_once()


def test_acquire_booth_target_rejects_large_shift_between_detect_passes():
    helper = _make_helper()
    first = ClusterRegion(centroid=(100, 120), bounds=(90, 110, 20, 20), pixels=[(100, 120)])
    second = ClusterRegion(centroid=(140, 170), bounds=(130, 160, 20, 20), pixels=[(140, 170)])
    helper._find_booth_cluster = MagicMock(side_effect=[first, second])
    helper._find_booth = MagicMock()

    with patch("bots.helpers.banker.time.sleep"):
        target = helper._acquire_booth_target()

    assert target is None
    helper._find_booth.assert_not_called()


@patch("bots.helpers.banker.find_runelight_origin", return_value=(100, 200))
def test_find_deposit_button_target_uses_search_region_and_returns_client_point(_origin):
    helper = _make_helper()
    frame = np.zeros((DEPOSIT_BUTTON_SEARCH_REGION[3], DEPOSIT_BUTTON_SEARCH_REGION[2], 3), dtype=np.uint8)
    _stamp_deposit_template(helper, frame, top=3, left=9)
    helper._screen.grab.return_value = frame
    helper._screen.pixel_color.return_value = (150, 110, 60)

    target = helper._find_deposit_button_target()

    assert target is not None
    helper._screen.grab.assert_called_once_with((508, 504, 72, 56))
    bx, by, bw, bh = DEPOSIT_BUTTON_CLICK_BOX
    assert bx <= target[0] < bx + bw
    assert by <= target[1] < by + bh


def test_find_deposit_button_target_avoids_same_pixel_twice():
    helper = _make_helper()
    helper._last_deposit_click = (428, 322)
    frame = np.zeros((DEPOSIT_BUTTON_SEARCH_REGION[3], DEPOSIT_BUTTON_SEARCH_REGION[2], 3), dtype=np.uint8)
    _stamp_deposit_template(helper, frame, top=3, left=9)
    helper._screen.grab.return_value = frame
    helper._screen.pixel_color.return_value = (150, 110, 60)

    with patch("bots.helpers.banker.find_runelight_origin", return_value=(100, 200)):
        target = helper._find_deposit_button_target()

    assert target is not None
    assert target != (428, 322)


def test_run_stops_if_deposit_button_is_not_detected():
    helper = _make_helper()
    helper._acquire_booth_target = MagicMock(return_value=(100, 100))
    helper._wait_for_bank_ui = MagicMock(return_value=True)
    helper._find_deposit_button_target = MagicMock(return_value=None)

    assert helper.run() is False
    helper._mouse.move_and_click_precise.assert_not_called()


def test_find_booth_cluster_falls_back_to_hsv_purple_when_exact_rgb_finds_nothing():
    helper = _make_helper()
    frame = np.zeros((334, 512, 3), dtype=np.uint8)
    frame[100:120, 150:180] = (202, 0, 255)  # BGR, purple highlight-like patch
    helper._screen.grab.return_value = frame
    helper._detector.find_cluster_regions.return_value = []

    cluster = helper._find_booth_cluster()

    assert cluster is not None
    assert len(cluster.pixels) >= 30


def test_detect_deposit_button_region_prefers_cluster_near_expected_center():
    helper = _make_helper()
    frame = np.zeros((DEPOSIT_BUTTON_SEARCH_REGION[3], DEPOSIT_BUTTON_SEARCH_REGION[2], 3), dtype=np.uint8)
    _stamp_deposit_template(helper, frame, top=3, left=9)
    helper._screen.grab.return_value = frame

    with patch("bots.helpers.banker.find_runelight_origin", return_value=(100, 200)):
        region = helper._detect_deposit_button_region()

    assert region is not None
    assert abs(region.centroid[0] - DEPOSIT_TEMPLATE_EXPECTED_CENTER[0]) <= 8
    assert abs(region.centroid[1] - DEPOSIT_TEMPLATE_EXPECTED_CENTER[1]) <= 8
