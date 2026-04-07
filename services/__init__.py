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

Service unit file (planned format — /services/<name>.service)
--------------------------------------------------------------
  name        = my-service
  entrypoint  = /services/my_service.py
  autostart   = true
  restart     = on-failure
"""

# TODO: from kernel.event_bus import EventBus, Event, Priority

SERVICES_DIR = "/services"


class ServiceState:
    REGISTERED = "registered"
    STARTING   = "starting"
    RUNNING    = "running"
    STOPPING   = "stopping"
    STOPPED    = "stopped"


class ServiceRecord:
    """Holds the runtime state of one registered service."""

    def __init__(self, name: str, unit: dict):
        # TODO: self.name = name
        # TODO: self.unit = unit          ← parsed unit file dict
        # TODO: self.state = ServiceState.REGISTERED
        # TODO: self.process = None       ← running process handle
        pass


class ServiceManager:
    """Discovers, registers, starts, and monitors services."""

    def __init__(self, event_bus, services_dir: str = SERVICES_DIR):
        # TODO: self._event_bus = event_bus
        # TODO: self._services_dir = services_dir
        # TODO: self._registry = {}       ← {name: ServiceRecord}
        pass

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> None:
        """Scan services_dir and register all valid service unit files."""
        # TODO: walk self._services_dir for *.service files
        # TODO: parse each unit file into a dict
        # TODO: call self.register(name, unit) for each valid unit
        pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def register(self, name: str, unit: dict) -> None:
        """Register a parsed service unit without starting it."""
        # TODO: validate unit has required keys (name, entrypoint)
        # TODO: self._registry[name] = ServiceRecord(name, unit)
        # TODO: publish SERVICE_REGISTERED event
        pass

    def start(self, name: str) -> None:
        """Start a registered service."""
        # TODO: look up ServiceRecord; assert state == REGISTERED or STOPPED
        # TODO: transition state → STARTING
        # TODO: launch entrypoint as subprocess / thread
        # TODO: transition state → RUNNING
        # TODO: publish SERVICE_STARTED event
        pass

    def stop(self, name: str) -> None:
        """Stop a running service."""
        # TODO: look up ServiceRecord; assert state == RUNNING
        # TODO: transition state → STOPPING
        # TODO: send termination signal to process
        # TODO: transition state → STOPPED
        # TODO: publish SERVICE_STOPPED event
        pass

    def status(self, name: str) -> str:
        """Return the current state string for a service."""
        # TODO: return self._registry[name].state if name in self._registry
        # TODO: else return "unknown"
        return "unknown"
