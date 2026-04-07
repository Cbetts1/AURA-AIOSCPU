"""
AURA-AIOSCPU Service Manager
=============================
Loads, starts, monitors, and stops services from /services.

A service is a long-lived background process described by a plain-text
service unit file. Services must not communicate directly with each other —
all inter-service messaging goes through the event bus.

Service lifecycle
-----------------
  REGISTERED → STARTING → RUNNING → STOPPING → STOPPED

Service unit file format — /services/<name>.service
-----------------------------------------------------
  name        = my-service
  entrypoint  = /services/my_service.py
  autostart   = true
  restart     = on-failure
"""

import logging
import os
import subprocess
import threading
from pathlib import Path

from kernel.event_bus import EventBus, Event, Priority

logger = logging.getLogger(__name__)

SERVICES_DIR = "/services"
REQUIRED_UNIT_KEYS = {"name", "entrypoint"}


class ServiceState:
    REGISTERED = "registered"
    STARTING   = "starting"
    RUNNING    = "running"
    STOPPING   = "stopping"
    STOPPED    = "stopped"


class ServiceRecord:
    """Holds the runtime state of one registered service."""

    def __init__(self, name: str, unit: dict):
        self.name = name
        self.unit = unit
        self.state = ServiceState.REGISTERED
        self.thread: threading.Thread | None = None

    def __repr__(self):
        return f"ServiceRecord(name={self.name!r}, state={self.state!r})"


def _parse_unit_file(path: str) -> dict:
    """Parse a simple key=value service unit file into a dict."""
    unit: dict[str, str] = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                unit[key.strip()] = value.strip()
    return unit


class ServiceManager:
    """Discovers, registers, starts, and monitors services."""

    def __init__(self, event_bus: EventBus,
                 services_dir: str = SERVICES_DIR):
        self._event_bus = event_bus
        self._services_dir = services_dir
        self._registry: dict[str, ServiceRecord] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> None:
        """Scan services_dir and register all valid service unit files."""
        sdir = Path(self._services_dir)
        if not sdir.is_dir():
            logger.warning("ServiceManager: services dir %r not found", str(sdir))
            return
        for unit_path in sdir.glob("*.service"):
            try:
                unit = _parse_unit_file(str(unit_path))
                name = unit.get("name", unit_path.stem)
                self.register(name, unit)
            except Exception:
                logger.exception("ServiceManager: failed to parse %r", str(unit_path))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def register(self, name: str, unit: dict) -> None:
        """Register a parsed service unit without starting it."""
        missing = REQUIRED_UNIT_KEYS - set(unit)
        if missing:
            raise ValueError(
                f"Service unit {name!r} missing required keys: {missing}"
            )
        self._registry[name] = ServiceRecord(name, unit)
        self._event_bus.publish(
            Event("SERVICE_REGISTERED", payload={"name": name},
                  priority=Priority.NORMAL, source="service_manager")
        )
        logger.info("ServiceManager: registered %r", name)

    def start(self, name: str) -> None:
        """Start a registered service in a daemon thread."""
        record = self._registry.get(name)
        if record is None:
            raise KeyError(f"Unknown service: {name!r}")
        if record.state not in (ServiceState.REGISTERED, ServiceState.STOPPED):
            raise RuntimeError(
                f"Cannot start service {name!r} from state {record.state!r}"
            )

        record.state = ServiceState.STARTING
        entrypoint = record.unit["entrypoint"]

        def _run():
            record.state = ServiceState.RUNNING
            self._event_bus.publish(
                Event("SERVICE_STARTED", payload={"name": name},
                      priority=Priority.NORMAL, source="service_manager")
            )
            logger.info("ServiceManager: started %r", name)
            try:
                # Run the entrypoint as a subprocess if it's a file path,
                # otherwise treat as a Python import path (future).
                if os.path.isfile(entrypoint):
                    subprocess.run(["python", entrypoint], check=False)
                else:
                    logger.warning(
                        "ServiceManager: entrypoint %r not found, "
                        "service %r running as no-op stub", entrypoint, name
                    )
            except Exception:
                logger.exception("ServiceManager: error in service %r", name)
            finally:
                record.state = ServiceState.STOPPED
                self._event_bus.publish(
                    Event("SERVICE_STOPPED", payload={"name": name},
                          priority=Priority.NORMAL, source="service_manager")
                )

        record.thread = threading.Thread(target=_run, name=f"svc-{name}",
                                         daemon=True)
        record.thread.start()

    def stop(self, name: str) -> None:
        """Signal a running service to stop and wait for it."""
        record = self._registry.get(name)
        if record is None:
            raise KeyError(f"Unknown service: {name!r}")
        if record.state != ServiceState.RUNNING:
            raise RuntimeError(
                f"Cannot stop service {name!r} from state {record.state!r}"
            )
        record.state = ServiceState.STOPPING
        if record.thread and record.thread.is_alive():
            record.thread.join(timeout=5.0)
        record.state = ServiceState.STOPPED
        self._event_bus.publish(
            Event("SERVICE_STOPPED", payload={"name": name},
                  priority=Priority.NORMAL, source="service_manager")
        )
        logger.info("ServiceManager: stopped %r", name)

    def status(self, name: str) -> str:
        """Return the current state string for a service."""
        record = self._registry.get(name)
        return record.state if record is not None else "unknown"

