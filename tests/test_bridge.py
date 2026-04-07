"""
Tests — Host Bridge
====================
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from host_bridge import HostBridge


class TestHostBridge:

    def test_instantiation_linux(self):
        bridge = HostBridge("linux")
        assert bridge is not None

    def test_instantiation_android(self):
        bridge = HostBridge("android")
        assert bridge is not None

    def test_unknown_host_type_raises(self):
        with pytest.raises(ValueError):
            HostBridge("amiga")

    def test_get_network_adapter_not_none(self):
        bridge = HostBridge("linux")
        assert bridge.get_network_adapter() is not None

    def test_get_filesystem_adapter_not_none(self):
        bridge = HostBridge("linux")
        assert bridge.get_filesystem_adapter("/tmp") is not None

    def test_get_display_adapter_not_none(self):
        bridge = HostBridge("linux")
        assert bridge.get_display_adapter() is not None

    def test_syscall_allowed_in_universal(self):
        bridge = HostBridge("linux")
        # fs_list is allowed in universal mode — should not raise
        result = bridge.syscall("fs_list", "/tmp")
        assert isinstance(result, list)

    def test_syscall_disallowed_in_universal_raises(self):
        bridge = HostBridge("linux")
        with pytest.raises(PermissionError):
            bridge.syscall("raw_socket_create")

    def test_available_capabilities_returns_set(self):
        bridge = HostBridge("linux")
        caps = bridge.available_capabilities()
        assert isinstance(caps, set)
        assert len(caps) > 0

    def test_adapters_are_cached(self):
        """Calling get_network_adapter() twice returns the same object."""
        bridge = HostBridge("linux")
        a1 = bridge.get_network_adapter()
        a2 = bridge.get_network_adapter()
        assert a1 is a2

