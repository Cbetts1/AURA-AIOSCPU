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

Built-in commands
-----------------
  help      status    services   sysinfo
  model     device    build      rebuild
  repair    test      logs       exit / quit
"""

import logging

from aura import AURA
from kernel.event_bus import EventBus, Event, Priority

logger = logging.getLogger(__name__)

BANNER = (
    "\n"
    "╔══════════════════════════════════════════════╗\n"
    "║          AURA-AIOSCPU  v0.1.0                ║\n"
    "║  AI-Driven OS · Universal · Self-Repairing   ║\n"
    "╚══════════════════════════════════════════════╝\n"
    "  Type 'help' for commands or ask AURA anything.\n"
)
PROMPT = "aura> "


class Shell:
    """Text-based AURA-integrated shell."""

    def __init__(self, aura: AURA, event_bus: EventBus,
                 build_service=None, model_manager=None,
                 device_profile=None):
        self._aura           = aura
        self._event_bus      = event_bus
        self._build_svc      = build_service
        self._model_mgr      = model_manager
        self._device_profile = device_profile
        self._running        = False
        self._builtins       = self._register_builtins()
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
        return {
            "help":     self._cmd_help,
            "status":   self._cmd_status,
            "services": self._cmd_services,
            "sysinfo":  self._cmd_sysinfo,
            "device":   self._cmd_device,
            "model":    self._cmd_model,
            "build":    self._cmd_build,
            "rebuild":  self._cmd_build,
            "repair":   self._cmd_repair,
            "test":     self._cmd_test,
            "logs":     self._cmd_logs,
            "exit":     self._cmd_exit,
            "quit":     self._cmd_exit,
        }

    def _cmd_help(self, _args) -> str:
        return (
            "Built-in commands:\n"
            "  help      — show this message\n"
            "  status    — kernel status snapshot\n"
            "  services  — list registered services\n"
            "  sysinfo   — full system state (JSON)\n"
            "  device    — hardware profile and phone compatibility\n"
            "  model     — AI model management  (model list | load <name> | unload)\n"
            "  build     — rebuild AURA rootfs from source\n"
            "  repair    — verify integrity and rebuild if changed\n"
            "  test      — run the full test suite\n"
            "  logs      — show recent log lines\n"
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
        import json
        snap = self._aura.get_state_snapshot()
        if not snap:
            return "No snapshot available yet."
        return json.dumps(snap, indent=2, default=str)

    def _cmd_device(self, _args) -> str:
        if self._device_profile is not None:
            import json
            return json.dumps(self._device_profile.to_dict(), indent=2)
        try:
            from kernel.device_profile import DeviceProfile
            import json
            return json.dumps(DeviceProfile().to_dict(), indent=2)
        except Exception as exc:
            return f"Device profile unavailable: {exc}"

    def _cmd_model(self, args) -> str:
        if not self._model_mgr:
            return "Model manager not initialised."
        sub = args[0].lower() if args else "list"
        if sub == "list":
            models = self._model_mgr.list_models()
            if not models:
                return "No models registered. Place .gguf files in models/"
            lines = ["Registered models:"]
            for m in models:
                active = " [active]" if m["name"] == self._model_mgr.active_model_name() else ""
                lines.append(f"  {m['name']}{active}  ({m['size_mb']:.1f}MB  {m['model_type']})")
            return "\n".join(lines)
        if sub == "load" and len(args) > 1:
            name = args[1]
            ok = self._model_mgr.load(name)
            return f"Model {name!r} loaded." if ok else f"Failed to load {name!r}."
        if sub == "unload":
            self._model_mgr.unload()
            return "Model unloaded — using stub engine."
        if sub == "scan":
            found = self._model_mgr.scan_models_dir()
            return f"Scanned models/: found {found}" if found else "No new models found."
        return "Usage:  model list | model load <name> | model unload | model scan"

    def _cmd_build(self, _args) -> str:
        if not self._build_svc:
            return "Build service not available."
        print("Building rootfs (this may take a moment) …")
        result = self._build_svc.rebuild_rootfs()
        if result:
            status = "✓ Build succeeded" if result.success else "✗ Build failed"
            return f"{status} in {result.duration_s:.1f}s\n{result.message}"
        return "Build started in background."

    def _cmd_repair(self, _args) -> str:
        if not self._build_svc:
            return "Build service not available."
        report = self._build_svc.verify_integrity()
        if report["integrity_ok"]:
            return (
                f"✓ Integrity OK — {report['total_files']} files verified, "
                "no changes detected."
            )
        changed = report["changed_files"]
        lines = [
            f"⚠  {len(changed)} file(s) have changed since last build:",
        ] + [f"  {f}" for f in changed[:10]]
        if len(changed) > 10:
            lines.append(f"  … and {len(changed) - 10} more")
        lines.append("Run 'rebuild' to rebuild the rootfs with the latest source.")
        return "\n".join(lines)

    def _cmd_test(self, _args) -> str:
        if not self._build_svc:
            return "Build service not available."
        print("Running test suite …")
        result = self._build_svc.run_tests()
        if result:
            status = "✓ Tests passed" if result.success else "✗ Tests failed"
            return f"{status} ({result.duration_s:.1f}s)"
        return "Tests running in background."

    def _cmd_logs(self, args) -> str:
        import os
        from pathlib import Path
        lines_n = 30
        if args and args[0].isdigit():
            lines_n = int(args[0])
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dirs  = [
            os.path.join(repo_root, "logs"),
            os.path.join(repo_root, "rootfs", "var", "log"),
        ]
        log_files = []
        for d in log_dirs:
            if os.path.isdir(d):
                log_files.extend(Path(d).glob("*.log"))
        if not log_files:
            return "No log files found."
        latest = sorted(log_files)[-1]
        try:
            with open(latest, errors="replace") as fh:
                content = fh.readlines()
            excerpt = "".join(content[-lines_n:])
            return f"--- {latest} (last {lines_n} lines) ---\n{excerpt}"
        except Exception as exc:
            return f"Could not read log: {exc}"

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
            answer = input(
                f"\n[AURA] Grant capability '{capability}'? [y/N]: "
            )
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        granted = answer.strip().lower() == "y"
        self._event_bus.publish(
            Event("PERMISSION_RESPONSE",
                  payload={"capability": capability, "granted": granted},
                  priority=Priority.HIGH, source="shell")
        )
        logger.info("Shell: permission '%s' -> %s", capability,
                    "granted" if granted else "denied")
