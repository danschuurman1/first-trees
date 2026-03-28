# core/keyboard.py
from __future__ import annotations
import random
import time
import threading
from typing import Callable, Optional

from pynput.keyboard import Key, Controller as KeyCtrl, Listener


class KeyboardController:
    """ESC kill switch + arrow-key camera rotation for re-scan."""

    def __init__(self, on_esc: Callable[[], None]) -> None:
        self._key_ctrl = KeyCtrl()
        self._on_esc = on_esc
        self._listener: Optional[Listener] = None

    def start_listener(self) -> None:
        def on_press(key):
            if key == Key.esc:
                self._on_esc()
        self._listener = Listener(on_press=on_press, daemon=True)
        self._listener.start()

    def stop_listener(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def rotate_camera(self, attempts: int = 1) -> None:
        """Press a random arrow key for a random duration to rotate the camera."""
        arrow = random.choice([Key.left, Key.right])
        duration = random.uniform(0.3, 0.8)
        self._key_ctrl.press(arrow)
        time.sleep(duration)
        self._key_ctrl.release(arrow)
        time.sleep(random.uniform(0.1, 0.4))
