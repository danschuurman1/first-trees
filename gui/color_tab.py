# gui/color_tab.py
from __future__ import annotations
import sys
import tkinter as tk
from tkinter import ttk, colorchooser
from typing import Callable, Dict
from config import BotConfig, ColorProfile


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


class ColorSlot(ttk.LabelFrame):
    """A reusable widget block for one ColorProfile."""

    def __init__(self, parent, label: str, profile: ColorProfile,
                 on_change: Callable[[], None], enable_toggle: bool = False) -> None:
        super().__init__(parent, text=label)
        self._profile = profile
        self._on_change = on_change
        self._updating_hex = False
        self._build(enable_toggle)
        self._refresh_swatch()

    def _build(self, enable_toggle: bool) -> None:
        row = 0
        if enable_toggle:
            self._enabled_var = tk.BooleanVar(value=self._profile.enabled)
            self._check = ttk.Checkbutton(self, text="Enabled", variable=self._enabled_var,
                            command=self._commit)
            self._check.grid(row=row, column=0, columnspan=4, sticky="w", padx=4)
            row += 1
        else:
            self._enabled_var = None

        self._swatch = tk.Label(self, width=4, height=2, relief="solid")
        self._swatch.grid(row=row, column=0, padx=4, pady=4)

        ttk.Button(self, text="Pick", command=self._pick_color).grid(row=row, column=1, padx=2)

        # Hex input field
        ttk.Label(self, text="Hex:").grid(row=row, column=2, sticky="e", padx=2)
        self._hex_var = tk.StringVar(value=_rgb_to_hex(self._profile.r, self._profile.g, self._profile.b))
        self._hex_entry = ttk.Entry(self, textvariable=self._hex_var, width=8)
        self._hex_entry.grid(row=row, column=3, padx=2)
        self._hex_entry.bind("<Return>", lambda _: self._apply_hex())
        self._hex_entry.bind("<FocusOut>", lambda _: self._apply_hex())

        # RGB Spinboxes
        self._r_var = tk.IntVar(value=self._profile.r)
        self._g_var = tk.IntVar(value=self._profile.g)
        self._b_var = tk.IntVar(value=self._profile.b)

        for i, (ch, var) in enumerate([("R", self._r_var), ("G", self._g_var), ("B", self._b_var)]):
            ttk.Label(self, text=ch).grid(row=row + 1, column=i, sticky="e", padx=2)
            sb = ttk.Spinbox(self, from_=0, to=255, textvariable=var, width=5,
                             command=self._commit)
            sb.grid(row=row + 2, column=i, padx=2)
            var.trace_add("write", lambda *_: self._commit())

        ttk.Label(self, text="Tol:").grid(row=row + 1, column=3, padx=2)
        self._tol_var = tk.IntVar(value=self._profile.tolerance)
        self._tol_scale = ttk.Scale(self, from_=0, to=50, variable=self._tol_var, orient="horizontal",
                  length=80, command=lambda _: self._commit())
        self._tol_scale.grid(row=row + 2, column=3, padx=2)

    def update_profile(self, new_profile: ColorProfile) -> None:
        """Update the UI to reflect a new profile instance."""
        self._profile = new_profile
        self._updating_hex = True
        self._r_var.set(new_profile.r)
        self._g_var.set(new_profile.g)
        self._b_var.set(new_profile.b)
        self._tol_var.set(new_profile.tolerance)
        if self._enabled_var:
            self._enabled_var.set(new_profile.enabled)
        self._updating_hex = False
        self._refresh_swatch()

    def _apply_hex(self) -> None:
        raw = self._hex_var.get().strip().lstrip("#")
        if len(raw) != 6:
            return
        try:
            r = int(raw[0:2], 16)
            g = int(raw[2:4], 16)
            b = int(raw[4:6], 16)
        except ValueError:
            return
        self._updating_hex = True
        self._r_var.set(r)
        self._g_var.set(g)
        self._b_var.set(b)
        self._updating_hex = False
        self._commit()

    def _pick_color(self) -> None:
        init = _rgb_to_hex(self._profile.r, self._profile.g, self._profile.b)
        result = colorchooser.askcolor(color=init, title="Pick color")
        if result and result[0]:
            r, g, b = (int(x) for x in result[0])
            self._r_var.set(r); self._g_var.set(g); self._b_var.set(b)
            self._commit()

    def _commit(self) -> None:
        if getattr(self, "_updating_hex", False):
            return
        try:
            self._profile.r = int(self._r_var.get())
            self._profile.g = int(self._g_var.get())
            self._profile.b = int(self._b_var.get())
            self._profile.tolerance = int(self._tol_var.get())
            if self._enabled_var:
                self._profile.enabled = self._enabled_var.get()
        except (tk.TclError, ValueError):
            return
        self._refresh_swatch()
        self._on_change()

    def _refresh_swatch(self) -> None:
        hex_val = _rgb_to_hex(self._profile.r, self._profile.g, self._profile.b)
        self._swatch.configure(bg=hex_val)
        if not getattr(self, "_updating_hex", False):
            try:
                if self.focus_get() != self._hex_entry:
                    self._hex_var.set(hex_val)
            except Exception:
                self._hex_var.set(hex_val)


