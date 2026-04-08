"""Tests for BuildService snapshot and rollback functionality."""

import json
import os
import sys
import tarfile
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.event_bus import EventBus
from services.build_service import BuildService


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def build_svc(bus):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return BuildService(bus, repo_root=repo)


# ---------------------------------------------------------------------------
# verify_integrity — has_baseline field
# ---------------------------------------------------------------------------

def test_verify_integrity_has_baseline_false_without_manifest(build_svc, tmp_path):
    """When no manifest exists, has_baseline must be False."""
    svc = BuildService(EventBus(), repo_root=str(tmp_path))
    # Create a minimal Python file so total_files > 0
    (tmp_path / "dummy.py").write_text("x = 1\n")
    report = svc.verify_integrity()
    assert "has_baseline" in report
    assert report["has_baseline"] is False
    assert report["integrity_ok"] is False


def test_verify_integrity_has_baseline_true_after_build(build_svc):
    """After a build the manifest exists so has_baseline must be True."""
    build_svc.rebuild_rootfs()
    report = build_svc.verify_integrity()
    assert report["has_baseline"] is True
    assert report["integrity_ok"] is True


def test_verify_integrity_integrity_ok_false_on_drift(build_svc):
    """After build, patching the manifest causes integrity_ok=False."""
    build_svc.rebuild_rootfs()
    manifest_path = os.path.join(build_svc._root, "dist", "manifest.json")
    with open(manifest_path) as fh:
        data = json.load(fh)
    first_key = next(iter(data.get("files", {})))
    data["files"][first_key] = "0" * 64
    with open(manifest_path, "w") as fh:
        json.dump(data, fh)
    report = build_svc.verify_integrity()
    assert report["integrity_ok"] is False
    assert report["has_baseline"] is True


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

class TestBuildServiceSnapshot:

    def test_snapshot_returns_success(self, build_svc):
        result = build_svc.snapshot(label="test")
        assert result["success"] is True
        assert result["snapshot_id"].endswith("_test")

    def test_snapshot_creates_tarball(self, build_svc):
        result = build_svc.snapshot()
        assert os.path.isfile(result["path"])
        assert result["path"].endswith(".tar.gz")

    def test_snapshot_tarball_contains_rootfs(self, build_svc):
        result = build_svc.snapshot()
        with tarfile.open(result["path"], "r:gz") as tar:
            names = tar.getnames()
        assert any("rootfs" in n for n in names)

    def test_snapshot_size_positive(self, build_svc):
        result = build_svc.snapshot()
        assert result["size_bytes"] > 0


# ---------------------------------------------------------------------------
# list_snapshots
# ---------------------------------------------------------------------------

class TestListSnapshots:

    def test_list_snapshots_empty_before_any(self, bus, tmp_path):
        svc = BuildService(bus, repo_root=str(tmp_path))
        # Ensure rootfs dir exists
        (tmp_path / "rootfs").mkdir()
        assert svc.list_snapshots() == []

    def test_list_snapshots_returns_created(self, build_svc):
        n_before = len(build_svc.list_snapshots())
        build_svc.snapshot(label="snap1")
        build_svc.snapshot(label="snap2")
        snapshots = build_svc.list_snapshots()
        assert len(snapshots) >= n_before + 2
        ids = [s["snapshot_id"] for s in snapshots]
        assert any("snap1" in i for i in ids)
        assert any("snap2" in i for i in ids)

    def test_list_snapshots_have_required_keys(self, build_svc):
        build_svc.snapshot(label="meta")
        snapshots = build_svc.list_snapshots()
        assert snapshots
        for s in snapshots:
            assert "snapshot_id" in s
            assert "path" in s
            assert "size_bytes" in s


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------

class TestBuildServiceRollback:

    def test_rollback_missing_snapshot_fails(self, build_svc):
        result = build_svc.rollback("nonexistent_snapshot_id")
        assert result["success"] is False
        assert "not found" in result["message"].lower()

    def test_rollback_restores_rootfs(self, build_svc, tmp_path):
        """Create a snapshot, modify rootfs, rollback, verify restoration."""
        # Take a snapshot of the current rootfs
        snap = build_svc.snapshot(label="rollback_test")
        assert snap["success"]

        # Introduce a sentinel file into rootfs
        sentinel = os.path.join(build_svc._root, "rootfs", "_rollback_test_sentinel")
        with open(sentinel, "w") as fh:
            fh.write("this should be gone after rollback")
        assert os.path.exists(sentinel)

        # Rollback
        result = build_svc.rollback(snap["snapshot_id"])
        assert result["success"] is True, result["message"]

        # Sentinel should no longer exist
        assert not os.path.exists(sentinel)
