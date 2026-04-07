"""
AURA-AIOSCPU Bridge Package
============================
Provides the correct HostBridge implementation for the current host.

Detection order (first match wins):
  1. Android / Termux
  2. macOS / Darwin
  3. Windows / WSL
  4. Linux (default)

Usage::

    from bridge import get_bridge, detect_host_type
    bridge = get_bridge()
    tmp    = bridge.get_temp_dir()       # safe — never assumes /tmp
    info   = bridge.get_sys_info()
    bridge.syscall("fs_list", "/home")   # routed through bridge layer

All host interactions MUST go through bridge.syscall() or the adapter
objects returned by HostBridge.get_*_adapter().
"""

import logging

from bridge.base import HostBridgeBase, BridgeCapability  # noqa: F401

logger = logging.getLogger(__name__)

_ACTIVE_BRIDGE: HostBridgeBase | None = None


def detect_host_type() -> str:
    """
    Return the canonical host type string for the current environment.

    Returns one of: "android" | "macos" | "windows" | "linux"
    """
    for cls in _bridge_classes():
        try:
            if cls.detect():
                return cls.__name__.replace("Bridge", "").lower()
        except Exception:
            pass
    return "linux"


def get_bridge() -> HostBridgeBase:
    """
    Return the process-singleton bridge for the current host.

    Thread-safe: subsequent calls return the same instance.
    """
    global _ACTIVE_BRIDGE
    if _ACTIVE_BRIDGE is None:
        _ACTIVE_BRIDGE = _create_bridge()
    return _ACTIVE_BRIDGE


def reset_bridge() -> None:
    """Force re-detection of the host bridge. Mainly for tests."""
    global _ACTIVE_BRIDGE
    _ACTIVE_BRIDGE = None


def _create_bridge() -> HostBridgeBase:
    """Detect the host and return the correct bridge instance."""
    for cls in _bridge_classes():
        try:
            if cls.detect():
                bridge = cls()
                logger.info("bridge: selected %s", cls.__name__)
                return bridge
        except Exception as exc:
            logger.warning("bridge: %s detection/init failed: %s",
                           cls.__name__, exc)
    from bridge.linux import LinuxBridge
    logger.warning("bridge: fallback to LinuxBridge")
    return LinuxBridge()


def _bridge_classes():
    """Return bridge classes in detection priority order."""
    from bridge.android import AndroidBridge
    from bridge.macos import MacOSBridge
    from bridge.windows import WindowsBridge
    from bridge.linux import LinuxBridge
    return [AndroidBridge, MacOSBridge, WindowsBridge, LinuxBridge]


__all__ = [
    "HostBridgeBase",
    "BridgeCapability",
    "detect_host_type",
    "get_bridge",
    "reset_bridge",
]
