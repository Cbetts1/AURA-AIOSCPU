"""
Tests — Host Bridge
====================
Validates that the host bridge exposes the unified adapter API and enforces
permission boundaries.

Covers
------
- HostBridge initialises for each supported host type.
- get_network_adapter() returns a non-None object.
- get_filesystem_adapter() returns a non-None object.
- syscall() raises PermissionError for disallowed calls in Universal mode.
- available_capabilities() returns a set.
"""

# TODO: import pytest
# TODO: from host_bridge import HostBridge


class TestHostBridge:

    def test_instantiation_linux(self):
        """HostBridge initialises for host_type='linux'."""
        # TODO: bridge = HostBridge("linux")
        # TODO: assert bridge is not None
        pass

    def test_instantiation_android(self):
        """HostBridge initialises for host_type='android'."""
        # TODO: bridge = HostBridge("android")
        # TODO: assert bridge is not None
        pass

    def test_get_network_adapter_not_none(self):
        """get_network_adapter() must not return None."""
        # TODO: bridge = HostBridge("linux")
        # TODO: assert bridge.get_network_adapter() is not None
        pass

    def test_get_filesystem_adapter_not_none(self):
        """get_filesystem_adapter() must not return None."""
        # TODO: bridge = HostBridge("linux")
        # TODO: assert bridge.get_filesystem_adapter("/tmp") is not None
        pass

    def test_syscall_disallowed_raises(self):
        """A disallowed syscall in Universal mode must raise PermissionError."""
        # TODO: bridge = HostBridge("linux")
        # TODO: with pytest.raises(PermissionError):
        #     bridge.syscall("raw_socket_create")
        pass

    def test_available_capabilities_returns_set(self):
        """available_capabilities() must return a set."""
        # TODO: bridge = HostBridge("linux")
        # TODO: caps = bridge.available_capabilities()
        # TODO: assert isinstance(caps, set)
        pass
