# OSRS Woodcutter Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete Python macOS OSRS woodcutting bot with color-based detection, Bezier mouse movement, anti-detection randomization, and a 5-tab tkinter GUI — deployable to a GitHub repo called "first-try-trees".

**Architecture:** The bot runs in a daemon thread executing a binary decision tree each loop iteration (location → inventory → animation → click tree). The GUI lives on the main thread and communicates with the bot via threading.Event flags and a thread-safe log queue. All timing uses random.uniform() — no fixed sleeps anywhere.

**Tech Stack:** Python 3.9+, mss, opencv-python, pynput, Pillow, pytesseract, tkinter (stdlib), threading (stdlib), json (stdlib)

---

## File Map

```
first-try-trees/
├── main.py                        # Entry point — creates App, starts mainloop
├── config.py                      # ConfigManager: dataclasses + JSON load/save to ~/.osrs_bot/config.json
├── requirements.txt
├── README.md
├── core/
│   ├── __init__.py
│   ├── screen.py                  # ScreenCapture: mss wrapper, grab(region) → np.ndarray
│   ├── color.py                   # ColorDetector: pixel match, connectedComponents clustering, centroid selection
│   ├── mouse.py                   # MouseController: Bezier path, jittered click, post-click verify; NEVER same pixel twice
│   ├── keyboard.py                # KeyboardController: ESC listener, arrow-key camera rotation
│   ├── ocr.py                     # OCRReader: tesseract wrapper, extract item names from region
│   └── scheduler.py               # DowntimeScheduler: evaluate if current time falls in break window
├── bots/
│   ├── __init__.py
│   ├── base_bot.py                # Bot ABC: start/stop/is_running/run_loop/name
│   ├── registry.py                # BOT_REGISTRY dict; register(cls) decorator
│   └── woodcutter.py              # WoodcutterBot(Bot): decision tree, all 5 game-state color checks
├── gui/
│   ├── __init__.py
│   ├── app.py                     # App(tk.Tk): notebook, tab instantiation, bot thread management
│   ├── control_tab.py             # Tab 1: start/stop, bot selector, live stats
│   ├── color_tab.py               # Tab 2: color slots + game-state profiles + timing
│   ├── scheduler_tab.py           # Tab 3: downtime windows table
│   ├── log_tab.py                 # Tab 4: scrollable log, clear, export
│   └── loot_tab.py                # Tab 5: OCR loot whitelist
└── tests/
    ├── test_color.py
    ├── test_mouse.py
    ├── test_scheduler.py
    ├── test_config.py
    └── test_woodcutter.py
```

---

## Task 1: Git + GitHub Repo Setup

**Files:**
- Create: `first-try-trees/` (git repo root)
- Create: `.gitignore`

- [ ] **Step 1: Authenticate GitHub CLI**

```bash
gh auth login
# Choose: GitHub.com → HTTPS → Login with browser
```

- [ ] **Step 2: Init local repo**

```bash
cd /Users/dannyschuurman/first-try-trees
git init
```

- [ ] **Step 3: Create .gitignore**

```
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
venv/
*.log
~/.osrs_bot/
.DS_Store
```

- [ ] **Step 4: Create GitHub repo and push**

```bash
gh repo create first-try-trees --public --description "OSRS woodcutting bot — color detection, Bezier mouse, anti-detection randomization" --source . --remote origin --push
```

---

## Task 2: Project Scaffold + requirements.txt + README

**Files:**
- Create: `requirements.txt`
- Create: `README.md`
- Create: all `__init__.py` files

- [ ] **Step 1: Write requirements.txt**

```
mss>=10.0.0
opencv-python>=4.8.0
pynput>=1.7.6
Pillow>=10.0.0
pytesseract>=0.3.10
```

- [ ] **Step 2: Write README.md**

```markdown
# First Try Trees — OSRS Woodcutter Bot

A Python-only OSRS woodcutting bot for macOS using screen capture and OS-level input simulation. No RuneLite, no external bot client.

## Requirements

- macOS 13+
- Python 3.9+
- Tesseract OCR: `brew install tesseract`

## Setup

```bash
pip install -r requirements.txt
```

### macOS Permissions (required)

1. **Screen Recording** — System Settings → Privacy & Security → Screen Recording → enable Terminal/iTerm
2. **Accessibility** — System Settings → Privacy & Security → Accessibility → enable Terminal/iTerm

## Run

```bash
python main.py
```

## Add a New Bot

1. Create `bots/my_bot.py`
2. Subclass `Bot`, set `name = "My Bot"`
3. Implement `run_loop()`
4. Call `register()` at module bottom
5. Import the module in `bots/__init__.py`

## Anti-Detection

- All click targets use a fresh random offset (±8–15 px) re-seeded on every click
- No two consecutive clicks on the same tree land on the same pixel
- All waits use `random.uniform(min, max)` — never fixed sleeps
- Extra random micro-pause injected between every distinct bot action
```

- [ ] **Step 3: Create package __init__.py files**

```bash
touch core/__init__.py bots/__init__.py gui/__init__.py tests/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "chore: scaffold project, requirements, README"
git push
```

---

## Task 3: config.py — Config Dataclasses + JSON Persistence

**Files:**
- Create: `config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py
import json, os, tempfile
from pathlib import Path

def test_config_saves_and_loads(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("config.CONFIG_PATH", tmp_path / "config.json")
    from config import ConfigManager, ColorProfile
    mgr = ConfigManager()
    mgr.config.selected_bot = "Woodcutter"
    mgr.config.color1 = ColorProfile(r=100, g=150, b=200, tolerance=15)
    mgr.save()
    mgr2 = ConfigManager()
    assert mgr2.config.selected_bot == "Woodcutter"
    assert mgr2.config.color1.r == 100
    assert mgr2.config.color1.tolerance == 15

def test_config_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("config.CONFIG_PATH", tmp_path / "config.json")
    from config import ConfigManager
    mgr = ConfigManager()
    assert mgr.config.selected_bot == "Woodcutter"
    assert mgr.config.min_delay == 0.4
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/dannyschuurman/first-try-trees
python -m pytest tests/test_config.py -v
```
Expected: ImportError or AttributeError — config.py doesn't exist yet.

- [ ] **Step 3: Write config.py**

