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


def test_inventory_full_opens_tab_before_grab():
    """_inventory_full must ensure inventory is open before grabbing the region."""
    bot = _make_bot()
    call_order = []
    bot._screen.pixel_color.return_value = (75, 70, 68)  # closed
    bot._mouse.move_and_click.side_effect = lambda pos: call_order.append("click") or pos
    bot._screen.grab.side_effect = lambda r: call_order.append("grab") or MagicMock()
    bot._color.find_clusters.return_value = []
    bot._inventory_full()
    assert call_order.index("click") < call_order.index("grab")


def test_inventory_has_logs_opens_tab_before_grab():
    """_inventory_has_logs must ensure inventory is open before grabbing the region."""
    bot = _make_bot()
    call_order = []
    bot._screen.pixel_color.return_value = (75, 70, 68)  # closed
    bot._mouse.move_and_click.side_effect = lambda pos: call_order.append("click") or pos
    bot._screen.grab.side_effect = lambda r: call_order.append("grab") or MagicMock()
    bot._color.find_clusters.return_value = []
    bot._inventory_has_logs()
    assert call_order.index("click") < call_order.index("grab")


# ---------------------------------------------------------------------------
# Bug 3 — Drop context menu: right-click required
# ---------------------------------------------------------------------------

def test_drop_one_log_right_clicks_item_before_drop():
    """_drop_one_log must right-click the log to open the context menu."""
    bot = _make_bot()
    bot._color.best_cluster.return_value = (600, 250)
    bot._mouse.right_click = MagicMock(return_value=(600, 250))
    bot._mouse.move_and_click.return_value = (600, 290)
    bot._drop_one_log()
    bot._mouse.right_click.assert_called_once_with((600, 250))


def test_drop_one_log_left_clicks_drop_option_after_right_click():
    """After right-clicking, _drop_one_log must left-click the Drop option below."""
    bot = _make_bot()
    bot._color.best_cluster.return_value = (600, 250)
    bot._mouse.right_click = MagicMock(return_value=(600, 250))
    bot._mouse.move_and_click.return_value = (600, 290)
    bot._drop_one_log()
    # The drop option click must have a y-offset from the item
    clicked_pos = bot._mouse.move_and_click.call_args[0][0]
    assert clicked_pos[1] > 250  # below the item


# ---------------------------------------------------------------------------
# Inventory clearing: shift+click all logs
# ---------------------------------------------------------------------------

def test_drop_all_logs_shift_clicks_every_log_cluster():
    """_drop_all_logs must hold Shift and left-click every log cluster."""
    bot = _make_bot()
    log_positions = [(580, 220), (604, 220), (628, 220)]
    bot._color.find_clusters.return_value = log_positions
    bot._mouse.move_and_click.return_value = (580, 220)
    bot._drop_all_logs()
    assert bot._mouse.move_and_click.call_count == len(log_positions)
    bot._keyboard.press_shift.assert_called()
    bot._keyboard.release_shift.assert_called()


def test_drop_all_logs_releases_shift_even_when_no_logs():
    """Shift must always be released, even when the inventory scan finds nothing."""
    bot = _make_bot()
    bot._color.find_clusters.return_value = []
    bot._drop_all_logs()
    # release_shift should not be called at all (or gracefully handle no logs)
    # At minimum, press_shift must not be left dangling: calls must be balanced
    press_count = bot._keyboard.press_shift.call_count
    release_count = bot._keyboard.release_shift.call_count
    assert press_count == release_count
