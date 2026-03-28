# core/keyboard.py
from __future__ import annotations
import random
import time

from pynput.keyboard import Key, Controller as KeyCtrl


class KeyboardController:
    """Arrow-key camera rotation for re-scan.

    ESC handling is done via tkinter's root.bind("<Escape>") on the main thread.
    pynput's Listener is intentionally omitted: on macOS 26 it calls
    TSMGetInputSourceProperty from a background thread which triggers
    dispatch_assert_queue_fail and kills the process.
    """

    def __init__(self) -> None:
        self._key_ctrl = KeyCtrl()

    def rotate_camera(self) -> None:
        """Press a random arrow key for a random duration to rotate the camera."""
        arrow = random.choice([Key.left, Key.right])
        duration = random.uniform(0.3, 0.8)
        self._key_ctrl.press(arrow)
        time.sleep(duration)
        self._key_ctrl.release(arrow)
        time.sleep(random.uniform(0.1, 0.4))
