# Log Dropping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop logs from inventory when no trees are found and the bot is in the respawn-wait state.

**Architecture:** Two focused changes to `bots/woodcutter.py`: (1) add `_is_slot_log()` for color-profile-based log detection and update `_drop_all_logs` to use it with randomized slot order; (2) add a drop call in the "no trees" else branch of `run_loop`.

**Tech Stack:** Python 3, pynput (via `core/keyboard.py` KeyboardController), mss (screen capture), pytest

---

## Current State (already implemented — do not re-implement)

These already exist in `bots/woodcutter.py` and must not be changed:
- `_slot_positions()` — returns 28 slot center coordinates
- `_is_slot_filled(pos)` — brightness threshold check (`max(R,G,B) > 65`)
- `_count_filled_slots()` — counts filled slots using `_is_slot_filled`
- `_is_inventory_open()` — red tab pixel check at `(ox+644, oy+169)`
- `_ensure_inventory_open()` — clicks tab if closed
- `_inventory_full()` — checks `_count_filled_slots() >= 28`
- `_inventory_has_logs()` — checks `_count_filled_slots() > 0`
- `_drop_all_logs()` — shift-clicks all filled slots (sequential order — THIS WILL BE MODIFIED)

`config.py` already has `log_color: ColorProfile`. GUI already shows "Log Color" entry.

---

### Task 1: Add log-color detection and randomized drop order to `_drop_all_logs`

**Problem:** `_drop_all_logs` uses `_is_slot_filled` (brightness check) — it drops everything, not just logs. It also drops in fixed row-by-row order every time.

**Files:**
- Modify: `bots/woodcutter.py`
- Modify: `tests/test_woodcutter.py`

- [ ] **Step 1: Write failing tests for `_is_slot_log` and randomized drop**

Add to `tests/test_woodcutter.py`:

```python
# ---------------------------------------------------------------------------
# Log-colour slot detection
# ---------------------------------------------------------------------------

def test_is_slot_log_returns_true_when_pixel_matches_log_color():
    bot = _make_bot(log_r=139, log_g=90, log_b=43, log_tol=20)
    bot._screen.pixel_color.return_value = (139, 90, 43)  # exact match
    assert bot._is_slot_log((600, 250)) is True


def test_is_slot_log_returns_false_outside_tolerance():
    bot = _make_bot(log_r=139, log_g=90, log_b=43, log_tol=10)
    bot._screen.pixel_color.return_value = (200, 200, 200)  # grey — not a log
    assert bot._is_slot_log((600, 250)) is False


def test_is_slot_log_returns_false_when_log_color_disabled():
    bot = _make_bot()
    bot._cfg.log_color.enabled = False
    bot._screen.pixel_color.return_value = (139, 90, 43)  # would match if enabled
    assert bot._is_slot_log((600, 250)) is False


# ---------------------------------------------------------------------------
# _drop_all_logs uses _is_slot_log (not _is_slot_filled)
# ---------------------------------------------------------------------------

def test_drop_all_logs_uses_log_color_not_brightness():
    """_drop_all_logs must call _is_slot_log, not _is_slot_filled, to identify logs."""
    bot = _make_bot()
    bot._ensure_inventory_open = MagicMock()
    bot._is_slot_log = MagicMock(return_value=False)
    bot._is_slot_filled = MagicMock(return_value=True)  # always bright — should be ignored
    bot._drop_all_logs()
    bot._is_slot_log.assert_called()
    bot._mouse.move_and_click.assert_not_called()  # no logs found via color check


def test_drop_all_logs_randomizes_order():
    """Drop order should differ from row-by-row on at least some runs."""
    import random
    bot = _make_bot()
    bot._ensure_inventory_open = MagicMock()
    all_slots = [(i * 42 + 569, 223) for i in range(8)]  # 8 slots to make pattern obvious
    bot._slot_positions = MagicMock(return_value=all_slots)
    bot._is_slot_log = MagicMock(return_value=True)
    bot._mouse.move_and_click.return_value = (0, 0)

    orders = set()
    for _ in range(20):
        bot._mouse.move_and_click.reset_mock()
        bot._drop_all_logs()
        order = tuple(call[0][0] for call in bot._mouse.move_and_click.call_args_list)
        orders.add(order)

    assert len(orders) > 1, "Drop order never changed across 20 runs — randomization missing"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/dannyschuurman/first-try-trees/.worktrees/log-dropping && /Users/dannyschuurman/first-try-trees/.venv/bin/pytest tests/test_woodcutter.py::test_is_slot_log_returns_true_when_pixel_matches_log_color tests/test_woodcutter.py::test_is_slot_log_returns_false_outside_tolerance tests/test_woodcutter.py::test_is_slot_log_returns_false_when_log_color_disabled tests/test_woodcutter.py::test_drop_all_logs_uses_log_color_not_brightness tests/test_woodcutter.py::test_drop_all_logs_randomizes_order -v
```

