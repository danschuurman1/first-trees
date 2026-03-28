# tests/test_scheduler.py
from datetime import datetime
from config import DowntimeWindow
from core.scheduler import DowntimeScheduler

def test_in_window_returns_true():
    window = DowntimeWindow(start_hhmm="22:00", end_hhmm="23:00", days=list(range(7)), variance_minutes=0)
    sched = DowntimeScheduler([window])
    dt = datetime(2026, 3, 28, 22, 30)
    assert sched.is_break_time(dt) is True

def test_outside_window_returns_false():
    window = DowntimeWindow(start_hhmm="22:00", end_hhmm="23:00", days=list(range(7)), variance_minutes=0)
    sched = DowntimeScheduler([window])
    dt = datetime(2026, 3, 28, 10, 0)
    assert sched.is_break_time(dt) is False

def test_disabled_scheduler_never_breaks():
    window = DowntimeWindow(start_hhmm="22:00", end_hhmm="23:00", days=list(range(7)), variance_minutes=0)
    sched = DowntimeScheduler([window], enabled=False)
    dt = datetime(2026, 3, 28, 22, 30)
    assert sched.is_break_time(dt) is False

def test_wrong_day_returns_false():
    # Window only on Monday (0)
    window = DowntimeWindow(start_hhmm="22:00", end_hhmm="23:00", days=[0], variance_minutes=0)
    sched = DowntimeScheduler([window])
    # 2026-03-28 is a Saturday (5)
    dt = datetime(2026, 3, 28, 22, 30)
    assert sched.is_break_time(dt) is False

def test_next_break_end_returns_hhmm():
    window = DowntimeWindow(start_hhmm="22:00", end_hhmm="23:30", days=list(range(7)), variance_minutes=0)
    sched = DowntimeScheduler([window])
    dt = datetime(2026, 3, 28, 22, 30)
    result = sched.next_break_end(dt)
    assert result == "23:30"
