"""
Tests — Kernel Modes (UniversalMode, InternalMode, HardwareMode)
=================================================================
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.event_bus import EventBus
from kernel.modes.universal import UniversalMode
from kernel.modes.internal import InternalMode
from kernel.modes.hardware import (
    HardwareMode,
    issue_consent_token,
    revoke_consent_token,
    _VALID_TOKENS,
)


# ---------------------------------------------------------------------------
# Kernel and HAL fakes
# ---------------------------------------------------------------------------

def _make_fake_bridge(**caps):
    bridge = MagicMock()
    bridge.available_capabilities.return_value = list(caps.keys()) if caps else ["net", "display"]
    bridge.get_network_adapter.return_value  = MagicMock()
    bridge.get_display_adapter.return_value  = MagicMock()
    return bridge


def _make_fake_hal():
    hal = MagicMock()
    return hal


def _make_fake_kernel():
    k = MagicMock()
    k.event_bus = EventBus()
    k.hal = _make_fake_hal()
    return k


# ---------------------------------------------------------------------------
# UniversalMode
# ---------------------------------------------------------------------------

class TestUniversalMode:
    def test_instantiates(self):
        mode = UniversalMode()
        assert mode is not None

    def test_name(self):
        assert UniversalMode.NAME == "universal"

    def test_kernel_none_before_activate(self):
        mode = UniversalMode()
        assert mode._kernel is None

    def test_bridge_none_before_activate(self):
        mode = UniversalMode()
        assert mode._bridge is None

    def test_activate_sets_kernel(self):
        mode = UniversalMode()
        k = _make_fake_kernel()
        with patch("kernel.modes.universal.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k)
        assert mode._kernel is k

    def test_activate_creates_bridge(self):
        mode = UniversalMode()
        k = _make_fake_kernel()
        with patch("kernel.modes.universal.HostBridge") as MockBridge:
            fake_bridge = _make_fake_bridge()
            MockBridge.return_value = fake_bridge
            mode.activate(k)
        assert mode._bridge is not None

    def test_activate_registers_hal_devices(self):
        mode = UniversalMode()
        k = _make_fake_kernel()
        with patch("kernel.modes.universal.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k)
        k.hal.register_device.assert_any_call("net0", k.hal.register_device.call_args_list[0][0][1])

    def test_activate_publishes_mode_activated_event(self):
        mode = UniversalMode()
        k = _make_fake_kernel()
        events = []
        k.event_bus.subscribe("MODE_ACTIVATED", events.append)
        with patch("kernel.modes.universal.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k)
        k.event_bus.drain()
        assert len(events) == 1
        assert events[0].payload["mode"] == "universal"

    def test_check_capabilities_without_activation_returns_empty(self):
        mode = UniversalMode()
        assert mode.check_capabilities() == {}

    def test_check_capabilities_after_activate(self):
        mode = UniversalMode()
        k = _make_fake_kernel()
        with patch("kernel.modes.universal.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge(net=True, display=True)
            mode.activate(k)
        caps = mode.check_capabilities()
        assert "net" in caps
        assert caps["net"] is True

    def test_check_capabilities_returns_dict_of_bools(self):
        mode = UniversalMode()
        k = _make_fake_kernel()
        with patch("kernel.modes.universal.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge(a=True, b=True)
            mode.activate(k)
        caps = mode.check_capabilities()
        for v in caps.values():
            assert v is True


# ---------------------------------------------------------------------------
# InternalMode
# ---------------------------------------------------------------------------

class TestInternalMode:
    def test_instantiates(self):
        mode = InternalMode()
        assert mode is not None

    def test_name(self):
        assert InternalMode.NAME == "internal"

    def test_activate_sets_kernel(self):
        mode = InternalMode()
        k = _make_fake_kernel()
        with patch("kernel.modes.internal.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k)
        assert mode._kernel is k

    def test_activate_with_permissions_passes_them_to_bridge(self):
        mode = InternalMode()
        k = _make_fake_kernel()
        permissions = {"fs_mount", "net_listen"}
        with patch("kernel.modes.internal.HostBridge") as MockBridge:
            fake_bridge = _make_fake_bridge()
            MockBridge.return_value = fake_bridge
            mode.activate(k, granted_permissions=permissions)
        fake_bridge.set_mode.assert_called_once_with("internal", permissions)

    def test_activate_without_permissions_uses_empty_set(self):
        mode = InternalMode()
        k = _make_fake_kernel()
        with patch("kernel.modes.internal.HostBridge") as MockBridge:
            fake_bridge = _make_fake_bridge()
            MockBridge.return_value = fake_bridge
            mode.activate(k)
        fake_bridge.set_mode.assert_called_once_with("internal", set())

    def test_activate_publishes_mode_activated_event(self):
        mode = InternalMode()
        k = _make_fake_kernel()
        events = []
        k.event_bus.subscribe("MODE_ACTIVATED", events.append)
        with patch("kernel.modes.internal.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k)
        k.event_bus.drain()
        assert len(events) == 1
        assert events[0].payload["mode"] == "internal"

    def test_activate_event_includes_permissions(self):
        mode = InternalMode()
        k = _make_fake_kernel()
        events = []
        k.event_bus.subscribe("MODE_ACTIVATED", events.append)
        with patch("kernel.modes.internal.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k, granted_permissions={"net_listen"})
        k.event_bus.drain()
        assert "net_listen" in events[0].payload["permissions"]

    def test_activate_registers_hal_devices(self):
        mode = InternalMode()
        k = _make_fake_kernel()
        with patch("kernel.modes.internal.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k)
        assert k.hal.register_device.call_count == 2

    def test_request_permission_publishes_event(self):
        mode = InternalMode()
        k = _make_fake_kernel()
        events = []
        k.event_bus.subscribe("PERMISSION_REQUEST", events.append)
        with patch("kernel.modes.internal.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k)
        mode.request_permission("net_listen")
        k.event_bus.drain()
        assert len(events) == 1
        assert events[0].payload["capability"] == "net_listen"

    def test_request_permission_without_kernel_is_noop(self):
        mode = InternalMode()
        mode.request_permission("anything")   # should not raise


# ---------------------------------------------------------------------------
# HardwareMode — consent token management
# ---------------------------------------------------------------------------

class TestConsentTokens:
    def setup_method(self):
        # Clear token store before each test
        _VALID_TOKENS.clear()

    def test_issue_token_adds_to_valid_set(self):
        issue_consent_token("tok-abc")
        assert "tok-abc" in _VALID_TOKENS

    def test_revoke_token_removes_from_set(self):
        issue_consent_token("tok-xyz")
        revoke_consent_token("tok-xyz")
        assert "tok-xyz" not in _VALID_TOKENS

    def test_revoke_nonexistent_token_does_not_raise(self):
        revoke_consent_token("not-issued")  # discard on a missing token is fine


# ---------------------------------------------------------------------------
# HardwareMode
# ---------------------------------------------------------------------------

class TestHardwareMode:
    def setup_method(self):
        _VALID_TOKENS.clear()

    def test_instantiates(self):
        mode = HardwareMode()
        assert mode is not None

    def test_name(self):
        assert HardwareMode.NAME == "hardware"

    def test_activate_without_valid_token_raises(self):
        mode = HardwareMode()
        k = _make_fake_kernel()
        with pytest.raises(PermissionError, match="consent token"):
            with patch("kernel.modes.hardware.HostBridge"):
                mode.activate(k, consent_token="invalid-token")

    def test_activate_with_valid_token_succeeds(self):
        mode = HardwareMode()
        k = _make_fake_kernel()
        issue_consent_token("good-token")
        with patch("kernel.modes.hardware.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k, consent_token="good-token")
        assert mode._kernel is k

    def test_activate_calls_hal_enable_projection(self):
        mode = HardwareMode()
        k = _make_fake_kernel()
        issue_consent_token("t1")
        with patch("kernel.modes.hardware.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k, consent_token="t1")
        k.hal.enable_projection.assert_called_once()

    def test_activate_registers_hal_devices(self):
        mode = HardwareMode()
        k = _make_fake_kernel()
        issue_consent_token("t2")
        with patch("kernel.modes.hardware.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k, consent_token="t2")
        assert k.hal.register_device.call_count == 2

    def test_activate_publishes_mode_activated_event(self):
        mode = HardwareMode()
        k = _make_fake_kernel()
        events = []
        k.event_bus.subscribe("MODE_ACTIVATED", events.append)
        issue_consent_token("t3")
        with patch("kernel.modes.hardware.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k, consent_token="t3")
        k.event_bus.drain()
        assert len(events) == 1
        assert events[0].payload["mode"] == "hardware"

    def test_project_without_activation_raises(self):
        mode = HardwareMode()
        with pytest.raises(RuntimeError, match="not active"):
            mode.project({"type": "network"})

    def test_project_after_activation_calls_hal(self):
        mode = HardwareMode()
        k = _make_fake_kernel()
        issue_consent_token("t4")
        with patch("kernel.modes.hardware.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k, consent_token="t4")
        mode.project({"type": "display", "resolution": "1080p"})
        k.hal.project.assert_called_once_with({"type": "display", "resolution": "1080p"})

    def test_project_publishes_device_projected_event(self):
        mode = HardwareMode()
        k = _make_fake_kernel()
        events = []
        k.event_bus.subscribe("DEVICE_PROJECTED", events.append)
        issue_consent_token("t5")
        with patch("kernel.modes.hardware.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k, consent_token="t5")
        mode.project({"type": "net"})
        k.event_bus.drain()
        assert len(events) == 1

    def test_revoke_calls_hal_teardown(self):
        mode = HardwareMode()
        k = _make_fake_kernel()
        issue_consent_token("t6")
        with patch("kernel.modes.hardware.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k, consent_token="t6")
        mode.revoke()
        k.hal.teardown_all.assert_called_once()

    def test_revoke_invalidates_token(self):
        token = "t7"
        issue_consent_token(token)
        mode = HardwareMode()
        k = _make_fake_kernel()
        with patch("kernel.modes.hardware.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k, consent_token=token)
        mode.revoke()
        assert token not in _VALID_TOKENS

    def test_revoke_publishes_projection_revoked_event(self):
        mode = HardwareMode()
        k = _make_fake_kernel()
        events = []
        k.event_bus.subscribe("PROJECTION_REVOKED", events.append)
        issue_consent_token("t8")
        with patch("kernel.modes.hardware.HostBridge") as MockBridge:
            MockBridge.return_value = _make_fake_bridge()
            mode.activate(k, consent_token="t8")
        mode.revoke()
        k.event_bus.drain()
        assert len(events) == 1

    def test_revoke_before_activate_is_noop(self):
        mode = HardwareMode()
        mode.revoke()   # kernel is None — should not raise
