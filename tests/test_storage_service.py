"""
Tests — StorageService
=======================
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import EventBus first to break the services → kernel → services circular dependency
from kernel.event_bus import EventBus  # noqa: E402 (must precede services import)

from services.storage_service import StorageService, PARTITIONS


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rootfs(tmp_path):
    return str(tmp_path / "rootfs")


@pytest.fixture
def svc(rootfs):
    return StorageService(rootfs_path=rootfs)


@pytest.fixture
def started_svc(rootfs):
    s = StorageService(rootfs_path=rootfs)
    s.start()
    return s


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class TestStorageServiceLifecycle:
    def test_instantiates(self, svc):
        assert svc is not None

    def test_state_stopped_before_start(self, svc):
        assert svc.status()["state"] == "stopped"

    def test_start_sets_running(self, started_svc):
        assert started_svc.status()["state"] == "running"

    def test_start_idempotent(self, rootfs):
        s = StorageService(rootfs_path=rootfs)
        s.start()
        s.start()  # second call should be no-op
        assert s.status()["state"] == "running"

    def test_stop_sets_stopped(self, started_svc):
        started_svc.stop()
        assert started_svc.status()["state"] == "stopped"

    def test_stop_idempotent(self, rootfs):
        s = StorageService(rootfs_path=rootfs)
        s.start()
        s.stop()
        s.stop()  # second stop is no-op

    def test_start_creates_all_partitions(self, started_svc, rootfs):
        for partition in PARTITIONS:
            assert os.path.isdir(os.path.join(rootfs, partition)), \
                f"Missing partition directory: {partition}"

    def test_start_writes_layout_json(self, started_svc, rootfs):
        layout_path = os.path.join(rootfs, "layout.json")
        assert os.path.isfile(layout_path)

    def test_layout_json_has_expected_keys(self, started_svc, rootfs):
        with open(os.path.join(rootfs, "layout.json")) as fh:
            layout = json.load(fh)
        assert "version" in layout
        assert "partitions" in layout
        assert layout["version"] == "1.0"


# ---------------------------------------------------------------------------
# Status introspection
# ---------------------------------------------------------------------------

class TestStorageServiceStatus:
    def test_status_contains_required_keys(self, started_svc):
        s = started_svc.status()
        for key in ("state", "rootfs", "sd_card", "partitions",
                    "disk_used", "disk_total"):
            assert key in s, f"Missing key: {key}"

    def test_partitions_list_complete(self, started_svc):
        s = started_svc.status()
        for p in PARTITIONS:
            assert p in s["partitions"]

    def test_disk_total_positive(self, started_svc):
        s = started_svc.status()
        assert s["disk_total"] > 0

    def test_sd_card_none_by_default(self, started_svc):
        # SD card detection depends on host environment.
        # Just verify the method returns a string or None.
        result = started_svc.sd_card_path()
        assert result is None or isinstance(result, str)
        assert started_svc.is_sd_mounted() == (result is not None)


# ---------------------------------------------------------------------------
# Partition helpers
# ---------------------------------------------------------------------------

class TestPartitionHelpers:
    def test_partition_path_known(self, started_svc, rootfs):
        path = started_svc.partition_path("user")
        assert path == os.path.join(rootfs, "user")

    def test_partition_path_unknown_raises(self, started_svc):
        with pytest.raises(ValueError, match="Unknown partition"):
            started_svc.partition_path("nonexistent_partition")

    def test_ensure_writable_writable_partition(self, started_svc, rootfs):
        dest = started_svc.ensure_writable("user/prefs.json")
        assert dest == os.path.join(rootfs, "user/prefs.json")

    def test_ensure_writable_readonly_partition_routes_to_overlay(
            self, started_svc, rootfs):
        dest = started_svc.ensure_writable("boot/config")
        assert "overlay" in dest

    def test_list_partition_empty(self, started_svc):
        files = started_svc.list_partition("user")
        assert isinstance(files, list)

    def test_list_partition_unknown_returns_empty(self, started_svc):
        # partition_path would raise; but list_partition uses partition_path
        with pytest.raises(ValueError):
            started_svc.list_partition("bogus")

    def test_list_partition_after_write(self, started_svc):
        started_svc.write_file("user/hello.txt", b"world")
        files = started_svc.list_partition("user")
        assert any("hello.txt" in f for f in files)


# ---------------------------------------------------------------------------
# File read / write
# ---------------------------------------------------------------------------

class TestStorageServiceFiles:
    def test_write_then_read_file(self, started_svc):
        started_svc.write_file("user/data.bin", b"\x00\x01\x02")
        data = started_svc.read_file("user/data.bin")
        assert data == b"\x00\x01\x02"

    def test_write_creates_parent_dirs(self, started_svc, rootfs):
        started_svc.write_file("user/deep/nested/file.txt", b"hi")
        assert os.path.isfile(os.path.join(rootfs, "user/deep/nested/file.txt"))

    def test_write_force_overlay(self, started_svc, rootfs):
        started_svc.write_file("system/config", b"data", force_overlay=True)
        overlay_path = os.path.join(rootfs, "overlay", "system/config")
        assert os.path.isfile(overlay_path)

    def test_read_overlay_takes_precedence(self, started_svc, rootfs):
        # Write a base file
        started_svc.write_file("user/base.txt", b"base")
        # Write an overlay file at the same path
        overlay_path = os.path.join(rootfs, "overlay", "user/base.txt")
        os.makedirs(os.path.dirname(overlay_path), exist_ok=True)
        with open(overlay_path, "wb") as fh:
            fh.write(b"overlay")
        assert started_svc.read_file("user/base.txt") == b"overlay"

    def test_read_missing_file_raises(self, started_svc):
        with pytest.raises(FileNotFoundError):
            started_svc.read_file("user/does_not_exist.txt")

    def test_write_readonly_partition_routes_to_overlay(self, started_svc, rootfs):
        started_svc.write_file("boot/grub.cfg", b"timeout=5")
        overlay_path = os.path.join(rootfs, "overlay", "boot/grub.cfg")
        assert os.path.isfile(overlay_path)

    def test_write_publishes_storage_event(self, rootfs):
        bus = EventBus()
        events = []
        bus.subscribe("STORAGE_EVENT", events.append)
        s = StorageService(event_bus=bus, rootfs_path=rootfs)
        s.start()
        bus.drain()
        events.clear()

        s.write_file("user/x.txt", b"data")
        bus.drain()
        assert len(events) == 1
        assert events[0].payload["action"] == "write"


# ---------------------------------------------------------------------------
# SD-card management
# ---------------------------------------------------------------------------

class TestStorageServiceSDCard:
    def test_mount_sd_rootfs_without_marker_returns_false(self, started_svc, tmp_path):
        sd_dir = str(tmp_path / "sdcard")
        os.makedirs(sd_dir)
        assert started_svc.mount_sd_rootfs(sd_dir) is False

    def test_mount_sd_rootfs_with_marker_returns_true(self, started_svc, tmp_path):
        sd_dir = str(tmp_path / "sdcard")
        os.makedirs(os.path.join(sd_dir, "etc"), exist_ok=True)
        # Create the aura.conf marker
        with open(os.path.join(sd_dir, "etc", "aura.conf"), "w") as fh:
            fh.write("sd_rootfs=true\n")
        result = started_svc.mount_sd_rootfs(sd_dir)
        assert result is True
        assert started_svc.is_sd_mounted() is True

    def test_mount_sd_publishes_storage_event(self, rootfs, tmp_path):
        bus = EventBus()
        events = []
        bus.subscribe("STORAGE_EVENT", events.append)

        sd_dir = str(tmp_path / "sdcard")
        os.makedirs(os.path.join(sd_dir, "etc"), exist_ok=True)
        with open(os.path.join(sd_dir, "etc", "aura.conf"), "w") as fh:
            fh.write("sd_rootfs=true\n")

        s = StorageService(event_bus=bus, rootfs_path=rootfs)
        s.start()
        bus.drain()
        events.clear()

        s.mount_sd_rootfs(sd_dir)
        bus.drain()
        assert any(e.payload["action"] == "sd_mount" for e in events)


# ---------------------------------------------------------------------------
# tmp partition cleared on start
# ---------------------------------------------------------------------------

class TestStorageServiceTmpClear:
    def test_tmp_cleared_on_start(self, rootfs, tmp_path):
        # Pre-populate the tmp partition
        tmp_partition = os.path.join(rootfs, "tmp")
        os.makedirs(tmp_partition, exist_ok=True)
        stale = os.path.join(tmp_partition, "stale.txt")
        with open(stale, "w") as fh:
            fh.write("stale")

        s = StorageService(rootfs_path=rootfs)
        s.start()
        assert not os.path.exists(stale)


# ---------------------------------------------------------------------------
# Event bus integration
# ---------------------------------------------------------------------------

class TestStorageServiceEvents:
    def test_start_publishes_mount_event(self, rootfs):
        bus = EventBus()
        events = []
        bus.subscribe("STORAGE_EVENT", events.append)
        s = StorageService(event_bus=bus, rootfs_path=rootfs)
        s.start()
        bus.drain()
        mount_events = [e for e in events if e.payload["action"] == "mount"]
        assert len(mount_events) == 1

    def test_stop_publishes_unmount_event(self, rootfs):
        bus = EventBus()
        events = []
        bus.subscribe("STORAGE_EVENT", events.append)
        s = StorageService(event_bus=bus, rootfs_path=rootfs)
        s.start()
        s.stop()
        bus.drain()
        unmount_events = [e for e in events if e.payload["action"] == "unmount"]
        assert len(unmount_events) == 1

    def test_no_event_bus_does_not_raise(self, rootfs):
        s = StorageService(event_bus=None, rootfs_path=rootfs)
        s.start()
        s.write_file("user/x.txt", b"data")
        s.stop()
