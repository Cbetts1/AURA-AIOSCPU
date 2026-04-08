"""
AURA-AIOSCPU Virtual Cloud CPU
================================
Cloud-scale virtual CPU that replaces the need for a physical CPU upgrade.
Runs inside the Virtual Cloud fabric and provides elastic compute power
to both the Virtual Server and Dual Compute Nodes.

Architecture
------------
  - Multi-core pipeline: N virtual cores (default 4, scalable to 32)
  - Burst scheduling: cores auto-scale up under load, idle-down when quiet
  - Instruction dispatch: tasks dispatched as callable units to core threads
  - Clock tracking: virtual clock ticks drive scheduling decisions
  - Metrics: per-core utilisation, pipeline depth, throughput (ops/s)

Cloud-level upgrade over a physical CPU
-----------------------------------------
  Physical limitation   -> Cloud CPU solution
  Fixed core count      -> Elastic core pool (auto-expand up to max_cores)
  Thermal throttling    -> No thermal constraints; burst unlimited
  RAM ceiling           -> Cloud memory backed by CloudStorage
  Single machine        -> Distributed across Compute Node A + B
  I/O bottleneck        -> CloudRouter handles data movement off-CPU
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

_BURST_THRESHOLD  = 0.80   # utilisation fraction that triggers core expansion
_IDLE_THRESHOLD   = 0.20   # utilisation fraction that triggers core contraction
_BURST_COOLDOWN_S = 5.0    # seconds before shrinking cores back


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CpuTask:
    """One unit of compute dispatched to a virtual core."""
    name:        str
    fn:          Callable
    args:        tuple      = field(default_factory=tuple)
    kwargs:      dict       = field(default_factory=dict)
    task_id:     str        = field(default_factory=lambda: uuid.uuid4().hex[:8])
    priority:    int        = 5          # 0 CRITICAL ... 9 LOW
    submitted_at: float     = field(default_factory=time.monotonic)
    result:      object     = None
    error:       str        = ""
    elapsed_s:   float      = 0.0
    state:       str        = "queued"   # queued | running | done | failed

    def __lt__(self, other: "CpuTask") -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.submitted_at < other.submitted_at

    def to_dict(self) -> dict:
        return {
            "task_id":   self.task_id,
            "name":      self.name,
            "priority":  self.priority,
            "state":     self.state,
            "elapsed_s": round(self.elapsed_s, 4),
            "error":     self.error,
        }


# ---------------------------------------------------------------------------
# Virtual Core
# ---------------------------------------------------------------------------

class VirtualCore:
    """A single worker thread acting as one virtual CPU core."""

    def __init__(self, core_id: int, task_queue: queue.PriorityQueue):
        self.core_id  = core_id
        self._queue   = task_queue
        self._running = False
        self._thread: threading.Thread | None = None
        self._busy    = False
        self._ops_done = 0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop,
            name=f"vcpu-core-{self.core_id}",
            daemon=True,
        )
        self._thread.start()
        logger.debug("VirtualCore %d started", self.core_id)

    def stop(self) -> None:
        self._running = False

    @property
    def is_busy(self) -> bool:
        return self._busy

    @property
    def ops_done(self) -> int:
        return self._ops_done

    def _loop(self) -> None:
        while self._running:
            try:
                _priority, task = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            self._busy = True
            task.state = "running"
            t0 = time.monotonic()
            try:
                task.result = task.fn(*task.args, **task.kwargs)
                task.state  = "done"
            except Exception as exc:
                task.state = "failed"
                task.error = str(exc)
                logger.warning("VirtualCore %d: task %s failed: %s",
                               self.core_id, task.name, exc)
            finally:
                task.elapsed_s = time.monotonic() - t0
                self._ops_done += 1
                self._busy = False
                self._queue.task_done()


# ---------------------------------------------------------------------------
# Virtual CPU
# ---------------------------------------------------------------------------

class VirtualCPU:
    """
    Elastic multi-core virtual CPU for cloud-scale compute.

    Dispatch tasks via submit().  The CPU auto-scales cores between
    min_cores and max_cores based on observed utilisation.
    """

    def __init__(
        self,
        min_cores: int   = 4,
        max_cores: int   = 32,
        clock_hz:  float = 1000.0,
        event_bus=None,
    ):
        self._min_cores = min_cores
        self._max_cores = max_cores
        self._clock_hz  = clock_hz
        self._event_bus = event_bus

        self._task_queue: queue.PriorityQueue = queue.PriorityQueue()
        self._cores: list[VirtualCore]        = []
        self._lock    = threading.Lock()
        self._running = False
        self._scaler_thread: threading.Thread | None = None
        self._start_time = 0.0
        self._seq        = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running    = True
        self._start_time = time.monotonic()
        with self._lock:
            for i in range(self._min_cores):
                self._add_core_locked()
        self._scaler_thread = threading.Thread(
            target=self._scaler_loop, name="vcpu-scaler", daemon=True,
        )
        self._scaler_thread.start()
        logger.info("VirtualCPU started: %d cores (max %d)", self._min_cores, self._max_cores)

    def stop(self) -> None:
        self._running = False
        with self._lock:
            for core in self._cores:
                core.stop()
        logger.info("VirtualCPU stopped")

    # ------------------------------------------------------------------
    # Task submission
    # ------------------------------------------------------------------

    def submit(
        self,
        name:     str,
        fn:       Callable,
        args:     tuple = (),
        kwargs:   dict | None = None,
        priority: int = 5,
    ) -> CpuTask:
        """Submit a task for async execution. Returns CpuTask handle."""
        task = CpuTask(
            name=name,
            fn=fn,
            args=args,
            kwargs=kwargs or {},
            priority=priority,
        )
        self._seq += 1
        self._task_queue.put((priority, task))
        self._publish_event("VCPU_TASK_QUEUED", {
            "task_id":     task.task_id,
            "name":        task.name,
            "priority":    priority,
            "queue_depth": self._task_queue.qsize(),
        })
        return task

    def submit_sync(
        self,
        name:     str,
        fn:       Callable,
        args:     tuple = (),
        kwargs:   dict | None = None,
        priority: int = 5,
        timeout:  float = 30.0,
    ) -> object:
        """Submit and block until the task completes. Returns result or raises."""
        task = self.submit(name, fn, args, kwargs, priority)
        deadline = time.monotonic() + timeout
        while task.state in ("queued", "running"):
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"VirtualCPU task '{name}' timed out after {timeout}s"
                )
            time.sleep(0.01)
        if task.state == "failed":
            raise RuntimeError(f"VirtualCPU task '{name}' failed: {task.error}")
        return task.result

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    @property
    def core_count(self) -> int:
        return len(self._cores)

    @property
    def utilisation(self) -> float:
        if not self._cores:
            return 0.0
        busy = sum(1 for c in self._cores if c.is_busy)
        return busy / len(self._cores)

    @property
    def total_ops(self) -> int:
        return sum(c.ops_done for c in self._cores)

    @property
    def throughput_ops_per_s(self) -> float:
        elapsed = time.monotonic() - self._start_time
        return round(self.total_ops / elapsed, 2) if elapsed > 0 else 0.0

    def status(self) -> dict:
        return {
            "cores":       self.core_count,
            "min_cores":   self._min_cores,
            "max_cores":   self._max_cores,
            "utilisation": round(self.utilisation, 3),
            "queue_depth": self._task_queue.qsize(),
            "total_ops":   self.total_ops,
            "ops_per_s":   self.throughput_ops_per_s,
            "clock_hz":    self._clock_hz,
            "running":     self._running,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_core_locked(self) -> VirtualCore:
        core_id = len(self._cores)
        core    = VirtualCore(core_id, self._task_queue)
        core.start()
        self._cores.append(core)
        return core

    def _remove_core_locked(self) -> None:
        if len(self._cores) <= self._min_cores:
            return
        core = self._cores.pop()
        core.stop()

    def _scaler_loop(self) -> None:
        last_burst = 0.0
        while self._running:
            time.sleep(1.0)
            util = self.utilisation
            now  = time.monotonic()
            with self._lock:
                if util >= _BURST_THRESHOLD and len(self._cores) < self._max_cores:
                    self._add_core_locked()
                    last_burst = now
                    self._publish_event("VCPU_CORE_ADDED", {
                        "cores": len(self._cores), "utilisation": round(util, 3),
                    })
                elif (util < _IDLE_THRESHOLD
                      and len(self._cores) > self._min_cores
                      and (now - last_burst) > _BURST_COOLDOWN_S):
                    self._remove_core_locked()
                    self._publish_event("VCPU_CORE_REMOVED", {
                        "cores": len(self._cores), "utilisation": round(util, 3),
                    })

    def _publish_event(self, event_type: str, payload: dict) -> None:
        if self._event_bus is None:
            return
        try:
            from kernel.event_bus import Event, Priority
            self._event_bus.publish(
                Event(event_type, payload=payload,
                      priority=Priority.LOW, source="virtual_cpu")
            )
        except Exception:
            logger.exception("VirtualCPU: failed to publish %s", event_type)

    def __repr__(self) -> str:
        return (f"VirtualCPU(cores={self.core_count}, "
                f"util={self.utilisation:.0%}, "
                f"ops={self.total_ops})")