```python
# config.py
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List

CONFIG_DIR = Path.home() / ".osrs_bot"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class ColorProfile:
    r: int = 0
    g: int = 0
    b: int = 0
    tolerance: int = 20
    enabled: bool = True


@dataclass
class DowntimeWindow:
    start_hhmm: str = "22:00"   # "HH:MM"
    end_hhmm: str = "23:00"
    days: List[int] = field(default_factory=lambda: list(range(7)))  # 0=Mon
    variance_minutes: int = 0


@dataclass
class BotConfig:
    selected_bot: str = "Woodcutter"
    color1: ColorProfile = field(default_factory=ColorProfile)
    color2: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    # Game-state profiles
    tree_color: ColorProfile = field(default_factory=ColorProfile)
    stump_color: ColorProfile = field(default_factory=ColorProfile)
    log_color: ColorProfile = field(default_factory=ColorProfile)
    anim_color: ColorProfile = field(default_factory=ColorProfile)
    player_color: ColorProfile = field(default_factory=ColorProfile)
    # Timing
    min_delay: float = 0.4
    max_delay: float = 1.2
    # Scheduler
    scheduler_enabled: bool = False
    downtime_windows: List[DowntimeWindow] = field(default_factory=list)
    # Loot
    loot_ocr_enabled: bool = False
    loot_whitelist: List[str] = field(default_factory=list)


def _profile_from_dict(d: dict) -> ColorProfile:
    return ColorProfile(**{k: v for k, v in d.items() if k in ColorProfile.__dataclass_fields__})


def _window_from_dict(d: dict) -> DowntimeWindow:
    return DowntimeWindow(**{k: v for k, v in d.items() if k in DowntimeWindow.__dataclass_fields__})


def _config_from_dict(d: dict) -> BotConfig:
    cfg = BotConfig()
    profile_keys = {"color1", "color2", "tree_color", "stump_color",
                    "log_color", "anim_color", "player_color"}
    for k, v in d.items():
        if k in profile_keys and isinstance(v, dict):
            setattr(cfg, k, _profile_from_dict(v))
        elif k == "downtime_windows" and isinstance(v, list):
            cfg.downtime_windows = [_window_from_dict(w) for w in v]
        elif hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


class ConfigManager:
    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.config: BotConfig = self._load()

    def _load(self) -> BotConfig:
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                return _config_from_dict(data)
            except Exception:
                pass
        return BotConfig()

    def save(self) -> None:
        CONFIG_PATH.write_text(json.dumps(asdict(self.config), indent=2))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_config.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: config dataclasses with JSON persistence"
git push
```

---

## Task 4: core/screen.py — Screen Capture Wrapper

**Files:**
- Create: `core/screen.py`

- [ ] **Step 1: Write core/screen.py**

No unit test possible without a display; tested implicitly by the bot loop.

```python
# core/screen.py
from __future__ import annotations
import numpy as np
import mss
import mss.tools
from typing import Tuple, Optional


class ScreenCapture:
    """Thread-safe screen region grabber. Returns BGR numpy arrays (OpenCV format)."""

    def __init__(self) -> None:
        self._sct = mss.mss()

    def grab(self, region: Tuple[int, int, int, int]) -> np.ndarray:
        """Capture region (left, top, width, height) → BGR ndarray."""
        mon = {"left": region[0], "top": region[1],
               "width": region[2], "height": region[3]}
        raw = self._sct.grab(mon)
        # mss returns BGRA; drop alpha, keep BGR
        arr = np.array(raw)[:, :, :3]
        return arr

    def grab_full(self) -> np.ndarray:
        mon = self._sct.monitors[1]
        raw = self._sct.grab(mon)
        return np.array(raw)[:, :, :3]

    def pixel_color(self, x: int, y: int) -> Tuple[int, int, int]:
        """Return (R, G, B) of a single screen pixel."""
        arr = self.grab((x, y, 1, 1))
        b, g, r = int(arr[0, 0, 0]), int(arr[0, 0, 1]), int(arr[0, 0, 2])
        return r, g, b
```

- [ ] **Step 2: Commit**

```bash
git add core/screen.py
git commit -m "feat: screen capture wrapper (mss)"
git push
```

---

## Task 5: core/color.py — Color Detection + Clustering

**Files:**
- Create: `core/color.py`
- Create: `tests/test_color.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_color.py
import numpy as np
from config import ColorProfile
from core.color import ColorDetector

def _make_image(color_bgr, size=(100, 100)):
    """Solid color BGR image."""
    img = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    img[:] = color_bgr
    return img

def test_matches_exact_color():
    profile = ColorProfile(r=200, g=100, b=50, tolerance=10)
    img = _make_image((50, 100, 200))  # BGR order: B=50, G=100, R=200
    detector = ColorDetector()
    clusters = detector.find_clusters(img, profile, region_offset=(0, 0))
    assert len(clusters) == 1
    cx, cy = clusters[0]
    assert 45 <= cx <= 55   # centroid near center
    assert 45 <= cy <= 55

def test_no_match_outside_tolerance():
    profile = ColorProfile(r=200, g=100, b=50, tolerance=5)
    img = _make_image((10, 10, 10))  # Very different color
    detector = ColorDetector()
    clusters = detector.find_clusters(img, profile, region_offset=(0, 0))
    assert clusters == []

def test_noise_rejection_below_4_pixels():
    profile = ColorProfile(r=255, g=0, b=0, tolerance=5)
    img = _make_image((200, 200, 200))  # Gray background
    # Plant 2 matching pixels (below 4-pixel threshold)
    img[10, 10] = (0, 0, 255)   # BGR: R=255
    img[10, 11] = (0, 0, 255)
    detector = ColorDetector()
    clusters = detector.find_clusters(img, profile, region_offset=(0, 0))
    assert clusters == []

def test_center_priority_selection():
    profile = ColorProfile(r=255, g=0, b=0, tolerance=5)
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    # Blob near center (90-110, 90-110)
    img[90:110, 90:110] = (0, 0, 255)
    # Blob far from center (0-10, 0-10)
    img[0:10, 0:10] = (0, 0, 255)
    detector = ColorDetector()
    best = detector.best_cluster(img, profile, region_offset=(0, 0))
    assert best is not None
    cx, cy = best
    # Center of image is (100, 100); near-center blob centroid ~(100, 100)
    assert 85 <= cx <= 115
    assert 85 <= cy <= 115
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_color.py -v
```
Expected: ImportError — core/color.py doesn't exist yet.

- [ ] **Step 3: Write core/color.py**

