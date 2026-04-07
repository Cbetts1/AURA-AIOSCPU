"""
AURA-AIOSCPU Shell
==================
A text-based, AURA-integrated command shell.

Responsibilities
----------------
- Accept user text input.
- Dispatch recognised OS commands (built-ins) directly.
- Forward unrecognised input to AURA.query() as natural language.
- Display AURA responses and command output.
- Surface PERMISSION_REQUEST events to the user and return consent tokens.

The shell is AURA's primary user-facing interface. It is started by the
kernel in a background thread after all other subsystems are ready.
"""

import logging

from aura import AURA
from kernel.event_bus import EventBus, Event, Priority

logger = logging.getLogger(__name__)

BANNER = "AURA-AIOSCPU shell — type a command or ask AURA anything."
PROMPT = "aura> "


class Shell:
    """Text-based AURA-integrated shell."""

    def __init__(self, aura: AURA, event_bus: EventBus):
        self._aura = aura
        self._event_bus = event_bus
        self._running = False
        self._builtins = self._register_builtins()
        self._event_bus.subscribe("PERMISSION_REQUEST",
                                  self._handle_permission_request)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Enter the interactive shell loop (blocks the calling thread)."""
        self._running = True
        print(BANNER)
        while self._running:
            try:
                line = input(PROMPT).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                self.stop()
                break
            if line:
                output = self.dispatch(line)
                if output:
                    print(output)

    def stop(self) -> None:
        """Signal the shell loop to exit."""
        self._running = False

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def dispatch(self, input_text: str) -> str:
        """Route input to a built-in handler or to AURA.

        Returns the output string to display.
        """
        tokens = input_text.split()
        if not tokens:
            return ""
        command = tokens[0].lower()
        if command in self._builtins:
            return self._builtins[command](tokens[1:])
        return self._aura.query(input_text)

    # ------------------------------------------------------------------
    # Built-in commands
    # ------------------------------------------------------------------

    def _register_builtins(self) -> dict:
        """Return the map of built-in command name → handler function."""
        return {
            "help":     self._cmd_help,
            "status":   self._cmd_status,
            "services": self._cmd_services,
            "sysinfo":  self._cmd_sysinfo,
            "exit":     self._cmd_exit,
            "quit":     self._cmd_exit,
        }

    def _cmd_help(self, _args) -> str:
        return (
            "Built-in commands:\n"
            "  help      — show this message\n"
            "  status    — show kernel status\n"
            "  services  — list registered services\n"
            "  sysinfo   — show system state snapshot\n"
            "  exit      — shut down AURA-AIOSCPU\n"
            "  <anything else> — ask AURA"
        )

    def _cmd_status(self, _args) -> str:
        snap = self._aura.get_state_snapshot()
        if not snap:
            return "Kernel status: running (no state yet)"
        lines = ["Kernel status:"]
        for k, v in snap.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    def _cmd_services(self, _args) -> str:
        snap = self._aura.get_state_snapshot()
        services = snap.get("services", {})
        if not services:
            return "No services registered."
        lines = ["Services:"]
        for name, state in services.items():
            lines.append(f"  {name}: {state}")
        return "\n".join(lines)

    def _cmd_sysinfo(self, _args) -> str:
        snap = self._aura.get_state_snapshot()
        if not snap:
            return "System info: no snapshot available yet."
        import json
        return json.dumps(snap, indent=2, default=str)

    def _cmd_exit(self, _args) -> str:
        self._event_bus.publish(
            Event("SHUTDOWN", payload={"source": "shell"},
                  priority=Priority.CRITICAL, source="shell")
        )
        self.stop()
        return "Shutting down AURA-AIOSCPU..."

    # ------------------------------------------------------------------
    # Permission request handler (subscribed to event bus)
    # ------------------------------------------------------------------

    def _handle_permission_request(self, event: Event) -> None:
        """Display a consent prompt and publish the user's response."""
        capability = (event.payload or {}).get("capability", "unknown")
        try:
            answer = input(f"\n[AURA] Grant capability '{capability}'? [y/N]: ")
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        granted = answer.strip().lower() == "y"
        self._event_bus.publish(
            Event("PERMISSION_RESPONSE",
                  payload={"capability": capability, "granted": granted},
                  priority=Priority.HIGH, source="shell")
        )
        logger.info("Shell: permission '%s' → %s", capability,
                    "granted" if granted else "denied")

