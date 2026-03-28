# bots/base_bot.py
from __future__ import annotations
import threading
import queue
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional


class Bot(ABC):
    """Abstract base class for all OSRS bots."""

    name: str = "Unnamed"

    def __init__(self) -> None:
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.loops: int = 0
        self.start_time: Optional[datetime] = None

    def start(self) -> None:
        if self._running.is_set():
            return
        self._running.set()
        self.start_time = datetime.now()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running.clear()

    def is_running(self) -> bool:
        return self._running.is_set()

    def _run(self) -> None:
        self.log(f"Bot '{self.name}' started.")
        while self._running.is_set():
            try:
                self.run_loop()
                self.loops += 1
            except Exception as exc:
                self.log(f"ERROR in run_loop: {exc}")
                self._running.clear()
        self.log(f"Bot '{self.name}' stopped.")

    @abstractmethod
    def run_loop(self) -> None:
        """Single iteration of the bot's decision tree. Called repeatedly."""

    def log(self, msg: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {msg}")

    def random_sleep(self, min_s: float = 0.4, max_s: float = 1.2) -> None:
        """Sleep a random duration. Use this instead of time.sleep() in subclasses."""
        time.sleep(random.uniform(min_s, max_s))

    def micro_pause(self) -> None:
        """Tiny unpredictable gap injected between every distinct action."""
        time.sleep(random.uniform(0.05, 0.25))

    @classmethod
    def register(cls) -> None:
        from bots.registry import BOT_REGISTRY
        BOT_REGISTRY[cls.name] = cls