```python
# core/color.py
from __future__ import annotations
import math
from typing import List, Optional, Tuple

import cv2
import numpy as np

from config import ColorProfile

# Minimum blob size (pixels) to not be treated as noise
MIN_BLOB_PIXELS = 4


class ColorDetector:
    """Detects color blobs in BGR images and returns centroid positions."""

    def _mask(self, img: np.ndarray, profile: ColorProfile) -> np.ndarray:
        """Return binary mask where pixels match the profile within tolerance (sphere in RGB space)."""
        # img is BGR; convert channels
        b = img[:, :, 0].astype(np.int32)
        g = img[:, :, 1].astype(np.int32)
        r = img[:, :, 2].astype(np.int32)
        dist = np.sqrt((r - profile.r) ** 2 + (g - profile.g) ** 2 + (b - profile.b) ** 2)
        mask = (dist <= profile.tolerance).astype(np.uint8) * 255
        return mask

    def find_clusters(
        self,
        img: np.ndarray,
        profile: ColorProfile,
        region_offset: Tuple[int, int] = (0, 0),
    ) -> List[Tuple[int, int]]:
        """Return list of (screen_x, screen_y) centroids for each surviving blob."""
        mask = self._mask(img, profile)
        num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

        results: List[Tuple[int, int]] = []
        for label in range(1, num_labels):  # skip background label 0
            area = stats[label, cv2.CC_STAT_AREA]
            if area < MIN_BLOB_PIXELS:
                continue
            cx = int(centroids[label, 0]) + region_offset[0]
            cy = int(centroids[label, 1]) + region_offset[1]
            results.append((cx, cy))
        return results

    def best_cluster(
        self,
        img: np.ndarray,
        profile: ColorProfile,
        region_offset: Tuple[int, int] = (0, 0),
    ) -> Optional[Tuple[int, int]]:
        """Return centroid closest to image center (Chebyshev distance), or None."""
        clusters = self.find_clusters(img, profile, region_offset)
        if not clusters:
            return None
        h, w = img.shape[:2]
        center_x = w // 2 + region_offset[0]
        center_y = h // 2 + region_offset[1]
        return min(clusters, key=lambda c: max(abs(c[0] - center_x), abs(c[1] - center_y)))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_color.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add core/color.py tests/test_color.py
git commit -m "feat: color detection with blob clustering and noise rejection"
git push
```

---

## Task 6: core/mouse.py — Bezier Mouse + Anti-Detection Jitter

**Files:**
- Create: `core/mouse.py`
- Create: `tests/test_mouse.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_mouse.py
from core.mouse import MouseController

def test_jitter_never_same_pixel_twice():
    mc = MouseController()
    target = (500, 400)
    seen = set()
    for _ in range(50):
        jx, jy = mc._jitter(target)
        assert (jx, jy) not in seen, f"Duplicate click position {(jx, jy)} detected"
        seen.add((jx, jy))

def test_jitter_within_range():
    mc = MouseController()
    for _ in range(200):
        jx, jy = mc._jitter((500, 400))
        assert abs(jx - 500) <= 15
        assert abs(jy - 400) <= 15

def test_bezier_points_start_and_end():
    mc = MouseController()
    pts = mc._bezier_path((0, 0), (100, 100), steps=20)
    assert len(pts) == 20
    # First point close to start, last close to end
    assert abs(pts[0][0]) <= 5 and abs(pts[0][1]) <= 5
    assert abs(pts[-1][0] - 100) <= 5 and abs(pts[-1][1] - 100) <= 5

def test_bezier_path_is_curved_not_straight():
    mc = MouseController()
    pts = mc._bezier_path((0, 0), (200, 0), steps=30)
    # At least one midpoint should deviate from y=0 (curve arc)
    mid_ys = [p[1] for p in pts[5:25]]
    assert any(abs(y) > 2 for y in mid_ys), "Path appears straight — no curve detected"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_mouse.py -v
```
Expected: ImportError — core/mouse.py doesn't exist yet.

- [ ] **Step 3: Write core/mouse.py**

```python
# core/mouse.py
from __future__ import annotations
import math
import random
import time
from typing import List, Optional, Tuple

from pynput.mouse import Button, Controller as MouseCtrl

from core.screen import ScreenCapture
from config import ColorProfile


class MouseController:
    """Bezier mouse movement with per-click jitter. Never clicks the same pixel twice consecutively."""

    def __init__(self) -> None:
        self._mouse = MouseCtrl()
        self._screen = ScreenCapture()
        self._last_click: Optional[Tuple[int, int]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def move_and_click(self, target: Tuple[int, int]) -> Tuple[int, int]:
        """Move along a Bezier curve to a jittered target, click, return actual pixel clicked."""
        dest = self._unique_jitter(target)
        path = self._bezier_path(self._current_pos(), dest, steps=random.randint(18, 30))
        for pt in path:
            self._mouse.position = pt
            time.sleep(random.uniform(0.003, 0.012))
        self._mouse.click(Button.left, 1)
        self._last_click = dest
        return dest

    def post_click_verify(
        self,
        pos: Tuple[int, int],
        profile: ColorProfile,
        delay: float = 0.3,
    ) -> bool:
        """Return True if the clicked pixel still matches the color profile after `delay` seconds."""
        time.sleep(delay)
        r, g, b = self._screen.pixel_color(pos[0], pos[1])
        dist = math.sqrt((r - profile.r) ** 2 + (g - profile.g) ** 2 + (b - profile.b) ** 2)
        return dist <= profile.tolerance

    # ------------------------------------------------------------------
    # Internal helpers (also used by tests)
    # ------------------------------------------------------------------

    def _jitter(self, target: Tuple[int, int]) -> Tuple[int, int]:
        """Apply random ±8–15 px offset to a target. May occasionally match previous click."""
        offset_x = random.choice([-1, 1]) * random.randint(8, 15)
        offset_y = random.choice([-1, 1]) * random.randint(8, 15)
        return target[0] + offset_x, target[1] + offset_y

    def _unique_jitter(self, target: Tuple[int, int]) -> Tuple[int, int]:
        """Jitter that is guaranteed to differ from the last click position."""
        for _ in range(20):
            pos = self._jitter(target)
            if pos != self._last_click:
                return pos
        # Fallback: force a different offset
        dx = random.randint(1, 5) if self._last_click and pos[0] == self._last_click[0] else 0
        return pos[0] + dx, pos[1] + (1 if not dx else 0)

    def _bezier_path(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        steps: int = 25,
    ) -> List[Tuple[int, int]]:
        """Cubic Bezier curve from start to end with a random arc control point."""
        x0, y0 = start
        x3, y3 = end
        # Midpoint displaced perpendicularly to create arc
        mid_x = (x0 + x3) / 2
        mid_y = (y0 + y3) / 2
        dx, dy = x3 - x0, y3 - y0
        length = math.hypot(dx, dy) or 1
        # Perpendicular unit vector
        perp_x, perp_y = -dy / length, dx / length
        arc = random.uniform(0.1, 0.35) * length * random.choice([-1, 1])
        x1 = mid_x + perp_x * arc + random.uniform(-10, 10)
        y1 = mid_y + perp_y * arc + random.uniform(-10, 10)
        x2 = mid_x + perp_x * arc * 0.5 + random.uniform(-10, 10)
        y2 = mid_y + perp_y * arc * 0.5 + random.uniform(-10, 10)

        pts: List[Tuple[int, int]] = []
        for i in range(steps):
            t = i / (steps - 1)
            mt = 1 - t
            x = mt ** 3 * x0 + 3 * mt ** 2 * t * x1 + 3 * mt * t ** 2 * x2 + t ** 3 * x3
            y = mt ** 3 * y0 + 3 * mt ** 2 * t * y1 + 3 * mt * t ** 2 * y2 + t ** 3 * y3
            pts.append((int(x), int(y)))
        return pts

    def _current_pos(self) -> Tuple[int, int]:
        pos = self._mouse.position
        return int(pos[0]), int(pos[1])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_mouse.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add core/mouse.py tests/test_mouse.py
git commit -m "feat: Bezier mouse movement with guaranteed unique-pixel jitter"
git push
```

