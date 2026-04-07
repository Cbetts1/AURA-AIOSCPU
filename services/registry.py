"""
AURA-AIOSCPU System Service Registry (SSR)
============================================
Implements the System Service Registry:
  - Loads service descriptors from /etc/aura/services.d/*.service
  - Tracks dependency graph
  - Enforces start order
  - Applies restart policies
  - Reports health
  - Provides service lifecycle API

Service descriptor format (.service files):
  [Service]
  Name=network
  Description=Network connectivity service
  Module=services.network_service:NetworkService
  AutoStart=true
  RestartPolicy=on-failure
  RestartDelay=5
  DependsOn=storage

  [Health]
  CheckInterval=30
  MaxFailures=3
"""

import configparser
import importlib
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

_DEFAULT_SERVICES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "rootfs", "etc", "aura", "services.d",
)


class ServiceState(Enum):
    STOPPED  = "stopped"
    STARTING = "starting"
    RUNNING  = "running"
    FAILED   = "failed"
    DISABLED = "disabled"


class RestartPolicy(Enum):
    NEVER      = "never"
    ALWAYS     = "always"
    ON_FAILURE = "on-failure"


@dataclass
class ServiceDescriptor:
    """Parsed service descriptor."""
    name:           str
    description:    str = ""
    module:         str = ""         # Python module path: "services.foo:FooClass"
    auto_start:     bool = True
    restart_policy: RestartPolicy = RestartPolicy.ON_FAILURE
    restart_delay:  float = 5.0
    depends_on:     list = field(default_factory=list)
    check_interval: float = 30.0
    max_failures:   int = 3
    state:          ServiceState = ServiceState.STOPPED
    failure_count:  int = 0
    started_at:     float = 0.0
    instance:       object = None


class ServiceRegistry:
    """
    System Service Registry.

    Discovers, validates, and manages services defined as .service files.
    """

    def __init__(self, services_dir: str | None = None, event_bus=None):
        self._dir      = services_dir or _DEFAULT_SERVICES_DIR
        self._bus      = event_bus
        self._registry: dict[str, ServiceDescriptor] = {}
        self._load_order: list[str] = []

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> int:
        """Scan services.d/ and load all .service files. Returns count."""
        if not os.path.isdir(self._dir):
            logger.debug("SSR: services dir not found: %s", self._dir)
            return 0
        count = 0
        for fname in sorted(os.listdir(self._dir)):
            if not fname.endswith(".service"):
                continue
            path = os.path.join(self._dir, fname)
            try:
                desc = self._parse_service_file(path)
                self._registry[desc.name] = desc
                count += 1
                logger.debug("SSR: registered service %r", desc.name)
            except Exception as exc:
                logger.warning("SSR: failed to parse %r: %s", fname, exc)
        self._compute_load_order()
        logger.info("SSR: discovered %d services", count)
        return count

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_all_autostart(self, event_bus=None) -> list:
        """Start all services with AutoStart=true, in dependency order."""
        started = []
        for name in self._load_order:
            desc = self._registry.get(name)
            if desc and desc.auto_start:
                if self._start_service(desc, event_bus):
                    started.append(name)
        return started

    def start(self, name: str, event_bus=None) -> bool:
        desc = self._registry.get(name)
        if not desc:
            logger.warning("SSR: unknown service %r", name)
            return False
        return self._start_service(desc, event_bus)

    def stop(self, name: str) -> bool:
        desc = self._registry.get(name)
        if not desc or desc.instance is None:
            return False
        try:
            if hasattr(desc.instance, "stop"):
                desc.instance.stop()
            desc.state    = ServiceState.STOPPED
            desc.instance = None
            self._publish("SERVICE_STOPPED", name)
            return True
        except Exception as exc:
            logger.error("SSR: stop %r failed: %s", name, exc)
            return False

    def restart(self, name: str, event_bus=None) -> bool:
        self.stop(name)
        return self.start(name, event_bus)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_report(self) -> dict:
        return {
            name: {
                "state":         desc.state.value,
                "failure_count": desc.failure_count,
                "started_at":    desc.started_at,
            }
            for name, desc in self._registry.items()
        }

    def get_state(self, name: str):
        desc = self._registry.get(name)
        return desc.state if desc else None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_services(self) -> list:
        return [
            {
                "name":        desc.name,
                "description": desc.description,
                "auto_start":  desc.auto_start,
                "state":       desc.state.value,
                "depends_on":  desc.depends_on,
            }
            for desc in self._registry.values()
        ]

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _start_service(self, desc: ServiceDescriptor, event_bus) -> bool:
        if not desc.module:
            desc.state = ServiceState.RUNNING
            desc.started_at = time.time()
            return True
        try:
            desc.state = ServiceState.STARTING
            module_path, class_name = desc.module.rsplit(":", 1)
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            instance = cls(event_bus or self._bus)
            if hasattr(instance, "start"):
                instance.start()
            desc.instance  = instance
            desc.state     = ServiceState.RUNNING
            desc.started_at = time.time()
            self._publish("SERVICE_STARTED", desc.name)
            return True
        except Exception as exc:
            desc.state         = ServiceState.FAILED
            desc.failure_count += 1
            logger.error("SSR: start %r failed: %s", desc.name, exc)
            self._publish("SERVICE_FAILED", desc.name)
            return False

    def _parse_service_file(self, path: str) -> ServiceDescriptor:
        cp = configparser.ConfigParser()
        cp.read(path)
        s = cp["Service"] if "Service" in cp else {}
        h = cp["Health"]  if "Health"  in cp else {}
        name = s.get("Name", os.path.basename(path).replace(".service", ""))
        depends_raw = s.get("DependsOn", "").strip()
        depends = [d.strip() for d in depends_raw.split(",") if d.strip()]
        policy_raw = s.get("RestartPolicy", "on-failure").strip()
        policy_map = {
            "never":      RestartPolicy.NEVER,
            "always":     RestartPolicy.ALWAYS,
            "on-failure": RestartPolicy.ON_FAILURE,
        }
        return ServiceDescriptor(
            name=name,
            description=s.get("Description", ""),
            module=s.get("Module", ""),
            auto_start=s.get("AutoStart", "true").lower() == "true",
            restart_policy=policy_map.get(policy_raw, RestartPolicy.ON_FAILURE),
            restart_delay=float(s.get("RestartDelay", "5")),
            depends_on=depends,
            check_interval=float(h.get("CheckInterval", "30")),
            max_failures=int(h.get("MaxFailures", "3")),
        )

    def _compute_load_order(self) -> None:
        """Topological sort of services by dependency graph."""
        visited: set = set()
        order:   list = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            desc = self._registry.get(name)
            if desc:
                for dep in desc.depends_on:
                    visit(dep)
            order.append(name)

        for name in self._registry:
            visit(name)
        self._load_order = order

    def _publish(self, event_type: str, service_name: str) -> None:
        if self._bus is None:
            return
        try:
            from kernel.event_bus import Event, Priority
            self._bus.publish(Event(
                event_type,
                payload={"service": service_name},
                priority=Priority.NORMAL,
                source="service_registry",
            ))
        except Exception:
            pass
