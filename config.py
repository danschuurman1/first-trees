# config.py
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict

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
    """Settings for a specific bot preset."""
    color1: ColorProfile = field(default_factory=ColorProfile)
    color2: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    # Game-state profiles
    tree_color: ColorProfile = field(default_factory=ColorProfile)
    stump_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    stump_color2: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    log_color: ColorProfile = field(default_factory=ColorProfile)
    inv_count_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    anim_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    player_color: ColorProfile = field(default_factory=ColorProfile)
    # New Banking & XP profiles
    bank_booth_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    xp_drop_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    grid_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    
    # Motherlode Mine profiles
    bank_chest_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    ore_active_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    ore_depleted_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    hopper_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    ladder_ascend_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    ladder_descend_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    sack_color: ColorProfile = field(default_factory=lambda: ColorProfile(enabled=False))
    
    # Timing
    min_delay: float = 0.4
    max_delay: float = 1.2
    run_duration_value: int = 0
    run_duration_unit: str = "minutes"
    # Scheduler
    scheduler_enabled: bool = False
    downtime_windows: List[DowntimeWindow] = field(default_factory=list)
    # Loot
    loot_ocr_enabled: bool = False
    loot_whitelist: List[str] = field(default_factory=list)


@dataclass
class GlobalConfig:
    """Overall application configuration with multiple presets."""
    selected_bot: str = "Woodcutter"
    presets: Dict[str, BotConfig] = field(default_factory=lambda: {
        "Woodcutter": BotConfig(),
        "Willow Trees": BotConfig(),
        "Willow Banker": BotConfig(),
        "Willow Chopper": BotConfig(),
        "Motherlode Mine": BotConfig()
    })


def _profile_from_dict(d: dict) -> ColorProfile:
    return ColorProfile(**{k: v for k, v in d.items() if k in ColorProfile.__dataclass_fields__})


def _window_from_dict(d: dict) -> DowntimeWindow:
    return DowntimeWindow(**{k: v for k, v in d.items() if k in DowntimeWindow.__dataclass_fields__})


def _bot_config_from_dict(d: dict) -> BotConfig:
    cfg = BotConfig()
    profile_keys = {
        "color1", "color2", "tree_color", "stump_color", "stump_color2",
        "log_color", "inv_count_color", "anim_color", "player_color",
        "bank_booth_color", "xp_drop_color", "grid_color",
        "bank_chest_color", "ore_active_color", "ore_depleted_color",
        "hopper_color", "ladder_ascend_color", "ladder_descend_color",
        "sack_color"
    }
    for k, v in d.items():
        if k in profile_keys and isinstance(v, dict):
            setattr(cfg, k, _profile_from_dict(v))
        elif k == "downtime_windows" and isinstance(v, list):
            cfg.downtime_windows = [_window_from_dict(w) for w in v]
        elif hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


def _global_config_from_dict(d: dict) -> GlobalConfig:
    cfg = GlobalConfig()
    if "selected_bot" in d:
        cfg.selected_bot = d["selected_bot"]
    if "presets" in d and isinstance(d["presets"], dict):
        for name, p_data in d["presets"].items():
            cfg.presets[name] = _bot_config_from_dict(p_data)
    # Migration helper: if old config format is detected
    elif "tree_color" in d:
        cfg.presets["Woodcutter"] = _bot_config_from_dict(d)
    return cfg


class ConfigManager:
    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.config: GlobalConfig = self._load()

    def _load(self) -> GlobalConfig:
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                return _global_config_from_dict(data)
            except Exception:
                pass
        return GlobalConfig()

    def save(self) -> None:
        CONFIG_PATH.write_text(json.dumps(asdict(self.config), indent=2))

    def get_current_preset(self) -> BotConfig:
        if self.config.selected_bot not in self.config.presets:
            self.config.presets[self.config.selected_bot] = BotConfig()
        return self.config.presets[self.config.selected_bot]
