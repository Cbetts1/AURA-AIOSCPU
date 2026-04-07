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

# TODO: from kernel.event_bus import EventBus
# TODO: from kernel.scheduler import Scheduler
# TODO: from aura import AURA

TICK_INTERVAL_MS = 16  # ~60 Hz — adjust based on workload measurements


class KernelLoop:
    """Runs continuously until stop() is called."""

    def __init__(self, scheduler, event_bus, aura):
        # TODO: self._scheduler = scheduler
        # TODO: self._event_bus = event_bus
        # TODO: self._aura = aura
        # TODO: self._stopping = False
        # TODO: self._system_state = {}
        pass

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Enter the main loop. Blocks until stop() is called."""
        # TODO: while not self._stopping:
        #     self._dispatch_events()
        #     self._scheduler.tick()
        #     self._update_system_state()
        #     self._aura.pulse(self._system_state)
        #     sleep(TICK_INTERVAL_MS / 1000)
        pass

    def stop(self) -> None:
        """Signal the loop to exit cleanly after the current tick."""
        # TODO: self._stopping = True
        pass

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _dispatch_events(self) -> None:
        """Drain the event bus and deliver events to subscribers."""
        # TODO: self._event_bus.drain()
        pass

    def _update_system_state(self) -> None:
        """Refresh the system state snapshot passed to AURA each tick."""
        # TODO: collect: scheduler queue depth, service status, HAL stats
        # TODO: update self._system_state dict
        pass
