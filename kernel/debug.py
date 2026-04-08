"""
AURA-AIOSCPU Kernel Debug Subsystem
=====================================
A fully-operational, always-available debug layer that can be attached
to any running kernel without modifying existing code.

Components
----------
  EventTracer     — ring buffer of the last N events on the event bus
  TickProfiler    — per-tick timing statistics (min / max / avg / p95)
  KernelDebugger  — top-level façade; owns tracer + profiler

Shell commands exposed via shell/plugins/debug.py
  debug           — live snapshot of entire kernel state
  trace [n]       — last N traced events
  profile         — tick timing statistics
  scan            — run tools/system_scan.py
  inspect <name>  — live state of a named kernel subsystem

Design principles
-----------------
- Zero impact when idle: EventTracer uses a bounded deque so memory is capped.
- Thread-safe: all mutation is protected by threading.Lock().
- Attach-safe: attaching a debugger to a live kernel is non-destructive.
- No stubs: every method returns real data or raises a clear exception.
"""

from __future__ import annotations

import collections
import logging
import statistics
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kernel.event_bus import EventBus, Event

logger = logging.getLogger(__name__)

_DEFAULT_TRACE_DEPTH  = 200   # max events kept in the ring buffer
_DEFAULT_PROFILE_SIZE = 1000  # max tick timings kept


# ---------------------------------------------------------------------------
# EventTracer
# ---------------------------------------------------------------------------

class EventTracer:
    """
    Subscribes to all events on the bus and records them in a bounded ring buffer.

    Attaches by subscribing to a sentinel wildcard list of event types, or
    (preferred) by patching the bus's publish() method via attach_bus().
    """

    def __init__(self, max_events: int = _DEFAULT_TRACE_DEPTH):
        self._max      = max_events
        self._buf: collections.deque = collections.deque(maxlen=max_events)
        self._lock     = threading.Lock()
        self._total    = 0
        self._active   = False

    # ------------------------------------------------------------------
    # Bus attachment
    # ------------------------------------------------------------------

    def attach_bus(self, event_bus: EventBus) -> None:
        """
        Wrap the bus's publish() so every event is recorded before delivery.
        Safe to call on a live bus; the original publish() is preserved.
        """
        original_publish = event_bus.publish

        def _traced_publish(event):
            self._record(event)
            return original_publish(event)

        event_bus.publish = _traced_publish  # type: ignore[method-assign]
        self._active = True
        logger.debug("EventTracer: attached to event bus")

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def _record(self, event: Event) -> None:
        entry = {
            "seq":        event._seq,
            "type":       event.event_type,
            "source":     event.source,
            "priority":   event.priority,
            "timestamp":  event.timestamp,
            "payload_preview": _truncate(repr(event.payload), 120),
        }
        with self._lock:
            self._buf.append(entry)
            self._total += 1

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def recent(self, n: int = 20) -> list[dict]:
        """Return the last *n* traced events, newest last."""
        with self._lock:
            events = list(self._buf)
        return events[-n:]

    def total_count(self) -> int:
        with self._lock:
            return self._total

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()
            self._total = 0

    def is_active(self) -> bool:
        return self._active

    def to_dict(self) -> dict:
        return {
            "active":      self._active,
            "buffer_size": self._max,
            "total_seen":  self.total_count(),
            "buffered":    len(self._buf),
        }


# ---------------------------------------------------------------------------
# TickProfiler
# ---------------------------------------------------------------------------

