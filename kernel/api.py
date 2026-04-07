"""
AURA-AIOSCPU Kernel API
========================
The public surface through which services and shell commands interact
with the kernel.

This is the only layer that should call into the kernel internals.
External code (services, plugins, apps) must go through KernelAPI —
never import kernel subsystems directly.

Capabilities checked
--------------------
Every method checks the PermissionModel before acting. If the current
mode does not allow an operation, PermissionDenied is raised.

Thread-safety
-------------
All public methods are safe to call from service threads or the shell thread.
State mutations go through the event bus to maintain the single-writer model.
"""

import logging
import threading

from kernel.permissions import PermissionModel, PermissionDenied

logger = logging.getLogger(__name__)


class KernelAPI:
    """
    Stable public surface for services and apps to interact with the kernel.

    Instantiated by the Kernel and passed to services that need it.
    Never exposes raw kernel internals.
    """

    def __init__(self, kernel, permissions: PermissionModel):
        self._kernel = kernel
        self._perms  = permissions
        self._lock   = threading.Lock()

    # ------------------------------------------------------------------
    # Event bus
    # ------------------------------------------------------------------

    def publish(self, event_type: str, payload: dict | None = None,
                priority: str = "normal") -> None:
        """Publish an event on the kernel event bus."""
        self._perms.check("event.publish")
        from kernel.event_bus import Event, Priority
        pri = {
            "critical": Priority.CRITICAL,
            "high":     Priority.HIGH,
            "normal":   Priority.NORMAL,
            "low":      Priority.LOW,
        }.get(priority.lower(), Priority.NORMAL)
        self._kernel.event_bus.publish(
            Event(event_type, payload=payload or {}, priority=pri,
                  source="kernel_api")
        )

    def subscribe(self, event_type: str, handler) -> None:
        """Subscribe a handler to an event type."""
        self._perms.check("event.subscribe")
        self._kernel.event_bus.subscribe(event_type, handler)

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    def get_service(self, name: str):
        """
        Return a registered service record by name.
        Returns None if not found.
        """
        self._perms.check("service.query")
        return self._kernel.services._registry.get(name)

    def list_services(self) -> dict:
        """Return a {name: state} dict for all registered services."""
        self._perms.check("service.query")
        return {
            name: rec.state
            for name, rec in self._kernel.services._registry.items()
        }

    def start_service(self, name: str) -> bool:
        """Start a registered service. Returns True on success."""
        self._perms.check("service.start")
        return self._kernel.services.start(name)

    def stop_service(self, name: str) -> bool:
        """Stop a running service. Returns True on success."""
        self._perms.check("service.stop")
        return self._kernel.services.stop(name)

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    def submit_task(self, task, priority: int = 5) -> None:
        """Submit a short-lived task to the kernel scheduler."""
        self._perms.check("job.submit")
        self._kernel.scheduler.submit_task(task, priority=priority)

    def schedule_job(self, job, interval_ms: int) -> None:
        """Schedule a periodic background job."""
        self._perms.check("job.submit")
        self._kernel.scheduler.schedule_job(job, interval_ms=interval_ms)

    # ------------------------------------------------------------------
    # AURA
    # ------------------------------------------------------------------

    def aura_query(self, prompt: str) -> str:
        """Route a query to AURA."""
        self._perms.check("aura.query")
        return self._kernel.aura.query(prompt)

    def aura_snapshot(self) -> dict:
        """Return AURA's current system state snapshot."""
        self._perms.check("aura.query")
        return self._kernel.aura.get_state_snapshot()

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def storage_read(self, key: str):
        """Read a value from virtual storage."""
        self._perms.check("fs.read")
        return self._kernel.storage.read(key)

    def storage_write(self, key: str, value) -> None:
        """Write a value to virtual storage."""
        self._perms.check("storage.write")
        self._kernel.storage.write(key, value)

    # ------------------------------------------------------------------
    # System info
    # ------------------------------------------------------------------

    def sysinfo(self) -> dict:
        """Return live system info (tick, mode, services, etc.)."""
        self._perms.check("sysinfo.read")
        return self._kernel.aura.get_state_snapshot()

    # ------------------------------------------------------------------
    # Mode management (tier 3 only)
    # ------------------------------------------------------------------

    def get_mode(self) -> str:
        """Return the current kernel surface mode name."""
        return getattr(getattr(self._kernel, "mode", None), "NAME", "unknown")

    def request_mode_switch(self, new_mode: str,
                            consent_token: str | None = None) -> None:
        """
        Request a kernel mode switch. Publishes a MODE_SWITCH_REQUEST event.
        Hardware mode requires a consent token.
        """
        self._perms.check("kernel.mode_switch")
        payload: dict = {"requested_mode": new_mode}
        if consent_token:
            payload["consent_token"] = consent_token
        self.publish("MODE_SWITCH_REQUEST", payload, priority="high")

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------

    def is_allowed(self, capability: str) -> bool:
        """Check if a capability is currently allowed."""
        return self._perms.is_allowed(capability)

    def grant_capability(self, capability: str) -> None:
        """Grant a runtime capability (after user consent)."""
        self._perms.grant(capability)
        self.publish("CAPABILITY_GRANTED",
                     {"capability": capability}, priority="high")

    def revoke_capability(self, capability: str) -> None:
        """Revoke a previously granted capability."""
        self._perms.revoke(capability)
        self.publish("CAPABILITY_REVOKED",
                     {"capability": capability}, priority="high")

    def permission_summary(self) -> dict:
        """Return a summary of the current permission model state."""
        return self._perms.summary()
