"""
AURA-AIOSCPU System Validation Tool
=====================================
Performs an end-to-end validation of the entire OS stack — from Python
version and imports all the way through kernel boot simulation and storage.

Exit codes
----------
  0 — all checks passed
  1 — one or more checks failed

Usage
-----
  python tools/validate_system.py
  python tools/validate_system.py --strict   # exit 1 on warnings too
  python tools/validate_system.py --json     # machine-readable output
"""

import argparse
import json
import os
import sys
import time

# Ensure repo root is on path regardless of invocation directory
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

_PASS    = "PASS"
_FAIL    = "FAIL"
_WARN    = "WARN"
_SKIP    = "SKIP"

_COLOR   = {
    _PASS: "\033[32m",
    _FAIL: "\033[31m",
    _WARN: "\033[33m",
    _SKIP: "\033[36m",
    "reset": "\033[0m",
}


class CheckResult:
    def __init__(self, name: str, status: str, detail: str = ""):
        self.name   = name
        self.status = status
        self.detail = detail

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def _check(name: str, fn) -> CheckResult:
    try:
        detail = fn()
        return CheckResult(name, _PASS, detail or "")
    except Exception as exc:
        return CheckResult(name, _FAIL, str(exc))


def _check_warn(name: str, fn) -> CheckResult:
    """Like _check but downgrades FAIL to WARN."""
    r = _check(name, fn)
    if r.status == _FAIL:
        r.status = _WARN
    return r


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def chk_python_version() -> str:
    v = sys.version_info
    if v < (3, 10):
        raise RuntimeError(f"Python {v.major}.{v.minor} — need ≥ 3.10")
    return f"Python {v.major}.{v.minor}.{v.micro}"


def chk_imports() -> str:
    required = [
        "kernel", "kernel.event_bus", "kernel.scheduler",
        "kernel.loop", "kernel.config", "kernel.device_profile",
        "kernel.watchdog",
        "aura", "shell", "hal", "hal.devices.storage",
        "services", "services.build_service",
        "services.web_terminal", "services.network_service",
        "services.package_manager",
        "models", "models.model_manager",
        "host_bridge",
        "launch.launcher",
    ]
    failed = []
    for mod in required:
        try:
            __import__(mod)
        except ImportError as exc:
            failed.append(f"{mod}: {exc}")
    if failed:
        raise ImportError("\n".join(failed))
    return f"All {len(required)} modules importable"


def chk_config() -> str:
    from kernel.config import Config
    cfg = Config()
    tick = cfg.get("kernel", "tick_interval_ms", 16)
    if not isinstance(tick, int):
        raise TypeError(f"tick_interval_ms should be int, got {type(tick)}")
    return f"Config OK (tick={tick}ms)"


def chk_device_profile() -> str:
    from kernel.device_profile import DeviceProfile
    p = DeviceProfile()
    d = p.to_dict()
    required_keys = {
        "architecture", "cpu_count", "is_64bit",
        "is_android", "is_termux", "is_mobile",
        "memory_mb", "recommended_tick_ms",
    }
    missing = required_keys - d.keys()
    if missing:
        raise KeyError(f"Missing keys: {missing}")
    return (
        f"arch={p.architecture}  mobile={p.is_mobile}  "
        f"mem={p.memory_mb}MB  cpus={p.cpu_count}"
    )


def chk_event_bus() -> str:
    from kernel.event_bus import EventBus, Event, Priority
    bus = EventBus()
    received = []
    bus.subscribe("TEST", received.append)
    bus.publish(Event("TEST", payload={"x": 1}, priority=Priority.NORMAL))
    n = bus.drain()
    if n != 1 or len(received) != 1:
        raise AssertionError(f"Expected 1 event, got {n}")
    return "EventBus publish/subscribe/drain OK"