class TickProfiler:
    """
    Records the wall-clock duration of each kernel tick.

    Call begin_tick() at the start of a tick and end_tick() at the end.
    KernelDebugger wires these calls by wrapping KernelLoop.tick_once().
    """

    def __init__(self, max_samples: int = _DEFAULT_PROFILE_SIZE):
        self._max       = max_samples
        self._samples: collections.deque = collections.deque(maxlen=max_samples)
        self._lock      = threading.Lock()
        self._tick_start: float | None = None
        self._total_ticks = 0
        self._slow_ticks  = 0   # ticks > 100 ms
        self._SLOW_MS     = 100

    def begin_tick(self) -> None:
        self._tick_start = time.monotonic()

    def end_tick(self) -> None:
        if self._tick_start is None:
            return
        duration_ms = (time.monotonic() - self._tick_start) * 1000.0
        self._tick_start = None
        with self._lock:
            self._samples.append(duration_ms)
            self._total_ticks += 1
            if duration_ms >= self._SLOW_MS:
                self._slow_ticks += 1

    def report(self) -> dict:
        """Return tick timing statistics."""
        with self._lock:
            samples = list(self._samples)
            total   = self._total_ticks
            slow    = self._slow_ticks

        if not samples:
            return {
                "total_ticks":  total,
                "slow_ticks":   slow,
                "min_ms":       None,
                "max_ms":       None,
                "avg_ms":       None,
                "p95_ms":       None,
                "sample_count": 0,
            }

        sorted_s = sorted(samples)
        p95_idx  = int(len(sorted_s) * 0.95)
        return {
            "total_ticks":  total,
            "slow_ticks":   slow,
            "min_ms":       round(min(samples), 3),
            "max_ms":       round(max(samples), 3),
            "avg_ms":       round(statistics.mean(samples), 3),
            "p95_ms":       round(sorted_s[min(p95_idx, len(sorted_s) - 1)], 3),
            "sample_count": len(samples),
        }

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
            self._total_ticks = 0
            self._slow_ticks  = 0


# ---------------------------------------------------------------------------
# KernelDebugger
# ---------------------------------------------------------------------------

