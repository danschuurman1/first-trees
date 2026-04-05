# gui/control_tab.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import Callable, List, Optional

from config import BotConfig


class ControlTab(ttk.Frame):
    """
    Main control panel. Replaces the old Control and Test tabs with a unified
    interface for selecting and running bots.
    """

    def __init__(
        self,
        parent: ttk.Notebook,
        preset: BotConfig,
        bot_names: List[str],
        on_start: Callable[[str], None],
        on_stop: Callable[[], None],
        on_reload: Callable[[], None] = None,
        on_bot_change: Callable[[str], None] = None,
        on_config_change: Callable[[], None] = None,
    ) -> None:
        super().__init__(parent)
        self._preset = preset
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_reload = on_reload
        self._on_bot_change = on_bot_change
        self._on_config_change = on_config_change
        self._start_time: Optional[datetime] = None
        self._build(bot_names)

    def _build(self, bot_names: List[str]) -> None:
        pad = {"padx": 8, "pady": 4}

        # ── header banner ────────────────────────────────────────────────
        ttk.Label(
            self,
            text="Bot Controls",
            font=("Helvetica", 12, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(6, 2), padx=8)

        # ── bot selector ─────────────────────────────────────────────────
        ttk.Label(self, text="Bot:").grid(row=1, column=0, sticky="e", **pad)
        self._bot_var = tk.StringVar(value=bot_names[0] if bot_names else "")
        self._bot_combo = ttk.Combobox(
            self,
            textvariable=self._bot_var,
            values=bot_names,
            state="readonly",
            width=22,
        )
        self._bot_combo.grid(row=1, column=1, sticky="w", **pad)
        self._bot_combo.bind("<<ComboboxSelected>>", self._handle_bot_change)

        # ── start / stop / reload ─────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=4)

        self._start_btn = ttk.Button(btn_frame, text="▶  Start", command=self._start, width=10)
        self._start_btn.pack(side="left", padx=6)

        self._stop_btn = ttk.Button(btn_frame, text="■  Stop", command=self._stop,
                                    state="disabled", width=10)
        self._stop_btn.pack(side="left", padx=6)

        self._reload_btn = ttk.Button(btn_frame, text="↺  Reload", command=self._reload, width=10)
        self._reload_btn.pack(side="left", padx=6)

        # ── runtime limit controls ───────────────────────────────────────
        runtime_frame = ttk.LabelFrame(self, text="Run Duration")
        runtime_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=(4, 2))
        ttk.Label(runtime_frame, text="Run for:").grid(row=0, column=0, padx=(8, 4), pady=8)
        self._duration_value_var = tk.IntVar(value=self._preset.run_duration_value)
        self._duration_value_spin = ttk.Spinbox(
            runtime_frame,
            from_=0,
            to=999,
            increment=1,
            textvariable=self._duration_value_var,
            width=8,
            command=self._save_runtime,
        )
        self._duration_value_spin.grid(row=0, column=1, padx=4, pady=8, sticky="w")
        self._duration_value_spin.bind("<FocusOut>", self._save_runtime)
        self._duration_value_spin.bind("<Return>", self._save_runtime)

        self._duration_unit_var = tk.StringVar(value=self._preset.run_duration_unit)
        self._duration_unit_combo = ttk.Combobox(
            runtime_frame,
            textvariable=self._duration_unit_var,
            values=["minutes", "hours"],
            state="readonly",
            width=10,
        )
        self._duration_unit_combo.grid(row=0, column=2, padx=4, pady=8, sticky="w")
        self._duration_unit_combo.bind("<<ComboboxSelected>>", self._save_runtime)

        ttk.Label(
            runtime_frame,
            text="Set to 0 to run until stopped manually.",
            foreground="gray",
        ).grid(row=1, column=0, columnspan=3, padx=8, pady=(0, 8), sticky="w")

        # ── status badge ─────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Idle")
        ttk.Label(
            self,
            textvariable=self._status_var,
            font=("Helvetica", 10, "bold"),
        ).grid(row=4, column=0, columnspan=2, pady=(0, 4))

        # ── runtime / loops ──────────────────────────────────────────────
        info_frame = ttk.Frame(self)
        info_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=8)

        ttk.Label(info_frame, text="Runtime:").pack(side="left")
        self._runtime_var = tk.StringVar(value="00:00:00")
        ttk.Label(info_frame, textvariable=self._runtime_var, width=10).pack(side="left")

        ttk.Label(info_frame, text="  LPM:").pack(side="left")
        self._lpm_var = tk.StringVar(value="0.0")
        ttk.Label(info_frame, textvariable=self._lpm_var, width=6).pack(side="left")

        # ── log panel ────────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self, text="Bot Log")
        log_frame.grid(row=6, column=0, columnspan=2, sticky="nsew", padx=8, pady=6)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(6, weight=1)

        self._log_text = tk.Text(
            log_frame,
            height=14,
            wrap="word",
            state="disabled",
            font=("Courier", 9),
        )
        vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._log_text.pack(side="left", fill="both", expand=True)

        # ── clear log button ─────────────────────────────────────────────
        ttk.Button(self, text="Clear Log", command=self._clear_log).grid(
            row=7, column=0, columnspan=2, pady=(0, 6)
        )

        ttk.Label(self, text="Press ESC to halt at any time.",
                  foreground="gray").grid(row=8, column=0, columnspan=2)

    def _start(self) -> None:
        self._save_runtime()
        self._start_time = datetime.now()
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._bot_combo.configure(state="disabled")
        self._on_start(self._bot_var.get())

    def _stop(self) -> None:
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._bot_combo.configure(state="readonly")
        self._on_stop()

    def _reload(self) -> None:
        if self._on_reload:
            self._on_reload()

    def _handle_bot_change(self, event=None) -> None:
        self._save_runtime()
        if self._on_bot_change:
            self._on_bot_change(self._bot_var.get())

    def _clear_log(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    def append_log(self, msg: str) -> None:
        self._log_text.configure(state="normal")
        self._log_text.insert("end", msg + "\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def update_stats(self, loops: int) -> None:
        if self._start_time:
            elapsed = datetime.now() - self._start_time
            secs = int(elapsed.total_seconds())
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            self._runtime_var.set(f"{h:02d}:{m:02d}:{s:02d}")
            
            minutes = elapsed.total_seconds() / 60 or 1
            self._lpm_var.set(f"{loops / minutes:.1f}")

    def set_bots(self, names: List[str]) -> None:
        self._bot_combo["values"] = names
        if names and not self._bot_var.get():
            self._bot_var.set(names[0])

    def set_selected_bot(self, name: str) -> None:
        self._bot_var.set(name)

    def refresh_preset(self, preset: BotConfig) -> None:
        self._preset = preset
        self._duration_value_var.set(preset.run_duration_value)
        self._duration_unit_var.set(preset.run_duration_unit)

    def force_stop_ui(self) -> None:
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._bot_combo.configure(state="readonly")
        self._status_var.set("Halted (ESC)")

    def _save_runtime(self, event=None) -> None:
        try:
            duration_value = int(self._duration_value_var.get())
        except (ValueError, tk.TclError):
            return

        duration_unit = self._duration_unit_var.get()
        if duration_unit not in {"minutes", "hours"}:
            return

        self._preset.run_duration_value = max(0, duration_value)
        self._preset.run_duration_unit = duration_unit
        if self._on_config_change:
            self._on_config_change()
