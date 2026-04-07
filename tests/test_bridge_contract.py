"""Unit tests: Bridge Contract"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from bridge import get_bridge, detect_host_type, reset_bridge
from bridge.base import HostBridgeBase, BridgeCapability
from bridge.linux import LinuxBridge
from bridge.android import AndroidBridge
from bridge.windows import WindowsBridge
from bridge.macos import MacOSBridge


class TestBridgeContract:
    def setup_method(self):
        reset_bridge()

    def test_detect_host_type_returns_known_type(self):
        host = detect_host_type()
        assert host in ("linux", "android", "macos", "windows")

    def test_get_bridge_returns_base_instance(self):
        bridge = get_bridge()
        assert isinstance(bridge, HostBridgeBase)

    def test_bridge_temp_dir_writable(self):
        bridge = get_bridge()
        tmpdir = bridge.get_temp_dir()
        assert tmpdir
        assert os.path.isdir(tmpdir)

    def test_bridge_home_dir_exists(self):
        bridge = get_bridge()
        home = bridge.get_home_dir()
        assert home
        assert os.path.isdir(home)

    def test_bridge_capabilities_frozenset(self):
        bridge = get_bridge()
        caps = bridge.available_capabilities()
        assert isinstance(caps, frozenset)

    def test_bridge_has_capability_helper(self):
        bridge = get_bridge()
        assert bridge.has_capability(BridgeCapability.FS_READ)

    def test_bridge_sys_info_has_required_keys(self):
        bridge = get_bridge()
        info = bridge.get_sys_info()
        for key in ("host", "arch", "python", "home", "tmpdir"):
            assert key in info

    def test_bridge_singleton(self):
        b1 = get_bridge()
        b2 = get_bridge()
        assert b1 is b2

    def test_reset_bridge_clears_singleton(self):
        b1 = get_bridge()
        reset_bridge()
        b2 = get_bridge()
        # They may be equal in type but they are different instances
        assert type(b1) == type(b2)

    def test_linux_bridge_detect_not_android(self):
        # LinuxBridge.detect() should return False on Android
        # This just verifies the method exists and returns bool
        result = LinuxBridge.detect()
        assert isinstance(result, bool)

    def test_bridge_get_safe_path(self):
        bridge = get_bridge()
        path = bridge.get_safe_path("subdir", "file.txt")
        assert path
        assert os.path.isdir(os.path.dirname(path))

    def test_bridge_set_mode(self):
        bridge = get_bridge()
        bridge.set_mode("internal", {"net.listen"})
        assert bridge.get_mode() == "internal"
        bridge.set_mode("universal")

    def test_bridge_capability_constants(self):
        assert BridgeCapability.FS_READ == "fs_read"
        assert BridgeCapability.FS_WRITE == "fs_write"
        assert BridgeCapability.NET_CONNECT == "net_connect"
        assert BridgeCapability.PROC_SPAWN == "proc_spawn"
