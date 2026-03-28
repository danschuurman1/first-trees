# tests/test_woodcutter.py
from bots.woodcutter import WoodcutterBot, chebyshev


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
