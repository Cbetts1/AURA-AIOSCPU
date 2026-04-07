"""
check_requirements.py — Pre-flight compatibility checker for AURA-AIOSCPU.

Run this on any device *before* installing AURA to verify it meets the
minimum requirements.  Works with only the Python standard library —
no pip installs needed first.

Exit code 0 = all required checks passed.
Exit code 1 = one or more required checks failed.
"""

import os
import platform
import sys


def check() -> list[dict]:
    results: list[dict] = []

    def add(name: str, ok, detail: str = "") -> None:
        results.append({"name": name, "ok": ok, "detail": detail})

    # ------------------------------------------------------------------
    # Required
    # ------------------------------------------------------------------
    py_ok = sys.version_info >= (3, 10)
    add("Python 3.10+", py_ok, platform.python_version())

    arch = platform.machine().lower()
    arch_ok = arch in (
        "x86_64", "amd64", "aarch64", "arm64", "armv7l", "armv8l", "arm"
    )
    add("Supported CPU architecture", arch_ok, arch)

    add("64-bit Python runtime", sys.maxsize > 2 ** 32, "")

    for mod in ("json", "sqlite3", "threading", "socket",
                "hashlib", "pathlib", "subprocess", "logging"):
        try:
            __import__(mod)
            add(f"stdlib: {mod}", True, "")
        except ImportError:
            add(f"stdlib: {mod}", False, "MISSING — required")

    # Disk space ≥ 100 MB
    try:
        stat    = os.statvfs(os.path.abspath("."))
        free_mb = (stat.f_bavail * stat.f_frsize) // (1024 * 1024)
        add("Disk space ≥ 100 MB", free_mb >= 100, f"{free_mb} MB free")
    except Exception:
        add("Disk space", None, "could not check")

    # ------------------------------------------------------------------
    # Informational
    # ------------------------------------------------------------------
    mem_mb: int | None = None
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    mem_mb = int(line.split()[1]) // 1024
                    break
    except OSError:
        pass

    if mem_mb is not None:
        add("RAM ≥ 512 MB", mem_mb >= 512,
            f"{mem_mb} MB total"
            + (" — AURA will run in memory-saver mode" if mem_mb < 512 else ""))

    is_termux = bool(
        os.environ.get("TERMUX_VERSION")
        or os.path.exists("/data/data/com.termux")
    )
    if is_termux:
        add("Termux environment", True, "Android phone detected ✓")

    try:
        import psutil  # type: ignore
        add("psutil (optional)", True, "enhanced metrics available")
    except ImportError:
        add("psutil (optional)", None, "pip install psutil  (not required)")

    return results


def main() -> int:
    w = 60
    print()
    print("╔" + "═" * (w - 2) + "╗")
    print("║  AURA-AIOSCPU Compatibility Checker" + " " * (w - 38) + "║")
    print("╚" + "═" * (w - 2) + "╝")
    print()

    results = check()
    passed  = sum(1 for r in results if r["ok"] is True)
    failed  = sum(1 for r in results if r["ok"] is False)
    warned  = sum(1 for r in results if r["ok"] is None)

    for r in results:
        icon   = "✓" if r["ok"] is True else ("✗" if r["ok"] is False else "?")
        detail = f"  — {r['detail']}" if r["detail"] else ""
        print(f"  {icon}  {r['name']}{detail}")

    print()
    print(f"  Passed: {passed}   Failed: {failed}   Warnings: {warned}")
    print()

    if failed == 0:
        print("  ✓  This device is ready to run AURA-AIOSCPU!")
    else:
        print("  ✗  Fix the issues above, then run this check again.")
    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
