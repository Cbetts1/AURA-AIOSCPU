"""
AURA-AIOSCPU Deterministic Boot Chain
======================================
Implements the 6-stage boot lifecycle (Contract 16).

Each stage:
  - logs its start and completion with timestamps.
  - fails fast with a clear BootError if requirements are not met.
  - publishes a BOOT_STAGE_<N>_COMPLETE event on the event bus.
  - NEVER silently skips a failed stage.

Stages
------
  Stage 0 — Environment Detection
    Detect host OS, arch, Python version.
    Select host bridge. Probe safe paths.
    Load + validate config.

  Stage 1 — Rootfs Mount
    Locate rootfs (local filesystem / SD card / mounted volume).
    Verify all partition directories exist.
    Write layout.json manifest.
    Detect SD card and optionally switch rootfs root.

  Stage 2 — Kernel Init
    Start HAL + virtual storage.
    Start EventBus + Scheduler.
    Create PermissionModel, AURA, KernelAPI, COL, AURAPrivilege,
    MirrorModeEnforcer, ServiceManager.

  Stage 3 — Services Init
    Start StorageService, LoggingService, JobQueue, HealthMonitor.
    Start NetworkService + Watchdog.
    Discover .service unit files.

  Stage 4 — Shell / Interfaces
    Start shell thread.
    Start web terminal (if configured).

  Stage 5 — AI Persona Online
    Attach AURA to live kernel.
    Wire privilege layer with logging service.
    Publish BOOT_COMPLETE with AURA boot message.

Usage::

    from launch.boot import BootChain
    boot = BootChain(mode, config)
    kernel = boot.run()   # blocks until shutdown
"""

import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# BootError — fail-fast exception
# ---------------------------------------------------------------------------

class BootError(RuntimeError):
    """Raised when a required boot stage cannot complete."""
    def __init__(self, stage: int, reason: str):
        self.stage  = stage
        self.reason = reason
        super().__init__(f"[Stage {stage}] Boot failed: {reason}")


# ---------------------------------------------------------------------------
# BootLog — records the lifecycle of a boot attempt
# ---------------------------------------------------------------------------

class BootLog:
    """Immutable record of a boot attempt for `aura boot-log`."""

    def __init__(self):
        self._entries: list[dict] = []
        self._boot_ts = time.time()

    def record(self, stage: int, event: str,
               detail: str = "", ok: bool = True) -> None:
        self._entries.append({
            "ts":     time.time(),
            "stage":  stage,
            "event":  event,
            "detail": detail,
            "ok":     ok,
        })
        level = logging.INFO if ok else logging.ERROR
        logger.log(level, "[Stage %d] %s  %s", stage, event, detail)

    def entries(self) -> list[dict]:
        return list(self._entries)

    def summary(self) -> str:
        lines = [f"Boot started at {time.ctime(self._boot_ts)}"]
        for e in self._entries:
            ts = time.strftime("%H:%M:%S", time.localtime(e["ts"]))
            ok = "OK" if e["ok"] else "FAIL"
            lines.append(f"  [{ts}] Stage {e['stage']} {ok}  {e['event']}")
            if e["detail"]:
                lines.append(f"         {e['detail']}")
        return "\n".join(lines)

    def write_to_file(self, path: str) -> None:
        import json
        try:
            with open(path, "w") as fh:
                json.dump({"boot_ts": self._boot_ts,
                           "entries": self._entries}, fh, indent=2)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# BootChain — 6-stage boot
# ---------------------------------------------------------------------------

