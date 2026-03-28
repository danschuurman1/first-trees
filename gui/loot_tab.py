# gui/loot_tab.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable
from config import BotConfig


class LootTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, config: BotConfig,
                 on_change: Callable[[], None]) -> None:
        super().__init__(parent)
        self._cfg = config
        self._on_change = on_change
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        self._enabled_var = tk.BooleanVar(value=self._cfg.loot_ocr_enabled)
        ttk.Checkbutton(top, text="Enable OCR loot filtering",
                        variable=self._enabled_var, command=self._commit).pack(side="left")

        entry_frame = ttk.LabelFrame(self, text="Item whitelist (comma-separated)")
        entry_frame.pack(fill="x", padx=8, pady=4)
        self._entry_var = tk.StringVar(value=", ".join(self._cfg.loot_whitelist))
        entry = ttk.Entry(entry_frame, textvariable=self._entry_var, width=60)
        entry.pack(padx=6, pady=4, fill="x")
        self._entry_var.trace_add("write", lambda *_: self._commit())

        ttk.Label(entry_frame, text="e.g. abyssal whip, coins, dragon bones",
                  foreground="gray").pack(padx=6, pady=2)

        ttk.Label(self, text="Parsed items:").pack(anchor="w", padx=8)
        self._listbox = tk.Listbox(self, height=8)
        self._listbox.pack(fill="both", expand=True, padx=8)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", padx=8, pady=4)
        ttk.Button(btn_row, text="Remove selected",
                   command=self._remove_selected).pack(side="left", padx=4)

        ttk.Label(self,
                  text="For best results: yellow/white text, no drop shadows, ground item names enabled.",
                  foreground="gray", wraplength=380).pack(padx=8, pady=4)

        self._refresh_list()

    def _commit(self) -> None:
        raw = self._entry_var.get()
        items = [x.strip().lower() for x in raw.split(",") if x.strip()]
        self._cfg.loot_whitelist = items
        self._cfg.loot_ocr_enabled = self._enabled_var.get()
        self._refresh_list()
        self._on_change()

    def _refresh_list(self) -> None:
        self._listbox.delete(0, "end")
        for item in self._cfg.loot_whitelist:
            self._listbox.insert("end", item)

    def _remove_selected(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        del self._cfg.loot_whitelist[idx]
        self._entry_var.set(", ".join(self._cfg.loot_whitelist))
        self._refresh_list()
        self._on_change()
