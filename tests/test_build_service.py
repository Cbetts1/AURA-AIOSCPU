"""Tests for services.build_service — BuildService self-build and repair."""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.event_bus import EventBus, Event, Priority
from services.build_service import BuildService, BuildResult, _sha256


# ---------------------------------------------------------------------------
# BuildResult unit tests
# ---------------------------------------------------------------------------

def test_build_result_success():
    r = BuildResult(True, "ok", 1.23)
    assert r.success is True
    assert r.message == "ok"
    assert r.duration_s == pytest.approx(1.23)


def test_build_result_to_dict():
    r = BuildResult(False, "fail", 0.5)
    d = r.to_dict()
    assert d["success"]    is False
    assert d["message"]    == "fail"
    assert d["duration_s"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# _sha256 helper
# ---------------------------------------------------------------------------

def test_sha256_deterministic(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"hello world")
    h1 = _sha256(f)
    h2 = _sha256(f)
    assert h1 == h2
    assert len(h1) == 64


def test_sha256_different_content_different_hash(tmp_path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_bytes(b"aaa")
    f2.write_bytes(b"bbb")
    assert _sha256(f1) != _sha256(f2)


# ---------------------------------------------------------------------------
# BuildService tests
# ---------------------------------------------------------------------------

@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def build_svc(bus, tmp_path):
    """BuildService rooted at a temp copy of the repo root."""
    import shutil
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Point to the real repo root so copytree finds source files
    svc = BuildService(bus, repo_root=repo)
    return svc


def test_build_service_instantiates(build_svc):
    assert build_svc is not None


def test_last_build_status_none_before_build(build_svc):
    assert build_svc.last_build_status() is None


def test_get_build_log_empty_initially(build_svc):
    assert build_svc.get_build_log() == []


def test_verify_integrity_returns_dict(build_svc):
    report = build_svc.verify_integrity()
    assert "total_files"   in report
    assert "changed_files" in report
    assert "integrity_ok"  in report


def test_verify_integrity_total_files_positive(build_svc):
    report = build_svc.verify_integrity()
    assert report["total_files"] > 0


def test_verify_integrity_changed_files_is_list(build_svc):
    report = build_svc.verify_integrity()
    assert isinstance(report["changed_files"], list)


def test_rebuild_rootfs_returns_result(build_svc):
    result = build_svc.rebuild_rootfs()
    assert result is not None
    assert isinstance(result.success, bool)


def test_rebuild_rootfs_success(build_svc):
    result = build_svc.rebuild_rootfs()
    assert result.success is True


def test_rebuild_rootfs_creates_dist(build_svc):
    build_svc.rebuild_rootfs()
    dist = os.path.join(build_svc._root, "dist")
    assert os.path.isdir(dist)


def test_rebuild_rootfs_creates_manifest(build_svc):
    build_svc.rebuild_rootfs()
    manifest = os.path.join(build_svc._root, "dist", "manifest.json")
    assert os.path.exists(manifest)
    with open(manifest) as fh:
        data = json.load(fh)
    assert "build_time"   in data
    assert "total_files"  in data
    assert "files"        in data


def test_rebuild_rootfs_creates_launcher(build_svc):
    build_svc.rebuild_rootfs()
    launcher = os.path.join(build_svc._root, "dist", "aura")
    assert os.path.exists(launcher)


def test_rebuild_rootfs_duration_positive(build_svc):
    result = build_svc.rebuild_rootfs()
    assert result.duration_s > 0


def test_rebuild_populates_build_log(build_svc):
    build_svc.rebuild_rootfs()
    log = build_svc.get_build_log()
    assert len(log) > 0


def test_rebuild_publishes_started_event(bus, build_svc):
    received = []
    bus.subscribe("BUILD_STARTED", lambda e: received.append(e))
    build_svc.rebuild_rootfs()
    bus.drain()
    assert len(received) >= 1


def test_rebuild_publishes_complete_event(bus, build_svc):
    received = []
    bus.subscribe("BUILD_COMPLETE", lambda e: received.append(e))
    build_svc.rebuild_rootfs()
    bus.drain()
    assert len(received) >= 1
    assert received[0].payload["success"] is True


def test_rebuild_concurrent_lock(bus):
    """A second concurrent rebuild should fail immediately."""
    svc = BuildService(bus)
    # Acquire the lock directly to simulate a running build
    svc._lock.acquire()
    try:
        result = svc.rebuild_rootfs()
        assert result.success is False
        assert "in progress" in result.message.lower()
    finally:
        svc._lock.release()


def test_rebuild_last_build_status_after_build(build_svc):
    build_svc.rebuild_rootfs()
    status = build_svc.last_build_status()
    assert status is not None
    assert "success" in status


def test_run_tests_returns_result(bus, tmp_path, monkeypatch):
    """run_tests() should return a BuildResult without executing subprocess."""
    import subprocess
    svc = BuildService(bus, repo_root=str(tmp_path))
    # Stub subprocess.run to avoid a real pytest invocation
    monkeypatch.setattr(
        "services.build_service.subprocess.run",
        lambda *a, **kw: type("R", (), {"returncode": 0,
                                        "stdout": "1 passed\n",
                                        "stderr": ""})(),
    )
    result = svc.run_tests()
    assert result is not None
    assert isinstance(result.success, bool)


def test_run_tests_publishes_complete_event(bus, tmp_path, monkeypatch):
    received = []
    bus.subscribe("TEST_COMPLETE", lambda e: received.append(e))
    svc = BuildService(bus, repo_root=str(tmp_path))
    monkeypatch.setattr(
        "services.build_service.subprocess.run",
        lambda *a, **kw: type("R", (), {"returncode": 0,
                                        "stdout": "1 passed\n",
                                        "stderr": ""})(),
    )
    svc.run_tests()
    bus.drain()
    assert len(received) >= 1


def test_integrity_alert_event_on_change(bus, build_svc, tmp_path):
    """If a file changed since last build, INTEGRITY_ALERT should fire."""
    # First build creates manifest
    build_svc.rebuild_rootfs()

    alerts = []
    bus.subscribe("INTEGRITY_ALERT", lambda e: alerts.append(e))

    # Corrupt a source file's manifest entry manually
    manifest_path = os.path.join(build_svc._root, "dist", "manifest.json")
    with open(manifest_path) as fh:
        data = json.load(fh)
    # Set a wrong hash for the first file in the manifest
    first_key = next(iter(data.get("files", {})))
    data["files"][first_key] = "0" * 64
    with open(manifest_path, "w") as fh:
        json.dump(data, fh)

    build_svc.verify_integrity()
    bus.drain()
    assert len(alerts) >= 1