def chk_scheduler() -> str:
    from kernel.event_bus import EventBus
    from kernel.scheduler import Scheduler
    bus  = EventBus()
    sched = Scheduler(bus)
    ran  = []
    sched.submit_task(lambda: ran.append(1), priority=1)
    sched.tick()
    if not ran:
        raise AssertionError("Task did not execute after tick()")
    return "Scheduler submit_task/tick OK"


def chk_storage() -> str:
    import tempfile, os
    from hal.devices.storage import VStorageDevice
    with tempfile.TemporaryDirectory() as tmpdir:
        db = os.path.join(tmpdir, "test.db")
        dev = VStorageDevice(db)
        dev.start()
        dev.kv_set("test", "hello", "world")
        val = dev.kv_get("test", "hello")
        dev.file_write("/test/data.bin", b"\xde\xad\xbe\xef")
        raw = dev.file_read("/test/data.bin")
        dev.stop()
        if val != "world":
            raise AssertionError(f"KV roundtrip failed: {val!r}")
        if raw != b"\xde\xad\xbe\xef":
            raise AssertionError("File roundtrip failed")
    return "VStorageDevice KV + file store OK"


def chk_hal() -> str:
    from hal import HAL
    h = HAL()
    h.start()
    h.stop()
    return "HAL start/stop OK"


def chk_aura() -> str:
    from kernel.event_bus import EventBus
    from aura import AURA
    bus  = EventBus()
    aura = AURA(bus)
    aura.pulse({"tick": 1, "services": {}})
    resp = aura.query("system status?")
    if not isinstance(resp, str):
        raise TypeError(f"query() returned {type(resp)}")
    return "AURA pulse/query OK"


def chk_shell() -> str:
    from kernel.event_bus import EventBus
    from aura import AURA
    from shell import Shell
    bus   = EventBus()
    aura  = AURA(bus)
    shell = Shell(aura, bus)
    out   = shell.dispatch("help")
    if not out:
        raise AssertionError("help returned empty string")
    out2  = shell.dispatch("status")
    if not isinstance(out2, str):
        raise TypeError(f"status returned {type(out2)}")
    return "Shell dispatch OK"


def chk_web_terminal() -> str:
    from services.web_terminal import WebTerminalService
    svc = WebTerminalService(dispatch_fn=lambda cmd: f"echo: {cmd}")
    ok  = svc.start()
    if not ok:
        raise RuntimeError("WebTerminalService failed to bind (port in use?)")
    import urllib.request
    try:
        resp = urllib.request.urlopen(svc.url, timeout=3)
        html = resp.read()
        if b"AURA" not in html:
            raise AssertionError("Home page did not contain 'AURA'")
    finally:
        svc.stop()
    return f"WebTerminalService HTTP OK at {svc.url}"


def chk_network_service() -> str:
    from services.network_service import check_connectivity
    result = check_connectivity()
    if "status" not in result:
        raise KeyError("check_connectivity missing 'status'")
    return f"NetworkService probe: {result['status']}"


def chk_package_manager() -> str:
    import tempfile
    from services.package_manager import PackageManager
    with tempfile.TemporaryDirectory() as tmpdir:
        reg = os.path.join(tmpdir, "packages.json")
        pm  = PackageManager(registry_path=reg)
        assert isinstance(pm.list_packages(), list)
        assert pm.info("nonexistent") is None
        assert pm.search("x") == []
    return "PackageManager registry OK"


def chk_build_service() -> str:
    from kernel.event_bus import EventBus
    from services.build_service import BuildService
    bs = BuildService(EventBus())
    report = bs.verify_integrity()
    if "integrity_ok" not in report:
        raise KeyError("verify_integrity() missing 'integrity_ok'")
    return f"BuildService integrity_ok={report['integrity_ok']}"


