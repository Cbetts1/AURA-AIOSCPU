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

Architecture
------------
  AURA
  ├── ConversationMemory   — rolling turn window
  ├── AURAPersonality      — voice / tone layer
  ├── SystemIntrospector   — reads live kernel state
  ├── ContextBuilder       — assembles prompt context
  └── ModelManager         — AI model inference (optional)
"""

import logging

from kernel.event_bus import EventBus, Event, Priority
from aura.memory import ConversationMemory
from aura.personality import AURAPersonality
from aura.introspection import SystemIntrospector
from aura.context_builder import ContextBuilder

logger = logging.getLogger(__name__)

# Events AURA subscribes to so its snapshot is always current
_WATCHED_EVENTS = (
    "SERVICE_REGISTERED", "SERVICE_STARTED", "SERVICE_STOPPED",
    "SERVICE_RESTARTING", "MODE_ACTIVATED",
    "PERMISSION_REQUEST", "PERMISSION_RESPONSE",
    "SHUTDOWN", "BUILD_COMPLETE", "HEALTH_CHECK", "INTEGRITY_ALERT",
    "NETWORK_STATUS", "STORAGE_EVENT", "JOB_QUEUED", "JOB_COMPLETE",
    "HEALTH_REPORT",
)


class AURA:
    """
    The kernel personality layer.

    Instantiated by the Kernel after the event bus is ready.
    Attach the kernel reference after boot with ``attach_kernel()``.
    """

    def __init__(self, event_bus: EventBus, model_manager=None):
        self._event_bus     = event_bus
        self._model_manager = model_manager
        self._snapshot: dict = {}

        # Sub-systems
        self._memory      = ConversationMemory(max_turns=20)
        self._personality = AURAPersonality()
        self._introspector = SystemIntrospector()
        self._context_builder = ContextBuilder(
            self._introspector, self._memory, self._personality
        )

        # Subscribe to key system events
        for event_type in _WATCHED_EVENTS:
            self._event_bus.subscribe(event_type, self._on_system_event)

    # ------------------------------------------------------------------
    # Kernel attachment (called after Kernel.start())
    # ------------------------------------------------------------------

    def attach_kernel(self, kernel) -> None:
        """Wire the introspector to the live kernel for deep inspection."""
        self._introspector.attach_kernel(kernel)
        mode = getattr(getattr(kernel, "mode", None), "NAME", "universal")
        from host_bridge import detect_host_type
        host = detect_host_type()
        self._personality.set_context(mode=mode, host=host)
        logger.info("AURA: attached to kernel (mode=%s, host=%s)", mode, host)

    # ------------------------------------------------------------------
    # Called by KernelLoop each tick
    # ------------------------------------------------------------------

    def pulse(self, system_state: dict) -> None:
        """Update AURA's world-view. Called every kernel tick."""
        self._snapshot.update(system_state)
        self._snapshot["last_pulse"] = system_state.get("tick", 0)
        # Merge introspector data on every pulse
        self._snapshot.update(self._introspector.snapshot())
        logger.debug("AURA pulse tick=%d", system_state.get("tick", 0))

    # ------------------------------------------------------------------
    # Query interface (Shell + services)
    # ------------------------------------------------------------------

    def query(self, prompt: str) -> str:
        """
        Answer a natural-language query using live system context.

        Flow:
          1. Record the user turn in conversation memory.
          2. Build a rich context dict via ContextBuilder.
          3. If a model is loaded → infer with full prompt.
          4. Otherwise → personality-driven template response.
          5. Record AURA's response in memory.
          6. Return formatted response string.
        """
        self._memory.add_user(prompt)

        ctx = self._context_builder.build_context_dict(prompt)

        if self._model_manager is not None:
            active = self._model_manager.active_model_name()
            if active:
                full_prompt = self._context_builder.build_prompt(prompt)
                raw = self._model_manager.infer(full_prompt, ctx)
                response = self._personality.format_response(raw, prompt, ctx)
            else:
                response = self._personality.format_response("", prompt, ctx)
        else:
            response = self._personality.format_response("", prompt, ctx)

        self._memory.add_aura(response)
        return response

    # ------------------------------------------------------------------
    # Introspection (used by Shell `status`, `sysinfo`, tests)
    # ------------------------------------------------------------------

    def get_state_snapshot(self) -> dict:
        """Return a copy of AURA's current world-view snapshot."""
        return dict(self._snapshot)

    def describe_system(self) -> str:
        """Return a human-readable system description."""
        return self._introspector.describe()

    def get_memory(self) -> ConversationMemory:
        """Return the conversation memory (read-only in tests)."""
        return self._memory

    def get_personality(self) -> AURAPersonality:
        """Return the personality engine."""
        return self._personality

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    def _on_system_event(self, event: Event) -> None:
        """Record system events into the snapshot for context."""
        key = f"last_{event.event_type.lower()}"
        self._snapshot[key] = event.payload
        logger.debug("AURA: recorded event %r", event.event_type)