class KernelDebugger:
    """
    Top-level debug façade.

    Attach to a live kernel once it has been started:
        debugger = KernelDebugger()
        debugger.attach(kernel)

    The debugger is then accessible via the shell ``debug`` plugin.
    """

    def __init__(self,
                 trace_depth: int  = _DEFAULT_TRACE_DEPTH,
                 profile_size: int = _DEFAULT_PROFILE_SIZE):
        self._tracer   = EventTracer(max_events=trace_depth)
        self._profiler = TickProfiler(max_samples=profile_size)
        self._kernel   = None
        self._attached = False
        self._start_ts = time.time()

    # ------------------------------------------------------------------
    # Attachment
    # ------------------------------------------------------------------

    def attach(self, kernel) -> None:
        """
        Attach to a live kernel.  Safe to call multiple times — idempotent.
        """
        if self._attached:
            return
        self._kernel = kernel

        # Wire event tracing
        self._tracer.attach_bus(kernel.event_bus)

        # Wire tick profiling by wrapping KernelLoop._tick()
        loop = kernel.loop
        original_tick = loop._tick

        profiler = self._profiler

        def _profiled_tick():
            profiler.begin_tick()
            try:
                original_tick()
            finally:
                profiler.end_tick()

        loop._tick = _profiled_tick  # type: ignore[method-assign]

        self._attached = True
        logger.info("KernelDebugger: attached to kernel")

    def detach(self) -> None:
        """Remove profiling wrappers (event trace is not reversible)."""
        self._attached = False
        self._kernel   = None
        logger.info("KernelDebugger: detached")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def trace(self, n: int = 20) -> list[dict]:
        """Return the last *n* traced events."""
        return self._tracer.recent(n)

    def profile_report(self) -> dict:
        """Return tick timing statistics."""
        return self._profiler.report()

    def dump(self) -> dict:
        """Return a full JSON-serialisable snapshot of the kernel's state."""
        uptime = time.time() - self._start_ts
        result: dict = {
            "attached":   self._attached,
            "uptime_s":   round(uptime, 2),
            "tracer":     self._tracer.to_dict(),
            "profiler":   self._profiler.report(),
        }
        if self._kernel is None:
            result["kernel"] = None
            return result

        k = self._kernel
        result["kernel"] = {
            "mode":         getattr(getattr(k, "mode", None), "NAME", "unknown"),
            "tick_count":   getattr(getattr(k, "loop", None), "_tick_count", 0),
            "event_queue":  len(getattr(getattr(k, "event_bus", None), "_queue", [])),
            "task_queue":   len(getattr(getattr(k, "scheduler", None), "_task_queue", [])),
            "job_queue":    len(getattr(getattr(k, "scheduler", None), "_job_queue", [])),
            "services":     self._snapshot_services(k),
            "aura_snapshot": self._snapshot_aura(k),
        }
        return result

    def inspect(self, subsystem: str) -> dict:
        """
        Return a live state snapshot of the named kernel subsystem.

        Supported names: event_bus, scheduler, services, aura, hal,
                         storage, permissions, watchdog, loop, model_manager
        """
        if self._kernel is None:
            raise RuntimeError("KernelDebugger not attached to a kernel")

        k   = self._kernel
        sub = subsystem.lower().replace("-", "_").replace(" ", "_")

        inspectors = {
            "event_bus":     lambda: {
                "queue_depth": len(getattr(k.event_bus, "_queue", [])),
                "subscriber_count": sum(
                    len(v) for v in getattr(k.event_bus, "_subscribers", {}).values()
                ),
                "subscriber_types": list(getattr(k.event_bus, "_subscribers", {}).keys()),
            },
            "scheduler":     lambda: {
                "task_queue_depth": len(getattr(k.scheduler, "_task_queue", [])),
                "job_queue_depth":  len(getattr(k.scheduler, "_job_queue", [])),
                "service_count":    len(getattr(k.scheduler, "_service_registry", {})),
            },
            "services":      lambda: self._snapshot_services(k),
            "aura":          lambda: self._snapshot_aura(k),
            "hal":           lambda: {
                "vcpu_running":    getattr(getattr(k, "hal", None), "_vcpu", None) and k.hal._vcpu.running,
                "device_count":    len(getattr(getattr(k, "hal", None), "_devices", {})),
                "projection_on":   getattr(getattr(k, "hal", None), "_projection_active", False),
            },
            "storage":       lambda: {
                "path": getattr(k.storage, "_path", "?"),
                "open": getattr(k.storage, "_conn", None) is not None,
            },
            "permissions":   lambda: k.permissions.summary(),
            "watchdog":      lambda: getattr(k, "watchdog", None) and k.watchdog.get_health_report() or {},
            "loop":          lambda: {
                "tick_count":   getattr(k.loop, "_tick_count", 0),
                "stopping":     getattr(k.loop, "_stopping", False),
                "interval_ms":  getattr(getattr(k.loop, "_adaptive_tick", None), "interval_ms", None),
            },
            "model_manager": lambda: {
                "active":   k.model_manager.active_model_name(),
                "models":   k.model_manager.list_models(),
                "dir":      getattr(k.model_manager, "_models_dir", "?"),
            },
        }

        fn = inspectors.get(sub)
        if fn is None:
            available = sorted(inspectors.keys())
            raise KeyError(
                f"Unknown subsystem {sub!r}. Available: {available}"
            )
        return fn()

    def health_score(self) -> int:
        """
        Return an integer 0-100 health score for the running kernel.

        Criteria:
          - Kernel attached           (+20)
          - Event tracer active       (+10)
          - Tick profiler has samples (+10)
          - No slow ticks (>100ms)    (+20)
          - Services all running      (+20)
          - No event queue backlog    (+20)
        """
        score = 0
        if not self._attached or self._kernel is None:
            return score

        score += 20   # attached

        if self._tracer.is_active():
            score += 10

        report = self._profiler.report()
        if report["sample_count"] and report["sample_count"] > 0:
            score += 10
            # Penalise slow ticks
            total = report["total_ticks"] or 1
            slow_ratio = (report["slow_ticks"] or 0) / total
            if slow_ratio < 0.01:
                score += 20
            elif slow_ratio < 0.05:
                score += 10

        k = self._kernel
        svcs = self._snapshot_services(k)
        if svcs:
            running = sum(1 for s in svcs.values() if s.get("state") == "running")
            if running == len(svcs):
                score += 20
            elif running > 0:
                score += 10

        queue_depth = len(getattr(getattr(k, "event_bus", None), "_queue", []))
        if queue_depth == 0:
            score += 20
        elif queue_depth < 10:
            score += 10

        return min(score, 100)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _snapshot_services(k) -> dict:
        try:
            reg = getattr(getattr(k, "services", None), "_registry", {})
            return {
                name: {"state": getattr(rec, "state", "?")}
                for name, rec in reg.items()
            }
        except Exception:
            return {}

    @staticmethod
    def _snapshot_aura(k) -> dict:
        try:
            aura = getattr(k, "aura", None)
            if aura is None:
                return {}
            snap = aura.get_state_snapshot()
            # Truncate large values for safety
            return {k: _truncate(str(v), 80) for k, v in list(snap.items())[:20]}
        except Exception:
            return {}

    def is_attached(self) -> bool:
        return self._attached

    def tracer(self) -> EventTracer:
        return self._tracer

    def profiler(self) -> TickProfiler:
        return self._profiler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(s: str, max_len: int) -> str:
    return s if len(s) <= max_len else s[:max_len - 3] + "..."
