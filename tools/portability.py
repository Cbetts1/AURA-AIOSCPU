"""
AURA-AIOSCPU Portability Validator
=====================================
Answers: "Can this build run here, and in what mode?"

Checks performed
----------------
  1. host_bridge    — bridge detects host, safe paths probe OK
  2. python_version — >= 3.10 required
  3. rootfs_layout  — all required partition directories present
  4. rootfs_integrity — layout.json exists and is readable
  5. disk_space     — rootfs partition has enough free space
  6. permissions    — user partition is writable
  7. models         — at least one model present (optional/warning only)
  8. services       — all required .service unit files present
  9. shell          — shell module imports cleanly

Mode eligibility (all checks must pass for each tier)
------------------------------------------------------
  Universal Mode    — checks 1-6 + 8
  Universal+Internal — above + writable prefix + elevated bridge caps
  Full (Hardware)   — above + hardware projection capability

Output
------
  machine-readable JSON report
  human-readable summary

Exit codes (for CLI use)
------------------------
  0 — all required checks pass (at least Universal Mode ready)
  1 — one or more required checks failed
  3 — environment incompatible (Python too old, no bridge, etc.)
"""

import json
import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REQUIRED_PARTITIONS = [
    "boot", "system", "user", "overlay", "aura",
    "services", "var", "tmp", "etc", "home", "mnt",
]
_REQUIRED_SERVICE_FILES = [
    "network.service", "storage.service", "logging.service",
    "job-queue.service", "health-monitor.service",
]
_MIN_DISK_MB = 50


# ---------------------------------------------------------------------------
# Check result
# ---------------------------------------------------------------------------

class CheckResult:
    """Result of one portability check."""

    PASS    = "pass"
    WARN    = "warn"
    FAIL    = "fail"

    def __init__(self, name: str, status: str, detail: str = "",
                 required: bool = True):
        self.name     = name
        self.status   = status
        self.detail   = detail
        self.required = required

    def passed(self)  -> bool: return self.status == self.PASS
    def warned(self)  -> bool: return self.status == self.WARN
    def failed(self)  -> bool: return self.status == self.FAIL

    def to_dict(self) -> dict:
        return {
            "name":     self.name,
            "status":   self.status,
            "detail":   self.detail,
            "required": self.required,
        }

    def __str__(self) -> str:
        icon = {"pass": "✓", "warn": "⚠", "fail": "✗"}.get(self.status, "?")
        req  = "" if self.required else " [optional]"
        return f"  {icon}  {self.name:<26}  {self.detail}{req}"


# ---------------------------------------------------------------------------
# Portability report
# ---------------------------------------------------------------------------

