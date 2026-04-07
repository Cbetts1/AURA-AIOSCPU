"""
AURA Context Builder
=====================
Builds rich, structured context dicts and prompt strings for model calls.

The context builder assembles everything the model needs to give a
grounded, accurate response:
  - live system state (from introspector)
  - conversation history (from memory)
  - active kernel mode
  - service states
  - recent logs
  - user prompt

This keeps the model construction logic in one place and out of AURA's
core query path.
"""

import logging
import time

logger = logging.getLogger(__name__)

# Maximum characters of log context to inject (keep prompts manageable)
_MAX_LOG_CHARS = 800
# Maximum conversation turns to include in prompt
_MAX_HISTORY_TURNS = 8


class ContextBuilder:
    """
    Assembles a rich context payload for AURA's model inference calls.

    Usage::

        builder = ContextBuilder(introspector, memory, personality)
        ctx_dict  = builder.build_context_dict(prompt)
        full_prompt = builder.build_prompt(prompt)
    """

    def __init__(self, introspector, memory, personality):
        self._introspector = introspector
        self._memory       = memory
        self._personality  = personality

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_context_dict(self, prompt: str) -> dict:
        """
        Return a flat dict containing all context for model inference.

        Keys are stable — downstream code (ModelManager, tests) can rely on them.
        """
        snap = self._introspector.snapshot()
        ctx: dict = {
            # Prompt
            "prompt":          prompt,
            "timestamp":       time.time(),
            # Live system
            "mode":            snap.get("mode", "unknown"),
            "tick":            snap.get("tick", 0),
            "uptime_s":        snap.get("uptime_s", 0.0),
            "service_count":   snap.get("service_count", 0),
            "services":        snap.get("services", {}),
            "network_status":  snap.get("network_status", "unknown"),
            "storage_status":  snap.get("storage_status", "unknown"),
            "active_model":    snap.get("active_model"),
            "models_available": snap.get("models_available", 0),
            "task_queue_depth": snap.get("task_queue_depth", 0),
            "job_queue_depth":  snap.get("job_queue_depth", 0),
            # Platform
            "platform":        snap.get("platform", "unknown"),
            "arch":            snap.get("arch", "unknown"),
            # Conversation
            "history":         self._memory.format_for_prompt(_MAX_HISTORY_TURNS),
            "turn_count":      self._memory.turn_count(),
            # Logs (truncated)
            "recent_logs":     self._recent_log_snippet(),
        }
        # Health summary if available
        health = self._introspector.get_health_summary()
        if health:
            ctx["health"] = health
        return ctx

    def build_prompt(self, user_prompt: str) -> str:
        """
        Build the full prompt string to send to the model.

        Structure::

            <system_prompt>

            [Conversation history]
            ...

            [Live system context]
            ...

            User: <user_prompt>
            AURA:
        """
        ctx  = self.build_context_dict(user_prompt)
        sys  = self._personality.build_system_prompt(ctx)
        hist = ctx["history"]
        logs = ctx["recent_logs"]

        parts = [sys]

        if hist:
            parts.append(f"[Conversation history]\n{hist}")

        if logs:
            parts.append(f"[Recent log activity]\n{logs}")

        parts.append(f"User: {user_prompt}\nAURA:")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _recent_log_snippet(self) -> str:
        """Return a truncated snippet of recent log lines."""
        try:
            lines = self._introspector.get_recent_logs(15)
            if not lines:
                return ""
            text = "\n".join(lines)
            if len(text) > _MAX_LOG_CHARS:
                text = "..." + text[-_MAX_LOG_CHARS:]
            return text
        except Exception:
            return ""
