"""
AURA-AIOSCPU  ·  Copilot Bridge
================================
What is this?
-------------
This script acts as a *bridge* between the AURA-AIOSCPU codebase and GitHub
Copilot (or any AI assistant).  It does five things automatically:

  1. Runs the built-in system validation suite  (tools/validate_system.py)
  2. Runs the full pytest test suite             (tests/)
  3. Inspects the Python environment for missing / outdated dependencies
  4. Checks AURA configuration for tuning opportunities
  5. Writes a self-contained Markdown report to ``copilot_report.md``

You (or Copilot) then open ``copilot_report.md`` and read the "Upgrade
Recommendations" section.  Every recommendation includes a short description
of *why* the change is beneficial, so Copilot can explain it to you in plain
language before you decide to apply it.

How does the bridge work?
-------------------------
The script imports and calls AURA's existing validation helpers directly (no
subprocess for the validation step), then shells out to pytest with
``--tb=short -q`` and captures the output.  All results are normalised into
a list of structured ``Finding`` objects that are rendered into Markdown.

The rendered report is also printed to stdout so that Copilot's inline chat
can read it without opening a file.

Usage
-----
  # Run from the repo root:
  python tools/copilot_bridge.py

  # Save to a custom location:
  python tools/copilot_bridge.py --output my_report.md

  # JSON output (machine-readable, useful for CI):
  python tools/copilot_bridge.py --json

  # Skip the (slow) pytest run:
  python tools/copilot_bridge.py --no-tests

Exit codes
----------
  0  all checks pass / no upgrades required
  1  one or more checks failed
  2  upgrade recommendations exist (not failures — just suggestions)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------------
# Ensure repo root is importable regardless of invocation directory
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

LEVEL_PASS   = "PASS"
LEVEL_WARN   = "WARN"
LEVEL_FAIL   = "FAIL"
LEVEL_INFO   = "INFO"
LEVEL_UPGRADE = "UPGRADE"


@dataclass
class Finding:
    """A single diagnostic result."""
    category:    str
    name:        str
    level:       str                   # PASS / WARN / FAIL / INFO / UPGRADE
    detail:      str  = ""
    suggestion:  str  = ""             # Only set for UPGRADE findings

    def to_dict(self) -> dict:
        return {
            "category":   self.category,
            "name":       self.name,
            "level":      self.level,
            "detail":     self.detail,
            "suggestion": self.suggestion,
        }


# ---------------------------------------------------------------------------
# Category 1 — System validation (delegates to validate_system.py)
# ---------------------------------------------------------------------------

def _run_system_validation() -> List[Finding]:
    """Import and run the existing validate_system checks directly."""
    findings: List[Finding] = []
    try:
        from tools.validate_system import CHECKS, _check, _check_warn
    except ImportError:
        # Fallback: load as file
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            "validate_system",
            os.path.join(_REPO_ROOT, "tools", "validate_system.py"),
        )
        vs = _ilu.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(vs)       # type: ignore[union-attr]
        CHECKS = vs.CHECKS

    for check_fn, name, fn in CHECKS:
        result = check_fn(name, fn)
        level = (
            LEVEL_PASS if result.status == "PASS"
            else LEVEL_WARN if result.status == "WARN"
            else LEVEL_FAIL
        )
        findings.append(Finding(
            category = "System Validation",
            name     = name,
            level    = level,
            detail   = result.detail,
        ))
    return findings


# ---------------------------------------------------------------------------
# Category 2 — pytest
# ---------------------------------------------------------------------------

def _run_tests() -> List[Finding]:
    findings: List[Finding] = []
    test_dir = os.path.join(_REPO_ROOT, "tests")
    if not os.path.isdir(test_dir):
        findings.append(Finding(
            "Tests", "pytest", LEVEL_WARN,
            "No tests/ directory found — cannot run suite.",
        ))
        return findings

    cmd = [sys.executable, "-m", "pytest", test_dir, "-q", "--tb=short",
           "--no-header", "--color=no"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=_REPO_ROOT,
        )
        output = (proc.stdout + proc.stderr).strip()
        # Extract summary line (last non-blank line)
        lines        = [l for l in output.splitlines() if l.strip()]
        summary_line = lines[-1] if lines else "(no output)"

        if proc.returncode == 0:
            findings.append(Finding(
                "Tests", "pytest suite", LEVEL_PASS,
                summary_line,
            ))
        else:
            # Pull out just the failure lines to keep the report readable
            fail_lines = [l for l in output.splitlines()
                          if "FAILED" in l or "ERROR" in l or "error" in l.lower()]
            fail_detail = "\n".join(fail_lines[:20]) if fail_lines else output[-800:]
            findings.append(Finding(
                "Tests", "pytest suite", LEVEL_FAIL,
                f"Return code {proc.returncode}. {summary_line}\n\n{fail_detail}",
            ))
    except subprocess.TimeoutExpired:
        findings.append(Finding(
            "Tests", "pytest suite", LEVEL_WARN,
            "Test run timed out after 5 minutes.",
        ))
    except FileNotFoundError:
        findings.append(Finding(
            "Tests", "pytest suite", LEVEL_WARN,
            "pytest not found — install with: pip install pytest",
        ))
    return findings


# ---------------------------------------------------------------------------
# Category 3 — Dependency audit
# ---------------------------------------------------------------------------

_OPTIONAL_PACKAGES = [
    (
        "psutil", ">=5.9",
        "Enhanced CPU / memory / disk metrics. Strongly recommended on all "
        "platforms.  Install: pip install psutil",
    ),
    (
        "llama_cpp", ">=0.2",
        "On-device GGUF model inference (ARM64 optimised, works on Android). "
        "Install: pip install llama-cpp-python",
    ),
    (
        "onnxruntime", ">=1.16",
        "ONNX model inference backend.  "
        "Install: pip install onnxruntime",
    ),
    (
        "uvicorn", ">=0.29",
        "High-performance ASGI server for the web terminal.  Replaces the "
        "built-in HTTPServer for production use.  "
        "Install: pip install uvicorn fastapi",
    ),
    (
        "cryptography", ">=42",
        "Enables encrypted SQLite storage and signed build manifests.  "
        "Install: pip install cryptography",
    ),
]

_REQUIRED_PACKAGES = [
    ("pytest", ">=7.0", "Required for the test suite.  Install: pip install pytest"),
]


def _pkg_installed(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _run_dependency_audit() -> List[Finding]:
    findings: List[Finding] = []

    for pkg, version_req, desc in _REQUIRED_PACKAGES:
        if _pkg_installed(pkg):
            findings.append(Finding(
                "Dependencies", f"{pkg} (required)", LEVEL_PASS,
                f"Installed.  Requirement: {version_req}",
            ))
        else:
            findings.append(Finding(
                "Dependencies", f"{pkg} (required)", LEVEL_FAIL,
                f"NOT installed.  Requirement: {version_req}",
                suggestion=desc,
            ))

    for pkg, version_req, desc in _OPTIONAL_PACKAGES:
        if _pkg_installed(pkg):
            findings.append(Finding(
                "Dependencies", f"{pkg} (optional)", LEVEL_PASS,
                f"Installed.  Requirement: {version_req}",
            ))
        else:
            findings.append(Finding(
                "Dependencies", f"{pkg} (optional)", LEVEL_UPGRADE,
                f"Not installed.  Requirement: {version_req}",
                suggestion=desc,
            ))

    return findings


# ---------------------------------------------------------------------------
# Category 4 — Python version
# ---------------------------------------------------------------------------

def _run_python_check() -> List[Finding]:
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"

    if v < (3, 10):
        return [Finding(
            "Environment", "Python version", LEVEL_FAIL,
            f"Python {ver_str} — AURA requires ≥ 3.10",
            suggestion="Upgrade Python to 3.12 LTS for best performance and "
                       "latest stdlib features.",
        )]

    level = LEVEL_PASS
    suggestion = ""
    if v < (3, 12):
        level = LEVEL_UPGRADE
        suggestion = (
            f"Python {ver_str} works but Python 3.12 is the current LTS release.  "
            "Upgrading brings faster startup, better error messages, and "
            "improved match/case performance used in the AURA shell."
        )

    return [Finding(
        "Environment", "Python version", level,
        f"Python {ver_str}  |  platform: {platform.platform()}",
        suggestion=suggestion,
    )]


# ---------------------------------------------------------------------------
# Category 5 — AURA config review
# ---------------------------------------------------------------------------

def _run_config_review() -> List[Finding]:
    findings: List[Finding] = []
    try:
        from kernel.config import Config
        cfg = Config()

        tick = cfg.get("kernel", "tick_interval_ms", 16)
        adaptive = cfg.get("kernel", "adaptive_tick", True)
        max_q    = cfg.get("kernel", "max_task_queue", 1000)
        max_svc  = cfg.get("services", "max_services", 32)
        ctx_win  = cfg.get("aura", "context_window", 4096)
        backend  = cfg.get("aura", "backend", None)
        log_lvl  = cfg.get("logging", "level", "INFO")
        wd_en    = cfg.get("watchdog", "enabled", True)

        # Adaptive tick
        if adaptive:
            findings.append(Finding(
                "Config", "adaptive_tick", LEVEL_PASS,
                "Enabled — kernel slows to 1 s when idle (battery saving).",
            ))
        else:
            findings.append(Finding(
                "Config", "adaptive_tick", LEVEL_UPGRADE,
                "Disabled.",
                suggestion="Enable adaptive_tick in config/user.json to save "
                           "battery on mobile and reduce CPU use when idle.",
            ))

        # Watchdog
        if wd_en:
            findings.append(Finding(
                "Config", "watchdog.enabled", LEVEL_PASS,
                "Watchdog is active — crashed services are auto-restarted.",
            ))
        else:
            findings.append(Finding(
                "Config", "watchdog.enabled", LEVEL_UPGRADE,
                "Watchdog is disabled.",
                suggestion='Set "enabled": true under "watchdog" in '
                           "config/user.json for automatic crash recovery.",
            ))

        # AI backend
        if backend:
            findings.append(Finding(
                "Config", "aura.backend", LEVEL_PASS,
                f"AI backend configured: {backend!r}",
            ))
        else:
            findings.append(Finding(
                "Config", "aura.backend", LEVEL_UPGRADE,
                "No AI backend configured — AURA runs in stub mode.",
                suggestion=(
                    "Connect a real AI model for richer responses.\n"
                    "  • Ollama (recommended): install ollama, run "
                    "`ollama pull phi3`, then set backend=ollama in config/user.json\n"
                    "  • OpenAI: set backend=openai and api_key in config/user.json\n"
                    "  • Local GGUF: copy a .gguf file to models/ and run "
                    "`aura> model scan`"
                ),
            ))

        # Context window
        if ctx_win < 2048:
            findings.append(Finding(
                "Config", "aura.context_window", LEVEL_UPGRADE,
                f"context_window={ctx_win} is very small.",
                suggestion="Increase context_window to at least 4096 for "
                           "meaningful multi-turn conversations.",
            ))
        else:
            findings.append(Finding(
                "Config", "aura.context_window", LEVEL_PASS,
                f"context_window={ctx_win}",
            ))

        # Logging level
        if log_lvl == "DEBUG":
            findings.append(Finding(
                "Config", "logging.level", LEVEL_WARN,
                "Logging level is DEBUG — verbose, may slow the system.",
                suggestion='Set logging.level to "INFO" for production use.',
            ))
        else:
            findings.append(Finding(
                "Config", "logging.level", LEVEL_PASS,
                f"logging.level={log_lvl!r}",
            ))

    except Exception as exc:
        findings.append(Finding(
            "Config", "config load", LEVEL_FAIL,
            str(exc),
        ))
    return findings


# ---------------------------------------------------------------------------
# Category 6 — Structural / code-level upgrade hints
# ---------------------------------------------------------------------------

def _run_upgrade_hints() -> List[Finding]:
    """
    Static checks that identify well-known upgrade opportunities based on
    what is (or is not) present in the repo.
    """
    findings: List[Finding] = []

    # GitHub Actions CI
    ci_path = os.path.join(_REPO_ROOT, ".github", "workflows")
    if os.path.isdir(ci_path) and any(
        f.endswith((".yml", ".yaml")) for f in os.listdir(ci_path)
    ):
        findings.append(Finding(
            "Upgrades", "CI / GitHub Actions", LEVEL_PASS,
            "Workflow files found.",
        ))
    else:
        findings.append(Finding(
            "Upgrades", "CI / GitHub Actions", LEVEL_UPGRADE,
            "No GitHub Actions workflow files found.",
            suggestion=(
                "Add a .github/workflows/ci.yml that runs "
                "`python tools/copilot_bridge.py --no-tests --json` on every "
                "push.  This lets Copilot see the latest system health in the "
                "PR diff and suggest targeted upgrades automatically."
            ),
        ))

    # Dockerfile
    if os.path.isfile(os.path.join(_REPO_ROOT, "Dockerfile")):
        findings.append(Finding(
            "Upgrades", "Docker / containerisation", LEVEL_PASS,
            "Dockerfile present.",
        ))
    else:
        findings.append(Finding(
            "Upgrades", "Docker / containerisation", LEVEL_UPGRADE,
            "No Dockerfile found.",
            suggestion=(
                "Add a Dockerfile so AURA can be run as a container — "
                "great for cloud deployment and reproducible demos."
            ),
        ))

    # Copilot instructions file
    copilot_dir = os.path.join(_REPO_ROOT, ".github", "copilot-instructions.md")
    if os.path.isfile(copilot_dir):
        findings.append(Finding(
            "Upgrades", "Copilot instructions", LEVEL_PASS,
            ".github/copilot-instructions.md found.",
        ))
    else:
        findings.append(Finding(
            "Upgrades", "Copilot instructions", LEVEL_UPGRADE,
            "No .github/copilot-instructions.md found.",
            suggestion=(
                "Create .github/copilot-instructions.md to teach Copilot "
                "about AURA's architecture, naming conventions, and preferred "
                "patterns.  This dramatically improves Copilot's inline "
                "suggestions throughout the codebase."
            ),
        ))

    # Type annotations in core kernel files
    kernel_api = os.path.join(_REPO_ROOT, "kernel", "api.py")
    if os.path.isfile(kernel_api):
        with open(kernel_api) as f:
            src = f.read()
        if "-> " in src or ": " in src:
            findings.append(Finding(
                "Upgrades", "Type annotations (kernel/api.py)", LEVEL_PASS,
                "Type hints detected.",
            ))
        else:
            findings.append(Finding(
                "Upgrades", "Type annotations (kernel/api.py)", LEVEL_UPGRADE,
                "No type annotations detected in kernel/api.py.",
                suggestion=(
                    "Add PEP 484 type annotations to public APIs.  "
                    "This allows Copilot (and mypy) to catch type errors "
                    "before runtime and provide smarter completions."
                ),
            ))

    # MANUAL.md
    if os.path.isfile(os.path.join(_REPO_ROOT, "MANUAL.md")):
        findings.append(Finding(
            "Upgrades", "User manual (MANUAL.md)", LEVEL_PASS,
            "MANUAL.md exists.",
        ))
    else:
        findings.append(Finding(
            "Upgrades", "User manual (MANUAL.md)", LEVEL_UPGRADE,
            "MANUAL.md not found.",
            suggestion=(
                "Create MANUAL.md with full installation, configuration, "
                "shell command reference, AI model setup, and troubleshooting "
                "sections.  This is the primary reference for new users."
            ),
        ))

    return findings


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

_EMOJI = {
    LEVEL_PASS:    "✅",
    LEVEL_WARN:    "⚠️",
    LEVEL_FAIL:    "❌",
    LEVEL_INFO:    "ℹ️",
    LEVEL_UPGRADE: "🔧",
}


def _render_markdown(
    findings: List[Finding],
    duration: float,
    *,
    run_date: str,
) -> str:
    lines: List[str] = []

    lines += [
        "# AURA-AIOSCPU · Copilot Bridge Report",
        "",
        "> **How to use this report:**  Share this file with GitHub Copilot "
        "(paste it into Copilot Chat, or open it in VS Code with Copilot "
        "enabled and ask _\"What upgrades does the AURA system need?\"_).  "
        "Copilot will read each 🔧 Upgrade Recommendation and explain what to "
        "do in plain language before any code is changed.",
        "",
        f"**Generated:** {run_date}  |  **Duration:** {duration:.1f}s  "
        f"|  **Python:** {sys.version.split()[0]}  "
        f"|  **Platform:** {platform.platform()}",
        "",
        "---",
        "",
    ]

    # Summary table
    passes   = sum(1 for f in findings if f.level == LEVEL_PASS)
    warns    = sum(1 for f in findings if f.level == LEVEL_WARN)
    fails    = sum(1 for f in findings if f.level == LEVEL_FAIL)
    upgrades = sum(1 for f in findings if f.level == LEVEL_UPGRADE)

    lines += [
        "## Summary",
        "",
        f"| ✅ Pass | ⚠️ Warn | ❌ Fail | 🔧 Upgrades |",
        f"|--------|--------|--------|------------|",
        f"| {passes} | {warns} | {fails} | {upgrades} |",
        "",
        "---",
        "",
    ]

    # Group by category
    categories: dict[str, List[Finding]] = {}
    for f in findings:
        categories.setdefault(f.category, []).append(f)

    for cat, cat_findings in categories.items():
        lines.append(f"## {cat}")
        lines.append("")
        lines.append("| Status | Check | Detail |")
        lines.append("|--------|-------|--------|")
        for f in cat_findings:
            emoji  = _EMOJI.get(f.level, f.level)
            detail = f.detail.replace("\n", "<br>") if f.detail else "—"
            lines.append(f"| {emoji} `{f.level}` | {f.name} | {detail} |")
        lines.append("")

    # Upgrade recommendations section
    upgrade_findings = [f for f in findings if f.level == LEVEL_UPGRADE]
    fail_findings    = [f for f in findings if f.level == LEVEL_FAIL]

    lines += [
        "---",
        "",
        "## 🔧 Upgrade Recommendations",
        "",
        "> The items below are *not* failures — the system works without "
        "them.  They are improvements that will make AURA more capable, "
        "faster, or easier to use.  Ask Copilot to explain any item before "
        "applying it.",
        "",
    ]

    if upgrade_findings:
        for i, f in enumerate(upgrade_findings, 1):
            lines += [
                f"### {i}. {f.name}",
                "",
                f"**Category:** {f.category}",
                "",
                f.suggestion or f.detail,
                "",
            ]
    else:
        lines.append("_No upgrade recommendations — system is fully optimised!_")
        lines.append("")

    if fail_findings:
        lines += [
            "---",
            "",
            "## ❌ Failures (action required)",
            "",
        ]
        for f in fail_findings:
            lines += [
                f"### {f.name}",
                "",
                f"**Category:** {f.category}",
                "",
                f"```\n{f.detail}\n```",
                "",
                f.suggestion or "",
                "",
            ]

    lines += [
        "---",
        "",
        "## How the Bridge Works",
        "",
        "```",
        "tools/copilot_bridge.py",
        "        │",
        "        ├── tools/validate_system.py   (imports directly)",
        "        │       └── checks Python, imports, kernel, HAL,",
        "        │           storage, shell, services, rootfs …",
        "        │",
        "        ├── pytest tests/              (subprocess, --tb=short)",
        "        │",
        "        ├── dependency audit           (importlib.util.find_spec)",
        "        │",
        "        ├── config review              (kernel.config.Config)",
        "        │",
        "        └── upgrade hints              (static file-system checks)",
        "                │",
        "                └──► copilot_report.md  (this file)",
        "```",
        "",
        "Run at any time with:  `python tools/copilot_bridge.py`",
        "Then open `copilot_report.md` in VS Code and ask Copilot Chat:",
        "_\"What does this report say and what should I do next?\"_",
        "",
    ]

    return "\n".join(lines)


def _render_json(findings: List[Finding], duration: float) -> str:
    passes   = sum(1 for f in findings if f.level == LEVEL_PASS)
    warns    = sum(1 for f in findings if f.level == LEVEL_WARN)
    fails    = sum(1 for f in findings if f.level == LEVEL_FAIL)
    upgrades = sum(1 for f in findings if f.level == LEVEL_UPGRADE)
    return json.dumps(
        {
            "summary": {
                "pass":    passes,
                "warn":    warns,
                "fail":    fails,
                "upgrade": upgrades,
                "duration_s": round(duration, 2),
            },
            "findings": [f.to_dict() for f in findings],
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_bridge(
    *,
    run_tests: bool = True,
    output_path: Optional[str] = None,
    as_json: bool = False,
) -> int:
    """
    Execute all bridge checks and write the report.

    Returns
    -------
    0  everything passed, no upgrades
    1  one or more hard failures
    2  no failures but upgrade recommendations exist
    """
    import datetime
    t_start  = time.monotonic()
    run_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    findings: List[Finding] = []

    print("  [1/5] Running system validation …", flush=True)
    findings += _run_python_check()
    findings += _run_system_validation()

    print("  [2/5] Auditing dependencies …", flush=True)
    findings += _run_dependency_audit()

    print("  [3/5] Reviewing configuration …", flush=True)
    findings += _run_config_review()

    print("  [4/5] Checking upgrade opportunities …", flush=True)
    findings += _run_upgrade_hints()

    if run_tests:
        print("  [5/5] Running test suite …", flush=True)
        findings += _run_tests()
    else:
        print("  [5/5] Test suite skipped (--no-tests).", flush=True)

    duration = time.monotonic() - t_start

    if as_json:
        report = _render_json(findings, duration)
    else:
        report = _render_markdown(findings, duration, run_date=run_date)

    # Write file
    if output_path is None:
        output_path = os.path.join(_REPO_ROOT, "copilot_report.md")
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(report)

    # Also print to stdout
    print()
    print(report)
    print()
    print(f"Report saved to: {output_path}")

    fails    = sum(1 for f in findings if f.level == LEVEL_FAIL)
    upgrades = sum(1 for f in findings if f.level == LEVEL_UPGRADE)

    if fails:
        return 1
    if upgrades:
        return 2
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AURA-AIOSCPU Copilot Bridge — test, audit, and report.",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="FILE",
        default=None,
        help="Path to write the Markdown report (default: copilot_report.md)",
    )
    parser.add_argument(
        "--no-tests",
        dest="run_tests",
        action="store_false",
        default=True,
        help="Skip the pytest suite (faster, useful for quick config checks)",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        default=False,
        help="Output machine-readable JSON instead of Markdown",
    )
    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║       AURA-AIOSCPU  ·  Copilot Bridge               ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    rc = run_bridge(
        run_tests   = args.run_tests,
        output_path = args.output,
        as_json     = args.as_json,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
