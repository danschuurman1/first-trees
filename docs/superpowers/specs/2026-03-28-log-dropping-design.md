# Log Dropping During Respawn Wait — Design Spec

**Date:** 2026-03-28
**Feature:** Drop logs from inventory when no trees are found and the bot is waiting for respawn.

---

## 1. Trigger Condition

The drop routine activates inside the existing "no trees found" branch in `bots/woodcutter.py` (`run_loop`, line ~109). It runs every time the bot finds no cyan tree blobs and enters the respawn wait state.

```
no trees found
  → drop_logs(screen, mouse, keyboard, origin, config)
  → random_sleep(2.0, 4.0)   ← existing respawn wait, unchanged
```

---

## 2. Config Change (`config.py`)

Add one new field to `BotConfig`:

```python
log_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
```

Same structure as `stump_color` — disabled by default, user enables and configures it in the GUI. If `log_color.enabled` is False, the drop routine exits immediately and does nothing.

---

## 3. GUI Change (`gui/color_tab.py`)

Add a "Log Color" row to the color configuration tab, following the same pattern as the existing stump color rows. No structural changes to the tab — just one additional color profile entry.

---

## 4. Inventory Module (`core/inventory.py`)

Single public function: `drop_logs(screen, mouse, keyboard, origin, config)`.

### 4a. Inventory Open Detection

Sample a single pixel at fixed offset `origin + (560, 210)` in screen coordinates. This falls inside the inventory grid background in the OSRS fixed client (765×503). The inventory background color is approximately `BGR (31, 43, 61)`.

- If pixel matches within tolerance ~25: inventory is open → proceed to scan.
- If not: click inventory icon (see 4b), pause 0.3s, then proceed.

### 4b. Open Inventory

Click the inventory tab icon at fixed offset `origin + (729, 168)`. Uses `mouse.move_and_click()` — bezier path + jitter applied automatically. Pause 0.3s after click.

### 4c. Inventory Slot Layout

OSRS fixed client inventory grid:
- **Grid origin (relative to RuneLite content origin):** `(548, 205)`
- **Slot size:** 42px wide × 36px tall
- **Layout:** 4 columns × 7 rows = 28 slots
- **Sample point per slot:** center of slot (`col * 42 + 21`, `row * 36 + 18`) relative to grid origin

Slot index mapping: `index = row * 4 + col`, rows 0–6, cols 0–3.

### 4d. Log Detection

For each of the 28 slot center pixels, grab a 1×1 pixel via `screen.pixel_color()` and compute RGB distance against `config.log_color`. If distance ≤ `config.log_color.tolerance`, the slot contains a log.

Collect all matching slot indices into a list.

### 4e. Randomized Drop Order

- Shuffle the list of matching slot indices with `random.shuffle()`.
- With 30% probability, split the list at a random midpoint and swap the halves after the initial shuffle — breaks any residual top-to-bottom pattern without adding complexity.

### 4f. Drop Action (Shift-Click)

For each slot index in the shuffled list:

1. Compute slot center screen coordinate from slot index + origin.
2. Press and hold `Shift` via `pynput.keyboard.Controller`.
3. Call `mouse.move_and_click(slot_center)` — bezier path + ±8–15px jitter applied automatically, ensuring no two clicks land on the exact same pixel.
4. Release `Shift`.
5. Sleep `random.uniform(0.05, 0.15)` seconds before the next slot.

---

## 5. Integration (`bots/woodcutter.py`)

Import `drop_logs` from `core.inventory`. Add a `pynput.keyboard.Controller` instance to `WoodcutterBot.__init__`. Replace the "no trees" branch:

```python
# Before
else:
    self.log("No trees found — waiting for respawn")
    self.random_sleep(2.0, 4.0)

# After
else:
    self.log("No trees found — dropping logs")
    drop_logs(self._screen, self._mouse, self._keyboard, self._origin, self._cfg)
    self.log("Waiting for respawn")
    self.random_sleep(2.0, 4.0)
```

---

## 6. Open Questions / Risks

| # | Question | Notes |
|---|---|---|
| 1 | Exact inventory background pixel color | `BGR (31, 43, 61)` is an estimate from standard OSRS UI. May need calibration per display/theme. Consider adding an "inventory open color" to config if this proves unreliable. |
| 2 | Inventory icon coordinate `(729, 168)` | Based on standard RuneLite fixed client layout. Verify against actual window before coding. |
| 3 | Grid origin `(548, 205)` | Same — verify empirically. Off-by-a-few-pixels errors will cause misclicks on slot borders. |
| 4 | Shift-click drop requires setting enabled | Standard OSRS default has shift-click drop on. If user has it disabled, drops will open a menu instead. Document this as a prerequisite. |
| 5 | Log color profile accuracy | Logs in different lighting/zoom may read slightly different RGB. User should sample the color while the game is running at their usual zoom level. |
