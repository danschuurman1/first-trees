# Gemini CLI — Project Rules (OSRS Bot)

## 1. Preset Integrity (CRITICAL)
- NEVER modify settings across bots. The `GlobalConfig.presets` dictionary is the source of truth.
- Changes made while the "Willow Trees" bot is active must only affect the "Willow Trees" preset.
- Validation: After any change to a bot's logic or config, verify that the "Woodcutter" preset remains unchanged.

## 2. UI Standards
- The "Controls" tab is the primary interface.
- All new bots must be added via `BOT_REGISTRY` and appear in the `ControlTab` dropdown.
- When a user switches bots in the UI, the `on_bot_change` callback MUST be used to swap the active `BotConfig` and refresh the `ColorTab`.

## 3. Bot Architecture
- New bots should inherit from `WoodcutterBot` if they use color-clustering for object detection.
- Core automation logic (mouse movement, screen grabbing) resides in `core/`. Do not duplicate these utilities; extend them if necessary.
- Emergency stop: Ensure the `ESC` key and the `/tmp/osrs_bot_stop` file logic are always functional in every bot loop.
