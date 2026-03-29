# tests/test_woodcutter.py
from unittest.mock import MagicMock, call, patch
from bots.woodcutter import WoodcutterBot, chebyshev
from bots.base_bot import Bot
from config import BotConfig, ColorProfile


def _make_bot(
    tree_r=0, tree_g=255, tree_b=255, tree_tol=30,
    log_r=139, log_g=90, log_b=43, log_tol=30,
):
    """Build a WoodcutterBot with all hardware replaced by mocks."""
    cfg = BotConfig(
        tree_color=ColorProfile(r=tree_r, g=tree_g, b=tree_b, tolerance=tree_tol, enabled=True),
        log_color=ColorProfile(r=log_r, g=log_g, b=log_b, tolerance=log_tol, enabled=True),
    )
    bot = WoodcutterBot.__new__(WoodcutterBot)
    Bot.__init__(bot)
    bot._cfg = cfg
    bot._screen = MagicMock()
    bot._color = MagicMock()
    bot._mouse = MagicMock()
    bot._keyboard = MagicMock()
    bot._scheduler = MagicMock()
    bot._scheduler.is_break_time.return_value = False
    bot._running.set()  # simulate running bot for loops that check _running
    bot._screen.pixel_color.return_value = (180, 25, 20)  # default: inventory open (red)
    bot._origin = (0, 0)
    return bot


def test_bot_name():
    assert WoodcutterBot.name == "Woodcutter"


def test_bot_registers():
    WoodcutterBot.register()
    from bots.registry import BOT_REGISTRY
    assert "Woodcutter" in BOT_REGISTRY


def test_stop_flag_exits_loop():
    bot = WoodcutterBot.__new__(WoodcutterBot)
    WoodcutterBot.__init__(bot)
    bot.start()
    assert bot.is_running()
    bot.stop()
    bot._thread.join(timeout=5)
    assert not bot.is_running()


def test_chebyshev_distance():
    assert chebyshev((3105, 3231), (3105, 3231)) == 0
    assert chebyshev((3105, 3231), (3115, 3231)) == 10
    assert chebyshev((3105, 3231), (3116, 3231)) == 11
    assert chebyshev((3105, 3231), (3115, 3241)) == 10


def test_chebyshev_diagonal():
    # Diagonal move: both axes equal, max = one axis
    assert chebyshev((0, 0), (5, 5)) == 5
    assert chebyshev((0, 0), (3, 7)) == 7


# ---------------------------------------------------------------------------
# Bug 1 — Tree detection: pixel sampling instead of cluster matching
# ---------------------------------------------------------------------------

def test_wait_for_tree_gone_uses_pixel_color_not_clusters():
    """_wait_for_tree_gone must sample a single pixel, never call find_clusters."""
    bot = _make_bot(tree_r=0, tree_g=255, tree_b=255, tree_tol=30)
    # First two polls: still cyan (tree present); third: grey (tree gone)
    bot._screen.pixel_color.side_effect = [
        (0, 255, 255),
        (0, 255, 255),
        (128, 128, 128),
    ]
    bot._wait_for_tree_gone((300, 200))
    assert bot._screen.pixel_color.call_count == 3
    bot._color.find_clusters.assert_not_called()


def test_wait_for_tree_gone_samples_the_clicked_coordinate():
    """pixel_color must be called with the exact pos passed to _wait_for_tree_gone."""
    bot = _make_bot(tree_r=0, tree_g=255, tree_b=255, tree_tol=30)
    bot._screen.pixel_color.side_effect = [(128, 128, 128)]  # immediately gone
    bot._wait_for_tree_gone((412, 210))
    bot._screen.pixel_color.assert_called_with(412, 210)


# ---------------------------------------------------------------------------
# Bug 2 — Inventory tab state: red = open, grey = closed
# ---------------------------------------------------------------------------

def test_is_inventory_open_returns_true_for_red_pixel():
    bot = _make_bot()
    bot._screen.pixel_color.return_value = (180, 25, 20)  # reddish
    assert bot._is_inventory_open() is True


