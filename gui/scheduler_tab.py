# gui/scheduler_tab.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable
from config import BotConfig, DowntimeWindow

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class SchedulerTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, config: BotConfig,
                 on_change: Callable[[], None]) -> None:
        super().__init__(parent)
        self._cfg = config
        self._on_change = on_change
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        self._enabled_var = tk.BooleanVar(value=self._cfg.scheduler_enabled)
        ttk.Checkbutton(top, text="Enable scheduled downtime",
                        variable=self._enabled_var, command=self._commit).pack(side="left")

        cols = ("Start", "End", "Days", "Variance (min)")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", height=8)
        for c in cols:
            self._tree.heading(c, text=c)
            self._tree.column(c, width=120)
        self._tree.pack(fill="both", expand=True, padx=8)
        self._refresh_tree()

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", padx=8, pady=4)
        ttk.Button(btn_row, text="Add window", command=self._add_window).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Remove selected", command=self._remove_selected).pack(side="left")

        var_frame = ttk.LabelFrame(self, text="Random break variance")
        var_frame.pack(fill="x", padx=8, pady=6)
        self._variance_var = tk.IntVar(value=0)
        ttk.Scale(var_frame, from_=0, to=15, variable=self._variance_var,
                  orient="horizontal", length=200).pack(side="left", padx=4)
        ttk.Label(var_frame, textvariable=self._variance_var).pack(side="left")
        ttk.Label(var_frame, text="minutes").pack(side="left")

    def _refresh_tree(self) -> None:
        for row in self._tree.get_children():
            self._tree.delete(row)
        for w in self._cfg.downtime_windows:
            days_str = ",".join(DAY_NAMES[d] for d in w.days)
            self._tree.insert("", "end", values=(w.start_hhmm, w.end_hhmm,
                                                  days_str, w.variance_minutes))

    def _add_window(self) -> None:
        self._cfg.downtime_windows.append(DowntimeWindow())
        self._refresh_tree()
        self._on_change()

    def _remove_selected(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        del self._cfg.downtime_windows[idx]
        self._refresh_tree()
        self._on_change()

    def _commit(self) -> None:
        self._cfg.scheduler_enabled = self._enabled_var.get()
        self._on_change()
