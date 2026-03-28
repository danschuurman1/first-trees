# core/scheduler.py
from __future__ import annotations
import random
from datetime import datetime, timedelta
from typing import List

from config import DowntimeWindow


class DowntimeScheduler:
    """Evaluates whether the current time falls within a configured downtime window."""

    def __init__(self, windows: List[DowntimeWindow], enabled: bool = True) -> None:
        self.windows = windows
        self.enabled = enabled

    def is_break_time(self, now: datetime = None) -> bool:
        if not self.enabled:
            return False
        if now is None:
            now = datetime.now()
        weekday = now.weekday()  # 0=Mon, 6=Sun
        for w in self.windows:
            if weekday not in w.days:
                continue
            variance = random.randint(-w.variance_minutes, w.variance_minutes)
            start_h, start_m = map(int, w.start_hhmm.split(":"))
            end_h, end_m = map(int, w.end_hhmm.split(":"))
            start_dt = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
            end_dt = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
            start_dt += timedelta(minutes=variance)
            end_dt += timedelta(minutes=variance)
            if start_dt <= now <= end_dt:
                return True
        return False

    def next_break_end(self, now: datetime = None) -> str:
        """Return 'HH:MM' of the end of the current active window (with variance), or empty string."""
        if now is None:
            now = datetime.now()
        for w in self.windows:
            if now.weekday() not in w.days:
                continue
            variance = random.randint(-w.variance_minutes, w.variance_minutes)
            end_h, end_m = map(int, w.end_hhmm.split(":"))
            end_dt = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
            end_dt += timedelta(minutes=variance)
            return f"{end_dt.hour:02d}:{end_dt.minute:02d}"
        return ""
