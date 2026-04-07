"""Tests for kernel.config — Config loader."""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.config import Config, _deep_merge, _parse_env_val


# ---------------------------------------------------------------------------
# _deep_merge helper
# ---------------------------------------------------------------------------

def test_deep_merge_flat():
    base = {"a": 1, "b": 2}
    _deep_merge(base, {"b": 99, "c": 3})
    assert base == {"a": 1, "b": 99, "c": 3}


def test_deep_merge_nested():
    base = {"kernel": {"tick": 16, "adaptive": True}}
    _deep_merge(base, {"kernel": {"tick": 100}})
    assert base == {"kernel": {"tick": 100, "adaptive": True}}


def test_deep_merge_does_not_shallow_replace_dicts():
    base = {"section": {"a": 1, "b": 2}}
    _deep_merge(base, {"section": {"c": 3}})
    assert "a" in base["section"]   # original key preserved


# ---------------------------------------------------------------------------
# _parse_env_val helper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("true",  True),
    ("TRUE",  True),
    ("1",     True),
    ("false", False),
    ("0",     False),
    ("42",    42),
    ("3.14",  3.14),
    ("hello", "hello"),
])
def test_parse_env_val(raw, expected):
    assert _parse_env_val(raw) == expected


# ---------------------------------------------------------------------------
# Config class
# ---------------------------------------------------------------------------

def _make_config(data: dict) -> str:
    """Write a config dict to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    )
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


def test_config_loads_default_json():
    """The shipped default.json should always load without errors."""
    cfg = Config()
    # Kernel tick must be present and positive
    assert cfg.get("kernel", "tick_interval_ms") > 0


def test_config_get_missing_returns_default():
    cfg = Config()
    assert cfg.get("nonexistent", "key", "fallback") == "fallback"


def test_config_set_overrides_at_runtime():
    cfg = Config()
    cfg.set("kernel", "tick_interval_ms", 999)
    assert cfg.get("kernel", "tick_interval_ms") == 999


def test_config_loads_custom_file():
    path = _make_config({"kernel": {"tick_interval_ms": 42}})
    try:
        cfg = Config(config_path=path)
        assert cfg.get("kernel", "tick_interval_ms") == 42
    finally:
        os.unlink(path)


def test_config_custom_file_merges_with_defaults():
    """Custom file should override only the specified keys."""
    path = _make_config({"kernel": {"tick_interval_ms": 55}})
    try:
        cfg = Config(config_path=path)
        # adaptive_tick should still come from default.json
        assert cfg.get("kernel", "adaptive_tick") is not None
    finally:
        os.unlink(path)


def test_config_get_section():
    cfg = Config()
    section = cfg.get_section("kernel")
    assert isinstance(section, dict)
    assert "tick_interval_ms" in section


def test_config_apply_mobile_profile():
    cfg = Config()
    cfg.apply_mobile_profile()
    # After applying mobile profile, tick must be the mobile value (100 by default)
    assert cfg.get("kernel", "tick_interval_ms") == cfg.get("mobile", "tick_interval_ms")


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("AURA_CFG_KERNEL_TICK_INTERVAL_MS", "77")
    cfg = Config()
    assert cfg.get("kernel", "tick_interval_ms") == 77


def test_config_repr():
    cfg = Config()
    r = repr(cfg)
    assert "Config" in r


def test_config_save_and_reload(tmp_path, monkeypatch):
    """Save user.json and verify it loads on next Config() init."""
    user_path = str(tmp_path / "user.json")
    monkeypatch.setattr(
        "kernel.config.USER_CONFIG_PATH", user_path
    )
    cfg = Config()
    cfg.set("kernel", "tick_interval_ms", 111)
    cfg.save_user()

    cfg2 = Config()
    assert cfg2.get("kernel", "tick_interval_ms") == 111
    os.unlink(user_path)