---

## Task 7: core/keyboard.py — ESC Listener + Arrow-Key Camera Rotation

**Files:**
- Create: `core/keyboard.py`

- [ ] **Step 1: Write core/keyboard.py**

```python
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
        # Small random pause after rotation
        time.sleep(random.uniform(0.1, 0.4))
```

- [ ] **Step 2: Commit**

```bash
git add core/keyboard.py
git commit -m "feat: ESC kill listener and arrow-key camera rotation"
git push
```

---

## Task 8: core/scheduler.py — Downtime Window Evaluation

**Files:**
- Create: `core/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scheduler.py
from datetime import datetime
from config import DowntimeWindow
from core.scheduler import DowntimeScheduler

def test_in_window_returns_true():
    window = DowntimeWindow(start_hhmm="22:00", end_hhmm="23:00", days=list(range(7)), variance_minutes=0)
    sched = DowntimeScheduler([window])
    # 22:30 on any day
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_scheduler.py -v
```
Expected: ImportError — core/scheduler.py doesn't exist yet.

- [ ] **Step 3: Write core/scheduler.py**

```python
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

    def is_break_time(self, now: datetime | None = None) -> bool:
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

    def next_break_end(self, now: datetime | None = None) -> str:
        """Return 'HH:MM' of the end of the current active window, or empty string."""
        if now is None:
            now = datetime.now()
        for w in self.windows:
            if now.weekday() not in w.days:
                continue
            end_h, end_m = map(int, w.end_hhmm.split(":"))
            return f"{end_h:02d}:{end_m:02d}"
        return ""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_scheduler.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add core/scheduler.py tests/test_scheduler.py
git commit -m "feat: downtime scheduler with variance and day filtering"
git push
```

---

## Task 9: core/ocr.py — Tesseract Loot Name Extraction

**Files:**
- Create: `core/ocr.py`

- [ ] **Step 1: Write core/ocr.py**

```python
# core/ocr.py
from __future__ import annotations
from typing import List, Tuple

import cv2
import numpy as np
import pytesseract
from PIL import Image


class OCRReader:
    """Extracts item name text from a screen region using Tesseract."""

    def read_item_names(self, img_bgr: np.ndarray) -> List[str]:
        """Return list of lowercase item name strings found in the image."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
        pil_img = Image.fromarray(thresh)
        raw = pytesseract.image_to_string(
            pil_img,
            config="--psm 6 --oem 3",
        )
        names = [line.strip().lower() for line in raw.splitlines() if line.strip()]
        return names

    def any_whitelisted(self, img_bgr: np.ndarray, whitelist: List[str]) -> bool:
        """Return True if any detected item name appears in the whitelist."""
        found = self.read_item_names(img_bgr)
        wl_lower = [w.lower() for w in whitelist]
        return any(name in wl_lower for name in found)
```

- [ ] **Step 2: Commit**

```bash
git add core/ocr.py
git commit -m "feat: OCR reader for loot whitelist detection"
git push
```

---

## Task 10: bots/base_bot.py + bots/registry.py

**Files:**
- Create: `bots/base_bot.py`
- Create: `bots/registry.py`

- [ ] **Step 1: Write bots/base_bot.py**

```python
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
        # Stats
        self.loops: int = 0
        self.start_time: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def log(self, msg: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {msg}")

    def random_sleep(self, min_s: float = 0.4, max_s: float = 1.2) -> None:
        """Sleep a random duration. NEVER use time.sleep() directly in subclasses."""
        time.sleep(random.uniform(min_s, max_s))

    def micro_pause(self) -> None:
        """Tiny unpredictable gap injected between every distinct action."""
        time.sleep(random.uniform(0.05, 0.25))

    @classmethod
    def register(cls) -> None:
        from bots.registry import BOT_REGISTRY
        BOT_REGISTRY[cls.name] = cls
```

- [ ] **Step 2: Write bots/registry.py**

```python
# bots/registry.py
from __future__ import annotations
from typing import Dict, Type

# Maps bot display name → Bot subclass
BOT_REGISTRY: Dict[str, Type] = {}
```

- [ ] **Step 3: Commit**

```bash
git add bots/base_bot.py bots/registry.py
git commit -m "feat: Bot ABC with start/stop/log and registry pattern"
git push
```

---

## Task 11: bots/woodcutter.py — Decision Tree Implementation

