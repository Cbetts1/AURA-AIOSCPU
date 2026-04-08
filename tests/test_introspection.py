"""
Tests — SystemIntrospector
============================
"""

import os
import sys
import platform
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aura.introspection import SystemIntrospector, _safe, _storage_status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeMode:
    NAME = "universal"


class _FakeLoop:
    def tick_count(self):
        return 42


class _FakeScheduler:
    _task_queue = [1, 2, 3]
    _job_queue  = [1, 2]


class _FakeModelManager:
    def active_model_name(self):
        return "stub-model"

    @property
    def _registry(self):
        return {"m1": object(), "m2": object()}


class _FakeNetworkService:
    last_status = {"status": "online"}


class _FakeStorageService:
    def status(self):
        return {"state": "running"}


class _FakeServiceManager:
    _registry = {
        "svc-a": type("R", (), {"state": "running"})(),
        "svc-b": type("R", (), {"state": "stopped"})(),
    }


class _FakeLoggingService:
    def get_recent(self, n=20):
        return [f"log line {i}" for i in range(n)]


class _FakeJobQueue:
    def pending_count(self):
        return 7


class _FakeHealthMonitor:
    def last_report(self):
        return {"healthy": 2, "failed": 0}


class _FakeKernel:
    def __init__(self):
        self.mode            = _FakeMode()
        self.loop            = _FakeLoop()
        self.scheduler       = _FakeScheduler()
        self.model_manager   = _FakeModelManager()
        self.network_service = _FakeNetworkService()
        self.storage_service = _FakeStorageService()
        self.storage         = type("S", (), {"_running": True})()
        self.services        = _FakeServiceManager()
        self.logging_service = _FakeLoggingService()
        self.job_queue       = _FakeJobQueue()
        self.health_monitor  = _FakeHealthMonitor()


# ---------------------------------------------------------------------------
# SystemIntrospector — basic instantiation
# ---------------------------------------------------------------------------

class TestSystemIntrospectorBasics:
    def test_instantiates(self):
        si = SystemIntrospector()
        assert si is not None

    def test_attach_kernel(self):
        si = SystemIntrospector()
        k = _FakeKernel()
        si.attach_kernel(k)
        assert si._kernel_ref is k

    def test_snapshot_without_kernel(self):
        si = SystemIntrospector()
        snap = si.snapshot()
        assert isinstance(snap, dict)
        assert "uptime_s" in snap
        assert "platform" in snap
        assert "arch" in snap
        assert "python" in snap
        assert "pid" in snap
        assert "timestamp" in snap

    def test_snapshot_uptime_non_negative(self):
        si = SystemIntrospector()
        snap = si.snapshot()
        assert snap["uptime_s"] >= 0.0

    def test_snapshot_pid_positive(self):
        si = SystemIntrospector()
        assert si.snapshot()["pid"] == os.getpid()

    def test_snapshot_platform_string(self):
        si = SystemIntrospector()
        assert si.snapshot()["platform"] == platform.system()


# ---------------------------------------------------------------------------
# SystemIntrospector — snapshot with kernel
# ---------------------------------------------------------------------------

class TestSystemIntrospectorWithKernel:
    def _make(self):
        si = SystemIntrospector()
        si.attach_kernel(_FakeKernel())
        return si

    def test_snapshot_mode(self):
        si = self._make()
        snap = si.snapshot()
        assert snap.get("mode") == "universal"

    def test_snapshot_tick(self):
        si = self._make()
        snap = si.snapshot()
        assert snap.get("tick") == 42

    def test_snapshot_service_count(self):
        si = self._make()
        snap = si.snapshot()
        assert snap.get("service_count") == 2

    def test_snapshot_services_dict(self):
        si = self._make()
        snap = si.snapshot()
        svcs = snap.get("services", {})
        assert "svc-a" in svcs
        assert "svc-b" in svcs

    def test_snapshot_active_model(self):
        si = self._make()
        snap = si.snapshot()
        assert snap.get("active_model") == "stub-model"

    def test_snapshot_models_available(self):
        si = self._make()
        snap = si.snapshot()
        assert snap.get("models_available") == 2

    def test_snapshot_network_status(self):
        si = self._make()
        snap = si.snapshot()
        assert snap.get("network_status") == "online"

    def test_snapshot_storage_status(self):
        si = self._make()
        snap = si.snapshot()
        assert snap.get("storage_status") == "running"

    def test_snapshot_task_queue_depth(self):
        si = self._make()
        snap = si.snapshot()
        assert snap.get("task_queue_depth") == 3

    def test_snapshot_job_queue_depth(self):
        si = self._make()
        snap = si.snapshot()
        assert snap.get("job_queue_depth") == 2


# ---------------------------------------------------------------------------
# describe()
# ---------------------------------------------------------------------------

