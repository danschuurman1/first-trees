# gui/control_tab.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import Callable, List, Optional


class ControlTab(ttk.Frame):
    def __init__(
        self,
        parent: ttk.Notebook,
        bot_names: List[str],
        on_start: Callable[[str], None],
        on_stop: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self._on_start = on_start
        self._on_stop = on_stop
        self._start_time: Optional[datetime] = None
        self._build(bot_names)

    def _build(self, bot_names: List[str]) -> None:
        pad = {"padx": 8, "pady": 4}

        ttk.Label(self, text="Bot:").grid(row=0, column=0, sticky="e", **pad)
        self._bot_var = tk.StringVar(value=bot_names[0] if bot_names else "")
        self._bot_combo = ttk.Combobox(self, textvariable=self._bot_var,
                                        values=bot_names, state="readonly", width=20)
        self._bot_combo.grid(row=0, column=1, sticky="w", **pad)

        self._toggle_btn = ttk.Button(self, text="Start", command=self._toggle)
        self._toggle_btn.grid(row=1, column=0, columnspan=2, **pad)

        self._status_var = tk.StringVar(value="Idle")
        ttk.Label(self, textvariable=self._status_var, font=("Helvetica", 11, "bold")).grid(
            row=2, column=0, columnspan=2, **pad)

        ttk.Label(self, text="Logs dropped:").grid(row=3, column=0, sticky="e", **pad)
        self._logs_var = tk.StringVar(value="0")
        ttk.Label(self, textvariable=self._logs_var).grid(row=3, column=1, sticky="w", **pad)

        ttk.Label(self, text="Runtime:").grid(row=4, column=0, sticky="e", **pad)
        self._runtime_var = tk.StringVar(value="00:00:00")
        ttk.Label(self, textvariable=self._runtime_var).grid(row=4, column=1, sticky="w", **pad)

        ttk.Label(self, text="Loops/min:").grid(row=5, column=0, sticky="e", **pad)
        self._lpm_var = tk.StringVar(value="0")
        ttk.Label(self, textvariable=self._lpm_var).grid(row=5, column=1, sticky="w", **pad)

        ttk.Label(self, text="Press ESC to halt bot at any time.",
                  foreground="gray").grid(row=6, column=0, columnspan=2, **pad)

    def _toggle(self) -> None:
        if self._toggle_btn["text"] == "Start":
            self._start_time = datetime.now()
            self._toggle_btn.configure(text="Stop")
            self._on_start(self._bot_var.get())
        else:
            self._toggle_btn.configure(text="Start")
            self._on_stop()

    def set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    def set_logs_dropped(self, n: int) -> None:
        self._logs_var.set(str(n))

    def update_stats(self, loops: int) -> None:
        if self._start_time:
            elapsed = datetime.now() - self._start_time
            secs = int(elapsed.total_seconds())
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            self._runtime_var.set(f"{h:02d}:{m:02d}:{s:02d}")
            minutes = elapsed.total_seconds() / 60 or 1
            self._lpm_var.set(f"{loops / minutes:.1f}")

    def force_stop_ui(self) -> None:
        """Called when ESC halts the bot externally."""
        self._toggle_btn.configure(text="Start")
        self._status_var.set("Halted (ESC)")