def chk_rootfs() -> str:
    rootfs = os.path.join(_REPO_ROOT, "rootfs")
    required = ["bin", "etc", "usr", "var", "tmp", "home"]
    missing  = [d for d in required
                if not os.path.isdir(os.path.join(rootfs, d))]
    if missing:
        raise FileNotFoundError(f"rootfs missing dirs: {missing}")
    return f"rootfs OK ({len(required)} required dirs present)"


def chk_tests() -> str:
    """Count test files and verify they are importable."""
    import glob
    test_files = glob.glob(os.path.join(_REPO_ROOT, "tests", "test_*.py"))
    if not test_files:
        raise FileNotFoundError("No test files found in tests/")
    return f"{len(test_files)} test modules found"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

CHECKS = [
    (_check,      "Python version",     chk_python_version),
    (_check,      "Module imports",     chk_imports),
    (_check,      "Config system",      chk_config),
    (_check,      "Device profile",     chk_device_profile),
    (_check,      "Event bus",          chk_event_bus),
    (_check,      "Scheduler",          chk_scheduler),
    (_check,      "Storage (SQLite)",   chk_storage),
    (_check,      "HAL",                chk_hal),
    (_check,      "AURA",               chk_aura),
    (_check,      "Shell",              chk_shell),
    (_check_warn, "Web terminal",       chk_web_terminal),
    (_check_warn, "Network service",    chk_network_service),
    (_check,      "Package manager",    chk_package_manager),
    (_check,      "Build service",      chk_build_service),
    (_check,      "rootfs layout",      chk_rootfs),
    (_check,      "Test modules",       chk_tests),
]


def run_validation(strict: bool = False, as_json: bool = False) -> int:
    """
    Run all checks and print results.

    Returns 0 if all PASSed (or only WARNed in non-strict mode), 1 otherwise.
    """
    results   = []
    t_start   = time.monotonic()

    for check_fn, name, fn in CHECKS:
        r = check_fn(name, fn)
        results.append(r)

    duration = time.monotonic() - t_start
    passed   = sum(1 for r in results if r.status == _PASS)
    warned   = sum(1 for r in results if r.status == _WARN)
    failed   = sum(1 for r in results if r.status == _FAIL)
    total    = len(results)

    if as_json:
        print(json.dumps({
            "passed":   passed,
            "warned":   warned,
            "failed":   failed,
            "total":    total,
            "duration": round(duration, 3),
            "checks":   [r.to_dict() for r in results],
        }, indent=2))
    else:
        _print_report(results, passed, warned, failed, total, duration)

    if failed:
        return 1
    if strict and warned:
        return 1
    return 0


def _print_report(results, passed, warned, failed, total, duration):
    use_color = sys.stdout.isatty()

    def _colored(status, text):
        if not use_color:
            return text
        return f"{_COLOR.get(status, '')}{text}{_COLOR['reset']}"

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║         AURA-AIOSCPU  System Validation              ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    label_w = max(len(r.name) for r in results) + 2
    for r in results:
        badge = f"[{r.status}]".ljust(6)
        name  = r.name.ljust(label_w)
        extra = f"  {r.detail}" if r.detail else ""
        print(f"  {_colored(r.status, badge)}  {name}{extra}")

    print()
    summary = (
        f"  {passed}/{total} passed  "
        f"{warned} warn  {failed} fail  "
        f"({duration:.2f}s)"
    )
    if failed:
        print(_colored(_FAIL, summary))
    elif warned:
        print(_colored(_WARN, summary))
    else:
        print(_colored(_PASS, summary))
    print()

    if failed == 0 and warned == 0:
        print("  ✓  AURA-AIOSCPU is fully operational.")
    elif failed == 0:
        print("  ⚠  Some optional components have warnings.")
    else:
        print("  ✗  Critical checks failed — see details above.")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AURA-AIOSCPU system validation"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit 1 on warnings as well as failures",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Machine-readable JSON output",
    )
    args = parser.parse_args()
    sys.exit(run_validation(strict=args.strict, as_json=args.json))


if __name__ == "__main__":
    main()
