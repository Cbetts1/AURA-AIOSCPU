"""
aura-service-status — Inspect AURA-AIOSCPU service unit files.

Usage
-----
  python tools/aura_service_status.py         # list all services
  python tools/aura_service_status.py --json  # JSON output
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_REPO_ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SERVICES_DIR = os.path.join(_REPO_ROOT, "services")


def _parse_unit(path: str) -> dict:
    unit: dict = {}
    with open(path, errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                unit[k.strip()] = v.strip()
    return unit


def list_services() -> list[dict]:
    sdir = Path(_SERVICES_DIR)
    results = []
    if not sdir.is_dir():
        return results
    for f in sorted(sdir.glob("*.service")):
        unit = _parse_unit(str(f))
        ep   = unit.get("entrypoint", "?")
        results.append({
            "file":        f.name,
            "name":        unit.get("name", f.stem),
            "entrypoint":  ep,
            "autostart":   unit.get("autostart", "false"),
            "restart":     unit.get("restart", "—"),
            "exists":      os.path.isfile(ep),
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AURA-AIOSCPU Service Status")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    services = list_services()

    if args.json:
        print(json.dumps(services, indent=2))
        return

    print("AURA-AIOSCPU — Service Units")
    print("=" * 50)
    if not services:
        print(f"  No .service files found in: {_SERVICES_DIR}")
        return
    for svc in services:
        ep_ok = "✓" if svc["exists"] else "?"
        print(f"  {svc['name']}")
        print(f"    file        : {svc['file']}")
        print(f"    entrypoint  : {svc['entrypoint']}  {ep_ok}")
        print(f"    autostart   : {svc['autostart']}")
        print(f"    restart     : {svc['restart']}")
        print()


if __name__ == "__main__":
    main()
