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
  help      status    services   sysinfo    version   uname
  model     device    build      rebuild    repair    test
  logs      exit/quit

  File system:   ls  cat  pwd  mkdir  rm  write  echo
  System:        ps  clear  history  date  uptime  whoami
  Network:       ping  net
  Packages:      pkg  (install/uninstall/list/info/search/upgrade)
  Web terminal:  web  (start/stop/status)
"""

import datetime
import logging
import os
import socket
import threading
import time

from aura import AURA
from kernel.event_bus import EventBus, Event, Priority

logger = logging.getLogger(__name__)

_VERSION = "0.1.0"

BANNER = (
    "\n"
    "╔══════════════════════════════════════════════════╗\n"
    "║           AURA-AIOSCPU  v0.1.0                   ║\n"
    "║   AI-Driven OS · Self-Repairing · Mobile-Ready   ║\n"
    "╚══════════════════════════════════════════════════╝\n"
    "  Type 'help' for commands or ask AURA anything.\n"
    "  Type 'web start' to open a browser terminal on port 7331.\n"
)
PROMPT = "aura> "

_HISTORY_LIMIT = 200


class Shell:
    """Text-based AURA-integrated shell."""

    def __init__(self, aura: AURA, event_bus: EventBus,
                 build_service=None, model_manager=None,
                 device_profile=None, web_terminal=None,
                 network_service=None, package_manager=None):
        self._aura            = aura
        self._event_bus       = event_bus
        self._build_svc       = build_service
        self._model_mgr       = model_manager
        self._device_profile  = device_profile
        self._web_terminal    = web_terminal
        self._network_svc     = network_service
        self._pkg_mgr         = package_manager
        self._running         = False
        self._history: list[str] = []
        self._start_time      = time.monotonic()
        self._cwd             = os.path.expanduser("~")
        self._builtins        = self._register_builtins()
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
                self._history.append(line)
                if len(self._history) > _HISTORY_LIMIT:
                    self._history.pop(0)
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
            # Core OS
            "help":     self._cmd_help,
            "status":   self._cmd_status,
            "services": self._cmd_services,
            "sysinfo":  self._cmd_sysinfo,
            "version":  self._cmd_version,
            "uname":    self._cmd_uname,
            # Device / hardware
            "device":   self._cmd_device,
            # AI model management
            "model":    self._cmd_model,
            # Build / self-repair
            "build":    self._cmd_build,
            "rebuild":  self._cmd_build,
            "repair":   self._cmd_repair,
            "test":     self._cmd_test,
            # Logs
            "logs":     self._cmd_logs,
            # File system
            "ls":       self._cmd_ls,
            "cat":      self._cmd_cat,
            "pwd":      self._cmd_pwd,
            "mkdir":    self._cmd_mkdir,
            "rm":       self._cmd_rm,
            "write":    self._cmd_write,
            "echo":     self._cmd_echo,
            # System info
            "ps":       self._cmd_ps,
            "clear":    self._cmd_clear,
            "history":  self._cmd_history,
            "date":     self._cmd_date,
            "uptime":   self._cmd_uptime,
            "whoami":   self._cmd_whoami,
            # Network
            "ping":     self._cmd_ping,
            "net":      self._cmd_net,
            # Package manager
            "pkg":      self._cmd_pkg,
            # Web terminal
            "web":      self._cmd_web,
            # Exit
            "exit":     self._cmd_exit,
            "quit":     self._cmd_exit,
        }

    def _cmd_help(self, _args) -> str:
        return (
            "Built-in commands:\n"
            "\n"
            "  Core OS\n"
            "    help      — show this message\n"
            "    status    — kernel status snapshot\n"
            "    services  — list registered services\n"
            "    sysinfo   — full system state (JSON)\n"
            "    version   — AURA-AIOSCPU version info\n"
            "    uname     — OS / kernel identity\n"
            "\n"
            "  Device\n"
            "    device    — hardware profile and phone compatibility\n"
            "\n"
            "  AI Model\n"
            "    model     — list | load <name> | unload | scan\n"
            "\n"
            "  Build & Repair\n"
            "    build     — rebuild AURA rootfs from source\n"
            "    repair    — verify and rebuild if changed\n"
            "    test      — run the full test suite\n"
            "    logs [N]  — show last N log lines (default 30)\n"
            "\n"
            "  File System\n"
            "    ls [path] — list directory contents\n"
            "    cat <file>— show file contents\n"
            "    pwd       — current working directory\n"
            "    mkdir <d> — create directory\n"
            "    rm <path> — remove file or empty directory\n"
            "    write <file> <text> — write text to file\n"
            "    echo <text>         — print text\n"
            "\n"
            "  System\n"
            "    ps        — show running threads\n"
            "    clear     — clear the terminal screen\n"
            "    history [N] — show recent commands\n"
            "    date      — current date and time\n"
            "    uptime    — system uptime\n"
            "    whoami    — current user\n"
            "\n"
            "  Network\n"
            "    ping <host>     — check connectivity to host\n"
            "    net             — network status\n"
            "\n"
            "  Packages\n"
            "    pkg list               — list installed packages\n"
            "    pkg install <name>     — install a Python package\n"
            "    pkg uninstall <name>   — remove a package\n"
            "    pkg upgrade <name>     — upgrade a package\n"
            "    pkg info <name>        — show package details\n"
            "    pkg search <term>      — search installed packages\n"
            "\n"
            "  Web Terminal\n"
            "    web start [port]  — start browser terminal (default :7331)\n"
            "    web stop          — stop browser terminal\n"
            "    web status        — show web terminal URL\n"
            "\n"
            "  Exit\n"
            "    exit / quit  — shut down AURA-AIOSCPU\n"
            "\n"
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
    # New commands — version / uname
    # ------------------------------------------------------------------

    def _cmd_version(self, _args) -> str:
        import platform
        return (
            f"AURA-AIOSCPU  v{_VERSION}\n"
            f"Python {platform.python_version()}  "
            f"[{platform.python_implementation()}]\n"
            f"Platform: {platform.system()} {platform.release()}\n"
            f"Machine:  {platform.machine()}"
        )

    def _cmd_uname(self, args) -> str:
        import platform
        if "-a" in args or not args:
            return (
                f"AURA-AIOSCPU {platform.node()} "
                f"{_VERSION} {platform.system()} "
                f"{platform.release()} {platform.machine()}"
            )
        return platform.system()

    # ------------------------------------------------------------------
    # File system commands
    # ------------------------------------------------------------------

    def _cmd_ls(self, args) -> str:
        path = args[0] if args else self._cwd
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        try:
            entries = sorted(os.listdir(path))
        except PermissionError:
            return f"ls: permission denied: {path}"
        except FileNotFoundError:
            return f"ls: no such directory: {path}"
        if not entries:
            return "(empty)"
        lines = []
        for name in entries:
            full = os.path.join(path, name)
            if os.path.isdir(full):
                lines.append(name + "/")
            else:
                size = os.path.getsize(full)
                lines.append(f"{name}  ({size:,} B)")
        return "\n".join(lines)

    def _cmd_cat(self, args) -> str:
        if not args:
            return "Usage: cat <file>"
        path = args[0]
        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        try:
            with open(path, errors="replace") as fh:
                content = fh.read()
            return content if content else "(empty file)"
        except FileNotFoundError:
            return f"cat: no such file: {path}"
        except PermissionError:
            return f"cat: permission denied: {path}"
        except Exception as exc:
            return f"cat: error: {exc}"

    def _cmd_pwd(self, _args) -> str:
        return self._cwd

    def _cmd_mkdir(self, args) -> str:
        if not args:
            return "Usage: mkdir <directory>"
        path = args[0]
        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        try:
            os.makedirs(path, exist_ok=True)
            return f"Created: {path}"
        except Exception as exc:
            return f"mkdir: {exc}"

    def _cmd_rm(self, args) -> str:
        if not args:
            return "Usage: rm <path>"
        path = args[0]
        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        try:
            if os.path.isdir(path):
                os.rmdir(path)
                return f"Removed directory: {path}"
            else:
                os.remove(path)
                return f"Removed: {path}"
        except FileNotFoundError:
            return f"rm: no such file or directory: {path}"
        except OSError as exc:
            return f"rm: {exc}"

    def _cmd_write(self, args) -> str:
        if len(args) < 2:
            return "Usage: write <file> <content...>"
        path    = args[0]
        content = " ".join(args[1:])
        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w") as fh:
                fh.write(content + "\n")
            return f"Written {len(content)} chars to {path}"
        except Exception as exc:
            return f"write: {exc}"

    def _cmd_echo(self, args) -> str:
        return " ".join(args)

    # ------------------------------------------------------------------
    # System info commands
    # ------------------------------------------------------------------

    def _cmd_ps(self, _args) -> str:
        threads = threading.enumerate()
        lines = [f"{'NAME':<32} {'DAEMON':<7} STATE"]
        lines.append("-" * 48)
        for t in sorted(threads, key=lambda x: x.name):
            daemon = "yes" if t.daemon else "no"
            state  = "alive" if t.is_alive() else "dead"
            lines.append(f"{t.name:<32} {daemon:<7} {state}")
        lines.append(f"\n{len(threads)} thread(s) total")
        return "\n".join(lines)

    def _cmd_clear(self, _args) -> str:
        return "\033[2J\033[H"

    def _cmd_history(self, args) -> str:
        n = 20
        if args and args[0].isdigit():
            n = int(args[0])
        items = self._history[-n:]
        if not items:
            return "No history yet."
        return "\n".join(f"  {i+1:>3}  {cmd}"
                         for i, cmd in enumerate(items))

    def _cmd_date(self, _args) -> str:
        now = datetime.datetime.now()
        return now.strftime("%A %Y-%m-%d  %H:%M:%S").strip()

    def _cmd_uptime(self, _args) -> str:
        elapsed = time.monotonic() - self._start_time
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        return f"AURA-AIOSCPU uptime: {h:02d}:{m:02d}:{s:02d}"

    def _cmd_whoami(self, _args) -> str:
        try:
            import pwd
            return pwd.getpwuid(os.getuid()).pw_name
        except Exception:
            return os.environ.get("USER",
                                  os.environ.get("USERNAME", "aura"))

    # ------------------------------------------------------------------
    # Network commands
    # ------------------------------------------------------------------

    def _cmd_ping(self, args) -> str:
        if not args:
            return "Usage: ping <host>"
        host    = args[0]
        timeout = 3.0
        for port in (80, 443, 53):
            try:
                t0   = time.monotonic()
                sock = socket.create_connection((host, port), timeout=timeout)
                rtt  = (time.monotonic() - t0) * 1000.0
                sock.close()
                return f"PING {host}:{port} — OK  {rtt:.1f} ms"
            except OSError:
                continue
        # DNS fallback
        try:
            addrs = socket.getaddrinfo(host, None)
            ip    = addrs[0][4][0] if addrs else "?"
            return f"PING {host} — DNS: {ip}  (TCP blocked)"
        except socket.gaierror:
            return f"PING {host} — unreachable (offline or no route)"

    def _cmd_net(self, _args) -> str:
        if self._network_svc is not None:
            result = self._network_svc.probe_now()
        else:
            from services.network_service import check_connectivity
            result = check_connectivity()
        lines = [
            f"Network status:  {result.get('status', 'unknown').upper()}",
            f"  Latency:    {result.get('latency_ms') or 'N/A'} ms",
            f"  DNS:        {'OK' if result.get('dns_ok') else 'FAIL'}",
            f"  Local IP:   {result.get('interface') or 'N/A'}",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Package manager commands
    # ------------------------------------------------------------------

    def _cmd_pkg(self, args) -> str:
        sub = args[0].lower() if args else "list"

        if self._pkg_mgr is None:
            from services.package_manager import PackageManager
            self._pkg_mgr = PackageManager(self._event_bus)

        if sub == "list":
            pkgs = self._pkg_mgr.list_packages()
            if not pkgs:
                return "No packages installed via AURA yet.\nTip: pkg install <name>"
            lines = [f"{'NAME':<25} {'VERSION':<15} DESCRIPTION"]
            lines.append("-" * 65)
            for p in pkgs:
                desc = (p["description"] or "")[:25]
                lines.append(f"{p['name']:<25} {p['version']:<15} {desc}")
            return "\n".join(lines)

        if sub == "install" and len(args) > 1:
            name = args[1]
            print(f"Installing {name!r} …")
            result = self._pkg_mgr.install(name)
            return result["message"]

        if sub == "uninstall" and len(args) > 1:
            name = args[1]
            result = self._pkg_mgr.uninstall(name)
            return result["message"]

        if sub == "upgrade" and len(args) > 1:
            name = args[1]
            print(f"Upgrading {name!r} …")
            result = self._pkg_mgr.upgrade(name)
            return result["message"]

        if sub == "info" and len(args) > 1:
            name = args[1]
            info = self._pkg_mgr.info(name)
            if info is None:
                return f"Package {name!r} not found in registry."
            return (
                f"Name:        {info['name']}\n"
                f"Version:     {info['version']}\n"
                f"Description: {info['description']}\n"
                f"Installed:   {datetime.datetime.fromtimestamp(info['installed_at'])}"
            )

        if sub == "search" and len(args) > 1:
            term  = args[1]
            found = self._pkg_mgr.search(term)
            if not found:
                return f"No packages matching {term!r}."
            return "\n".join(
                f"  {p['name']}  {p['version']}" for p in found
            )

        return (
            "Usage:\n"
            "  pkg list\n"
            "  pkg install <name>\n"
            "  pkg uninstall <name>\n"
            "  pkg upgrade <name>\n"
            "  pkg info <name>\n"
            "  pkg search <term>"
        )

    # ------------------------------------------------------------------
    # Web terminal commands
    # ------------------------------------------------------------------

    def _cmd_web(self, args) -> str:
        sub  = args[0].lower() if args else "status"
        port = 7331
        if len(args) > 1 and args[1].isdigit():
            port = int(args[1])

        if sub == "start":
            if self._web_terminal is None:
                from services.web_terminal import WebTerminalService
                self._web_terminal = WebTerminalService(
                    dispatch_fn=self.dispatch,
                    event_bus=self._event_bus,
                    port=port,
                )
            if self._web_terminal.is_running:
                return f"Web terminal already running at {self._web_terminal.url}"
            ok = self._web_terminal.start()
            if ok:
                return (
                    f"✓ Web terminal started at {self._web_terminal.url}\n"
                    f"  Open Chrome on your S21 and go to:\n"
                    f"  {self._web_terminal.url}"
                )
            return "✗ Failed to start web terminal (port may be in use)."

        if sub == "stop":
            if self._web_terminal is None or not self._web_terminal.is_running:
                return "Web terminal is not running."
            self._web_terminal.stop()
            return "Web terminal stopped."

        if sub == "status":
            if self._web_terminal and self._web_terminal.is_running:
                return (
                    f"Web terminal: running\n"
                    f"  URL: {self._web_terminal.url}"
                )
            return "Web terminal: stopped.  Run 'web start' to launch it."

        return "Usage:  web start [port] | web stop | web status"

    # ------------------------------------------------------------------
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