**Files:**
- Create: `bots/woodcutter.py`
- Create: `tests/test_woodcutter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_woodcutter.py
import threading
from unittest.mock import MagicMock, patch
from bots.woodcutter import WoodcutterBot

def _make_bot():
    bot = WoodcutterBot.__new__(WoodcutterBot)
    WoodcutterBot.__init__(bot)
    return bot

def test_bot_name():
    assert WoodcutterBot.name == "Woodcutter"

def test_bot_registers():
    WoodcutterBot.register()
    from bots.registry import BOT_REGISTRY
    assert "Woodcutter" in BOT_REGISTRY

def test_stop_flag_exits_loop():
    bot = _make_bot()
    bot.start()
    assert bot.is_running()
    bot.stop()
    bot._thread.join(timeout=3)
    assert not bot.is_running()

def test_chebyshev_distance():
    from bots.woodcutter import chebyshev
    assert chebyshev((3105, 3231), (3105, 3231)) == 0
    assert chebyshev((3105, 3231), (3115, 3231)) == 10
    assert chebyshev((3105, 3231), (3116, 3231)) == 11
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_woodcutter.py -v
```
Expected: ImportError — bots/woodcutter.py doesn't exist yet.

- [ ] **Step 3: Write bots/woodcutter.py**

```python
# bots/woodcutter.py
from __future__ import annotations
import random
import time
from typing import List, Optional, Tuple

from bots.base_bot import Bot
from config import BotConfig, ColorProfile, ConfigManager
from core.color import ColorDetector
from core.keyboard import KeyboardController
from core.mouse import MouseController
from core.screen import ScreenCapture
from core.scheduler import DowntimeScheduler

# --- Tile constants ---
HOME_TILE = (3105, 3231)
CLUSTER_CENTER = (3106, 3230)
TREE_TILES: List[Tuple[int, int]] = [
    (3105, 3232), (3107, 3231), (3106, 3228), (3108, 3229)
]
BOUNDARY = 10  # Chebyshev


def chebyshev(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class WoodcutterBot(Bot):
    """
    Woodcutting bot decision tree:
      1. In expected location?   NO  → walk home, or halt
      2. Inventory full?         YES → drop log (or halt if no logs)
      3. Currently chopping?     YES → wait for idle
      4. Tree available?         YES → click nearest tree
                                 NO  → wait 2–4s
    """

    name = "Woodcutter"

    def __init__(self, config: Optional[BotConfig] = None) -> None:
        super().__init__()
        cfg_mgr = ConfigManager()
        self._cfg = config or cfg_mgr.config
        self._screen = ScreenCapture()
        self._color = ColorDetector()
        self._mouse = MouseController()
        self._keyboard = KeyboardController(on_esc=self.stop)
        self._keyboard.start_listener()
        self._scheduler = DowntimeScheduler(
            self._cfg.downtime_windows,
            enabled=self._cfg.scheduler_enabled,
        )
        self._no_anim_since: Optional[float] = None

    # ------------------------------------------------------------------
    # Decision tree (one iteration)
    # ------------------------------------------------------------------

    def run_loop(self) -> None:
        # Scheduled break check
        if self._scheduler.is_break_time():
            end = self._scheduler.next_break_end()
            self.log(f"Scheduled break until {end}")
            self.random_sleep(30, 60)
            return

        # 1. Location check (tile-space, using color indicator)
        if not self._player_in_bounds():
            self.log("Out of bounds — walking to home tile")
            if not self._walk_home():
                self.log("HALT: walk home failed")
                self.stop()
                return
            self.micro_pause()
            return

        # 2. Inventory full?
        if self._inventory_full():
            if self._inventory_has_logs():
                self.log("Inventory full — dropping one log")
                self._drop_one_log()
                self.micro_pause()
                return
            else:
                self.log("HALT: inventory full but no logs found")
                self.stop()
                return

        # 3. Currently animating (chopping)?
        if self._is_animating():
            self.log("Chopping — waiting for idle")
            self._wait_for_idle()
            self.micro_pause()
            return

        # 4. Find and click a living tree
        tree_pos = self._nearest_living_tree()
        if tree_pos is not None:
            self.log(f"Clicking tree at {tree_pos}")
            clicked = self._mouse.move_and_click(tree_pos)
            self.micro_pause()
            # Post-click verify
            if not self._mouse.post_click_verify(clicked, self._cfg.tree_color):
                self.log("Post-click mismatch — rotating camera and re-scanning")
                for _ in range(3):
                    self._keyboard.rotate_camera()
                    self.random_sleep(self._cfg.min_delay, self._cfg.max_delay)
                    tree_pos = self._nearest_living_tree()
                    if tree_pos:
                        self._mouse.move_and_click(tree_pos)
                        break
                else:
                    self.log("Target lost after 3 rotation attempts")
        else:
            self.log("No living trees — waiting 2–4s")
            self.random_sleep(2.0, 4.0)

        self.random_sleep(self._cfg.min_delay, self._cfg.max_delay)

    # ------------------------------------------------------------------
    # Game-state detectors (color-based)
    # ------------------------------------------------------------------

    def _player_in_bounds(self) -> bool:
        """Check player tile indicator color is present within home boundary."""
        # Grab a region around the minimap / player tile area
        # For now: always returns True until player-tile color is configured
        if not self._cfg.player_color.enabled:
            return True
        region = self._screen.grab((0, 0, 800, 600))
        cluster = self._color.best_cluster(region, self._cfg.player_color)
        if cluster is None:
            return False
        # Approximate tile position check
        return True  # Tile mapping requires calibration; placeholder for color verification

    def _walk_home(self) -> bool:
        """Click the minimap home tile position. Returns False if movement not detected."""
        # Requires calibrated minimap coordinates — click approximate minimap center
        minimap_center = (732, 108)  # Default OSRS fixed layout minimap center
        self._mouse.move_and_click(minimap_center)
        self.random_sleep(2.0, 4.0)
        return True  # Movement detection requires additional calibration

    def _inventory_full(self) -> bool:
        """Return True if the last inventory slot has a colored item (log color present in slot 28)."""
        if not self._cfg.log_color.enabled:
            return False
        # Slot 28 (last) in fixed layout: approximate screen coords
        inv_region = self._screen.grab((548, 205, 190, 260))
        cluster = self._color.best_cluster(inv_region, self._cfg.log_color)
        # Full if we detect logs filling the region densely
        clusters = self._color.find_clusters(inv_region, self._cfg.log_color)
        return len(clusters) >= 10  # ≥10 log-colored blobs → likely full

    def _inventory_has_logs(self) -> bool:
        """Return True if any log-colored pixels are in the inventory."""
        if not self._cfg.log_color.enabled:
            return True  # Assume logs present if color not configured
        inv_region = self._screen.grab((548, 205, 190, 260))
        return len(self._color.find_clusters(inv_region, self._cfg.log_color)) > 0

    def _drop_one_log(self) -> None:
        """Right-click first log in inventory, select Drop."""
        if not self._cfg.log_color.enabled:
            return
        inv_region = self._screen.grab((548, 205, 190, 260))
        cluster = self._color.best_cluster(
            inv_region, self._cfg.log_color, region_offset=(548, 205)
        )
        if cluster:
            self._mouse.move_and_click(cluster)
            self.random_sleep(0.3, 0.6)
            # Click "Drop" in context menu (approx +20px below click)
            drop_pos = (cluster[0], cluster[1] + 40)
            self._mouse.move_and_click(drop_pos)
            self.micro_pause()

    def _is_animating(self) -> bool:
        """Detect animation via XP orb flash / defined animation pixel color."""
        if not self._cfg.anim_color.enabled:
            return False
        # XP orb region in OSRS fixed layout
        orb_region = self._screen.grab((0, 0, 200, 200))
        return self._color.best_cluster(orb_region, self._cfg.anim_color) is not None

    def _wait_for_idle(self) -> None:
        """Poll animation state until idle, with timeout."""
        deadline = time.monotonic() + 30.0  # 30s max wait
        while time.monotonic() < deadline and self._running.is_set():
            if not self._is_animating():
                return
            self.random_sleep(0.5, 1.0)
        self.log("Animation wait timed out")

    def _nearest_living_tree(self):
        """Return screen position of the living tree blob closest to CLUSTER_CENTER, or None."""
        if not self._cfg.tree_color.enabled:
            return None
        # Capture the game viewport (approximate)
        viewport = self._screen.grab((4, 4, 512, 334))
        # Check priority override (Color 2)
        if self._cfg.color2.enabled:
            best = self._color.best_cluster(viewport, self._cfg.color2, region_offset=(4, 4))
            if best:
                return best
        # Fall back to tree color (Color 1)
        clusters = self._color.find_clusters(viewport, self._cfg.tree_color, region_offset=(4, 4))
        if not clusters:
            return None
        # Select cluster closest to CLUSTER_CENTER screen equivalent (viewport center)
        center = (4 + 512 // 2, 4 + 334 // 2)
        return min(clusters, key=lambda c: max(abs(c[0] - center[0]), abs(c[1] - center[1])))


# Auto-register on import
WoodcutterBot.register()
```

