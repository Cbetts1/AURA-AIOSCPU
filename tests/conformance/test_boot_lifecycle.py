"""Conformance: Boot Lifecycle (Contract 4 / 16)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json, pytest, time
from launch.boot import BootChain, BootLog, BootError, _locate_rootfs


class TestBootLifecycle:
    def test_boot_log_records_entries(self):
        log = BootLog()
        log.record(0, "START", "test")
        assert len(log.entries()) == 1
        assert log.entries()[0]["stage"] == 0

    def test_boot_log_ok_flag(self):
        log = BootLog()
        log.record(1, "FAIL", "missing rootfs", ok=False)
        assert not log.entries()[0]["ok"]

    def test_boot_log_summary_contains_stages(self):
        log = BootLog()
        log.record(0, "COMPLETE", "env")
        log.record(1, "COMPLETE", "rootfs")
        s = log.summary()
        assert "Stage 0" in s
        assert "Stage 1" in s

    def test_boot_error_has_stage_and_reason(self):
        err = BootError(2, "kernel init failed")
        assert err.stage == 2
        assert "kernel init" in err.reason
        assert "Stage 2" in str(err)

    def test_locate_rootfs_finds_default(self):
        path = _locate_rootfs(None)
        assert path is not None
        assert os.path.isdir(path)

    def test_boot_log_write_and_read(self, tmp_path):
        log = BootLog()
        log.record(0, "START", "env")
        log.record(5, "COMPLETE", "online")
        path = str(tmp_path / "boot.log")
        log.write_to_file(path)
        with open(path) as fh:
            data = json.load(fh)
        assert data["boot_ts"] > 0
        assert len(data["entries"]) == 2

    def test_stage_0_environment(self):
        """Stage 0 environment detection must succeed on any host."""
        log = BootLog()
        log.record(0, "START", "env")
        from bridge import get_bridge, detect_host_type
        host = detect_host_type()
        bridge = get_bridge()
        info = bridge.get_sys_info()
        assert host in ("linux", "android", "macos", "windows")
        assert "arch" in info
        log.record(0, "COMPLETE", f"host={host}")
        assert log.entries()[-1]["ok"]

    def test_stage_1_rootfs_layout_present(self):
        """Stage 1 rootfs must have required partitions."""
        rootfs = _locate_rootfs(None)
        assert rootfs is not None
        required = ["var", "etc", "home", "tmp"]
        for p in required:
            assert os.path.isdir(os.path.join(rootfs, p)), f"Missing partition: {p}"

    def test_all_six_stages_defined(self):
        """BootChain must define all 6 stage methods."""
        from launch.boot import BootChain
        for stage in range(6):
            method = f"_stage_{stage}_" 
            # Check at least one method starts with _stage_{stage}_
            matches = [m for m in dir(BootChain) if m.startswith(f"_stage_{stage}_")]
            assert matches, f"No method for stage {stage}"
