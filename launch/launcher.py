"""
AURA-AIOSCPU Launcher
=====================
The first thing that runs.

Boot sequence
-------------
1. Detect host environment (bare-metal SD card / host OS / internal).
2. Mount (or verify) rootfs at the expected path.
3. Select the correct kernel surface mode: Hardware | Internal | Universal.
4. Instantiate and start the Kernel.

This file lives at /launch/launcher.py (outside rootfs).
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

# Add the repo root to sys.path so all packages are importable regardless
# of where the launcher is invoked from.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kernel import Kernel                              # noqa: E402
from kernel.modes.universal import UniversalMode       # noqa: E402
from kernel.modes.internal import InternalMode         # noqa: E402
from kernel.modes.hardware import HardwareMode         # noqa: E402

ROOTFS_PATH = os.path.join(_REPO_ROOT, "rootfs")
ROOTFS_REQUIRED_DIRS = ["bin", "etc", "usr", "var", "tmp", "home"]


def detect_mode() -> str:
    """Detect the correct kernel surface mode for this environment.

    Returns one of: 'hardware', 'internal', 'universal'
    """
    # AURA_MODE env var allows explicit override (useful for testing)
    env_mode = os.environ.get("AURA_MODE", "").lower()
    if env_mode in ("hardware", "internal", "universal"):
        logger.info("Launcher: mode overridden via AURA_MODE=%r", env_mode)
        return env_mode

    # Heuristic: if running as root → Internal mode
    if os.getuid() == 0:
        return "internal"

    # Default: Universal (no root, host-bridge only)
    return "universal"


def mount_rootfs(rootfs_path: str) -> bool:
    """Verify the rootfs exists and has the expected directory layout.

    Returns True if the rootfs is usable, False otherwise.
    """
    if not os.path.isdir(rootfs_path):
        logger.error("Launcher: rootfs not found at %r", rootfs_path)
        return False

    missing = [
        d for d in ROOTFS_REQUIRED_DIRS
        if not os.path.isdir(os.path.join(rootfs_path, d))
    ]
    if missing:
        logger.error("Launcher: rootfs missing required dirs: %s", missing)
        return False

    logger.info("Launcher: rootfs OK at %r", rootfs_path)
    return True


def build_mode(mode_name: str):
    """Instantiate the correct mode object."""
    if mode_name == "hardware":
        return HardwareMode()
    if mode_name == "internal":
        return InternalMode()
    return UniversalMode()


def main() -> None:
    """Entry point — called when the launcher is executed directly."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    mode_name = detect_mode()
    logger.info("Launcher: detected mode=%r", mode_name)

    ok = mount_rootfs(ROOTFS_PATH)
    if not ok:
        print("ERROR: rootfs is not ready. Cannot boot.", file=sys.stderr)
        sys.exit(1)

    mode = build_mode(mode_name)
    kernel = Kernel(mode)

    try:
        kernel.start()
    except KeyboardInterrupt:
        print("\nInterrupted — shutting down.")
        kernel.shutdown()


if __name__ == "__main__":
    main()

