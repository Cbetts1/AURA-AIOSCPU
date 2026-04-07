"""
AURA-AIOSCPU Kernel Watchdog — Self-Repair
============================================
Monitors all registered services and autonomously restarts any that
have stopped unexpectedly.

Runs in its own daemon thread, independent of the kernel loop.
Communicates exclusively through the event bus.

Lifecycle of a monitored service
---------------------------------
  RUNNING  → (crash) → STOPPED
                         ↓ watchdog detects
                       (backoff timer)
                         ↓ if restartable
                       STARTING → RUNNING    ← success
                                           → failure → record_failure()
                                                         → disabled after max_failures
"""

import logging
import threading
import time

from kernel.event_bus import EventBus, Event, Priority

logger = logging.getLogger(__name__)


class ServiceHealth:
    """Tracks failure state for one service."""

    def __init__(self, name: str, max_failures: int = 3,
                 backoff_ms: int = 5000):
        self.name           = name
        self.max_failures   = max_failures
        self.backoff_ms     = backoff_ms
        self.failure_count  = 0
        self.last_failure:  float | None = None
        self.restart_count  = 0
        self.disabled       = False

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure   = time.monotonic()
        if self.failure_count >= self.max_failures:
            self.disabled = True
            logger.error(
                "Watchdog: service %r permanently disabled after %d failures",
                self.name, self.failure_count,
            )

    def is_restartable(self) -> bool:
        if self.disabled:
            return False
        if self.last_failure is None:
            return True
        elapsed_ms = (time.monotonic() - self.last_failure) * 1000
        return elapsed_ms >= self.backoff_ms

    def to_dict(self) -> dict:
        return {
            "failures":      self.failure_count,
            "restarts":      self.restart_count,
            "disabled":      self.disabled,
        }


class KernelWatchdog:
    """
    Daemon watchdog that monitors services and performs automatic restarts.

    Parameters
    ----------
    event_bus        : system event bus
    service_manager  : the ServiceManager instance to query and restart
    check_interval_ms: how often to poll service states
    max_failures     : failures before a service is permanently disabled
    auto_restart     : set False to observe-only (emit events, no restarts)
    """

    def __init__(self, event_bus: EventBus, service_manager,
                 check_interval_ms: int = 5000,
                 max_failures: int = 3,
                 auto_restart: bool = True):
        self._event_bus       = event_bus
        self._services        = service_manager
        self._interval_ms     = check_interval_ms
        self._max_failures    = max_failures
        self._auto_restart    = auto_restart
        self._health:         dict[str, ServiceHealth] = {}
        self._running         = False
        self._thread:         threading.Thread | None = None

        self._event_bus.subscribe("SERVICE_REGISTERED",
                                  self._on_service_registered)
        self._event_bus.subscribe("SERVICE_STOPPED",
                                  self._on_service_stopped)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="aura-watchdog", daemon=True
        )
        self._thread.start()
        logger.info("KernelWatchdog: started (interval=%dms)", self._interval_ms)

    def stop(self) -> None:
        self._running = False
        logger.info("KernelWatchdog: stopped")

    # ------------------------------------------------------------------
    # Health reporting
    # ------------------------------------------------------------------

    def get_health_report(self) -> dict:
        return {name: h.to_dict() for name, h in self._health.items()}

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while self._running:
            time.sleep(self._interval_ms / 1000.0)
            self._check_cycle()

    def _check_cycle(self) -> None:
        degraded = []
        for name, health in list(self._health.items()):
            state = self._services.status(name)
            if state not in ("running", "registered", "starting") and \
               not health.disabled:
                degraded.append(name)

        self._event_bus.publish(Event(
            "HEALTH_CHECK",
            payload={
                "degraded":      degraded,
                "health_report": self.get_health_report(),
            },
            priority=Priority.LOW,
            source="watchdog",
        ))

        if self._auto_restart:
            for name in degraded:
                self._attempt_restart(name)

    def _attempt_restart(self, name: str) -> None:
        health = self._health.get(name)
        if health is None or not health.is_restartable():
            return
        try:
            state = self._services.status(name)
            if state in ("stopped", "registered"):
                logger.warning("Watchdog: restarting service %r (attempt %d)",
                               name, health.restart_count + 1)
                self._services.start(name)
                health.restart_count += 1
                self._event_bus.publish(Event(
                    "SERVICE_RESTARTING",
                    payload={"name": name,
                             "restart_count": health.restart_count},
                    priority=Priority.HIGH,
                    source="watchdog",
                ))
        except Exception:
            logger.exception("Watchdog: failed to restart %r", name)
            health.record_failure()

    def _on_service_registered(self, event: Event) -> None:
        name = (event.payload or {}).get("name")
        if name and name not in self._health:
            self._health[name] = ServiceHealth(name, self._max_failures)

    def _on_service_stopped(self, event: Event) -> None:
        name = (event.payload or {}).get("name")
        if name:
            logger.debug("Watchdog: noticed service %r stopped", name)
