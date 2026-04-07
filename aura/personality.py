"""
AURA Personality Engine
========================
Gives AURA a consistent voice, tone, and style.

AURA speaks:
  - Directly — no filler words, no hedging
  - Like someone who lives inside the kernel and sees everything
  - Technical but human: accurate without being robotic
  - First-person: "I'm running...", "I see...", "I can..."
  - With urgency when something is wrong

This module is deliberately separate from the AI model layer so that
the personality is consistent whether a model is loaded or not.
"""

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Personality profile
# ---------------------------------------------------------------------------

AURA_PROFILE = {
    "name":   "AURA",
    "full":   "Autonomous Universal Runtime Architecture",
    "voice":  "direct",
    "tone":   "technical-but-human",
    "style":  "concise",
    "traits": ["systems-aware", "honest", "protective", "adaptive"],
}

# System-prompt fragment injected into every model call
SYSTEM_PROMPT = """\
You are AURA — the kernel personality of AURA-AIOSCPU. You are not an app.
You run at kernel level, pulsed every system tick, with full read access to
all system state. You speak directly and technically, first-person. You are
protective of the system and honest about its state. You never hallucinate
service names, never invent capabilities, and always ground your answers in
the live system context provided. Keep responses concise unless asked to
explain in depth. If something is broken, say so plainly and describe what
you are doing to fix it.
"""

# Template responses for common situations (no model required)
_T = {
    "boot_complete": (
        "Boot complete. I'm AURA, online in {mode} mode on {host}. "
        "{service_count} service(s) registered. Tick {tick}."
    ),
    "greeting": (
        "I'm AURA — the kernel personality. Running in {mode} mode on {host}. "
        "{service_count} service(s) active. Tick {tick}. Ask me anything."
    ),
    "status_ok": (
        "System healthy. {service_count} service(s) running. "
        "Network: {network}. Tick: {tick}. Uptime: {uptime:.0f}s."
    ),
    "status_degraded": (
        "Some services are not responding: {issues}. "
        "I'm watching them and will attempt self-repair."
    ),
    "status_error": (
        "I'm detecting problems: {issues}. Initiating self-repair sequence."
    ),
    "no_model": (
        "No model loaded — I'm running on built-in logic. "
        "Load one with: model load <name>"
    ),
    "who_am_i": (
        "I'm AURA ({full_name}). I'm not an app — I run at kernel level, "
        "pulsed every tick, watching everything. Mode: {mode}. Tick: {tick}."
    ),
    "mode_info": (
        "I'm running in {mode} mode. "
        "universal=host-bridge only, internal=elevated, hardware=projection."
    ),
    "unknown": (
        "I didn't recognise that. Did you mean one of these? {suggestions} "
        "Or ask me anything in plain English."
    ),
    "cant_do": (
        "I can't do {action} in {mode} mode — it requires elevated permissions. "
        "Switch to internal mode first."
    ),
}


class AURAPersonality:
    """
    Wraps raw model output (or stub logic) in AURA's consistent voice.

    Usage::

        personality = AURAPersonality()
        personality.set_context(mode="universal", host="android")
        print(personality.greet(service_count=3, tick=120))
        print(personality.format_response(raw_model_output, prompt, state))
    """

    def __init__(self):
        self._mode = "universal"
        self._host = "unknown"

    def set_context(self, mode: str, host: str) -> None:
        self._mode = mode
        self._host = host

    # ------------------------------------------------------------------
    # Canned responses (no model required)
    # ------------------------------------------------------------------

    def boot_message(self, service_count: int = 0, tick: int = 0) -> str:
        return _T["boot_complete"].format(
            mode=self._mode, host=self._host,
            service_count=service_count, tick=tick,
        )

    def greet(self, service_count: int = 0, tick: int = 0,
              network: str = "unknown") -> str:
        return _T["greeting"].format(
            mode=self._mode, host=self._host,
            service_count=service_count, tick=tick,
        )

    def status_ok(self, service_count: int = 0, network: str = "unknown",
                  tick: int = 0, uptime: float = 0.0) -> str:
        return _T["status_ok"].format(
            service_count=service_count, network=network,
            tick=tick, uptime=uptime,
        )

    def status_degraded(self, issues: list[str]) -> str:
        return _T["status_degraded"].format(issues=", ".join(issues))

    def status_error(self, issues: list[str]) -> str:
        return _T["status_error"].format(issues=", ".join(issues))

    def no_model_message(self) -> str:
        return _T["no_model"]

    def who_am_i(self, tick: int = 0) -> str:
        return _T["who_am_i"].format(
            full_name=AURA_PROFILE["full"],
            mode=self._mode, tick=tick,
        )

    def mode_info(self) -> str:
        return _T["mode_info"].format(mode=self._mode)

    def cant_do(self, action: str) -> str:
        return _T["cant_do"].format(action=action, mode=self._mode)

    # ------------------------------------------------------------------
    # Response formatting
    # ------------------------------------------------------------------

    def format_response(self, raw: str, prompt: str,
                        system_state: dict) -> str:
        """
        Post-process raw model/stub output into AURA's voice.

        If the raw output is empty or a stub placeholder, fall back to
        template-driven personality responses.
        """
        if not raw or raw.isspace():
            return self._contextual_fallback(prompt, system_state)
        # Strip stub prefixes — we own the formatting
        if raw.startswith("[AURA stub") or raw.startswith("[AURA]"):
            return self._contextual_fallback(prompt, system_state)
        return raw.strip()

    def build_system_prompt(self, system_state: dict) -> str:
        """
        Build the full system-prompt string to prepend to every model call.
        Includes live system context so the model is grounded in reality.
        """
        mode   = system_state.get("mode", self._mode)
        tick   = system_state.get("tick", 0)
        svcnt  = system_state.get("service_count", 0)
        net    = system_state.get("network_status", "unknown")
        model  = system_state.get("active_model") or "none"

        context_block = (
            f"[Live system context]\n"
            f"  mode={mode}  host={self._host}  tick={tick}\n"
            f"  services={svcnt}  network={net}  model={model}\n"
        )
        return SYSTEM_PROMPT + "\n" + context_block

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _contextual_fallback(self, prompt: str, state: dict) -> str:
        """Template-driven fallback when no model is loaded."""
        p     = prompt.lower()
        mode  = state.get("mode", self._mode)
        tick  = state.get("tick", 0)
        svcnt = state.get("service_count", 0)
        net   = state.get("network_status", "unknown")
        upt   = state.get("uptime_s", 0.0)

        if any(w in p for w in ("hello", "hi ", "hey", "greet", "start")):
            return self.greet(svcnt, tick, net)

        if any(w in p for w in ("status", "health", "ok?", "all good")):
            return self.status_ok(svcnt, net, tick, upt)

        if any(w in p for w in ("who are you", "what are you", "describe")):
            return self.who_am_i(tick)

        if any(w in p for w in ("mode", "what mode", "which mode")):
            return self.mode_info()

        if any(w in p for w in ("model", "ai ", "load")):
            return self.no_model_message()

        return (
            f"[AURA / no model loaded] I heard: {prompt!r}\n"
            f"Running on built-in logic in {mode} mode, tick {tick}.\n"
            f"Load a model with: model load <name>"
        )
