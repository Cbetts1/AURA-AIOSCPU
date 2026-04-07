"""
AURA System Introspection
==========================
Reads live kernel/service state and exposes it to AURA's query layer.

The introspector is attached to the kernel after boot and queried:
  - every pulse (lightweight snapshot)
  - on-demand for deep inspection (shell `status`, AURA queries)

It never modifies state — read-only observation only.
"""

import logging
import os
import platform
import time

logger = logging.getLogger(__name__)


class SystemIntrospector:
    """
    Provides AURA with a rich, up-to-date picture of the running system.

    Attach after kernel boot::

        introspector = SystemIntrospector()
        introspector.attach_kernel(kernel)
        snap = introspector.snapshot()
    """

    def __init__(self):
        self._boot_time  = time.time()
        self._kernel_ref = None   # set by kernel after boot via attach_kernel()

    # ------------------------------------------------------------------
    # Attach / detach
    # ------------------------------------------------------------------

    def attach_kernel(self, kernel) -> None:
        """Wire this introspector to the live kernel object."""
        self._kernel_ref = kernel
        logger.debug("SystemIntrospector: attached to kernel")

    # ------------------------------------------------------------------
    # Snapshot (fast path — called every pulse)
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """
        Return a flat dict snapshot of the current system state.

        Always returns immediately; never raises.
        """
        snap: dict = {
            "uptime_s":      round(time.time() - self._boot_time, 1),
            "platform":      platform.system(),
            "arch":          platform.machine(),
            "python":        platform.python_version(),
            "pid":           os.getpid(),
            "timestamp":     time.time(),
        }
        if self._kernel_ref is not None:
            snap.update(self._kernel_snapshot())
        return snap

    # ------------------------------------------------------------------
    # Deep inspection (on-demand queries)
    # ------------------------------------------------------------------

    def describe(self) -> str:
        """Return a human-readable multi-line system description."""
        s = self.snapshot()
        lines = [
            f"AURA-AIOSCPU   uptime={s.get('uptime_s', 0):.0f}s"
            f"   mode={s.get('mode', '?')}",
            f"Platform : {s.get('platform', '?')} / {s.get('arch', '?')}",
            f"Services : {s.get('service_count', 0)} registered",
            f"Tick     : {s.get('tick', 0)}",
            f"Model    : {s.get('active_model') or 'none loaded'}",
            f"Network  : {s.get('network_status', 'unknown')}",
            f"Storage  : {s.get('storage_status', 'unknown')}",
        ]
        svcs = s.get("services", {})
        if svcs:
            lines.append("Service states:")
            for name, state in svcs.items():
                lines.append(f"  {name:<20} {state}")
        return "\n".join(lines)

    def list_services(self) -> dict:
        """Return {name: state} for all registered services."""
        if self._kernel_ref is None:
            return {}
        try:
            return {
                name: rec.state
                for name, rec in self._kernel_ref.services._registry.items()
            }
        except Exception:
            return {}

    def get_recent_logs(self, n: int = 20) -> list[str]:
        """Return the last n log lines (requires LoggingService to be running)."""
        if self._kernel_ref is None:
            return []
        try:
            ls = getattr(self._kernel_ref, "logging_service", None)
            if ls is not None:
                return ls.get_recent(n)
        except Exception:
            pass
        return []

    def get_job_queue_depth(self) -> int:
        """Return the number of pending jobs in the job queue service."""
        if self._kernel_ref is None:
            return 0
        try:
            jq = getattr(self._kernel_ref, "job_queue", None)
            if jq is not None:
                return jq.pending_count()
        except Exception:
            pass
        try:
            return len(self._kernel_ref.scheduler._job_queue)
        except Exception:
            return 0

    def get_storage_info(self) -> dict:
        """Return storage service status dict."""
        if self._kernel_ref is None:
            return {}
        try:
            ss = getattr(self._kernel_ref, "storage_service", None)
            if ss is not None:
                return ss.status()
        except Exception:
            pass
        return {}

    def get_health_summary(self) -> dict:
        """Return the most recent health monitor report."""
        if self._kernel_ref is None:
            return {}
        try:
            hm = getattr(self._kernel_ref, "health_monitor", None)
            if hm is not None:
                return hm.last_report()
        except Exception:
            pass
        return {}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _kernel_snapshot(self) -> dict:
        """Extract key values from the live kernel; silently skip on error."""
        k = self._kernel_ref
        result: dict = {}

        _safe(result, "mode",
              lambda: getattr(getattr(k, "mode", None), "NAME", "unknown"))
        _safe(result, "tick",
              lambda: k.loop.tick_count())
        _safe(result, "service_count",
              lambda: len(k.services._registry))
        _safe(result, "services",
              lambda: {n: r.state for n, r in k.services._registry.items()})
        _safe(result, "task_queue_depth",
              lambda: len(k.scheduler._task_queue))
        _safe(result, "job_queue_depth",
              lambda: len(k.scheduler._job_queue))
        _safe(result, "active_model",
              lambda: k.model_manager.active_model_name())
        _safe(result, "models_available",
              lambda: len(k.model_manager._registry))
        _safe(result, "network_status",
              lambda: k.network_service.last_status.get("status", "unknown"))
        _safe(result, "storage_status",
              lambda: _storage_status(k))
        return result


def _safe(d: dict, key: str, fn) -> None:
    """Run fn(); store result in d[key]. Silently ignore all exceptions."""
    try:
        d[key] = fn()
    except Exception:
        pass


def _storage_status(k) -> str:
    try:
        ss = getattr(k, "storage_service", None)
        if ss is not None:
            return ss.status().get("state", "unknown")
        # Fall back to VStorageDevice
        return "mounted" if k.storage._running else "stopped"
    except Exception:
        return "unknown"
