"""
AURA — Kernel Personality Layer
================================
AURA is not a user-space application. It is a first-class component of the
kernel, pulsed every tick, with read access to all system state.

Responsibilities
----------------
- Observe  : system topology, kernel state, service status, logs, configs.
- Advise   : publish PRIORITY_HINT events to influence the scheduler.
- Respond  : answer shell and service queries using live system context.
- Act      : perform autonomous actions within the permission model.

AURA's authority is bounded by the active kernel mode:
  Universal → may advise only (no autonomous actions)
  Internal  → may act within user-granted permissions
  Hardware  → may project virtual devices with explicit consent
"""

import logging

from kernel.event_bus import EventBus, Event, Priority

logger = logging.getLogger(__name__)


class AURA:
    """The kernel personality layer."""

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._snapshot: dict = {}
        self._model = None  # model_manager — stub until AI pipeline is wired

        # Subscribe to key system events so AURA always knows what happened
        for event_type in (
            "SERVICE_REGISTERED", "SERVICE_STARTED", "SERVICE_STOPPED",
            "MODE_ACTIVATED", "PERMISSION_REQUEST", "PERMISSION_RESPONSE",
            "SHUTDOWN",
        ):
            self._event_bus.subscribe(event_type, self._on_system_event)

    # ------------------------------------------------------------------
    # Called by KernelLoop each tick
    # ------------------------------------------------------------------

    def pulse(self, system_state: dict) -> None:
        """Update AURA's world-view and emit any pending advisory events."""
        self._snapshot.update(system_state)
        self._snapshot["last_pulse"] = system_state.get("tick", 0)
        # Stub reasoning: log state; real model inference goes here later
        logger.debug("AURA pulse: snapshot keys=%s", list(self._snapshot))

    # ------------------------------------------------------------------
    # Query interface (used by Shell and services)
    # ------------------------------------------------------------------

    def query(self, prompt: str) -> str:
        """Answer a natural-language query using live system context.

        Returns a plain-text response string.
        Until the AI model is wired in, returns a context-aware stub reply.
        """
        context_summary = ", ".join(
            f"{k}={v}" for k, v in list(self._snapshot.items())[:5]
        )
        if self._model is not None:
            return self._model.infer(prompt, self._snapshot)
        # Stub: echo the prompt with context until model is available
        return (
            f"[AURA stub] Received: {prompt!r}. "
            f"System context: {context_summary or 'none yet'}."
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_state_snapshot(self) -> dict:
        """Return a copy of AURA's current system state view."""
        return dict(self._snapshot)

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    def _on_system_event(self, event: Event) -> None:
        """Record system events into the snapshot for context."""
        key = f"last_{event.event_type.lower()}"
        self._snapshot[key] = event.payload
        logger.debug("AURA: recorded event %r", event.event_type)

