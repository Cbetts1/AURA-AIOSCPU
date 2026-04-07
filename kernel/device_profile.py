"""
AURA-AIOSCPU Device Profile
============================
Detects the current device's hardware profile and recommends
kernel settings tuned for that device.

Key detections
--------------
- ARM / ARM64 architecture  (Android phones, Apple Silicon, RPi)
- Android operating system
- Termux environment        (Python on Android without root)
- Available RAM
- CPU core count

Used by the launcher to auto-apply the mobile config profile and to
display accurate system information via ``aura-sys-info``.
"""

import logging
import os
import platform
import sys

logger = logging.getLogger(__name__)


class DeviceProfile:
    """Snapshot of the current device's hardware and software environment."""

    def __init__(self):
        self.architecture: str  = platform.machine().lower()
        self.python_version     = sys.version_info
        self.cpu_count: int     = os.cpu_count() or 1
        self.is_64bit: bool     = sys.maxsize > 2 ** 32
        self.is_termux: bool    = self._detect_termux()
        self.is_android: bool   = self._detect_android()
        self.is_mobile: bool    = self.is_android or self.is_termux
        self.is_arm: bool       = self.architecture in (
            "aarch64", "arm64", "armv7l", "armv8l", "arm"
        )
        self.memory_mb: int     = self._get_memory_mb()
        self.hostname: str      = platform.node()
        self.os_name: str       = platform.system()

        logger.info(
            "DeviceProfile: arch=%s mobile=%s android=%s termux=%s "
            "arm=%s mem=%dMB cpus=%d",
            self.architecture, self.is_mobile, self.is_android,
            self.is_termux, self.is_arm, self.memory_mb, self.cpu_count,
        )

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def recommended_tick_ms(self) -> int:
        """Kernel loop interval — lower = more responsive, higher = less power."""
        if self.is_mobile and self.memory_mb < 512:
            return 200   # very constrained device
        if self.is_mobile:
            return 100   # typical phone — 10 Hz
        return 16        # desktop/server  — ~60 Hz

    def recommended_max_memory_mb(self) -> int:
        """Safe AURA memory budget for this device."""
        if self.is_mobile:
            return min(self.memory_mb // 4, 256)
        return min(self.memory_mb // 2, 2048)

    def recommended_max_task_queue(self) -> int:
        return 256 if self.is_mobile else 1000

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "architecture":              self.architecture,
            "cpu_count":                 self.cpu_count,
            "is_64bit":                  self.is_64bit,
            "is_android":                self.is_android,
            "is_termux":                 self.is_termux,
            "is_mobile":                 self.is_mobile,
            "is_arm":                    self.is_arm,
            "memory_mb":                 self.memory_mb,
            "hostname":                  self.hostname,
            "os_name":                   self.os_name,
            "python_version":            ".".join(
                str(v) for v in self.python_version[:3]
            ),
            "recommended_tick_ms":       self.recommended_tick_ms(),
            "recommended_max_memory_mb": self.recommended_max_memory_mb(),
        }

    def __repr__(self):
        return (
            f"DeviceProfile(arch={self.architecture!r}, "
            f"mobile={self.is_mobile}, mem={self.memory_mb}MB)"
        )

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------

    def _detect_termux(self) -> bool:
        return bool(
            os.environ.get("TERMUX_VERSION")
            or os.path.exists("/data/data/com.termux")
            or "com.termux" in os.environ.get("HOME", "")
            or "com.termux" in os.environ.get("PREFIX", "")
        )

    def _detect_android(self) -> bool:
        if self._detect_termux():
            return True
        try:
            with open("/proc/version") as fh:
                return "android" in fh.read().lower()
        except OSError:
            pass
        return "android" in sys.version.lower()

    def _get_memory_mb(self) -> int:
        """Best-effort total RAM in MB (falls back to 1 024 MB)."""
        try:
            with open("/proc/meminfo") as fh:
                for line in fh:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) // 1024
        except OSError:
            pass
        # psutil fallback (optional dependency)
        try:
            import psutil  # type: ignore
            return psutil.virtual_memory().total // (1024 * 1024)
        except ImportError:
            pass
        return 1024
