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
"""

import logging
import time

from kernel.event_bus import EventBus, Event, Priority
from kernel.scheduler import Scheduler
from aura import AURA

logger = logging.getLogger(__name__)

TICK_INTERVAL_MS = 16  # ~60 Hz — adjust based on workload measurements


class KernelLoop:
    """Runs continuously until stop() is called."""

    def __init__(self, scheduler: Scheduler, event_bus: EventBus, aura: AURA):
        self._scheduler = scheduler
        self._event_bus = event_bus
        self._aura = aura
        self._stopping = False
        self._tick_count = 0
        self._system_state: dict = {}

        # Stop the loop when a SHUTDOWN event arrives
        self._event_bus.subscribe("SHUTDOWN", self._on_shutdown)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Enter the main loop. Blocks until stop() is called."""
        logger.info("KernelLoop: starting")
        while not self._stopping:
            self._tick()
            time.sleep(TICK_INTERVAL_MS / 1000.0)
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
        self._dispatch_events()
        self._scheduler.tick()
        self._update_system_state()
        self._aura.pulse(self._system_state)

    def _dispatch_events(self) -> None:
        """Drain the event bus and deliver events to subscribers."""
        self._event_bus.drain()

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

