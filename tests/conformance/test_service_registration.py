"""Conformance: Service Registration (Contract 5)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from services import ServiceManager
from kernel.event_bus import EventBus

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SERVICES_DIR = os.path.join(_REPO_ROOT, "services")

REQUIRED_SERVICE_FILES = [
    "network.service",
    "storage.service",
    "logging.service",
    "job-queue.service",
    "health-monitor.service",
]


class TestServiceRegistration:
    def test_service_manager_importable(self):
        from services import ServiceManager  # noqa: F401
        assert ServiceManager

    def test_service_manager_instantiable(self):
        bus = EventBus()
        sm = ServiceManager(bus, services_dir=_SERVICES_DIR)
        assert sm is not None

    @pytest.mark.parametrize("service_file", REQUIRED_SERVICE_FILES)
    def test_required_service_file_exists(self, service_file):
        path = os.path.join(_SERVICES_DIR, service_file)
        assert os.path.isfile(path), f"Missing service file: {service_file}"

    def test_storage_service_importable(self):
        from services.storage_service import StorageService  # noqa: F401
        assert StorageService

    def test_logging_service_importable(self):
        from services.logging_service import LoggingService  # noqa: F401
        assert LoggingService

    def test_job_queue_importable(self):
        from services.job_queue import JobQueue  # noqa: F401
        assert JobQueue

    def test_health_monitor_importable(self):
        from services.health_monitor import HealthMonitor  # noqa: F401
        assert HealthMonitor

    def test_network_service_importable(self):
        from services.network_service import NetworkService  # noqa: F401
        assert NetworkService

    def test_logging_service_has_write_method(self):
        from services.logging_service import LoggingService
        bus = EventBus()
        svc = LoggingService(bus)
        assert hasattr(svc, "write")
        assert callable(svc.write)

    def test_job_queue_has_submit_method(self):
        from services.job_queue import JobQueue
        from kernel.scheduler import Scheduler
        bus = EventBus()
        sch = Scheduler(bus)
        jq = JobQueue(bus, sch)
        assert hasattr(jq, "submit")
        assert callable(jq.submit)

    def test_health_monitor_has_check_all_method(self):
        from services.health_monitor import HealthMonitor
        bus = EventBus()
        sm = ServiceManager(bus, services_dir=_SERVICES_DIR)
        from services.job_queue import JobQueue
        from kernel.scheduler import Scheduler
        sch = Scheduler(bus)
        jq = JobQueue(bus, sch)
        hm = HealthMonitor(bus, sm, jq)
        assert hasattr(hm, "run_check_now") or hasattr(hm, "_check_all")

    def test_service_discover_runs_without_error(self):
        bus = EventBus()
        sm = ServiceManager(bus, services_dir=_SERVICES_DIR)
        sm.discover()  # must not raise