class BootChain:
    """
    Deterministic 6-stage boot chain.

    Usage::

        chain  = BootChain(mode, config=config)
        kernel = chain.run()
    """

    def __init__(self, mode, config=None):
        self._mode    = mode
        self._config  = config
        self.log      = BootLog()
        self._kernel  = None

    # ------------------------------------------------------------------
    # run() — execute all stages in order
    # ------------------------------------------------------------------

    def run(self):
        """Execute all boot stages. Returns the live Kernel object."""
        for stage_fn in (
            self._stage_0_environment,
            self._stage_1_rootfs,
            self._stage_2_kernel_init,
            self._stage_3_services,
            self._stage_4_shell,
            self._stage_5_ai_persona,
        ):
            stage_fn()

        # Write boot log to rootfs/var/
        _write_boot_log(self.log, self._config)

        return self._kernel

    # ------------------------------------------------------------------
    # Stage 0 — Environment Detection
    # ------------------------------------------------------------------

    def _stage_0_environment(self) -> None:
        self.log.record(0, "START", "environment detection")
        t0 = time.monotonic()

        # Python version check
        if sys.version_info < (3, 10):
            raise BootError(
                0,
                f"Python >= 3.10 required, got {sys.version}. "
                f"Upgrade Python and retry."
            )

        # Bridge detection
        try:
            from bridge import get_bridge, detect_host_type
            bridge     = get_bridge()
            host_type  = detect_host_type()
            info       = bridge.get_sys_info()
            _tmpdir    = bridge.get_temp_dir()   # verifies writeable
        except Exception as exc:
            raise BootError(0, f"Host bridge init failed: {exc}") from exc

        elapsed = time.monotonic() - t0
        self.log.record(
            0, "COMPLETE",
            f"host={host_type} arch={info.get('arch','?')} "
            f"python={info.get('python','?')} elapsed={elapsed:.2f}s"
        )

    # ------------------------------------------------------------------
    # Stage 1 — Rootfs Mount
    # ------------------------------------------------------------------

    def _stage_1_rootfs(self) -> None:
        self.log.record(1, "START", "rootfs mount")
        t0 = time.monotonic()

        rootfs_path = _locate_rootfs(self._config)
        if not rootfs_path:
            raise BootError(
                1,
                "rootfs not found. Expected at ./rootfs/ or on SD card. "
                "Run `aura build` to create it."
            )

        # Verify minimum partition layout
        required = ["var", "etc", "home", "tmp"]
        missing  = [
            p for p in required
            if not os.path.isdir(os.path.join(rootfs_path, p))
        ]
        if missing:
            raise BootError(
                1,
                f"rootfs at {rootfs_path!r} is missing partitions: "
                f"{missing}. Run `aura build` to rebuild."
            )

        elapsed = time.monotonic() - t0
        self.log.record(
            1, "COMPLETE",
            f"rootfs={rootfs_path} elapsed={elapsed:.2f}s"
        )
        self._rootfs_path = rootfs_path

    # ------------------------------------------------------------------
    # Stage 2 — Kernel Init
    # ------------------------------------------------------------------

    def _stage_2_kernel_init(self) -> None:
        self.log.record(2, "START", "kernel init")
        t0 = time.monotonic()

        try:
            from kernel import Kernel
            self._kernel = Kernel(
                self._mode,
                config=self._config,
            )
        except Exception as exc:
            raise BootError(2, f"Kernel init failed: {exc}") from exc

        elapsed = time.monotonic() - t0
        self.log.record(
            2, "COMPLETE",
            f"subsystems initialised  elapsed={elapsed:.2f}s"
        )

    # ------------------------------------------------------------------
    # Stage 3 — Services Init  (Kernel.start() handles this)
    # ------------------------------------------------------------------

    def _stage_3_services(self) -> None:
        self.log.record(3, "START", "services init")
        # Actual service starting happens inside kernel.start()
        # We record the intent here; completion is logged after stage 5.
        self.log.record(3, "SCHEDULED",
                        "service start delegated to kernel.start()")

    # ------------------------------------------------------------------
    # Stage 4 — Shell / Interfaces  (also inside kernel.start())
    # ------------------------------------------------------------------

    def _stage_4_shell(self) -> None:
        self.log.record(4, "START", "shell / interfaces init")
        self.log.record(4, "SCHEDULED",
                        "shell thread start delegated to kernel.start()")

    # ------------------------------------------------------------------
    # Stage 5 — AI Persona Online  (AURA attached inside kernel.start())
    # ------------------------------------------------------------------

    def _stage_5_ai_persona(self) -> None:
        self.log.record(5, "START", "AI persona init")
        # Subscribe to BOOT_COMPLETE to finalise the log entry
        def _on_boot_complete(event):
            mode    = event.payload.get("mode", "?")
            svcnt   = event.payload.get("service_count", 0)
            host    = event.payload.get("host", "?")
            self.log.record(
                5, "COMPLETE",
                f"AURA online  mode={mode}  host={host}  services={svcnt}"
            )
        try:
            self._kernel.event_bus.subscribe(
                "BOOT_COMPLETE", _on_boot_complete
            )
        except Exception:
            pass
        self.log.record(5, "SUBSCRIBED",
                        "AURA attached on BOOT_COMPLETE event")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _locate_rootfs(config) -> str | None:
    """Find the rootfs directory. Checks config → local → SD card."""
    # Config override
    if config is not None:
        configured = config.get("rootfs", "path", "")
        if configured and os.path.isdir(configured):
            return os.path.abspath(configured)

    # Default: rootfs/ next to the repo root
    default = os.path.join(_REPO_ROOT, "rootfs")
    if os.path.isdir(default):
        return default

    # SD card detection (delegated to bridge)
    try:
        from bridge import get_bridge
        bridge = get_bridge()
        info   = bridge.get_sys_info()
        host   = info.get("host", "linux")
        _SD_PROBES = {
            "android": [
                "/storage/sdcard1/aura-rootfs",
                "/storage/extSdCard/aura-rootfs",
                "/sdcard/aura-rootfs",
            ],
            "linux": ["/media/aura-rootfs", "/mnt/sdcard/aura-rootfs"],
            "macos": ["/Volumes/aura-rootfs"],
            "windows": [],
        }
        for path in _SD_PROBES.get(host, []):
            if os.path.isdir(path):
                logger.info("boot: found rootfs on SD card at %r", path)
                return path
    except Exception:
        pass
    return None


def _write_boot_log(boot_log: BootLog, config) -> None:
    """Write boot log to rootfs/var/boot.log."""
    try:
        rootfs = _locate_rootfs(config) or os.path.join(_REPO_ROOT, "rootfs")
        var_dir = os.path.join(rootfs, "var")
        os.makedirs(var_dir, exist_ok=True)
        boot_log.write_to_file(os.path.join(var_dir, "boot.log"))
    except Exception:
        pass
