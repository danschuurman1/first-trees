from unittest.mock import MagicMock

from bots.base_bot import Bot
from bots.willow_banker import WillowBankerBot
from config import BotConfig, ColorProfile


def _make_bot() -> WillowBankerBot:
    bot = WillowBankerBot.__new__(WillowBankerBot)
    Bot.__init__(bot)
    bot._cfg = BotConfig(
        log_color=ColorProfile(r=1, g=2, b=3, tolerance=5, enabled=True),
        bank_booth_color=ColorProfile(r=4, g=5, b=6, tolerance=7, enabled=True),
    )
    bot._screen = MagicMock()
    bot._mouse = MagicMock()
    bot._color = MagicMock()
    bot._banker = MagicMock()
    bot._log_color = bot._cfg.log_color
    bot._window_region = (0, 0, 765, 503)
    bot._activate_runelite = MagicMock()
    bot._count_logs_in_window = MagicMock(return_value=0)
    bot.random_sleep = MagicMock()
    return bot


def test_run_loop_triggers_banking_at_27_logs():
    bot = _make_bot()
    bot._count_logs_in_window.return_value = 27

    bot.run_loop()

    bot._banker.run.assert_called_once_with(bot.log)


def test_run_loop_does_not_trigger_banking_below_27_logs():
    bot = _make_bot()
    bot._count_logs_in_window.return_value = 26

    bot.run_loop()

    bot._banker.run.assert_not_called()


def test_run_banking_if_ready_skips_when_bank_color_disabled():
    bot = _make_bot()
    bot._cfg.bank_booth_color.enabled = False

    bot._run_banking_if_ready()

    bot._banker.run.assert_not_called()