class TestSystemIntrospectorDescribe:
    def test_describe_without_kernel_returns_string(self):
        si = SystemIntrospector()
        d = si.describe()
        assert isinstance(d, str)
        assert len(d) > 10

    def test_describe_with_kernel_includes_mode(self):
        si = SystemIntrospector()
        si.attach_kernel(_FakeKernel())
        d = si.describe()
        assert "universal" in d

    def test_describe_includes_services_section(self):
        si = SystemIntrospector()
        si.attach_kernel(_FakeKernel())
        d = si.describe()
        assert "svc-a" in d or "Service" in d


# ---------------------------------------------------------------------------
# list_services()
# ---------------------------------------------------------------------------

class TestSystemIntrospectorListServices:
    def test_list_services_without_kernel_empty(self):
        si = SystemIntrospector()
        assert si.list_services() == {}

    def test_list_services_with_kernel(self):
        si = SystemIntrospector()
        si.attach_kernel(_FakeKernel())
        svcs = si.list_services()
        assert "svc-a" in svcs


# ---------------------------------------------------------------------------
# get_recent_logs()
# ---------------------------------------------------------------------------

class TestSystemIntrospectorRecentLogs:
    def test_recent_logs_without_kernel_empty(self):
        si = SystemIntrospector()
        assert si.get_recent_logs() == []

    def test_recent_logs_with_kernel(self):
        si = SystemIntrospector()
        si.attach_kernel(_FakeKernel())
        logs = si.get_recent_logs(5)
        assert isinstance(logs, list)
        assert len(logs) == 5

    def test_recent_logs_no_logging_service_returns_empty(self):
        si = SystemIntrospector()
        k = _FakeKernel()
        del k.logging_service
        si.attach_kernel(k)
        logs = si.get_recent_logs()
        assert logs == []


# ---------------------------------------------------------------------------
# get_job_queue_depth()
# ---------------------------------------------------------------------------

class TestSystemIntrospectorJobQueueDepth:
    def test_without_kernel_returns_zero(self):
        si = SystemIntrospector()
        assert si.get_job_queue_depth() == 0

    def test_with_job_queue_service(self):
        si = SystemIntrospector()
        si.attach_kernel(_FakeKernel())
        depth = si.get_job_queue_depth()
        assert depth == 7

    def test_fallback_to_scheduler_job_queue(self):
        si = SystemIntrospector()
        k = _FakeKernel()
        del k.job_queue
        si.attach_kernel(k)
        depth = si.get_job_queue_depth()
        assert depth == 2   # _FakeScheduler._job_queue has 2 items


# ---------------------------------------------------------------------------
# get_storage_info()
# ---------------------------------------------------------------------------

class TestSystemIntrospectorStorageInfo:
    def test_without_kernel_returns_empty(self):
        si = SystemIntrospector()
        assert si.get_storage_info() == {}

    def test_with_storage_service(self):
        si = SystemIntrospector()
        si.attach_kernel(_FakeKernel())
        info = si.get_storage_info()
        assert info.get("state") == "running"

    def test_no_storage_service_returns_empty(self):
        si = SystemIntrospector()
        k = _FakeKernel()
        del k.storage_service
        si.attach_kernel(k)
        assert si.get_storage_info() == {}


# ---------------------------------------------------------------------------
# get_health_summary()
# ---------------------------------------------------------------------------

class TestSystemIntrospectorHealthSummary:
    def test_without_kernel_returns_empty(self):
        si = SystemIntrospector()
        assert si.get_health_summary() == {}

    def test_with_health_monitor(self):
        si = SystemIntrospector()
        si.attach_kernel(_FakeKernel())
        summary = si.get_health_summary()
        assert summary.get("healthy") == 2

    def test_no_health_monitor_returns_empty(self):
        si = SystemIntrospector()
        k = _FakeKernel()
        del k.health_monitor
        si.attach_kernel(k)
        assert si.get_health_summary() == {}


# ---------------------------------------------------------------------------
# _safe helper
# ---------------------------------------------------------------------------

class TestSafeHelper:
    def test_stores_value_on_success(self):
        d = {}
        _safe(d, "key", lambda: 42)
        assert d["key"] == 42

    def test_does_not_raise_on_exception(self):
        d = {}
        _safe(d, "key", lambda: 1 / 0)  # ZeroDivisionError is silenced
        assert "key" not in d

    def test_stores_none_if_fn_returns_none(self):
        d = {}
        _safe(d, "k", lambda: None)
        assert d["k"] is None


# ---------------------------------------------------------------------------
# _storage_status helper
# ---------------------------------------------------------------------------

class TestStorageStatusHelper:
    def test_returns_state_from_storage_service(self):
        k = _FakeKernel()
        assert _storage_status(k) == "running"

    def test_fallback_to_storage_device(self):
        k = _FakeKernel()
        del k.storage_service
        # _FakeKernel.storage._running is True → "mounted"
        result = _storage_status(k)
        assert result == "mounted"

    def test_returns_unknown_on_exception(self):
        k = type("K", (), {})()
        # No attributes at all
        assert _storage_status(k) == "unknown"
