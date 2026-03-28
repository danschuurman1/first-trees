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

## Anti-Detection

- All click targets use a fresh random offset (±8–15 px) re-seeded on every click
- No two consecutive clicks on the same tree land on the same pixel
- All waits use `random.uniform(min, max)` — never fixed sleeps
- Extra random micro-pause injected between every distinct bot action

## Add a New Bot

1. Create `bots/my_bot.py`
2. Subclass `Bot`, set `name = "My Bot"`
3. Implement `run_loop()`
4. Call `register()` at module bottom
5. Import the module in `bots/__init__.py`
