"""
AURA-AIOSCPU Configuration System
==================================
Hierarchical configuration loader:
  1. config/default.json   — shipped defaults
  2. config/user.json      — user / runtime overrides
  3. AURA_CFG_* env vars   — environment overrides (AURA_CFG_KERNEL_TICK_INTERVAL_MS=100)

Config is available everywhere via the singleton ``get_config()``.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(_REPO_ROOT, "config", "default.json")
USER_CONFIG_PATH = os.path.join(_REPO_ROOT, "config", "user.json")

_instance: "Config | None" = None


def get_config() -> "Config":
    """Return the process-wide Config singleton (initialised on first call)."""
    global _instance
    if _instance is None:
        _instance = Config()
    return _instance


class Config:
    """Process-wide hierarchical configuration."""

    def __init__(self, config_path: str | None = None):
        self._data: dict = {}
        self._load_file(DEFAULT_CONFIG_PATH)
        extra = config_path or (
            USER_CONFIG_PATH if os.path.exists(USER_CONFIG_PATH) else None
        )
        if extra:
            self._load_file(extra)
        self._apply_env_overrides()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, section: str, key: str, default=None):
        """Return a single config value."""
        return self._data.get(section, {}).get(key, default)

    def get_section(self, section: str) -> dict:
        """Return an entire section as a shallow copy."""
        return dict(self._data.get(section, {}))

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def set(self, section: str, key: str, value) -> None:
        """Set a value at runtime (not persisted unless save_user() is called)."""
        self._data.setdefault(section, {})[key] = value

    def save_user(self) -> None:
        """Persist the current config to config/user.json."""
        os.makedirs(os.path.dirname(USER_CONFIG_PATH), exist_ok=True)
        with open(USER_CONFIG_PATH, "w") as fh:
            json.dump(self._data, fh, indent=2)
        logger.info("Config: saved user config to %r", USER_CONFIG_PATH)

    # ------------------------------------------------------------------
    # Device profiles
    # ------------------------------------------------------------------

    def apply_mobile_profile(self) -> None:
        """Override kernel settings with the mobile-optimised values."""
        mobile = self._data.get("mobile", {})
        self._data.setdefault("kernel", {})["tick_interval_ms"] = (
            mobile.get("tick_interval_ms", 100)
        )
        self._data.setdefault("hal", {})["max_memory_mb"] = (
            mobile.get("max_memory_mb", 256)
        )
        self._data.setdefault("kernel", {})["max_task_queue"] = (
            mobile.get("max_task_queue", 256)
        )
        logger.info("Config: mobile profile applied (tick=%dms, mem=%dMB)",
                    self._data["kernel"]["tick_interval_ms"],
                    self._data["hal"]["max_memory_mb"])

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_file(self, path: str) -> None:
        if not os.path.exists(path):
            return
        try:
            with open(path) as fh:
                data = json.load(fh)
            _deep_merge(self._data, data)
            logger.debug("Config: loaded %r", path)
        except Exception:
            logger.exception("Config: failed to load %r", path)

    def _apply_env_overrides(self) -> None:
        """AURA_CFG_<SECTION>_<KEY>=value overrides any config key."""
        for env_key, env_val in os.environ.items():
            if not env_key.startswith("AURA_CFG_"):
                continue
            remainder = env_key[len("AURA_CFG_"):]
            parts = remainder.lower().split("_", 1)
            if len(parts) == 2:
                section, key = parts
                if section in self._data:
                    self._data[section][key] = _parse_env_val(env_val)

    def __repr__(self):
        return f"Config(sections={list(self._data)})"


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _parse_env_val(val: str):
    if val.lower() in ("true", "1", "yes"):
        return True
    if val.lower() in ("false", "0", "no"):
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val
