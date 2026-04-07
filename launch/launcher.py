"""
AURA-AIOSCPU Launcher
=====================
The first thing that runs.

Boot sequence
-------------
1. Set up structured logging (file + console).
2. Detect host environment and select kernel surface mode.
3. Load configuration (config/default.json → config/user.json → env vars).
4. Detect device hardware profile and apply mobile tuning if needed.
5. Mount (or verify) rootfs at the expected path.
6. Instantiate and start the Kernel.

This file lives at /launch/launcher.py (outside rootfs).
"""

import logging
import logging.handlers
import os
import sys

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
LOG_DIR = os.path.join(_REPO_ROOT, "logs")


def _setup_logging() -> None:
    """Configure logging to both console and a rotating file."""
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "aura.log")

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # Rotating file handler (10 MB × 3 rotations)
    try:
        fh = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=10 * 1024 * 1024, backupCount=3
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass  # read-only filesystem — log to console only

logger = logging.getLogger(__name__)


def detect_mode() -> str:
    """Detect the correct kernel surface mode for this environment."""
    env_mode = os.environ.get("AURA_MODE", "").lower()
    if env_mode in ("hardware", "internal", "universal"):
        logger.info("Launcher: mode overridden via AURA_MODE=%r", env_mode)
        return env_mode

    if hasattr(os, "getuid") and os.getuid() == 0:
        return "internal"

    return "universal"


def mount_rootfs(rootfs_path: str) -> bool:
    """Verify the rootfs exists and has the expected directory layout."""
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
    _setup_logging()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    from kernel.config import Config
    config = Config()
    logger.info("Launcher: config loaded %r", config)

    # ------------------------------------------------------------------
    # Device profile — auto-tune for phones
    # ------------------------------------------------------------------
    from kernel.device_profile import DeviceProfile
    profile = DeviceProfile()
    if profile.is_mobile:
        logger.info("Launcher: mobile device detected — applying mobile profile")
        config.apply_mobile_profile()
    else:
        config.set("kernel", "tick_interval_ms",
                   profile.recommended_tick_ms())

    logger.info("Launcher: device profile %r", profile)

    # ------------------------------------------------------------------
    # Mode + rootfs
    # ------------------------------------------------------------------
    mode_name = detect_mode()
    logger.info("Launcher: detected mode=%r", mode_name)

    ok = mount_rootfs(ROOTFS_PATH)
    if not ok:
        print("ERROR: rootfs is not ready. Cannot boot.", file=sys.stderr)
        sys.exit(1)

    mode   = build_mode(mode_name)
    kernel = Kernel(mode, config=config, device_profile=profile)

    try:
        kernel.start()
    except KeyboardInterrupt:
        print("\nInterrupted — shutting down.")
        kernel.shutdown()


if __name__ == "__main__":
    main()