class ColorTab(ttk.Frame):
    """
    Redesigned ColorTab using a Sub-Notebook (Tabs) to eliminate scrolling.
    Settings are grouped logically to fit within a small fixed-size UI.
    """
    def __init__(self, parent: ttk.Notebook, preset: BotConfig,
                 on_change: Callable[[], None]) -> None:
        super().__init__(parent)
        self._preset = preset
        self._on_change = on_change
        self._slots: Dict[str, ColorSlot] = {}
        self._build()

    def _build(self) -> None:
        # Create a sub-notebook inside the Color Tab
        self._sub_nb = ttk.Notebook(self)
        self._sub_nb.pack(fill="both", expand=True, padx=2, pady=2)

        # 1. Primary Colors Tab
        f_primary = ttk.Frame(self._sub_nb)
        self._sub_nb.add(f_primary, text="Main")
        self._build_primary(f_primary)

        # 2. Signals Tab (Stumps, XP)
        f_signals = ttk.Frame(self._sub_nb)
        self._sub_nb.add(f_signals, text="Signals")
        self._build_signals(f_signals)

        # 3. Inventory & UI Tab
        f_inv = ttk.Frame(self._sub_nb)
        self._sub_nb.add(f_inv, text="Inv/UI")
        self._build_inventory(f_inv)

        # 4. World & Navigation Tab
        f_world = ttk.Frame(self._sub_nb)
        self._sub_nb.add(f_world, text="World")
        self._build_world(f_world)

        # 5. Timing Tab
        f_timing = ttk.Frame(self._sub_nb)
        self._sub_nb.add(f_timing, text="Timing")
        self._build_timing(f_timing)

        # 6. Motherlode Mine Tab
        f_mlm = ttk.Frame(self._sub_nb)
        self._sub_nb.add(f_mlm, text="MLM")
        self._build_mlm(f_mlm)

    def _build_primary(self, parent: ttk.Frame) -> None:
        pad = {"padx": 6, "pady": 4}
        self._slots["tree_color"] = ColorSlot(parent, "Tree Color (Primary)", self._preset.tree_color,
                                              self._on_change)
        self._slots["tree_color"].pack(fill="x", **pad)
        
        self._slots["color2"] = ColorSlot(parent, "Override Color (Color 2)", self._preset.color2,
                                          self._on_change, enable_toggle=True)
        self._slots["color2"].pack(fill="x", **pad)

    def _build_signals(self, parent: ttk.Frame) -> None:
        pad = {"padx": 6, "pady": 4}
        self._slots["stump_color"] = ColorSlot(parent, "Stump Color 1", self._preset.stump_color,
                                               self._on_change, enable_toggle=True)
        self._slots["stump_color"].pack(fill="x", **pad)
        
        self._slots["stump_color2"] = ColorSlot(parent, "Stump Color 2", self._preset.stump_color2,
                                                self._on_change, enable_toggle=True)
        self._slots["stump_color2"].pack(fill="x", **pad)

        self._slots["xp_drop_color"] = ColorSlot(parent, "XP Drop Color (Green)", self._preset.xp_drop_color,
                                                 self._on_change, enable_toggle=True)
        self._slots["xp_drop_color"].pack(fill="x", **pad)

    def _build_inventory(self, parent: ttk.Frame) -> None:
        pad = {"padx": 6, "pady": 4}
        self._slots["log_color"] = ColorSlot(parent, "Log Color (Inventory)", self._preset.log_color,
                                             self._on_change, enable_toggle=True)
        self._slots["log_color"].pack(fill="x", **pad)
        
        self._slots["inv_count_color"] = ColorSlot(parent, "Inventory Count Text", self._preset.inv_count_color,
                                                   self._on_change, enable_toggle=True)
        self._slots["inv_count_color"].pack(fill="x", **pad)

    def _build_world(self, parent: ttk.Frame) -> None:
        pad = {"padx": 6, "pady": 4}
        self._slots["bank_booth_color"] = ColorSlot(parent, "Bank Booth (Purple)", self._preset.bank_booth_color,
                                                    self._on_change, enable_toggle=True)
        self._slots["bank_booth_color"].pack(fill="x", **pad)
        
        self._slots["grid_color"] = ColorSlot(parent, "Grid Color (Anchor)", self._preset.grid_color,
                                              self._on_change, enable_toggle=True)
        self._slots["grid_color"].pack(fill="x", **pad)

    def _build_timing(self, parent: ttk.Frame) -> None:
        pad = {"padx": 10, "pady": 10}
        timing = ttk.LabelFrame(parent, text="Scan Cycle Timing")
        timing.pack(fill="x", **pad)
        
        tk.Label(timing, text="Min delay (s):").grid(row=0, column=0, padx=4, pady=8)
        self._min_var = tk.DoubleVar(value=self._preset.min_delay)
        self._min_spin = ttk.Spinbox(timing, from_=0.1, to=5.0, increment=0.1, textvariable=self._min_var,
                    width=6, command=self._save_timing)
        self._min_spin.grid(row=0, column=1, padx=4)
        
        tk.Label(timing, text="Max delay (s):").grid(row=0, column=2, padx=4)
        self._max_var = tk.DoubleVar(value=self._preset.max_delay)
        self._max_spin = ttk.Spinbox(timing, from_=0.1, to=5.0, increment=0.1, textvariable=self._max_var,
                    width=6, command=self._save_timing)
        self._max_spin.grid(row=0, column=3, padx=4)
        
        tk.Label(timing, text="Bot waits random(min, max) between scans.", 
                 foreground="gray", font=("Helvetica", 8)).grid(row=1, column=0, columnspan=4, pady=(0, 8))

    def _build_mlm(self, parent: ttk.Frame) -> None:
        # Create a scrollable frame for MLM since there are many slots
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        pad = {"padx": 6, "pady": 4}
        mlm_slots = [
            ("bank_chest_color", "Bank Chest"),
            ("ore_active_color", "Active Ore"),
            ("ore_depleted_color", "Depleted Ore"),
            ("hopper_color", "Hopper"),
            ("ladder_ascend_color", "Ladder Ascend"),
            ("ladder_descend_color", "Ladder Descend"),
            ("sack_color", "Sack"),
            ("inv_ore_color", "Inventory Ore"),
        ]
        
        for key, label in mlm_slots:
            self._slots[key] = ColorSlot(scrollable_frame, label, getattr(self._preset, key),
                                        self._on_change, enable_toggle=True)
            self._slots[key].pack(fill="x", **pad)

    def refresh_preset(self, new_preset: BotConfig) -> None:
        """Update all widgets to reflect a new preset."""
        self._preset = new_preset
        for key, slot in self._slots.items():
            profile = getattr(new_preset, key)
            slot.update_profile(profile)
        
        self._min_var.set(new_preset.min_delay)
        self._max_var.set(new_preset.max_delay)

    def _save_timing(self) -> None:
        try:
            self._preset.min_delay = float(self._min_var.get())
            self._preset.max_delay = float(self._max_var.get())
        except (ValueError, tk.TclError):
            return
        self._on_change()