Expected: `AttributeError: 'WoodcutterBot' object has no attribute '_is_slot_log'`

- [ ] **Step 3: Add `_is_slot_log` and update `_drop_all_logs` in `bots/woodcutter.py`**

Add `_is_slot_log` after the `_is_slot_filled` method (around line 123):

```python
def _is_slot_log(self, pos: Tuple[int, int]) -> bool:
    """Return True if the slot centre pixel matches the log_color profile."""
    if not self._cfg.log_color.enabled:
        return False
    profile = self._cfg.log_color
    r, g, b = self._screen.pixel_color(pos[0], pos[1])
    dist = math.sqrt(
        (r - profile.r) ** 2 + (g - profile.g) ** 2 + (b - profile.b) ** 2
    )
    return dist <= profile.tolerance
```

Replace the existing `_drop_all_logs` method:

```python
def _drop_all_logs(self) -> None:
    """Hold Shift and left-click every log slot in a randomized order."""
    self._ensure_inventory_open()
    log_slots = [pos for pos in self._slot_positions() if self._is_slot_log(pos)]
    if not log_slots:
        return
    random.shuffle(log_slots)
    if random.random() < 0.30:
        mid = random.randint(1, len(log_slots))
        log_slots = log_slots[mid:] + log_slots[:mid]
    self._keyboard.press_shift()
    try:
        for pos in log_slots:
            self._mouse.move_and_click(pos)
            self.micro_pause()
    finally:
        self._keyboard.release_shift()
```

- [ ] **Step 4: Update existing drop tests that mock `_is_slot_filled`**

In `tests/test_woodcutter.py`, the following tests reference `_is_slot_filled` in the context of `_drop_all_logs`. Update them to mock `_is_slot_log` instead:

`test_drop_all_logs_shift_clicks_every_log_cluster` — change:
```python
# Before
bot._is_slot_filled = MagicMock(return_value=True)
# After
bot._is_slot_log = MagicMock(return_value=True)
```

`test_drop_all_logs_releases_shift_even_when_no_logs` — change:
```python
# Before
bot._is_slot_filled = MagicMock(return_value=False)
# After (remove the _is_slot_filled mock — _is_slot_log will return False by default
# since log_color has enabled=False in _make_bot unless you set it)
# Instead mock _is_slot_log:
bot._is_slot_log = MagicMock(return_value=False)
```

`test_drop_all_logs_skips_empty_slots` — change:
```python
# Before
bot._is_slot_filled = MagicMock(side_effect=lambda pos: all_slots.index(pos) in filled_positions)
# After
bot._is_slot_log = MagicMock(side_effect=lambda pos: all_slots.index(pos) in filled_positions)
```

`test_drop_all_logs_holds_shift_around_clicks` — change:
```python
# Before
bot._is_slot_filled = MagicMock(return_value=True)
# After
bot._is_slot_log = MagicMock(return_value=True)
```

`test_drop_all_logs_releases_shift_when_no_slots` — no `_is_slot_filled` mock here, but
add:
```python
bot._is_slot_log = MagicMock(return_value=False)
```

