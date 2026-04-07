#!/usr/bin/env python3
"""
aura — AURA-AIOSCPU Unified Operator CLI
==========================================
Usage:
  aura                        → interactive shell (via launcher)
  aura status                 → kernel + services state
  aura doctor                 → deep system + environment validation
  aura build [--verify]       → build rootfs from source
  aura repair                 → verify and rebuild if drift detected
  aura test [--conformance]   → run test suite
  aura logs [--tail N]        → show system logs
  aura mirror                 → mirror/projection status
  aura host                   → host-bridge capabilities
  aura boot-log               → last boot lifecycle
  aura provenance             → build time, source commit, environment
  aura override <action>      → request a COL override (interactive)
  aura --help                 → this help

Exit codes:
  0  — all OK
  1  — validation/test failure
  2  — runtime error
  3  — environment incompatible

Scripting notes:
  All subcommands are non-interactive unless marked [interactive].
  Use --json for machine-readable output where supported.
  This CLI NEVER mutates /src without explicit intent.
"""

import argparse
import json
import os
import subprocess
import sys
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_header(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def _ok(msg: str)   -> None: print(f"  ✓  {msg}")
def _warn(msg: str) -> None: print(f"  ⚠  {msg}")
def _fail(msg: str) -> None: print(f"  ✗  {msg}", file=sys.stderr)
def _info(msg: str) -> None: print(f"     {msg}")


def _require_python() -> None:
    if sys.version_info < (3, 10):
        _fail(f"Python 3.10+ required (got {sys.version})")
        sys.exit(3)


def _add_repo_to_path() -> None:
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_status(args) -> int:
    """Print kernel + services state."""
    _add_repo_to_path()
    _print_header("AURA-AIOSCPU  Status")
    try:
        from bridge import get_bridge, detect_host_type
        bridge    = get_bridge()
        host_type = detect_host_type()
        info      = bridge.get_sys_info()
        _ok(f"Host bridge    : {host_type}  ({info.get('arch','?')})")
        _ok(f"Temp dir       : {bridge.get_temp_dir()}")
    except Exception as exc:
        _fail(f"Bridge error: {exc}")
        return 2

    rootfs = os.path.join(_REPO_ROOT, "rootfs")
    if os.path.isdir(rootfs):
        _ok(f"Rootfs         : {rootfs}")
    else:
        _warn("Rootfs         : not built — run `aura build`")

    layout = os.path.join(rootfs, "layout.json")
    if os.path.isfile(layout):
        try:
            with open(layout) as fh:
                data = json.load(fh)
            _ok(f"Rootfs layout  : v{data.get('version','?')}  "
                f"({data.get('partition_count', len(data.get('partitions', {})))} partitions)")
        except Exception:
            _warn("Rootfs layout  : layout.json unreadable")

    boot_log = os.path.join(rootfs, "var", "boot.log")
    if os.path.isfile(boot_log):
        _ok(f"Boot log       : {boot_log}")
    else:
        _warn("Boot log       : no boot log found")

    services_dir = os.path.join(_REPO_ROOT, "services")
    service_files = [f for f in os.listdir(services_dir)
                     if f.endswith(".service")] if os.path.isdir(services_dir) else []
    _ok(f"Service units  : {len(service_files)} found")

    models_dir = os.path.join(_REPO_ROOT, "models")
    model_files = []
    if os.path.isdir(models_dir):
        model_files = [f for f in os.listdir(models_dir)
                       if f.endswith((".gguf", ".bin", ".pt", ".onnx"))]
    if model_files:
        _ok(f"AI models      : {len(model_files)} model(s)")
    else:
        _warn("AI models      : none — stub mode active")

    print()
    return 0


def cmd_doctor(args) -> int:
    """Deep system + environment validation."""
    _add_repo_to_path()
    _print_header("AURA-AIOSCPU  Doctor")
    try:
        from tools.portability import validate_and_print
        rc = validate_and_print(json_output=args.json)
        print()
        if rc == 0:
            _ok("System is healthy and ready.")
        elif rc == 3:
            _fail("Environment is fundamentally incompatible with AURA-AIOSCPU.")
        else:
            _fail("System has issues. Review the checks above.")
        return rc
    except Exception as exc:
        _fail(f"Doctor failed: {exc}")
        return 2


def cmd_build(args) -> int:
    """Build rootfs from source."""
    _add_repo_to_path()
    _print_header("AURA-AIOSCPU  Build")

    build_script = os.path.join(_REPO_ROOT, "build.py")
    if not os.path.isfile(build_script):
        _fail(f"build.py not found at {build_script}")
        return 2

    _info("Running build.py ...")
    t0 = time.monotonic()
    result = subprocess.run(
        [sys.executable, build_script],
        cwd=_REPO_ROOT,
    )
    elapsed = time.monotonic() - t0

    if result.returncode != 0:
        _fail(f"Build failed in {elapsed:.1f}s (exit {result.returncode})")
        return 1

    _ok(f"Build complete in {elapsed:.1f}s")

    # Generate manifest
    if not args.no_manifest:
        _info("Generating rootfs manifest ...")
        try:
            from tools.manifest import build_manifest, write_manifest
            manifest = build_manifest()
            path     = write_manifest(manifest)
            _ok(f"Manifest written: {path} ({manifest['file_count']} files)")
        except Exception as exc:
            _warn(f"Manifest generation failed: {exc}")

    # Verify if requested
    if args.verify:
        return cmd_verify(args)

    print()
    return 0


def cmd_verify(args) -> int:
    """Verify runtime rootfs matches built manifest."""
    _add_repo_to_path()
    _print_header("AURA-AIOSCPU  Verify")
    try:
        from tools.manifest import load_manifest, verify_manifest
        manifest_path = os.path.join(_REPO_ROOT, "rootfs", "system",
                                     "manifest.json")
        if not os.path.isfile(manifest_path):
            _fail(f"No manifest at {manifest_path}. Run `aura build` first.")
            return 1
        manifest       = load_manifest(manifest_path)
        ok, diffs      = verify_manifest(manifest)
        if ok:
            _ok(f"Rootfs integrity verified ({manifest.get('file_count',0)} files)")
            return 0
        _fail(f"{len(diffs)} discrepancies found:")
        for d in diffs[:20]:
            _info(d)
        if len(diffs) > 20:
            _info(f"... and {len(diffs) - 20} more")
        return 1
    except Exception as exc:
        _fail(f"Verify failed: {exc}")
        return 2


def cmd_repair(args) -> int:
    """Verify and rebuild if drift is detected."""
    _add_repo_to_path()
    _print_header("AURA-AIOSCPU  Repair")
    _info("Checking integrity ...")
    verify_rc = cmd_verify(args)
    if verify_rc == 0:
        _ok("No drift detected — nothing to repair.")
        return 0
    if verify_rc == 2:
        _fail("Cannot check integrity — aborting repair.")
        return 2
    _warn("Drift detected — rebuilding rootfs ...")
    return cmd_build(args)


def cmd_test(args) -> int:
    """Run test suite."""
    _add_repo_to_path()
    _print_header("AURA-AIOSCPU  Tests")

    cmd = [sys.executable, "-m", "pytest", "tests/", "-q"]

    if args.conformance:
        _info("Running conformance suite ...")
        cmd = [sys.executable, "-m", "pytest", "tests/conformance/",
               "-v", "--tb=short"]
    elif args.filter:
        cmd += ["-k", args.filter]

    result = subprocess.run(cmd, cwd=_REPO_ROOT)
    print()
    if result.returncode == 0:
        _ok("All tests passed.")
    else:
        _fail(f"Tests failed (exit {result.returncode})")
    return result.returncode


def cmd_logs(args) -> int:
    """Show system logs."""
    _add_repo_to_path()
    _print_header("AURA-AIOSCPU  Logs")

    log_path = os.path.join(_REPO_ROOT, "logs", "aura_events.log")
    if not os.path.isfile(log_path):
        _warn("No event log found. Boot the OS first.")
        return 0

    tail = args.tail
    try:
        with open(log_path) as fh:
            lines = fh.readlines()
        lines = lines[-tail:] if tail else lines
        for line in lines:
            try:
                entry = json.loads(line)
                ts    = time.strftime("%H:%M:%S",
                                      time.localtime(entry.get("ts", 0)))
                level  = entry.get("level", "INFO")[:4]
                source = entry.get("source", "")[:18]
                event  = entry.get("event", "")[:20]
                msg    = entry.get("msg", "")[:60]
                print(f"[{ts}] {level:<4} {source:<18} {event:<20} {msg}")
            except json.JSONDecodeError:
                print(line.rstrip())
        return 0
    except Exception as exc:
        _fail(f"Could not read logs: {exc}")
        return 2


def cmd_mirror(args) -> int:
    """Show mirror/projection status."""
    _add_repo_to_path()
    _print_header("AURA-AIOSCPU  Mirror Status")
    try:
        from bridge import get_bridge, detect_host_type
        bridge    = get_bridge()
        host_type = detect_host_type()
        info      = bridge.get_sys_info()
        caps      = bridge.available_capabilities()

        _ok(f"Host type      : {host_type}")
        _ok(f"Architecture   : {info.get('arch', '?')}")
        _ok(f"Bridge class   : {bridge.__class__.__name__}")
        _ok(f"Capabilities   : {len(caps)}")
        print()
        _info("Mode eligibility:")
        _ok("  Universal Mode    — always available (guest OS on top of host)")
        if "net_listen" in caps or "fs_chmod" in caps:
            _ok("  Internal Mode     — available (elevated bridge caps present)")
        else:
            _warn("  Internal Mode     — limited (elevated caps not available)")
        if "hal_project" in caps:
            _ok("  Hardware Mode     — available (hal.project supported)")
        else:
            _warn("  Hardware Mode     — unavailable (hal.project not supported)")
        print()
        _info("Bridge capabilities:")
        for cap in sorted(caps):
            _info(f"    {cap}")
        print()
        return 0
    except Exception as exc:
        _fail(f"Mirror status failed: {exc}")
        return 2


def cmd_host(args) -> int:
    """Show host-bridge status and capabilities."""
    _add_repo_to_path()
    _print_header("AURA-AIOSCPU  Host Bridge")
    try:
        from bridge import get_bridge, detect_host_type
        bridge    = get_bridge()
        host_type = detect_host_type()
        info      = bridge.get_sys_info()
        caps      = bridge.available_capabilities()

        data = {
            "host_type":      host_type,
            "bridge_class":   bridge.__class__.__name__,
            "sys_info":       info,
            "capabilities":   sorted(caps),
            "temp_dir":       bridge.get_temp_dir(),
            "home_dir":       bridge.get_home_dir(),
        }

        if args.json:
            print(json.dumps(data, indent=2))
        else:
            for k, v in data.items():
                if isinstance(v, list):
                    _ok(f"{k:<22}: [{', '.join(str(x) for x in v[:5])}...]")
                elif isinstance(v, dict):
                    _ok(f"{k:<22}:")
                    for dk, dv in v.items():
                        _info(f"    {dk:<16}: {dv}")
                else:
                    _ok(f"{k:<22}: {v}")
        print()
        return 0
    except Exception as exc:
        _fail(f"Host info failed: {exc}")
        return 2


def cmd_boot_log(args) -> int:
    """Show last boot lifecycle."""
    _add_repo_to_path()
    _print_header("AURA-AIOSCPU  Boot Log")
    log_path = os.path.join(_REPO_ROOT, "rootfs", "var", "boot.log")
    if not os.path.isfile(log_path):
        _warn("No boot log found. Boot the OS first.")
        return 0
    try:
        with open(log_path) as fh:
            data = json.load(fh)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            boot_ts = data.get("boot_ts", 0)
            _ok(f"Boot started : {time.ctime(boot_ts)}")
            print()
            for entry in data.get("entries", []):
                ts    = time.strftime("%H:%M:%S",
                                      time.localtime(entry.get("ts", 0)))
                stage = entry.get("stage", "?")
                event = entry.get("event", "")
                detail = entry.get("detail", "")
                ok_s   = "OK  " if entry.get("ok", True) else "FAIL"
                print(f"  [{ts}] Stage {stage}  {ok_s}  {event}")
                if detail:
                    print(f"              {detail}")
        return 0
    except Exception as exc:
        _fail(f"Could not read boot log: {exc}")
        return 2


def cmd_provenance(args) -> int:
    """Show build provenance."""
    _add_repo_to_path()
    _print_header("AURA-AIOSCPU  Provenance")
    try:
        from tools.manifest import get_provenance
        prov = get_provenance()
        if args.json:
            print(json.dumps(prov, indent=2))
        else:
            _ok(f"Build time    : {prov.get('build_time_human', 'unknown')}")
            _ok(f"Commit        : {prov.get('commit', 'unknown')}")
            _ok(f"Manifest      : {prov.get('manifest_path', 'unknown')}")
            _ok(f"File count    : {prov.get('file_count', 0)}")
            env = prov.get("environment", {})
            _ok(f"Python        : {env.get('python', '?')}")
            _ok(f"Platform      : {env.get('platform', '?')}")
            _ok(f"Arch          : {env.get('arch', '?')}")
        print()
        return 0
    except Exception as exc:
        _fail(f"Provenance failed: {exc}")
        return 2


def cmd_override(args) -> int:
    """Request a COL override [interactive]."""
    _add_repo_to_path()
    _print_header("AURA-AIOSCPU  Command Override")
    try:
        from kernel.override import CommandOverrideLayer
        from bridge import get_bridge
        bridge = get_bridge()
        col    = CommandOverrideLayer(bridge=bridge)
        result = col.request_override(
            action=args.action,
            reason=args.reason or "operator-requested via aura CLI",
            confirm=args.force,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        elif result.approved:
            _ok(f"Override approved: {args.action}  (id={result.request_id})")
        else:
            _fail(f"Override denied: {result.denial_reason}")
        return 0 if result.approved else 1
    except Exception as exc:
        _fail(f"Override error: {exc}")
        return 2


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aura",
        description="AURA-AIOSCPU Operator CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--json", action="store_true",
                   help="Machine-readable JSON output")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("status",     help="Kernel + services state")

    doc = sub.add_parser("doctor",  help="Deep system + environment validation")
    doc.add_argument("--json", action="store_true")

    bld = sub.add_parser("build",   help="Build rootfs from source")
    bld.add_argument("--verify",       action="store_true",
                     help="Verify after build")
    bld.add_argument("--no-manifest",  action="store_true",
                     help="Skip manifest generation")

    sub.add_parser("repair",  help="Verify and rebuild if drift detected")
    sub.add_parser("verify",  help="Check rootfs against manifest")

    tst = sub.add_parser("test",    help="Run test suite")
    tst.add_argument("--conformance", action="store_true",
                     help="Run conformance suite only")
    tst.add_argument("--filter", "-k", default="",
                     help="pytest -k filter expression")

    lg = sub.add_parser("logs",     help="Show system logs")
    lg.add_argument("--tail", "-n", type=int, default=50,
                    help="Number of log lines to show (default: 50)")

    sub.add_parser("mirror",     help="Mirror/projection status")

    host_p = sub.add_parser("host",   help="Host-bridge capabilities")
    host_p.add_argument("--json", action="store_true")

    bl = sub.add_parser("boot-log",  help="Last boot lifecycle")
    bl.add_argument("--json", action="store_true")

    pr = sub.add_parser("provenance", help="Build provenance")
    pr.add_argument("--json", action="store_true")

    ov = sub.add_parser("override",  help="Request a COL override [interactive]")
    ov.add_argument("action",  help="Action to override (e.g. net.listen)")
    ov.add_argument("--reason", "-r", default="",
                    help="Justification for the override")
    ov.add_argument("--force",  action="store_true",
                    help="Skip interactive confirmation (--force)")
    ov.add_argument("--json",   action="store_true")

    return p


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    _require_python()
    parser  = build_parser()
    args    = parser.parse_args(argv)

    # Propagate top-level --json to sub-commands that support it
    if args.json and not hasattr(args, "json"):
        setattr(args, "json", True)

    dispatch = {
        "status":     cmd_status,
        "doctor":     cmd_doctor,
        "build":      cmd_build,
        "repair":     cmd_repair,
        "verify":     cmd_verify,
        "test":       cmd_test,
        "logs":       cmd_logs,
        "mirror":     cmd_mirror,
        "host":       cmd_host,
        "boot-log":   cmd_boot_log,
        "provenance": cmd_provenance,
        "override":   cmd_override,
        None:         cmd_status,   # bare `aura` → status
    }

    fn = dispatch.get(args.command, cmd_status)
    try:
        return fn(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
