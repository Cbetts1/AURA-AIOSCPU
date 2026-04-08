"""
AURA-AIOSCPU Kernel Loop
========================
The heartbeat of the system.

Responsibilities (each tick)
-----------------------------
1. Dispatch all pending events from the event bus.
2. Advance the scheduler (tasks / services / background jobs).
3. Pulse AURA with the latest system state snapshot.
4. Refresh the global system state.

The loop runs until stop() is called (e.g. by a SHUTDOWN event).

Adaptive tick rate
------------------
When the system is idle (no tasks, no events) the interval doubles each
cycle up to ``max_tick_interval_ms`` to reduce power consumption on
mobile devices.  Any activity resets the interval to the base value.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from kernel.event_bus import EventBus, Event, Priority
from kernel.scheduler import Scheduler

if TYPE_CHECKING:
    from aura import AURA

logger = logging.getLogger(__name__)

_DEFAULT_TICK_MS     = 16     # ~60 Hz — overridden by config/device profile
_MAX_IDLE_TICK_MS    = 1000   # maximum 1-second interval when fully idle
_IDLE_BACKOFF_FACTOR = 2      # multiply interval by this when idle


class AdaptiveTick:
    """
    Tracks the current loop interval and adjusts it based on system activity.

    Busy tick (tasks/events pending)  → interval snaps back to base_ms
    Idle  tick (nothing to do)        → interval doubles up to max_ms
    """

    def __init__(self, base_ms: int = _DEFAULT_TICK_MS,
                 max_ms: int = _MAX_IDLE_TICK_MS,
                 backoff_factor: int = _IDLE_BACKOFF_FACTOR):
        self._base    = base_ms
        self._max     = max_ms
        self._factor  = backoff_factor
        self._current = base_ms
        self._idle_ticks = 0

    @property
    def interval_ms(self) -> int:
        return self._current

    def mark_busy(self) -> None:
        self._idle_ticks = 0
        self._current    = self._base

    def mark_idle(self) -> None:
        self._idle_ticks += 1
        if self._idle_ticks > 3:                        # grace period
            self._current = min(
                self._current * self._factor, self._max
            )


class KernelLoop:
    """Runs continuously until stop() is called."""

    def __init__(self, scheduler: Scheduler, event_bus: EventBus, aura: AURA,
                 tick_interval_ms: int = _DEFAULT_TICK_MS,
                 adaptive: bool = True,
                 max_tick_interval_ms: int = _MAX_IDLE_TICK_MS):
        self._scheduler = scheduler
        self._event_bus = event_bus
        self._aura      = aura
        self._stopping  = False
        self._tick_count = 0
        self._system_state: dict = {}
        self._adaptive_tick = AdaptiveTick(
            base_ms=tick_interval_ms,
            max_ms=max_tick_interval_ms if adaptive else tick_interval_ms,
        )

        # Stop the loop when a SHUTDOWN event arrives
        self._event_bus.subscribe("SHUTDOWN", self._on_shutdown)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Enter the main loop. Blocks until stop() is called."""
        logger.info("KernelLoop: starting (base_tick=%dms)",
                    self._adaptive_tick._base)
        while not self._stopping:
            self._tick()
            time.sleep(self._adaptive_tick.interval_ms / 1000.0)
        logger.info("KernelLoop: stopped after %d ticks", self._tick_count)

    def stop(self) -> None:
        """Signal the loop to exit cleanly after the current tick."""
        self._stopping = True

    # ------------------------------------------------------------------
    # Single tick (also callable directly in tests)
    # ------------------------------------------------------------------

    def tick_once(self) -> None:
        """Execute exactly one tick without the sleep. Useful for tests."""
        self._tick()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._tick_count += 1
        events_dispatched = self._dispatch_events()
        tasks_ran         = self._scheduler.tick()
        self._update_system_state()
        self._aura.pulse(self._system_state)

        # Adaptive tick: back off when the system is idle
        if events_dispatched or tasks_ran:
            self._adaptive_tick.mark_busy()
        else:
            self._adaptive_tick.mark_idle()

    def _dispatch_events(self) -> int:
        """Drain the event bus and deliver events to subscribers.
        Returns the number of events dispatched."""
        return self._event_bus.drain()

    def _update_system_state(self) -> None:
        """Refresh the system state snapshot passed to AURA each tick."""
        self._system_state.update({
            "tick": self._tick_count,
            "task_queue_depth": len(self._scheduler._task_queue),
            "job_queue_depth": len(self._scheduler._job_queue),
            "service_count": len(self._scheduler._service_registry),
        })

    def tick_count(self) -> int:
        """Return the total number of ticks completed by this loop."""
        return self._tick_count

    def _on_shutdown(self, event: Event) -> None:
        logger.info("KernelLoop: SHUTDOWN event received — stopping loop")
        self.stop()