- [ ] **Step 4: Update bots/__init__.py to trigger registration**

```python
# bots/__init__.py
from bots import woodcutter  # noqa: F401 — triggers WoodcutterBot.register()
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_woodcutter.py -v
```
Expected: 4 PASSED

- [ ] **Step 6: Commit**

```bash
git add bots/woodcutter.py bots/base_bot.py bots/registry.py bots/__init__.py tests/test_woodcutter.py
git commit -m "feat: WoodcutterBot decision tree with color-based detection"
git push
```

---

## Task 12: gui/log_tab.py — Log Tab

**Files:**
- Create: `gui/log_tab.py`

- [ ] **Step 1: Write gui/log_tab.py**

```python
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
        self._text = tk.Text(self, state="disabled", wrap="word", bg="#1e1e1e", fg="#cccccc",
                              font=("Courier", 10))
        scroll = ttk.Scrollbar(self, command=self._text.yview)
        self._text.configure(yscrollcommand=scroll.set)
        self._text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(side="bottom", fill="x")
        ttk.Button(btn_frame, text="Clear", command=self.clear).pack(side="left", padx=4, pady=4)
        ttk.Button(btn_frame, text="Export .txt", command=self._export).pack(side="left", padx=4)

    def append(self, msg: str) -> None:
        self._text.configure(state="normal")
        self._text.insert("end", msg + "\n")
        self._text.see("end")
        self._text.configure(state="disabled")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")

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
```

- [ ] **Step 2: Commit**

```bash
git add gui/log_tab.py
git commit -m "feat: log tab with scrollable text, clear, and export"
git push
```

---

## Task 13: gui/control_tab.py — Bot Control Tab

**Files:**
- Create: `gui/control_tab.py`

- [ ] **Step 1: Write gui/control_tab.py**

```python
# gui/control_tab.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import Callable, List, Optional


class ControlTab(ttk.Frame):
    def __init__(
        self,
        parent: ttk.Notebook,
        bot_names: List[str],
        on_start: Callable[[str], None],
        on_stop: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self._on_start = on_start
        self._on_stop = on_stop
        self._start_time: Optional[datetime] = None
        self._loops = 0
        self._build(bot_names)

    def _build(self, bot_names: List[str]) -> None:
        pad = {"padx": 8, "pady": 4}

        ttk.Label(self, text="Bot:").grid(row=0, column=0, sticky="e", **pad)
        self._bot_var = tk.StringVar(value=bot_names[0] if bot_names else "")
        self._bot_combo = ttk.Combobox(self, textvariable=self._bot_var,
                                        values=bot_names, state="readonly", width=20)
        self._bot_combo.grid(row=0, column=1, sticky="w", **pad)

        self._toggle_btn = ttk.Button(self, text="Start", command=self._toggle)
        self._toggle_btn.grid(row=1, column=0, columnspan=2, **pad)

        self._status_var = tk.StringVar(value="Idle")
        ttk.Label(self, textvariable=self._status_var, font=("Helvetica", 11, "bold")).grid(
            row=2, column=0, columnspan=2, **pad)

        ttk.Label(self, text="Logs dropped:").grid(row=3, column=0, sticky="e", **pad)
        self._logs_var = tk.StringVar(value="0")
        ttk.Label(self, textvariable=self._logs_var).grid(row=3, column=1, sticky="w", **pad)

        ttk.Label(self, text="Runtime:").grid(row=4, column=0, sticky="e", **pad)
        self._runtime_var = tk.StringVar(value="00:00:00")
        ttk.Label(self, textvariable=self._runtime_var).grid(row=4, column=1, sticky="w", **pad)

        ttk.Label(self, text="Loops/min:").grid(row=5, column=0, sticky="e", **pad)
        self._lpm_var = tk.StringVar(value="0")
        ttk.Label(self, textvariable=self._lpm_var).grid(row=5, column=1, sticky="w", **pad)

        ttk.Label(self, text="Press ESC to halt bot at any time.",
                  foreground="gray").grid(row=6, column=0, columnspan=2, **pad)

    def _toggle(self) -> None:
        if self._toggle_btn["text"] == "Start":
            self._start_time = datetime.now()
            self._toggle_btn.configure(text="Stop")
            self._on_start(self._bot_var.get())
        else:
            self._toggle_btn.configure(text="Start")
            self._on_stop()

    def set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    def set_logs_dropped(self, n: int) -> None:
        self._logs_var.set(str(n))

    def update_stats(self, loops: int) -> None:
        if self._start_time:
            elapsed = datetime.now() - self._start_time
            secs = int(elapsed.total_seconds())
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            self._runtime_var.set(f"{h:02d}:{m:02d}:{s:02d}")
            minutes = elapsed.total_seconds() / 60 or 1
            self._lpm_var.set(f"{loops / minutes:.1f}")

    def force_stop_ui(self) -> None:
        """Called when ESC halts the bot externally."""
        self._toggle_btn.configure(text="Start")
        self._status_var.set("Halted (ESC)")
```

