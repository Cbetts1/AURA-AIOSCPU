"""
aura-logs — Structured log viewer for AURA-AIOSCPU.

Usage
-----
  python tools/aura_logs.py              # show last 50 lines of most-recent log
  python tools/aura_logs.py --list       # list available log files
  python tools/aura_logs.py --tail 100   # show last 100 lines
  python tools/aura_logs.py --follow     # follow log in real time (tail -f)
  python tools/aura_logs.py path/to.log  # view a specific file
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_REPO_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOGS_DIRS      = [
    os.path.join(_REPO_ROOT, "logs"),
    os.path.join(_REPO_ROOT, "rootfs", "var", "log"),
]


def find_log_files() -> list[str]:
    files = []
    for d in _LOGS_DIRS:
        if os.path.isdir(d):
            files.extend(str(p) for p in Path(d).glob("**/*.log"))
    return sorted(files)


def tail_file(path: str, lines: int, follow: bool) -> None:
    with open(path, errors="replace") as fh:
        content = fh.readlines()

    for line in content[-lines:]:
        print(line, end="")

    if not follow:
        return

    with open(path, errors="replace") as fh:
        fh.seek(0, 2)
        print(f"\n--- following {path}  (Ctrl-C to stop) ---\n")
        try:
            while True:
                chunk = fh.readline()
                if chunk:
                    print(chunk, end="", flush=True)
                else:
                    time.sleep(0.2)
        except KeyboardInterrupt:
            print()


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA-AIOSCPU Log Viewer")
    parser.add_argument("--list",   "-l", action="store_true",
                        help="List available log files")
    parser.add_argument("--tail",   "-n", type=int, default=50,
                        help="Lines to show (default: 50)")
    parser.add_argument("--follow", "-f", action="store_true",
                        help="Follow log in real time")
    parser.add_argument("file", nargs="?",
                        help="Log file (default: most recent)")
    args = parser.parse_args()

    files = find_log_files()

    if args.list:
        if not files:
            print("No log files found.")
            return
        print("Available log files:")
        for f in files:
            size = os.path.getsize(f) if os.path.exists(f) else 0
            print(f"  {f}  ({size:,} bytes)")
        return

    target = args.file or (files[-1] if files else None)
    if not target:
        print("No log files found. Start AURA to generate logs.")
        return
    if not os.path.exists(target):
        print(f"Log file not found: {target}")
        sys.exit(1)

    tail_file(target, lines=args.tail, follow=args.follow)


if __name__ == "__main__":
    main()
