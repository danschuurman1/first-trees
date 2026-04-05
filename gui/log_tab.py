# gui/log_tab.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog
from datetime import datetime


class LogTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        btn_frame = ttk.Frame(self)
        btn_frame.pack(side="bottom", fill="x")
        ttk.Button(btn_frame, text="Clear", command=self.clear).pack(side="left", padx=4, pady=4)
        ttk.Button(btn_frame, text="Copy", command=self._copy).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Export .txt", command=self._export).pack(side="left", padx=4)

        self._text = tk.Text(self, state="disabled", wrap="word", bg="#1e1e1e", fg="#cccccc",
                              font=("Courier", 10))
        scroll = ttk.Scrollbar(self, command=self._text.yview)
        self._text.configure(yscrollcommand=scroll.set)
        self._text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def append(self, msg: str) -> None:
        self._text.configure(state="normal")
        self._text.insert("end", msg + "\n")
        self._text.see("end")
        self._text.configure(state="disabled")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")

    def _copy(self) -> None:
        content = self._text.get("1.0", "end-1c")
        self._text.clipboard_clear()
        self._text.clipboard_append(content)

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            initialfile=f"osrs_bot_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        )
        if path:
            content = self._text.get("1.0", "end")
            with open(path, "w") as f:
                f.write(content)
