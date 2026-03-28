# tests/test_config.py
import json
from pathlib import Path
import pytest
from config import BotConfig, ColorProfile, DowntimeWindow, _config_from_dict, _profile_from_dict


def test_color_profile_defaults():
    p = ColorProfile()
    assert p.r == 0
    assert p.tolerance == 20
    assert p.enabled is True


def test_config_saves_and_loads(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("config.CONFIG_PATH", tmp_path / "config.json")
    # Re-import to pick up monkeypatched values
    import importlib, config as cfg_mod
    importlib.reload(cfg_mod)
    from config import ConfigManager, ColorProfile
    mgr = cfg_mod.ConfigManager()
    mgr.config.selected_bot = "Woodcutter"
    mgr.config.color1 = ColorProfile(r=100, g=150, b=200, tolerance=15)
    mgr.save()
    mgr2 = cfg_mod.ConfigManager()
    assert mgr2.config.selected_bot == "Woodcutter"
    assert mgr2.config.color1.r == 100
    assert mgr2.config.color1.tolerance == 15


def test_config_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("config.CONFIG_PATH", tmp_path / "no_such.json")
    import importlib, config as cfg_mod
    importlib.reload(cfg_mod)
    mgr = cfg_mod.ConfigManager()
    assert mgr.config.selected_bot == "Woodcutter"
    assert mgr.config.min_delay == 0.4


def test_profile_from_dict_ignores_unknown_keys():
    d = {"r": 10, "g": 20, "b": 30, "tolerance": 5, "enabled": True, "unknown_key": 99}
    p = _profile_from_dict(d)
    assert p.r == 10
    assert not hasattr(p, "unknown_key")


def test_botconfig_has_7_color_profiles():
    cfg = BotConfig()
    for attr in ("color1", "color2", "tree_color", "stump_color", "log_color", "anim_color", "player_color"):
        value = getattr(cfg, attr)
        assert type(value).__name__ == "ColorProfile"
        assert hasattr(value, 'r') and hasattr(value, 'tolerance')