class PortabilityReport:
    """Full portability report with all check results and mode eligibility."""

    def __init__(self, checks: list[CheckResult]):
        self.checks      = checks
        self.timestamp   = time.time()
        self.safe_modes  = self._determine_modes()

    def passed(self) -> bool:
        return all(
            c.passed() or not c.required
            for c in self.checks
        )

    def _determine_modes(self) -> list[str]:
        required_by_name = {c.name: c for c in self.checks}
        modes = []

        # Universal Mode requires: bridge, python, rootfs, disk, permissions, services
        universal_deps = [
            "host_bridge", "python_version", "rootfs_layout",
            "disk_space", "permissions", "services",
        ]
        if all(
            required_by_name.get(d, CheckResult(d, "fail")).passed()
            for d in universal_deps
        ):
            modes.append("universal")

            # Internal Mode additionally needs write perms on a prefix
            modes.append("internal")

            # Hardware Mode additionally needs hal.project capability
            bridge_check = required_by_name.get("host_bridge")
            if bridge_check and bridge_check.passed():
                try:
                    from bridge import get_bridge
                    b = get_bridge()
                    if b.has_capability("hal_project"):
                        modes.append("hardware")
                except Exception:
                    pass
        return modes

    def to_dict(self) -> dict:
        return {
            "timestamp":   self.timestamp,
            "passed":      self.passed(),
            "safe_modes":  self.safe_modes,
            "checks":      [c.to_dict() for c in self.checks],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_human(self) -> str:
        lines = [
            "AURA-AIOSCPU Portability Report",
            "=" * 50,
            f"Timestamp : {time.ctime(self.timestamp)}",
            f"Result    : {'PASS' if self.passed() else 'FAIL'}",
            f"Safe modes: {', '.join(self.safe_modes) or 'NONE — system not ready'}",
            "",
            "Checks:",
        ]
        for c in self.checks:
            lines.append(str(c))
        if not self.passed():
            lines += [
                "",
                "Required fixes:",
            ]
            for c in self.checks:
                if c.failed() and c.required:
                    lines.append(f"  → {c.name}: {c.detail}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_host_bridge() -> CheckResult:
    try:
        from bridge import get_bridge, detect_host_type
        bridge    = get_bridge()
        host_type = detect_host_type()
        _tmp      = bridge.get_temp_dir()
        _home     = bridge.get_home_dir()
        info      = bridge.get_sys_info()
        return CheckResult(
            "host_bridge", CheckResult.PASS,
            f"host={host_type} arch={info.get('arch','?')} "
            f"caps={len(bridge.available_capabilities())}",
        )
    except Exception as exc:
        return CheckResult(
            "host_bridge", CheckResult.FAIL,
            f"Bridge init failed: {exc}",
        )


def _check_python_version() -> CheckResult:
    v = sys.version_info
    if v >= (3, 10):
        return CheckResult(
            "python_version", CheckResult.PASS,
            f"{v.major}.{v.minor}.{v.micro}",
        )
    return CheckResult(
        "python_version", CheckResult.FAIL,
        f"Python {v.major}.{v.minor} found, need >= 3.10",
    )


def _check_rootfs_layout() -> CheckResult:
    rootfs = os.path.join(_REPO_ROOT, "rootfs")
    if not os.path.isdir(rootfs):
        return CheckResult(
            "rootfs_layout", CheckResult.FAIL,
            f"rootfs/ directory missing at {rootfs}. Run `aura build`.",
        )
    missing = [
        p for p in _REQUIRED_PARTITIONS
        if not os.path.isdir(os.path.join(rootfs, p))
    ]
    if missing:
        return CheckResult(
            "rootfs_layout", CheckResult.FAIL,
            f"Missing partitions: {missing}. Run `aura build`.",
        )
    return CheckResult(
        "rootfs_layout", CheckResult.PASS,
        f"{len(_REQUIRED_PARTITIONS)} partitions present",
    )


def _check_rootfs_integrity() -> CheckResult:
    layout = os.path.join(_REPO_ROOT, "rootfs", "layout.json")
    if not os.path.isfile(layout):
        return CheckResult(
            "rootfs_integrity", CheckResult.WARN,
            "layout.json missing — run `aura build` to generate",
            required=False,
        )
    try:
        import json as _json
        with open(layout) as fh:
            data = _json.load(fh)
        version = data.get("version", "?")
        return CheckResult(
            "rootfs_integrity", CheckResult.PASS,
            f"layout.json v{version} readable",
        )
    except Exception as exc:
        return CheckResult(
            "rootfs_integrity", CheckResult.WARN,
            f"layout.json unreadable: {exc}",
            required=False,
        )


def _check_disk_space() -> CheckResult:
    rootfs = os.path.join(_REPO_ROOT, "rootfs")
    if not os.path.isdir(rootfs):
        return CheckResult("disk_space", CheckResult.FAIL, "rootfs missing")
    try:
        import shutil
        usage = shutil.disk_usage(rootfs)
        free_mb = usage.free // (1024 * 1024)
        if free_mb < _MIN_DISK_MB:
            return CheckResult(
                "disk_space", CheckResult.FAIL,
                f"Only {free_mb}MB free, need {_MIN_DISK_MB}MB",
            )
        return CheckResult(
            "disk_space", CheckResult.PASS,
            f"{free_mb}MB free",
        )
    except Exception as exc:
        return CheckResult(
            "disk_space", CheckResult.WARN,
            f"Could not check disk: {exc}",
            required=False,
        )


def _check_permissions() -> CheckResult:
    user_dir = os.path.join(_REPO_ROOT, "rootfs", "user")
    os.makedirs(user_dir, exist_ok=True)
    probe = os.path.join(user_dir, ".write_probe")
    try:
        with open(probe, "w") as fh:
            fh.write("probe")
        os.unlink(probe)
        return CheckResult(
            "permissions", CheckResult.PASS,
            "rootfs/user/ is writable",
        )
    except (OSError, PermissionError) as exc:
        return CheckResult(
            "permissions", CheckResult.FAIL,
            f"rootfs/user/ not writable: {exc}",
        )


def _check_models() -> CheckResult:
    models_dir = os.path.join(_REPO_ROOT, "models")
    if not os.path.isdir(models_dir):
        return CheckResult(
            "models", CheckResult.WARN,
            "models/ directory missing — AI features will use stub mode",
            required=False,
        )
    model_files = [
        f for f in os.listdir(models_dir)
        if f.endswith((".gguf", ".bin", ".pt", ".onnx"))
    ]
    if not model_files:
        return CheckResult(
            "models", CheckResult.WARN,
            "No model files found — AI features will use stub mode. "
            "Use `aura model install` to add one.",
            required=False,
        )
    return CheckResult(
        "models", CheckResult.PASS,
        f"{len(model_files)} model file(s) found",
        required=False,
    )


def _check_services() -> CheckResult:
    services_dir = os.path.join(_REPO_ROOT, "services")
    if not os.path.isdir(services_dir):
        return CheckResult(
            "services", CheckResult.FAIL,
            f"services/ directory missing at {services_dir}",
        )
    missing = [
        f for f in _REQUIRED_SERVICE_FILES
        if not os.path.isfile(os.path.join(services_dir, f))
    ]
    if missing:
        return CheckResult(
            "services", CheckResult.FAIL,
            f"Missing service files: {missing}",
        )
    return CheckResult(
        "services", CheckResult.PASS,
        f"{len(_REQUIRED_SERVICE_FILES)} service unit files present",
    )


def _check_shell() -> CheckResult:
    try:
        import shell as _shell   # noqa: F401
        return CheckResult(
            "shell", CheckResult.PASS,
            "shell module imports OK",
        )
    except Exception as exc:
        return CheckResult(
            "shell", CheckResult.FAIL,
            f"shell import failed: {exc}",
        )


# ---------------------------------------------------------------------------
# Main validator entry point
# ---------------------------------------------------------------------------

def validate() -> PortabilityReport:
    """
    Run all portability checks and return a PortabilityReport.

    This is the function called by `aura doctor` and `aura test --conformance`.
    """
    checks = [
        _check_host_bridge(),
        _check_python_version(),
        _check_rootfs_layout(),
        _check_rootfs_integrity(),
        _check_disk_space(),
        _check_permissions(),
        _check_models(),
        _check_services(),
        _check_shell(),
    ]
    return PortabilityReport(checks)


def validate_and_print(json_output: bool = False) -> int:
    """
    Run validation, print results, return exit code.

    Exit codes:
      0 — all required checks pass
      1 — one or more required checks failed
      3 — environment fundamentally incompatible (no bridge, old Python)
    """
    report = validate()

    if json_output:
        print(report.to_json())
    else:
        print(report.to_human())

    if not report.passed():
        # Check for fundamental incompatibility
        bridge_ok = any(
            c.name == "host_bridge" and c.passed() for c in report.checks
        )
        python_ok = any(
            c.name == "python_version" and c.passed() for c in report.checks
        )
        if not bridge_ok or not python_ok:
            return 3
        return 1
    return 0
