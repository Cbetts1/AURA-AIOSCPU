"""
aura-sys-info — System information and device compatibility reporter.

Shows hardware profile, AURA compatibility status, and recommended settings
for this device.  Run it on your phone before installing AURA.
"""

import json
import os
import platform
import sys
import time

# Make importable from the repo root regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_sys_info() -> dict:
    from kernel.device_profile import DeviceProfile
    profile = DeviceProfile()
    info    = profile.to_dict()
    info["timestamp"]    = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    info["python_impl"]  = platform.python_implementation()
    info["python_build"] = " ".join(platform.python_build())

    # Compatibility checks
    checks: dict[str, bool | None] = {
        "python_3_10_plus": sys.version_info >= (3, 10),
        "64bit":            info["is_64bit"],
        "sqlite3":          _check_import("sqlite3"),
        "threading":        _check_import("threading"),
        "json":             _check_import("json"),
        "pathlib":          _check_import("pathlib"),
    }
    info["compatibility_checks"] = checks
    info["aura_ready"] = all(v is True for v in checks.values())

    # Optional psutil for richer metrics
    try:
        import psutil  # type: ignore
        vm  = psutil.virtual_memory()
        bat = None
        if hasattr(psutil, "sensors_battery"):
            b = psutil.sensors_battery()
            if b:
                bat = {"percent": b.percent, "plugged": b.power_plugged}
        freq = psutil.cpu_freq()
        info.update({
            "memory_total_mb":     vm.total    // (1024 * 1024),
            "memory_available_mb": vm.available // (1024 * 1024),
            "memory_percent":      vm.percent,
            "cpu_freq_mhz":        freq.current if freq else None,
            "battery":             bat,
        })
    except ImportError:
        pass

    return info


def _check_import(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def main() -> None:
    info = get_sys_info()
    w = 62
    print("=" * w)
    print("  AURA-AIOSCPU — System Information")
    print("=" * w)

    # Group output
    skip = {"compatibility_checks"}
    for key, val in info.items():
        if key in skip:
            continue
        print(f"  {key:<30} {val}")

    print()
    print("  Compatibility checks:")
    for k, v in info.get("compatibility_checks", {}).items():
        icon = "✓" if v else "✗"
        print(f"    {icon}  {k}")

    print()
    if info.get("aura_ready"):
        print("  ✓  This device is AURA-AIOSCPU compatible!")
    else:
        print("  ✗  Some required checks failed — see above.")

    if info.get("is_termux"):
        print()
        print("  📱 Termux detected  →  run:  python launch/launcher.py")
    elif info.get("is_android"):
        print()
        print("  📱 Android detected  →  install Termux (F-Droid) for best results.")

    print("=" * w)
    print()


if __name__ == "__main__":
    main()
