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
