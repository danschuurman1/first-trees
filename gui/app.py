# gui/app.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

import bots  # noqa: F401 — triggers WoodcutterBot.register()
from bots.registry import BOT_REGISTRY
from config import ConfigManager
from gui.control_tab import ControlTab
from gui.color_tab import ColorTab
from gui.scheduler_tab import SchedulerTab
from gui.log_tab import LogTab
from gui.loot_tab import LootTab


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("OSRS Bot — First Try Trees")
        self.attributes("-topmost", True)
        self.resizable(True, True)

        self._cfg_mgr = ConfigManager()
        self._cfg = self._cfg_mgr.config
        self._active_bot = None

        self._build_ui()
        self._poll_log()

    def _build_ui(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=4, pady=4)
        self.bind_all("<Escape>", lambda _: self._esc_stop())

        bot_names = list(BOT_REGISTRY.keys()) or ["Woodcutter"]

        self._control_tab = ControlTab(nb, bot_names, self._start_bot, self._stop_bot)
        self._color_tab = ColorTab(nb, self._cfg, self._save_config)
        self._scheduler_tab = SchedulerTab(nb, self._cfg, self._save_config)
        self._log_tab = LogTab(nb)
        self._loot_tab = LootTab(nb, self._cfg, self._save_config)

        nb.add(self._control_tab, text="Control")
        nb.add(self._color_tab, text="Colors")
        nb.add(self._scheduler_tab, text="Scheduler")
        nb.add(self._log_tab, text="Log")
        nb.add(self._loot_tab, text="Loot")

    def _start_bot(self, bot_name: str) -> None:
        BotClass = BOT_REGISTRY.get(bot_name)
        if not BotClass:
            self._log_tab.append(f"Unknown bot: {bot_name}")
            return
        try:
            self._active_bot = BotClass(config=self._cfg)
        except Exception as exc:
            self._log_tab.append(f"ERROR creating bot: {exc}")
            self._control_tab.set_status(f"Error: {exc}")
            self._control_tab.force_stop_ui()
            return

        try:
            self._active_bot.start()
        except Exception as exc:
            self._log_tab.append(f"ERROR starting bot: {exc}")
            self._control_tab.set_status(f"Error: {exc}")
            self._control_tab.force_stop_ui()
            return

        self._control_tab.set_status("Running")
        self._log_tab.append(f"Started bot: {bot_name}")

    def _stop_bot(self) -> None:
        if self._active_bot:
            self._active_bot.stop()
            self._active_bot = None
        self._control_tab.set_status("Idle")

    def _esc_stop(self) -> None:
        self._stop_bot()
        self._control_tab.force_stop_ui()

    def _save_config(self) -> None:
        self._cfg_mgr.save()

    def _poll_log(self) -> None:
        """Pull messages from bot log queue every 200ms and update UI."""
        if self._active_bot:
            loops = self._active_bot.loops
            self._control_tab.update_stats(loops)
            if not self._active_bot.is_running() and loops > 0:
                self._control_tab.set_status(f"Halted after {loops} loops")
                self._control_tab.force_stop_ui()
            while not self._active_bot.log_queue.empty():
                msg = self._active_bot.log_queue.get_nowait()
                self._log_tab.append(msg)
        self.after(200, self._poll_log)
