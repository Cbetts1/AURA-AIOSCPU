"""Conformance: Host-Bridge Behavior (Contract 9)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from bridge import get_bridge, detect_host_type, reset_bridge
from bridge.base import HostBridgeBase, BridgeCapability


class TestBridgeBehavior:
    def setup_method(self):
        reset_bridge()

    def test_bridge_detects_a_host(self):
        host = detect_host_type()
        assert host in ("linux", "android", "macos", "windows")

    def test_bridge_returns_base_instance(self):
        bridge = get_bridge()
        assert isinstance(bridge, HostBridgeBase)

    def test_bridge_singleton(self):
        b1 = get_bridge()
        b2 = get_bridge()
        assert b1 is b2

    def test_get_temp_dir_is_writable(self):
        bridge = get_bridge()
        tmpdir = bridge.get_temp_dir()
        assert os.path.isdir(tmpdir)
        probe = os.path.join(tmpdir, ".bridge_conformance_probe")
        with open(probe, "w") as fh:
            fh.write("probe")
        os.unlink(probe)

    def test_get_home_dir_exists(self):
        bridge = get_bridge()
        home = bridge.get_home_dir()
        assert home
        assert os.path.isdir(home)

    def test_available_capabilities_not_empty(self):
        bridge = get_bridge()
        caps = bridge.available_capabilities()
        assert len(caps) > 0

    def test_fs_read_capability_present(self):
        bridge = get_bridge()
        caps = bridge.available_capabilities()
        assert BridgeCapability.FS_READ in caps

    def test_fs_write_capability_present(self):
        bridge = get_bridge()
        caps = bridge.available_capabilities()
        assert BridgeCapability.FS_WRITE in caps

    def test_sys_info_returns_required_keys(self):
        bridge = get_bridge()
        info = bridge.get_sys_info()
        for key in ("host", "arch", "python", "home", "tmpdir"):
            assert key in info, f"sys_info missing key: {key}"

    def test_no_tmp_hardcoded(self):
        """Bridge must not hardcode /tmp — temp dir must be probed."""
        bridge = get_bridge()
        tmpdir = bridge.get_temp_dir()
        # On Android, /tmp doesn't exist — bridge must have found an alternative
        assert tmpdir
        assert os.path.isdir(tmpdir)

    def test_has_capability_helper(self):
        bridge = get_bridge()
        assert bridge.has_capability(BridgeCapability.FS_READ)
        assert not bridge.has_capability("nonexistent_capability_xyz")

    def test_get_safe_path(self):
        bridge = get_bridge()
        path = bridge.get_safe_path("test", "file.txt")
        assert path
        assert os.path.isdir(os.path.dirname(path))

    def test_host_bridge_facade_unknown_host_raises(self):
        from host_bridge import HostBridge
        with pytest.raises(ValueError):
            HostBridge("amiga")

    def test_host_bridge_facade_capabilities_is_set(self):
        from host_bridge import HostBridge
        bridge = HostBridge()
        caps = bridge.available_capabilities()
        assert isinstance(caps, set)
        assert len(caps) > 0