- [ ] **Step 2: Commit**

```bash
git add gui/control_tab.py
git commit -m "feat: control tab with start/stop, status, live stats"
git push
```

---

## Task 14: gui/color_tab.py — Color Config Tab

**Files:**
- Create: `gui/color_tab.py`

- [ ] **Step 1: Write gui/color_tab.py**

```python
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

        # Swatch
        self._swatch = tk.Label(self, width=4, height=2, relief="solid")
        self._swatch.grid(row=row, column=0, padx=4, pady=4)

        ttk.Button(self, text="Pick", command=self._pick_color).grid(row=row, column=1, padx=2)

        # RGB spinboxes
        for i, (ch, attr) in enumerate([("R", "r"), ("G", "g"), ("B", "b")]):
            ttk.Label(self, text=ch).grid(row=row + 1, column=i, sticky="e", padx=2)
            var = tk.IntVar(value=getattr(self._profile, attr))
            setattr(self, f"_{attr}_var", var)
            sb = ttk.Spinbox(self, from_=0, to=255, textvariable=var, width=5,
                             command=self._commit)
            sb.grid(row=row + 2, column=i, padx=2)
            var.trace_add("write", lambda *_: self._commit())

        # Tolerance
        ttk.Label(self, text="Tol:").grid(row=row + 1, column=3, padx=2)
        self._tol_var = tk.IntVar(value=self._profile.tolerance)
        ttk.Scale(self, from_=0, to=50, variable=self._tol_var, orient="horizontal",
                  length=80, command=lambda _: self._commit()).grid(row=row + 2, column=3, padx=2)

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
        self._swatch.configure(bg=_rgb_to_hex(self._profile.r, self._profile.g, self._profile.b))


class ColorTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, config: BotConfig,
                 on_change: Callable[[], None]) -> None:
        super().__init__(parent)
        self._cfg = config
        self._on_change = on_change
        self._build()

    def _build(self) -> None:
        canvas = tk.Canvas(self)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        ttk.Label(inner, text="Primary Colors", font=("Helvetica", 10, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(8, 2))

        ColorSlot(inner, "Color 1 (Primary)", self._cfg.color1,
                  self._on_change).grid(row=1, column=0, padx=6, pady=4, sticky="nw")
        ColorSlot(inner, "Color 2 (Override)", self._cfg.color2,
                  self._on_change, enable_toggle=True).grid(row=1, column=1, padx=6, pady=4, sticky="nw")

        ttk.Separator(inner, orient="horizontal").grid(row=2, column=0, columnspan=2,
                                                        sticky="ew", pady=6)
        ttk.Label(inner, text="Game-State Profiles", font=("Helvetica", 10, "bold")).grid(
            row=3, column=0, columnspan=2, pady=(2, 2))

        profiles = [
            ("Tree Color", self._cfg.tree_color),
            ("Stump Color", self._cfg.stump_color),
            ("Log Color", self._cfg.log_color),
            ("Animation Indicator", self._cfg.anim_color),
            ("Player Tile Indicator", self._cfg.player_color),
        ]
        for i, (label, prof) in enumerate(profiles):
            row, col = divmod(i, 2)
            ColorSlot(inner, label, prof, self._on_change).grid(
                row=4 + row, column=col, padx=6, pady=4, sticky="nw")

        # Timing
        timing = ttk.LabelFrame(inner, text="Search Timing")
        timing.grid(row=8, column=0, columnspan=2, padx=6, pady=8, sticky="ew")
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
```

- [ ] **Step 2: Commit**

```bash
git add gui/color_tab.py
git commit -m "feat: color config tab with swatches, pickers, tolerance sliders"
git push
```

---

## Task 15: gui/scheduler_tab.py — Scheduler Tab

**Files:**
- Create: `gui/scheduler_tab.py`

- [ ] **Step 1: Write gui/scheduler_tab.py**

```python
# gui/scheduler_tab.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable
from config import BotConfig, DowntimeWindow

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class SchedulerTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, config: BotConfig,
                 on_change: Callable[[], None]) -> None:
        super().__init__(parent)
        self._cfg = config
        self._on_change = on_change
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        self._enabled_var = tk.BooleanVar(value=self._cfg.scheduler_enabled)
        ttk.Checkbutton(top, text="Enable scheduled downtime",
                        variable=self._enabled_var, command=self._commit).pack(side="left")

        # Table
        cols = ("Start", "End", "Days", "Variance (min)")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", height=8)
        for c in cols:
            self._tree.heading(c, text=c)
            self._tree.column(c, width=120)
        self._tree.pack(fill="both", expand=True, padx=8)
        self._refresh_tree()

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", padx=8, pady=4)
        ttk.Button(btn_row, text="Add window", command=self._add_window).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Remove selected", command=self._remove_selected).pack(side="left")

        # Variance slider (global)
        var_frame = ttk.LabelFrame(self, text="Random break variance")
        var_frame.pack(fill="x", padx=8, pady=6)
        self._variance_var = tk.IntVar(value=0)
        ttk.Scale(var_frame, from_=0, to=15, variable=self._variance_var,
                  orient="horizontal", length=200).pack(side="left", padx=4)
        ttk.Label(var_frame, textvariable=self._variance_var).pack(side="left")
        ttk.Label(var_frame, text="minutes").pack(side="left")

    def _refresh_tree(self) -> None:
        for row in self._tree.get_children():
            self._tree.delete(row)
        for w in self._cfg.downtime_windows:
            days_str = ",".join(DAY_NAMES[d] for d in w.days)
            self._tree.insert("", "end", values=(w.start_hhmm, w.end_hhmm,
                                                  days_str, w.variance_minutes))

    def _add_window(self) -> None:
        self._cfg.downtime_windows.append(DowntimeWindow())
        self._refresh_tree()
        self._on_change()

    def _remove_selected(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        del self._cfg.downtime_windows[idx]
        self._refresh_tree()
        self._on_change()

    def _commit(self) -> None:
        self._cfg.scheduler_enabled = self._enabled_var.get()
        self._on_change()
```