- [ ] **Step 5: Run the full test suite**

```bash
cd /Users/dannyschuurman/first-try-trees/.worktrees/log-dropping && /Users/dannyschuurman/first-try-trees/.venv/bin/pytest tests/test_woodcutter.py -v
```

Expected: all woodcutter tests PASS

- [ ] **Step 6: Run the full suite**

```bash
cd /Users/dannyschuurman/first-try-trees/.worktrees/log-dropping && /Users/dannyschuurman/first-try-trees/.venv/bin/pytest -v
```

Expected: all 48+ tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/dannyschuurman/first-try-trees/.worktrees/log-dropping && git add bots/woodcutter.py tests/test_woodcutter.py && git commit -m "feat: add log-color slot detection and randomized drop order"
```

---

### Task 2: Add no-trees drop trigger in `run_loop`

**Problem:** The "no trees" else branch in `run_loop` only sleeps. It should call `_drop_all_logs()` before sleeping so logs are dropped while waiting for respawn.

**Files:**
- Modify: `bots/woodcutter.py`
- Modify: `tests/test_woodcutter.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_woodcutter.py`:

```python
# ---------------------------------------------------------------------------
# No-trees respawn trigger
# ---------------------------------------------------------------------------

def test_no_trees_branch_calls_drop_all_logs():
    """When no tree is found, _drop_all_logs must be called before sleeping."""
    bot = _make_bot()
    bot._nearest_living_tree = MagicMock(return_value=None)
    bot._is_animating = MagicMock(return_value=False)
    bot._inventory_full = MagicMock(return_value=False)
    bot._drop_all_logs = MagicMock()
    bot.random_sleep = MagicMock()
    bot.run_loop()
    bot._drop_all_logs.assert_called_once()


def test_no_trees_branch_sleeps_after_drop():
    """random_sleep must be called after _drop_all_logs in the no-trees branch."""
    bot = _make_bot()
    bot._nearest_living_tree = MagicMock(return_value=None)
    bot._is_animating = MagicMock(return_value=False)
    bot._inventory_full = MagicMock(return_value=False)
    call_order = []
    bot._drop_all_logs = MagicMock(side_effect=lambda: call_order.append("drop"))
    bot.random_sleep = MagicMock(side_effect=lambda *_: call_order.append("sleep"))
    bot.run_loop()
    assert call_order == ["drop", "sleep"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/dannyschuurman/first-try-trees/.worktrees/log-dropping && /Users/dannyschuurman/first-try-trees/.venv/bin/pytest tests/test_woodcutter.py::test_no_trees_branch_calls_drop_all_logs tests/test_woodcutter.py::test_no_trees_branch_sleeps_after_drop -v
```

Expected: FAIL — `AssertionError: Expected '_drop_all_logs' to have been called once`

- [ ] **Step 3: Update the `run_loop` else branch in `bots/woodcutter.py`**

Find the else branch at the bottom of `run_loop` (currently around line 99–101):

```python
        else:
            self.log("No living trees — waiting for respawn")
            self.random_sleep(3.0, 6.0)
```

Replace with:

```python
        else:
            self.log("No living trees — dropping logs and waiting for respawn")
            self._drop_all_logs()
            self.random_sleep(3.0, 6.0)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/dannyschuurman/first-try-trees/.worktrees/log-dropping && /Users/dannyschuurman/first-try-trees/.venv/bin/pytest tests/test_woodcutter.py::test_no_trees_branch_calls_drop_all_logs tests/test_woodcutter.py::test_no_trees_branch_sleeps_after_drop -v
```

Expected: both PASS

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/dannyschuurman/first-try-trees/.worktrees/log-dropping && /Users/dannyschuurman/first-try-trees/.venv/bin/pytest -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/dannyschuurman/first-try-trees/.worktrees/log-dropping && git add bots/woodcutter.py tests/test_woodcutter.py && git commit -m "feat: drop logs when no trees found during respawn wait"
```