def test_is_inventory_open_returns_false_for_grey_pixel():
    bot = _make_bot()
    bot._screen.pixel_color.return_value = (75, 70, 68)  # grey
    assert bot._is_inventory_open() is False


def test_ensure_inventory_open_clicks_tab_when_closed():
    bot = _make_bot()
    bot._screen.pixel_color.return_value = (75, 70, 68)  # grey = closed
    bot._mouse.move_and_click.return_value = (644, 169)
    bot._ensure_inventory_open()
    bot._mouse.move_and_click.assert_called_once()


def test_ensure_inventory_open_does_not_click_when_already_open():
    bot = _make_bot()
    bot._screen.pixel_color.return_value = (180, 25, 20)  # red = open
    bot._mouse.move_and_click.return_value = (644, 169)
    bot._ensure_inventory_open()
    bot._mouse.move_and_click.assert_not_called()


def test_inventory_full_calls_ensure_open():
    bot = _make_bot()
    bot._ensure_inventory_open = MagicMock()
    bot._count_filled_slots = MagicMock(return_value=0)
    bot._inventory_full()
    bot._ensure_inventory_open.assert_called_once()


def test_inventory_has_logs_calls_ensure_open():
    bot = _make_bot()
    bot._ensure_inventory_open = MagicMock()
    bot._count_filled_slots = MagicMock(return_value=0)
    bot._inventory_has_logs()
    bot._ensure_inventory_open.assert_called_once()


# ---------------------------------------------------------------------------
# Inventory clearing: shift+click all logs
# ---------------------------------------------------------------------------

def test_drop_all_logs_shift_clicks_every_log_cluster():
    """_drop_all_logs must hold Shift and left-click every filled slot."""
    bot = _make_bot()
    bot._ensure_inventory_open = MagicMock()
    positions = [(580, 220), (604, 220), (628, 220)]
    bot._slot_positions = MagicMock(return_value=positions)
    bot._is_slot_log = MagicMock(return_value=True)
    bot._mouse.move_and_click.return_value = (580, 220)
    bot._drop_all_logs()
    assert bot._mouse.move_and_click.call_count == len(positions)
    bot._keyboard.press_shift.assert_called()
    bot._keyboard.release_shift.assert_called()


def test_drop_all_logs_releases_shift_even_when_no_logs():
    """When no slots are filled, shift must never be pressed (no dangling press)."""
    bot = _make_bot()
    bot._ensure_inventory_open = MagicMock()
    bot._slot_positions = MagicMock(return_value=[])
    bot._is_slot_log = MagicMock(return_value=False)
    bot._drop_all_logs()
    press_count = bot._keyboard.press_shift.call_count
    release_count = bot._keyboard.release_shift.call_count
    assert press_count == release_count


# ---------------------------------------------------------------------------
# Calibration / origin offset tests
# ---------------------------------------------------------------------------

def test_viewport_grab_uses_origin_x_offset():
    """_nearest_living_tree must apply origin x to the grab region."""
    bot = _make_bot()
    bot._origin = (20, 0)
    bot._color.find_clusters.return_value = []
    bot._nearest_living_tree()
    left = bot._screen.grab.call_args[0][0][0]
    assert left == 20 + 4  # ox + 4


def test_viewport_grab_uses_origin_y_offset():
    bot = _make_bot()
    bot._origin = (0, 30)
    bot._color.find_clusters.return_value = []
    bot._nearest_living_tree()
    top = bot._screen.grab.call_args[0][0][1]
    assert top == 30 + 4  # oy + 4


def test_inventory_tab_pixel_check_includes_origin():
    """_is_inventory_open must sample pixel at (ox+644, oy+169)."""
    bot = _make_bot()
    bot._origin = (10, 20)
    bot._screen.pixel_color.return_value = (180, 25, 20)
    bot._is_inventory_open()
    bot._screen.pixel_color.assert_called_with(10 + 644, 20 + 169)


def test_ensure_inventory_open_tab_click_includes_origin():
    """When tab is closed, click target must include origin offset."""
    bot = _make_bot()
    bot._origin = (10, 20)
    bot._screen.pixel_color.return_value = (75, 70, 68)  # grey = closed
    bot._mouse.move_and_click.return_value = (654, 189)
    bot._ensure_inventory_open()
    clicked = bot._mouse.move_and_click.call_args[0][0]
    assert clicked == (10 + 644, 20 + 169)


