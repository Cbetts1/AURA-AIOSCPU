"""
AURA-AIOSCPU Init System (aura-init)
=====================================
PID1-equivalent init system for AURA-AIOSCPU.

This is the canonical entry point for the OS. It:
  1. Runs the 6-stage boot chain.
  2. Manages the kernel process lifecycle.
  3. Handles signals (SIGTERM, SIGINT) for graceful shutdown.
  4. Writes PID file to rootfs/var/aura.pid.
  5. Reports exit code to the host.

Usage:
  python launch/aura_init.py [--mode universal|internal|hardware]
  python launch/aura_init.py --help

This file is the OS entry point, not the kernel.
"""

import argparse
import logging
import os
import signal
import sys
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aura-init")

_PID_FILE = os.path.join(_REPO_ROOT, "rootfs", "var", "aura.pid")


def _write_pid() -> None:
    try:
        os.makedirs(os.path.dirname(_PID_FILE), exist_ok=True)
        with open(_PID_FILE, "w") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass


def _remove_pid() -> None:
    try:
        os.unlink(_PID_FILE)
    except OSError:
        pass


def _select_mode(mode_name: str):
    from kernel.modes.universal import UniversalMode
    from kernel.modes.internal import InternalMode
    from kernel.modes.hardware import HardwareProjectionMode
    modes = {
        "universal": UniversalMode,
        "internal":  InternalMode,
        "hardware":  HardwareProjectionMode,
    }
    cls = modes.get(mode_name.lower())
    if cls is None:
        raise ValueError(
            f"Unknown mode {mode_name!r}. "
            f"Valid: {list(modes.keys())}"
        )
    return cls()


def _load_config():
    try:
        from config import Config
        return Config()
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="aura-init",
        description="AURA-AIOSCPU Init System — OS entry point",
    )
    parser.add_argument(
        "--mode", default=os.environ.get("AURA_MODE", "universal"),
        choices=["universal", "internal", "hardware"],
        help="Kernel surface mode (default: universal)",
    )
    parser.add_argument(
        "--loglevel", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.loglevel))
    logger.info("aura-init: starting (mode=%s pid=%d)", args.mode, os.getpid())

    _write_pid()
    _kernel = None

    def _handle_signal(signum, frame):
        logger.info("aura-init: received signal %d — shutting down", signum)
        if _kernel is not None:
            try:
                _kernel.shutdown()
            except Exception:
                pass
        _remove_pid()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT,  _handle_signal)

    try:
        mode   = _select_mode(args.mode)
        config = _load_config()

        from launch.boot import BootChain
        chain  = BootChain(mode, config=config)

        # Stage 0-1 run synchronously; stages 2-5 run inside kernel.start()
        for stage_fn in (
            chain._stage_0_environment,
            chain._stage_1_rootfs,
            chain._stage_2_kernel_init,
            chain._stage_3_services,
            chain._stage_4_shell,
            chain._stage_5_ai_persona,
        ):
            stage_fn()

        _kernel = chain._kernel
        from launch.boot import _write_boot_log
        _write_boot_log(chain.log, config)

        logger.info("aura-init: boot chain complete — starting kernel")
        _kernel.start()   # blocks until shutdown

    except Exception as exc:
        logger.error("aura-init: fatal boot failure: %s", exc, exc_info=True)
        _remove_pid()
        return 1

    _remove_pid()
    logger.info("aura-init: clean shutdown")
    return 0


if __name__ == "__main__":
    sys.exit(main())
