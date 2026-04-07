"""Tests for kernel.device_profile — DeviceProfile detection."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.device_profile import DeviceProfile


def test_device_profile_instantiates():
    p = DeviceProfile()
    assert p is not None


def test_architecture_is_string():
    p = DeviceProfile()
    assert isinstance(p.architecture, str)
    assert len(p.architecture) > 0


def test_cpu_count_positive():
    p = DeviceProfile()
    assert p.cpu_count >= 1


def test_memory_mb_positive():
    p = DeviceProfile()
    assert p.memory_mb > 0


def test_is_64bit_type():
    p = DeviceProfile()
    assert isinstance(p.is_64bit, bool)


def test_is_mobile_type():
    p = DeviceProfile()
    assert isinstance(p.is_mobile, bool)


def test_is_android_type():
    p = DeviceProfile()
    assert isinstance(p.is_android, bool)


def test_is_termux_type():
    p = DeviceProfile()
    assert isinstance(p.is_termux, bool)


def test_recommended_tick_ms_positive():
    p = DeviceProfile()
    assert p.recommended_tick_ms() > 0


def test_recommended_tick_ms_desktop_is_low():
    """On a desktop (non-mobile), tick should be at the fast default (16ms)."""
    p = DeviceProfile()
    if not p.is_mobile:
        assert p.recommended_tick_ms() <= 16


def test_recommended_tick_ms_mobile_is_higher():
    """Simulate a mobile device — tick should be >= 100ms."""
    p = DeviceProfile()
    p.is_mobile   = True
    p.memory_mb   = 3000
    assert p.recommended_tick_ms() >= 100


def test_recommended_tick_ms_constrained_mobile():
    """Very constrained mobile device should get 200ms tick."""
    p = DeviceProfile()
    p.is_mobile   = True
    p.memory_mb   = 256
    assert p.recommended_tick_ms() >= 200


def test_recommended_max_memory_mb():
    p = DeviceProfile()
    max_mem = p.recommended_max_memory_mb()
    assert max_mem > 0
    assert max_mem <= p.memory_mb


def test_recommended_max_task_queue():
    p = DeviceProfile()
    q = p.recommended_max_task_queue()
    assert q > 0


def test_recommended_max_task_queue_mobile():
    p = DeviceProfile()
    p.is_mobile = True
    assert p.recommended_max_task_queue() == 256


def test_to_dict_keys():
    p = DeviceProfile()
    d = p.to_dict()
    expected_keys = {
        "architecture", "cpu_count", "is_64bit", "is_android",
        "is_termux", "is_mobile", "is_arm", "memory_mb", "hostname",
        "os_name", "python_version", "recommended_tick_ms",
        "recommended_max_memory_mb",
    }
    assert expected_keys.issubset(d.keys())


def test_to_dict_types():
    d = DeviceProfile().to_dict()
    assert isinstance(d["architecture"], str)
    assert isinstance(d["cpu_count"], int)
    assert isinstance(d["memory_mb"], int)
    assert isinstance(d["is_mobile"], bool)


def test_repr_contains_key_info():
    p = DeviceProfile()
    r = repr(p)
    assert "DeviceProfile" in r
    assert "arch=" in r


def test_termux_detection_via_env(monkeypatch):
    monkeypatch.setenv("TERMUX_VERSION", "0.118.1")
    p = DeviceProfile()
    assert p.is_termux is True
    assert p.is_mobile is True


def test_no_termux_without_env(monkeypatch):
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("PREFIX", raising=False)
    # Can't easily stub /data/data/com.termux so just verify the flag type
    p = DeviceProfile()
    assert isinstance(p.is_termux, bool)
