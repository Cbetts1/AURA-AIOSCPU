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

# TODO: from kernel import Kernel
# TODO: from kernel.modes.universal import UniversalMode
# TODO: from kernel.modes.internal import InternalMode
# TODO: from kernel.modes.hardware import HardwareMode

ROOTFS_PATH = "/rootfs"


def detect_mode():
    """Detect the correct kernel surface mode for this environment.

    Returns one of: 'hardware', 'internal', 'universal'
    """
    # TODO: check for bare-metal / SD-card indicators → 'hardware'
    # TODO: check for user-granted elevated permissions → 'internal'
    # TODO: default fallback → 'universal'
    return "universal"


def mount_rootfs(rootfs_path: str) -> bool:
    """Verify the rootfs exists and has the expected directory layout.

    Returns True if the rootfs is usable, False otherwise.
    """
    # TODO: check rootfs_path exists
    # TODO: verify required subdirs: bin, etc, usr, var, tmp, home
    # TODO: set up sys.path / environment so kernel modules are importable
    return False


def main() -> None:
    """Entry point — called when the launcher is executed directly."""
    # TODO: mode_name = detect_mode()
    # TODO: ok = mount_rootfs(ROOTFS_PATH)
    # TODO: if not ok: print error and exit
    # TODO: mode = { 'universal': UniversalMode, ... }[mode_name]()
    # TODO: kernel = Kernel(mode)
    # TODO: kernel.start()
    pass


if __name__ == "__main__":
    main()
