#!/usr/bin/env python
"""
AURA-AIOSCPU Build Script
==========================
Assembles a portable, self-contained rootfs image ready to deploy.

Usage
-----
  python build.py                 full build (clean + package + verify)
  python build.py --test          run test suite first, abort on failure
  python build.py --verify        verify integrity of an existing build
  python build.py --clean         wipe dist/ then build
  python build.py --no-verify     skip post-build integrity check
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("aura.build")

REPO_ROOT  = os.path.dirname(os.path.abspath(__file__))
DIST_DIR   = os.path.join(REPO_ROOT, "dist")
ROOTFS_SRC = os.path.join(REPO_ROOT, "rootfs")
ROOTFS_DST = os.path.join(DIST_DIR,  "rootfs")
VERSION    = "0.1.0"

PACKAGES = [
    "kernel", "hal", "aura", "services", "shell",
    "host_bridge", "models", "tools", "config", "launch",
]

REQUIRED_ROOTFS_DIRS = [
    "bin", "etc", "home", "tmp",
    "usr/bin", "usr/lib/aura", "var/log", "var/run",
]

TOOLS = {
    "aura-sys-info":       "tools.aura_sys_info",
    "aura-logs":           "tools.aura_logs",
    "aura-service-status": "tools.aura_service_status",
    "aura-check":          "tools.check_requirements",
}


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def banner(text: str) -> None:
    w = 62
    print("\n" + "═" * w)
    print(f"  {text}")
    print("═" * w)


def step(text: str) -> None:
    print(f"\n→  {text}")


def ok(text: str) -> None:
    print(f"   ✓  {text}")


def err(text: str) -> None:
    print(f"   ✗  {text}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Build phases
# ---------------------------------------------------------------------------

def run_tests() -> bool:
    step("Running test suite …")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        err("Tests failed — build aborted")
        return False
    ok("All tests passed")
    return True


def clean() -> None:
    step("Cleaning dist/ …")
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR)
    ok("dist/ cleaned")


def build_rootfs() -> None:
    step("Building rootfs layout …")
    for d in REQUIRED_ROOTFS_DIRS:
        os.makedirs(os.path.join(ROOTFS_DST, d), exist_ok=True)
    ok("Directory structure created")

    if os.path.exists(ROOTFS_SRC):
        _copy_tree(ROOTFS_SRC, ROOTFS_DST)
        ok("Base rootfs content copied")


def package_source() -> None:
    step("Packaging Python source …")
    pkg_dir = os.path.join(ROOTFS_DST, "usr", "lib", "aura")
    os.makedirs(pkg_dir, exist_ok=True)

    for pkg in PACKAGES:
        src = os.path.join(REPO_ROOT, pkg)
        if not os.path.exists(src):
            continue
        dst = os.path.join(pkg_dir, pkg)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(
            src, dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        ok(f"Packaged {pkg}/")

    with open(os.path.join(pkg_dir, "__init__.py"), "w") as fh:
        fh.write("# AURA-AIOSCPU package root\n")


def write_launchers() -> None:
    step("Writing launcher scripts …")

    # dist/aura — run from anywhere
    _write_launcher(
        os.path.join(DIST_DIR, "aura"),
        "sys.path.insert(0, os.path.join("
        "os.path.dirname(os.path.abspath(__file__)),"
        " 'rootfs', 'usr', 'lib', 'aura'))",
    )
    ok("dist/aura")

    # dist/rootfs/bin/aura — in-rootfs entry
    _write_launcher(
        os.path.join(ROOTFS_DST, "bin", "aura"),
        "sys.path.insert(0, '/usr/lib/aura')",
    )
    ok("rootfs/bin/aura")

    # Tool entry-points in usr/bin/
    usr_bin = os.path.join(ROOTFS_DST, "usr", "bin")
    for tool_name, module in TOOLS.items():
        tool_path = os.path.join(usr_bin, tool_name)
        with open(tool_path, "w") as fh:
            fh.write("#!/usr/bin/env python\n")
            fh.write("import sys; sys.path.insert(0, '/usr/lib/aura')\n")
            fh.write(f"from {module} import main\n")
            fh.write("if __name__ == '__main__':\n    main()\n")
        os.chmod(tool_path, 0o755)
        ok(f"usr/bin/{tool_name}")


def write_manifest() -> None:
    step("Writing build manifest …")
    # Store checksums of source files (same keys as verify_integrity uses)
    checksums = {}
    repo = Path(REPO_ROOT)
    for py_file in sorted(repo.rglob("*.py")):
        rel = str(py_file.relative_to(repo))
        if any(p in rel for p in (".git", "__pycache__", "dist", "/tmp")):
            continue
        checksums[rel] = _sha256(py_file)

    manifest = {
        "build_time":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "build_epoch":  time.time(),
        "version":      VERSION,
        "total_files":  len(checksums),
        "files":        checksums,
    }
    with open(os.path.join(DIST_DIR, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    ok(f"manifest.json  ({len(checksums)} source files)")


def verify_build() -> bool:
    step("Verifying build integrity …")
    manifest_path = os.path.join(DIST_DIR, "manifest.json")
    if not os.path.exists(manifest_path):
        err("No manifest.json — run build first")
        return False

    with open(manifest_path) as fh:
        manifest = json.load(fh)

    bad = []
    for rel, expected in manifest.get("files", {}).items():
        full = os.path.join(DIST_DIR, rel)
        if not os.path.exists(full):
            bad.append(f"MISSING: {rel}")
            continue
        if _sha256(full) != expected:
            bad.append(f"CHANGED: {rel}")

    for b in bad:
        err(b)

    n = len(manifest.get("files", {}))
    ok(f"All {n} files verified ✓") if not bad else None
    return not bad


def print_summary(duration: float) -> None:
    banner("Build Summary")
    total = sum(1 for _ in Path(DIST_DIR).rglob("*") if Path(_).is_file())
    size  = sum(
        p.stat().st_size for p in Path(DIST_DIR).rglob("*") if p.is_file()
    )
    print(f"  Output dir   : {DIST_DIR}/")
    print(f"  Launcher     : {DIST_DIR}/aura")
    print(f"  Rootfs       : {ROOTFS_DST}/")
    print(f"  Files        : {total}   Size: {size / 1024:.1f} KB")
    print(f"  Build time   : {duration:.2f}s")
    print()
    print("  Run AURA:")
    print(f"    python {DIST_DIR}/aura")
    print()
    print("  Run on Android / Termux:")
    print("    bash install_termux.sh")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="AURA-AIOSCPU Build Script")
    parser.add_argument("--test",      action="store_true",
                        help="Run tests before building")
    parser.add_argument("--verify",    action="store_true",
                        help="Only verify integrity of an existing build")
    parser.add_argument("--clean",     action="store_true",
                        help="Clean dist/ before building")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip post-build integrity check")
    args = parser.parse_args()

    banner(f"AURA-AIOSCPU Build System  v{VERSION}")
    t0 = time.monotonic()

    if args.verify:
        return 0 if verify_build() else 1

    if args.test:
        if not run_tests():
            return 1

    if args.clean:
        clean()

    os.makedirs(DIST_DIR, exist_ok=True)
    build_rootfs()
    package_source()
    write_launchers()
    write_manifest()

    if not args.no_verify:
        if not verify_build():
            err("Build verification failed!")
            return 1

    print_summary(time.monotonic() - t0)
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_launcher(path: str, sys_path_stmt: str) -> None:
    with open(path, "w") as fh:
        fh.write("#!/usr/bin/env python\n")
        fh.write('"""AURA-AIOSCPU auto-generated launcher."""\n')
        fh.write("import os, sys\n")
        fh.write(f"{sys_path_stmt}\n")
        fh.write("from launch.launcher import main\n")
        fh.write("if __name__ == '__main__':\n    main()\n")
    os.chmod(path, 0o755)


def _copy_tree(src: str, dst: str) -> None:
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel      = os.path.relpath(root, src)
        dest_dir = os.path.join(dst, rel)
        os.makedirs(dest_dir, exist_ok=True)
        for f in files:
            if not f.endswith((".pyc", ".pyo")):
                shutil.copy2(
                    os.path.join(root, f),
                    os.path.join(dest_dir, f),
                )


if __name__ == "__main__":
    sys.exit(main())
