"""
AURA-AIOSCPU Health Monitor
==============================
Monitors service health, detects failures, and triggers self-healing.

Design
------
- Runs health checks on all registered services every check_interval_s.
- Detects stopped/crashed services and publishes HEALTH_REPORT events.
- Submits self-repair jobs to the JobQueue when failures are detected.
- Tracks consecutive failure counts per service (circuit breaker pattern).
- Publishes an INTEGRITY_ALERT if the failure rate exceeds thresholds.

Circuit breaker
---------------
  CLOSED   → service healthy, checks passing
  OPEN     → too many consecutive failures, self-repair submitted
  HALF_OPEN → repair submitted, waiting for recovery confirmation

Events published
----------------
  HEALTH_REPORT   { healthy, degraded, failed, services, timestamp }
  INTEGRITY_ALERT { service, failures, action }
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

_DEFAULT_CHECK_S    = 30.0
_DEFAULT_MAX_FAIL   = 3      # consecutive failures before circuit opens
_CIRCUIT_RESET_S    = 60.0   # time before a half-open circuit is retried


class ServiceHealth:
    """Per-service health tracking."""

    CLOSED    = "closed"     # healthy
    OPEN      = "open"       # too many failures — repair queued
    HALF_OPEN = "half_open"  # repair queued, awaiting recovery

    def __init__(self, name: str):
        self.name            = name
        self.circuit         = self.CLOSED
        self.consecutive_failures = 0
        self.last_check_ts   = 0.0
        self.last_failure_ts = 0.0
        self.total_checks    = 0
        self.total_failures  = 0
        self.last_state      = "unknown"

    def record_healthy(self) -> None:
        self.consecutive_failures = 0
        self.circuit = self.CLOSED
        self.total_checks += 1

    def record_failure(self, max_failures: int) -> bool:
        """Record a failure. Returns True if circuit just opened."""
        self.consecutive_failures += 1
        self.total_failures += 1
        self.total_checks += 1
        self.last_failure_ts = time.time()
        if (self.circuit == self.CLOSED
                and self.consecutive_failures >= max_failures):
            self.circuit = self.OPEN
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "circuit":              self.circuit,
            "consecutive_failures": self.consecutive_failures,
            "total_failures":       self.total_failures,
            "total_checks":         self.total_checks,
            "last_state":           self.last_state,
        }


class HealthMonitor:
    """
    Background service health monitor with self-repair capability.

    Integrates with ServiceManager (to query/restart services) and
    JobQueue (to schedule repair tasks asynchronously).
    """

    def __init__(self, event_bus=None, service_manager=None,
                 job_queue=None,
                 check_interval_s: float = _DEFAULT_CHECK_S,
                 max_consecutive_failures: int = _DEFAULT_MAX_FAIL):
        self._event_bus    = event_bus
        self._svc_mgr      = service_manager
        self._job_queue    = job_queue
        self._interval     = check_interval_s
        self._max_failures = max_consecutive_failures
        self._health: dict[str, ServiceHealth] = {}
        self._running      = False
        self._thread: threading.Thread | None = None
        self._last_report: dict = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop,
            name="aura-health-monitor",
            daemon=True,
        )
        self._thread.start()
        logger.info("HealthMonitor: started (interval=%.0fs)", self._interval)

    def stop(self) -> None:
        self._running = False
        logger.info("HealthMonitor: stopped")

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def last_report(self) -> dict:
        """Return the most recent health report dict."""
        return dict(self._last_report)

    def service_health(self, name: str) -> dict | None:
        h = self._health.get(name)
        return h.to_dict() if h else None

    def all_health(self) -> dict:
        return {name: h.to_dict() for name, h in self._health.items()}

    # ------------------------------------------------------------------
    # Manual check (callable from shell `repair` command)
    # ------------------------------------------------------------------

    def run_check_now(self) -> dict:
        """Run an immediate health check and return the report."""
        return self._check_all()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        # Initial check after a short settle delay
        time.sleep(5.0)
        while self._running:
            self._check_all()
            # Sleep in short increments so stop() is responsive
            elapsed = 0.0
            while self._running and elapsed < self._interval:
                time.sleep(1.0)
                elapsed += 1.0

    def _check_all(self) -> dict:
        """Check all known services and build a health report."""
        if self._svc_mgr is None:
            return {}

        healthy_names  = []
        degraded_names = []
        failed_names   = []

        try:
            registry = self._svc_mgr._registry
        except Exception:
            return {}

        for name, record in registry.items():
            if name not in self._health:
                self._health[name] = ServiceHealth(name)
            h = self._health[name]
            h.last_check_ts = time.time()
            h.last_state    = record.state

            if record.state == "running":
                h.record_healthy()
                healthy_names.append(name)
            else:
                circuit_opened = h.record_failure(self._max_failures)
                if circuit_opened:
                    self._handle_failure(name, record)
                    failed_names.append(name)
                elif h.consecutive_failures > 0:
                    degraded_names.append(name)
                else:
                    healthy_names.append(name)

        report = {
            "timestamp":  time.time(),
            "healthy":    len(healthy_names),
            "degraded":   len(degraded_names),
            "failed":     len(failed_names),
            "services":   {n: self._health[n].to_dict()
                           for n in self._health},
            "healthy_list":  healthy_names,
            "degraded_list": degraded_names,
            "failed_list":   failed_names,
        }
        self._last_report = report
        self._publish_report(report)
        return report

    def _handle_failure(self, name: str, record) -> None:
        """Open the circuit and submit a repair job."""
        logger.warning("HealthMonitor: circuit OPEN for %r — queueing repair",
                       name)
        self._publish("INTEGRITY_ALERT", {
            "service":  name,
            "failures": self._health[name].consecutive_failures,
            "action":   "repair_queued",
        })
        if self._job_queue is not None:
            self._job_queue.submit(
                f"repair:{name}",
                lambda n=name: self._repair_service(n),
                priority=1,
                max_retries=2,
            )

    def _repair_service(self, name: str) -> None:
        """Attempt to restart a failed service."""
        logger.info("HealthMonitor: attempting restart of service %r", name)
        if self._svc_mgr is None:
            return
        try:
            stopped = self._svc_mgr.stop(name)
            if stopped:
                started = self._svc_mgr.start(name)
                if started:
                    self._health[name].circuit = ServiceHealth.HALF_OPEN
                    logger.info("HealthMonitor: restarted %r — circuit HALF_OPEN",
                                name)
                    self._publish("SERVICE_RESTARTING",
                                  {"name": name, "reason": "health_monitor"})
        except Exception as exc:
            logger.error("HealthMonitor: repair of %r failed: %s", name, exc)

    def _publish_report(self, report: dict) -> None:
        self._publish("HEALTH_REPORT", report, priority="low")

    def _publish(self, event_type: str, payload: dict,
                 priority: str = "normal") -> None:
        if self._event_bus is None:
            return
        try:
            from kernel.event_bus import Event, Priority
            pri = {"low": Priority.LOW, "high": Priority.HIGH}.get(
                priority, Priority.NORMAL)
            self._event_bus.publish(
                Event(event_type, payload=payload,
                      priority=pri, source="health_monitor")
            )
        except Exception:
            pass