# ---------------------------------------------------------------------------
# Slot-based inventory tests
# ---------------------------------------------------------------------------

def test_slot_positions_returns_28():
    bot = _make_bot()
    assert len(bot._slot_positions()) == 28


def test_slot_positions_include_origin():
    """All slot positions must include the origin offset."""
    bot = _make_bot()
    bot._origin = (10, 20)
    slots = bot._slot_positions()
    # Every x must be > 10, every y must be > 20
    assert all(x > 10 for x, y in slots)
    assert all(y > 20 for x, y in slots)


def test_slot_positions_evenly_spaced():
    """Consecutive columns in the same row differ by _INV_SLOT_W exactly."""
    from bots.woodcutter import _INV_SLOT_W, _INV_SLOT_H
    bot = _make_bot()
    slots = bot._slot_positions()
    # Row 0: slots 0-3 should be spaced by _INV_SLOT_W horizontally
    row0 = slots[0:4]
    for i in range(3):
        assert row0[i + 1][0] - row0[i][0] == _INV_SLOT_W
    # Column 0: slots 0, 4, 8... should be spaced by _INV_SLOT_H vertically
    col0 = [slots[r * 4] for r in range(7)]
    for i in range(6):
        assert col0[i + 1][1] - col0[i][1] == _INV_SLOT_H


def test_is_slot_filled_returns_false_for_dark_pixel():
    bot = _make_bot()
    bot._screen.pixel_color.return_value = (55, 52, 48)  # empty slot background
    assert bot._is_slot_filled((600, 250)) is False


def test_is_slot_filled_returns_true_for_bright_pixel():
    bot = _make_bot()
    bot._screen.pixel_color.return_value = (140, 90, 43)  # log item
    assert bot._is_slot_filled((600, 250)) is True


def test_inventory_full_true_when_28_filled():
    bot = _make_bot()
    bot._ensure_inventory_open = MagicMock()
    bot._count_filled_slots = MagicMock(return_value=28)
    assert bot._inventory_full() is True


def test_inventory_full_false_when_fewer_than_28():
    bot = _make_bot()
    bot._ensure_inventory_open = MagicMock()
    bot._count_filled_slots = MagicMock(return_value=17)
    assert bot._inventory_full() is False


def test_drop_all_logs_skips_empty_slots():
    """Only filled slots get clicked — empty slots are ignored."""
    from bots.woodcutter import _INV_ROWS, _INV_COLS
    bot = _make_bot()
    bot._ensure_inventory_open = MagicMock()
    # 28 slots; only slot 0 and slot 5 are filled
    filled_positions = {0, 5}
    all_slots = [(i * 10, i * 10) for i in range(28)]
    bot._slot_positions = MagicMock(return_value=all_slots)
    bot._is_slot_log = MagicMock(side_effect=lambda pos: all_slots.index(pos) in filled_positions)
    bot._mouse.move_and_click.return_value = (0, 0)
    bot._drop_all_logs()
    assert bot._mouse.move_and_click.call_count == 2


def test_drop_all_logs_holds_shift_around_clicks():
    bot = _make_bot()
    bot._ensure_inventory_open = MagicMock()
    all_slots = [(i * 10, 0) for i in range(3)]
    bot._slot_positions = MagicMock(return_value=all_slots)
    bot._is_slot_log = MagicMock(return_value=True)
    bot._mouse.move_and_click.return_value = (0, 0)
    bot._drop_all_logs()
    bot._keyboard.press_shift.assert_called_once()
    bot._keyboard.release_shift.assert_called_once()


def test_drop_all_logs_releases_shift_when_no_slots():
    bot = _make_bot()
    bot._ensure_inventory_open = MagicMock()
    bot._slot_positions = MagicMock(return_value=[])
    bot._is_slot_log = MagicMock(return_value=False)
    bot._drop_all_logs()
    # press_shift should never be called if no slots
    bot._keyboard.press_shift.assert_not_called()
