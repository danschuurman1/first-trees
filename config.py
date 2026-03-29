# config.py
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

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
class BotConfig:
    selected_bot: str = "Woodcutter"
    # Primary tree color (cyan) — what the bot clicks
    tree_color: ColorProfile = field(default_factory=ColorProfile)
    # Stump color — signals tree has been cut
    stump_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    # Second stump color — alternative cut signal
    stump_color2: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    # Optional override color — checked before tree_color if enabled
    color2: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    # Scan timing
    min_delay: float = 0.4
    max_delay: float = 1.2


def _profile_from_dict(d: dict) -> ColorProfile:
    return ColorProfile(**{k: v for k, v in d.items() if k in ColorProfile.__dataclass_fields__})


def _config_from_dict(d: dict) -> BotConfig:
    cfg = BotConfig()
    profile_keys = {"tree_color", "stump_color", "stump_color2", "color2"}
    for k, v in d.items():
        if k in profile_keys and isinstance(v, dict):
            setattr(cfg, k, _profile_from_dict(v))
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