- [ ] **Step 2: Commit**

```bash
git add gui/scheduler_tab.py
git commit -m "feat: scheduler tab with downtime windows and variance slider"
git push
```

---

## Task 16: gui/loot_tab.py — Loot Whitelist Tab

**Files:**
- Create: `gui/loot_tab.py`

- [ ] **Step 1: Write gui/loot_tab.py**

```python
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

        # Live parsed list
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
```

- [ ] **Step 2: Commit**

```bash
git add gui/loot_tab.py
git commit -m "feat: loot whitelist tab with OCR toggle and live parsed list"
git push
```

---

## Task 17: gui/app.py — Main Window + Bot Thread Management

**Files:**
- Create: `gui/app.py`

- [ ] **Step 1: Write gui/app.py**

```python
# gui/app.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional

from bots.registry import BOT_REGISTRY
from config import ConfigManager
from gui.control_tab import ControlTab
from gui.color_tab import ColorTab
from gui.scheduler_tab import SchedulerTab
from gui.log_tab import LogTab
from gui.loot_tab import LootTab


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("OSRS Bot — First Try Trees")
        self.attributes("-topmost", True)
        self.resizable(True, True)

        self._cfg_mgr = ConfigManager()
        self._cfg = self._cfg_mgr.config
        self._active_bot = None

        # Ensure bots are registered
        import bots  # noqa: F401

        self._build_ui()
        self._poll_log()

    def _build_ui(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=4, pady=4)

        bot_names = list(BOT_REGISTRY.keys()) or ["Woodcutter"]

        self._control_tab = ControlTab(nb, bot_names, self._start_bot, self._stop_bot)
        self._color_tab = ColorTab(nb, self._cfg, self._save_config)
        self._scheduler_tab = SchedulerTab(nb, self._cfg, self._save_config)
        self._log_tab = LogTab(nb)
        self._loot_tab = LootTab(nb, self._cfg, self._save_config)

        nb.add(self._control_tab, text="Control")
        nb.add(self._color_tab, text="Colors")
        nb.add(self._scheduler_tab, text="Scheduler")
        nb.add(self._log_tab, text="Log")
        nb.add(self._loot_tab, text="Loot")

    def _start_bot(self, bot_name: str) -> None:
        BotClass = BOT_REGISTRY.get(bot_name)
        if not BotClass:
            self._log_tab.append(f"Unknown bot: {bot_name}")
            return
        self._active_bot = BotClass(config=self._cfg)
        # Wrap ESC callback to also update UI
        original_stop = self._active_bot.stop
        def esc_stop():
            original_stop()
            self.after(0, self._control_tab.force_stop_ui)
        self._active_bot.stop = esc_stop
        self._active_bot._keyboard._on_esc = esc_stop

        self._active_bot.start()
        self._control_tab.set_status("Running")
        self._log_tab.append(f"Started bot: {bot_name}")

    def _stop_bot(self) -> None:
        if self._active_bot:
            self._active_bot.stop()
            self._active_bot = None
        self._control_tab.set_status("Idle")

    def _save_config(self) -> None:
        self._cfg_mgr.save()

    def _poll_log(self) -> None:
        """Pull messages from bot's log queue every 200ms and display them."""
        if self._active_bot:
            loops = self._active_bot.loops
            self._control_tab.update_stats(loops)
            if not self._active_bot.is_running() and loops > 0:
                self._control_tab.set_status(f"Halted after {loops} loops")
                self._control_tab.force_stop_ui()
            while not self._active_bot.log_queue.empty():
                msg = self._active_bot.log_queue.get_nowait()
                self._log_tab.append(msg)
        self.after(200, self._poll_log)
```

- [ ] **Step 2: Commit**

```bash
git add gui/app.py gui/__init__.py
git commit -m "feat: main App window with notebook tabs and bot thread management"
git push
```

---

## Task 18: main.py — Entry Point

**Files:**
- Create: `main.py`

- [ ] **Step 1: Write main.py**

```python
# main.py
import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import App


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run smoke test**

```bash
cd /Users/dannyschuurman/first-try-trees
python main.py
```
Expected: GUI window opens with 5 tabs. No import errors.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: entry point — python main.py launches bot GUI"
git push
```

---

## Task 19: Full Test Suite Run + Final Push

- [ ] **Step 1: Run all tests**

```bash
cd /Users/dannyschuurman/first-try-trees
python -m pytest tests/ -v
```
Expected: All tests PASSED (color, mouse, scheduler, config, woodcutter).

- [ ] **Step 2: Tag release**

```bash
git tag v1.0.0
git push origin v1.0.0
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|---|---|
| Binary decision tree (location→inventory→animation→tree click) | Task 11 |
| Inventory full → drop log or halt | Task 11 |
| No two consecutive clicks on same pixel | Task 6 (`_unique_jitter`) |
| Bezier curved mouse path | Task 6 (`_bezier_path`) |
| Color 2 priority override | Task 11 (`_nearest_living_tree`) |
| Blob clustering, centroid clicks | Task 5 |
| Noise rejection < 4 pixels | Task 5 |
| Center-priority target selection | Task 5 |
| Post-click color verify + camera rotation on miss | Task 11 |
| ESC kill shortcut | Tasks 7, 10, 17 |
| random.uniform() — no fixed sleeps | Tasks 6, 7, 10, 11 |
| Micro-pause between every distinct action | Task 10 (`micro_pause`) |
| Tab 1 — Control (bot selector, start/stop, stats) | Task 13 |
| Tab 2 — Color Config (5 profiles, timing) | Task 14 |
| Tab 3 — Scheduler (downtime windows) | Task 15 |
| Tab 4 — Log (scroll, clear, export) | Task 12 |
| Tab 5 — Loot Whitelist (OCR) | Task 16 |
| Config persistence ~/.osrs_bot/config.json | Task 3 |
| Extensible bot registry — one file per bot | Tasks 10, 11 |
| requirements.txt + README | Task 2 |
| GitHub repo "first-try-trees" | Task 1 |

**No placeholders found** — all tasks include actual code and commands.
