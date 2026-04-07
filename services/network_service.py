"""
AURA-AIOSCPU Network Monitor Service
======================================
Monitors network connectivity and publishes NETWORK_STATUS events on the
event bus.  Works fully offline — simply reports OFFLINE when no connection
is detected.

Design
------
- Checks connectivity by attempting a non-blocking TCP connection to a
  configurable set of well-known hosts (defaults: 8.8.8.8:53, 1.1.1.1:53).
- Performs a DNS resolution sanity-check as a secondary probe.
- Runs in a daemon thread; check interval is configurable (default 30 s).
- Gracefully degrades — never raises, always publishes a status event.
- Zero external dependencies (stdlib socket + threading only).

NETWORK_STATUS event payload
-----------------------------
  {
    "status":      "online" | "offline" | "degraded",
    "latency_ms":  float | None,
    "dns_ok":      bool,
    "interface":   str | None,   # local IP of first active interface
    "checked_at":  float,        # epoch
  }
"""

import logging
import socket
import threading
import time

logger = logging.getLogger(__name__)

_DEFAULT_PROBES  = [("8.8.8.8", 53), ("1.1.1.1", 53)]
_DNS_TEST_HOST   = "google.com"
_PROBE_TIMEOUT_S = 3.0
_DEFAULT_CHECK_INTERVAL_S = 30


def _probe_tcp(host: str, port: int, timeout: float) -> float | None:
    """Attempt a TCP connect; return round-trip ms or None on failure."""
    try:
        t0   = time.monotonic()
        sock = socket.create_connection((host, port), timeout=timeout)
        rtt  = (time.monotonic() - t0) * 1000.0
        sock.close()
        return rtt
    except Exception:
        return None


def _probe_dns(hostname: str, timeout: float) -> bool:
    """Try to resolve a hostname; return True on success."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.getaddrinfo(hostname, None)
        return True
    except Exception:
        return False
    finally:
        socket.setdefaulttimeout(None)


def _local_ip() -> str | None:
    """Best-effort local IP address of the default interface."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


def check_connectivity(
    probes=None,
    dns_host: str = _DNS_TEST_HOST,
    timeout: float = _PROBE_TIMEOUT_S,
) -> dict:
    """
    Run connectivity probes and return a status dict.

    This function is standalone so it can be called from the shell `net`
    command without starting the background service.
    """
    probes = probes or _DEFAULT_PROBES

    latencies = []
    for host, port in probes:
        rtt = _probe_tcp(host, port, timeout)
        if rtt is not None:
            latencies.append(rtt)

    dns_ok   = _probe_dns(dns_host, timeout) if latencies else False
    local_ip = _local_ip()

    if latencies and dns_ok:
        status = "online"
    elif latencies:
        status = "degraded"   # TCP works but DNS failed
    else:
        status = "offline"

    return {
        "status":     status,
        "latency_ms": round(min(latencies), 1) if latencies else None,
        "dns_ok":     dns_ok,
        "interface":  local_ip,
        "checked_at": time.time(),
    }


# ---------------------------------------------------------------------------
# NetworkService
# ---------------------------------------------------------------------------

class NetworkService:
    """
    Background connectivity monitor.

    Publishes ``NETWORK_STATUS`` events to the event bus every
    ``check_interval_s`` seconds.  Also exposes the last status dict
    synchronously via ``last_status``.
    """

    def __init__(self,
                 event_bus=None,
                 check_interval_s: float = _DEFAULT_CHECK_INTERVAL_S,
                 probes=None):
        self._event_bus         = event_bus
        self._check_interval_s  = check_interval_s
        self._probes            = probes or _DEFAULT_PROBES
        self._last_status: dict = {}
        self._running           = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start monitoring in a daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop,
            name="aura-network-monitor",
            daemon=True,
        )
        self._thread.start()
        logger.info("NetworkService: started (interval=%.0fs)", self._check_interval_s)

    def stop(self) -> None:
        """Signal the monitor to stop."""
        self._running = False
        logger.info("NetworkService: stopped")

    # ------------------------------------------------------------------
    # Synchronous probe (usable from the shell)
    # ------------------------------------------------------------------

    def probe_now(self) -> dict:
        """Run an immediate connectivity check and return the result."""
        result = check_connectivity(probes=self._probes)
        self._last_status = result
        self._publish(result)
        return result

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def last_status(self) -> dict:
        """Most recent connectivity status (empty dict if never checked)."""
        return dict(self._last_status)

    @property
    def is_online(self) -> bool:
        return self._last_status.get("status") == "online"

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        # Do an immediate check on start
        self._check_once()
        while self._running:
            for _ in range(int(self._check_interval_s * 10)):
                if not self._running:
                    break
                time.sleep(0.1)
            if self._running:
                self._check_once()

    def _check_once(self) -> None:
        try:
            result = check_connectivity(probes=self._probes)
            self._last_status = result
            logger.debug("NetworkService: %s (%.0f ms)",
                         result["status"],
                         result["latency_ms"] or 0)
            self._publish(result)
        except Exception:
            logger.exception("NetworkService: probe failed unexpectedly")

    def _publish(self, status: dict) -> None:
        if self._event_bus is None:
            return
        try:
            from kernel.event_bus import Event, Priority
            self._event_bus.publish(
                Event("NETWORK_STATUS", payload=status,
                      priority=Priority.LOW, source="network_service")
            )
        except Exception:
            logger.exception("NetworkService: failed to publish event")

    def __repr__(self):
        st = self._last_status.get("status", "unknown")
        return f"NetworkService(status={st!r}, running={self._running})"
