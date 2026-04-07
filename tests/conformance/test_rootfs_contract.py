"""Conformance: Rootfs Contract (Contract 11)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json, pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ROOTFS = os.path.join(_REPO_ROOT, "rootfs")

REQUIRED_PARTITIONS = [
    "boot", "system", "user", "overlay", "aura",
    "services", "var", "tmp", "etc", "home", "mnt",
]

class TestRootfsContract:
    def test_rootfs_directory_exists(self):
        assert os.path.isdir(_ROOTFS), f"rootfs not found at {_ROOTFS}"

    @pytest.mark.parametrize("partition", REQUIRED_PARTITIONS)
    def test_required_partition_exists(self, partition):
        path = os.path.join(_ROOTFS, partition)
        assert os.path.isdir(path), f"Missing partition: {partition}"

    def test_layout_json_exists(self):
        layout = os.path.join(_ROOTFS, "layout.json")
        assert os.path.isfile(layout), "layout.json missing"

    def test_layout_json_is_valid(self):
        layout = os.path.join(_ROOTFS, "layout.json")
        with open(layout) as fh:
            data = json.load(fh)
        assert "version" in data
        assert "partitions" in data
        assert isinstance(data["partitions"], dict)

    def test_layout_json_has_all_partitions(self):
        layout = os.path.join(_ROOTFS, "layout.json")
        with open(layout) as fh:
            data = json.load(fh)
        for p in REQUIRED_PARTITIONS:
            assert p in data["partitions"], f"Partition {p!r} missing from layout.json"

    def test_var_partition_is_writable(self):
        var_dir = os.path.join(_ROOTFS, "var")
        os.makedirs(var_dir, exist_ok=True)
        probe = os.path.join(var_dir, ".conformance_probe")
        with open(probe, "w") as fh:
            fh.write("probe")
        os.unlink(probe)

    def test_tmp_partition_is_writable(self):
        tmp_dir = os.path.join(_ROOTFS, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        probe = os.path.join(tmp_dir, ".conformance_probe")
        with open(probe, "w") as fh:
            fh.write("probe")
        os.unlink(probe)

    def test_system_partition_exists(self):
        system = os.path.join(_ROOTFS, "system")
        assert os.path.isdir(system)

    def test_boot_partition_exists(self):
        boot = os.path.join(_ROOTFS, "boot")
        assert os.path.isdir(boot)

    def test_manifest_module_importable(self):
        from tools.manifest import build_manifest, verify_manifest, load_manifest  # noqa: F401
        assert callable(build_manifest)
        assert callable(verify_manifest)

    def test_manifest_build_produces_dict(self):
        from tools.manifest import build_manifest
        m = build_manifest()
        assert isinstance(m, dict)
        assert "version" in m
        assert "files" in m
        assert isinstance(m["files"], dict)
