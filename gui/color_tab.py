# gui/color_tab.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, colorchooser
from typing import Callable
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
            ttk.Checkbutton(self, text="Enabled", variable=self._enabled_var,
                            command=self._commit).grid(row=row, column=0, columnspan=4,
                                                       sticky="w", padx=4)
            row += 1
        else:
            self._enabled_var = None

        self._swatch = tk.Label(self, width=4, height=2, relief="solid")
        self._swatch.grid(row=row, column=0, padx=4, pady=4)

        ttk.Button(self, text="Pick", command=self._pick_color).grid(row=row, column=1, padx=2)

        # Hex input field — paste #FF0000 style codes directly from RuneScape object markers
        ttk.Label(self, text="Hex:").grid(row=row, column=2, sticky="e", padx=2)
        self._hex_var = tk.StringVar(value=_rgb_to_hex(self._profile.r, self._profile.g, self._profile.b))
        self._hex_entry = ttk.Entry(self, textvariable=self._hex_var, width=8)
        self._hex_entry.grid(row=row, column=3, padx=2)
        self._hex_entry.bind("<Return>", lambda _: self._apply_hex())
        self._hex_entry.bind("<FocusOut>", lambda _: self._apply_hex())

        for i, (ch, attr) in enumerate([("R", "r"), ("G", "g"), ("B", "b")]):
            ttk.Label(self, text=ch).grid(row=row + 1, column=i, sticky="e", padx=2)
            var = tk.IntVar(value=getattr(self._profile, attr))
            setattr(self, f"_{attr}_var", var)
            sb = ttk.Spinbox(self, from_=0, to=255, textvariable=var, width=5,
                             command=self._commit)
            sb.grid(row=row + 2, column=i, padx=2)
            var.trace_add("write", lambda *_: self._commit())

        ttk.Label(self, text="Tol:").grid(row=row + 1, column=3, padx=2)
        self._tol_var = tk.IntVar(value=self._profile.tolerance)
        ttk.Scale(self, from_=0, to=50, variable=self._tol_var, orient="horizontal",
                  length=80, command=lambda _: self._commit()).grid(row=row + 2, column=3, padx=2)

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
        try:
            self._profile.r = int(self._r_var.get())
            self._profile.g = int(self._g_var.get())
            self._profile.b = int(self._b_var.get())
            self._profile.tolerance = int(self._tol_var.get())
            if self._enabled_var:
                self._profile.enabled = self._enabled_var.get()
        except tk.TclError:
            return
        self._refresh_swatch()
        self._on_change()

    def _refresh_swatch(self) -> None:
        hex_val = _rgb_to_hex(self._profile.r, self._profile.g, self._profile.b)
        self._swatch.configure(bg=hex_val)
        if not getattr(self, "_updating_hex", False):
            try:
                if self._hex_entry.focus_get() != self._hex_entry:
                    self._hex_var.set(hex_val)
            except Exception:
                self._hex_var.set(hex_val)


class ColorTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, config: BotConfig,
                 on_change: Callable[[], None]) -> None:
        super().__init__(parent)
        self._cfg = config
        self._on_change = on_change
        self._build()

    def _build(self) -> None:
        # Scrollable canvas wrapper
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        # Resize inner frame to canvas width when canvas resizes
        def _on_canvas_resize(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_resize)

        # Update scroll region when inner frame changes size
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")
        ))

        # Mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Build all widgets inside inner frame
        pad = {"padx": 6, "pady": 4}

        ttk.Label(inner, text="Tree Color (Cyan)", font=("Helvetica", 10, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(8, 2))

        ColorSlot(inner, "Tree Color (Primary)", self._cfg.tree_color,
                  self._on_change).grid(row=1, column=0, columnspan=2, sticky="nw", **pad)

        ttk.Separator(inner, orient="horizontal").grid(row=2, column=0, columnspan=2,
                                                        sticky="ew", pady=6)
        ttk.Label(inner, text="Stump Colors", font=("Helvetica", 10, "bold")).grid(
            row=3, column=0, columnspan=2, pady=(2, 2))
        ttk.Label(inner, text="Set to depleted stump colors. Enable to use stump detection.",
                  foreground="gray").grid(row=4, column=0, columnspan=2, pady=(0, 2))

        ColorSlot(inner, "Stump Color (tree-cut signal)", self._cfg.stump_color,
                  self._on_change, enable_toggle=True).grid(row=5, column=0, columnspan=2,
                                                             sticky="nw", **pad)

        ColorSlot(inner, "Stump Color 2 (tree-cut signal)", self._cfg.stump_color2,
                  self._on_change, enable_toggle=True).grid(row=6, column=0, columnspan=2,
                                                             sticky="nw", **pad)

        ttk.Separator(inner, orient="horizontal").grid(row=7, column=0, columnspan=2,
                                                        sticky="ew", pady=6)
        ttk.Label(inner, text="Override Color", font=("Helvetica", 10, "bold")).grid(
            row=8, column=0, columnspan=2, pady=(2, 2))

        ColorSlot(inner, "Color 2 (Override — checked first)", self._cfg.color2,
                  self._on_change, enable_toggle=True).grid(row=9, column=0, columnspan=2,
                                                             sticky="nw", **pad)

        ttk.Separator(inner, orient="horizontal").grid(row=10, column=0, columnspan=2,
                                                        sticky="ew", pady=6)

        timing = ttk.LabelFrame(inner, text="Search Timing")
        timing.grid(row=11, column=0, columnspan=2, padx=6, pady=8, sticky="ew")
        ttk.Label(timing, text="Min delay (s):").grid(row=0, column=0, padx=4, pady=4)
        self._min_var = tk.DoubleVar(value=self._cfg.min_delay)
        ttk.Spinbox(timing, from_=0.1, to=5.0, increment=0.1, textvariable=self._min_var,
                    width=6, command=self._save_timing).grid(row=0, column=1, padx=4)
        ttk.Label(timing, text="Max delay (s):").grid(row=0, column=2, padx=4)
        self._max_var = tk.DoubleVar(value=self._cfg.max_delay)
        ttk.Spinbox(timing, from_=0.1, to=5.0, increment=0.1, textvariable=self._max_var,
                    width=6, command=self._save_timing).grid(row=0, column=3, padx=4)
        ttk.Label(timing, text="Bot waits random.uniform(min, max) seconds between scan cycles.",
                  foreground="gray").grid(row=1, column=0, columnspan=4, padx=4, pady=2)

    def _save_timing(self) -> None:
        try:
            self._cfg.min_delay = float(self._min_var.get())
            self._cfg.max_delay = float(self._max_var.get())
        except (ValueError, tk.TclError):
            return
        self._on_change()
