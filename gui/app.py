# gui/app.py
from __future__ import annotations
import importlib
import tkinter as tk
from tkinter import ttk

import bots  # noqa: F401 — triggers bot .register() / .register_test() calls
from bots.registry import BOT_REGISTRY
from config import ConfigManager, GlobalConfig, BotConfig
from gui.control_tab import ControlTab
from gui.color_tab import ColorTab


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("OSRS Bot — Ticker UI")
        self.attributes("-topmost", True)
        self.resizable(True, True)

        self._cfg_mgr = ConfigManager()
        self._cfg: GlobalConfig = self._cfg_mgr.config
        self._active_bot  = None

        self._build_ui()
        self._poll_log()

    def _build_ui(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=4, pady=4)
        self.bind_all("<Escape>", lambda _: self._esc_stop())

        bot_names = list(BOT_REGISTRY.keys()) or ["Woodcutter", "Willow Trees"]

        self._control_tab = ControlTab(
            nb, 
            self._cfg_mgr.get_current_preset(),
            bot_names, 
            self._start_bot, 
            self._stop_bot,
            on_reload=self._reload_all,
            on_bot_change=self._on_bot_change,
            on_config_change=self._save_config,
        )
        # Set initial selection in UI from config
        self._control_tab.set_selected_bot(self._cfg.selected_bot)

        # ColorTab needs the PRESET, not the GlobalConfig
        self._color_tab = ColorTab(nb, self._cfg_mgr.get_current_preset(), self._save_config)

        nb.add(self._control_tab, text="Controls")
        nb.add(self._color_tab,   text="Colors")

    def _on_bot_change(self, new_bot_name: str) -> None:
        """Triggered when the dropdown in ControlTab changes."""
        self._cfg.selected_bot = new_bot_name
        self._save_config()
        self._control_tab.refresh_preset(self._cfg_mgr.get_current_preset())
        # Refresh ColorTab with the new preset
        self._color_tab.refresh_preset(self._cfg_mgr.get_current_preset())
        self._control_tab.append_log(f"Switched to preset: {new_bot_name}")

    def _start_bot(self, bot_name: str) -> None:
        BotClass = BOT_REGISTRY.get(bot_name)
        if not BotClass:
            self._control_tab.append_log(f"Unknown bot: {bot_name}")
            return
        try:
            # Pass the current preset to the bot
            preset = self._cfg_mgr.get_current_preset()
            self._active_bot = BotClass(config=preset)
            self._active_bot.start()
        except Exception as exc:
            self._control_tab.append_log(f"ERROR: {exc}")
            self._control_tab.set_status(f"Error: {exc}")
            self._control_tab.force_stop_ui()
            return
        self._control_tab.set_status("Running")
        self._control_tab.append_log(f"Started bot: {bot_name}")

    def _stop_bot(self) -> None:
        if self._active_bot:
            self._active_bot.stop()
            self._active_bot = None
        self._control_tab.set_status("Idle")

    def _reload_all(self) -> None:
        """Comprehensive 'Hot Reload' of all bot logic and core monitor modules."""
        try:
            # Import modules
            import bots.woodcutter as _wc
            import bots.willow_trees as _wt
            import bots.willow_banker as _wb
            import bots.willow_chopper_launcher as _wcl
            import bots.motherlode_mine as _mlm
            import bots.helpers.banker as _bh
            import core.inventory_monitor as _im
            import core.xp_monitor as _xm
            import core.geographic_leash as _gl
            import bots.registry as _reg

            # Perform reloads
            importlib.reload(_wc)
            importlib.reload(_wt)
            importlib.reload(_wb)
            importlib.reload(_wcl)
            importlib.reload(_mlm)
            importlib.reload(_bh)
            importlib.reload(_im)
            importlib.reload(_xm)
            importlib.reload(_gl)
            importlib.reload(_reg)

            # Update the UI dropdown with fresh registry
            from bots.registry import BOT_REGISTRY
            self._control_tab.set_bots(list(BOT_REGISTRY.keys()))
            self._control_tab.append_log("[Reload] Success: Bots, Core Monitors, and Helpers refreshed.")
        except Exception as e:
            self._control_tab.append_log(f"[Reload] ERROR: {str(e)}")

    def _esc_stop(self) -> None:
        self._stop_bot()
        self._control_tab.force_stop_ui()

    def _save_config(self) -> None:
        self._cfg_mgr.save()

    def _poll_log(self) -> None:
        if self._active_bot:
            loops = self._active_bot.loops
            self._control_tab.update_stats(loops)
            if not self._active_bot.is_running() and loops > 0:
                self._control_tab.set_status(f"Halted after {loops} loops")
                self._control_tab.force_stop_ui()
            while not self._active_bot.log_queue.empty():
                self._control_tab.append_log(self._active_bot.log_queue.get_nowait())

        self.after(200, self._poll_log)


if __name__ == "__main__":
    app = App()
    app.mainloop()
