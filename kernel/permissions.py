"""
AURA-AIOSCPU Kernel Permission / Capability Model
==================================================
Every operation in AURA-AIOSCPU is gated by a capability. Capabilities
are organised into tiers that map directly to kernel surface modes.

Capability tiers
----------------
  TIER_0  — always allowed (read-only, safe, no side-effects)
  TIER_1  — universal mode (host-bridge I/O, process spawn, network)
  TIER_2  — internal mode (elevated: fs mount, net listen, sys info)
  TIER_3  — hardware mode (projection, device write, kernel patch)

The permission model is enforced in three places:
  1. HostBridge.syscall()  — rejects disallowed syscalls
  2. KernelAPI             — rejects service calls above current tier
  3. Shell                 — surfaces PERMISSION_REQUEST to the user

Capability strings use dot-notation:  <subsystem>.<action>
Examples:  fs.read   net.listen   hal.project   kernel.mode_switch
"""

import logging
from typing import FrozenSet

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Capability definitions by tier
# ---------------------------------------------------------------------------

TIER_0: FrozenSet[str] = frozenset({
    "aura.query",
    "aura.pulse",
    "fs.read",
    "event.publish",
    "event.subscribe",
    "shell.command",
    "sysinfo.read",
})

TIER_1: FrozenSet[str] = TIER_0 | frozenset({
    "fs.write",
    "fs.list",
    "net.connect",
    "net.send",
    "net.recv",
    "proc.spawn",
    "proc.kill",
    "service.query",
    "log.read",
    "job.submit",
    "pkg.install",
    "pkg.list",
})

TIER_2: FrozenSet[str] = TIER_1 | frozenset({
    "fs.chmod",
    "fs.mount_bind",
    "net.listen",
    "net.raw",
    "sys.info",
    "service.start",
    "service.stop",
    "service.register",
    "kernel.config_write",
    "storage.write",
    "storage.partition",
    "log.write",
    "job.cancel",
    "model.load",
    "model.unload",
})

TIER_3: FrozenSet[str] = TIER_2 | frozenset({
    "hal.project",
    "hal.teardown",
    "kernel.mode_switch",
    "kernel.patch",
    "device.write",
    "device.project",
    "hardware.bind",
    "hardware.unbind",
})

_TIER_MAP: dict[str, FrozenSet[str]] = {
    "universal": TIER_1,
    "internal":  TIER_2,
    "hardware":  TIER_3,
}

_MODE_TIER: dict[str, int] = {
    "universal": 1,
    "internal":  2,
    "hardware":  3,
}

_CAPABILITY_TIER: dict[str, int] = {}
for _cap in TIER_0:
    _CAPABILITY_TIER[_cap] = 0
for _cap in TIER_1 - TIER_0:
    _CAPABILITY_TIER[_cap] = 1
for _cap in TIER_2 - TIER_1:
    _CAPABILITY_TIER[_cap] = 2
for _cap in TIER_3 - TIER_2:
    _CAPABILITY_TIER[_cap] = 3


# ---------------------------------------------------------------------------
# PermissionDenied exception
# ---------------------------------------------------------------------------

class PermissionDenied(PermissionError):
    """Raised when an operation is not permitted in the current kernel mode."""

    def __init__(self, capability: str, current_mode: str,
                 required_mode: str | None = None):
        self.capability   = capability
        self.current_mode = current_mode
        self.required_mode = required_mode
        msg = (
            f"Capability {capability!r} is not permitted in "
            f"{current_mode!r} mode."
        )
        if required_mode:
            msg += f" Requires at least {required_mode!r} mode."
        super().__init__(msg)


# ---------------------------------------------------------------------------
# PermissionModel
# ---------------------------------------------------------------------------

class PermissionModel:
    """
    Enforces capability-based access control for the kernel.

    The model tracks:
      - The current kernel surface mode (universal / internal / hardware)
      - User-granted runtime permissions (additional capabilities)
      - Revoked capabilities (deny-list overrides grants)

    Usage::

        pm = PermissionModel(mode="universal")
        pm.check("fs.write")           # OK — tier 1
        pm.check("net.listen")         # raises PermissionDenied
        pm.grant("net.listen")         # user grants at runtime
        pm.check("net.listen")         # OK now
        pm.revoke("net.listen")
        pm.check("net.listen")         # raises PermissionDenied again
    """

    def __init__(self, mode: str = "universal"):
        self._mode    = self._validate_mode(mode)
        self._granted: set[str] = set()   # runtime user grants
        self._revoked: set[str] = set()   # explicit revocations (override grants)

    # ------------------------------------------------------------------
    # Mode management
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, new_mode: str) -> None:
        """Switch to a different kernel surface mode."""
        old = self._mode
        self._mode = self._validate_mode(new_mode)
        # Revoke any grants that were only valid in a higher-tier mode
        if _MODE_TIER[self._mode] < _MODE_TIER[old]:
            self._granted.clear()
        logger.info("PermissionModel: mode switched %r → %r", old, self._mode)

    # ------------------------------------------------------------------
    # Runtime grants / revocations
    # ------------------------------------------------------------------

    def grant(self, capability: str) -> None:
        """
        Grant a specific capability at runtime (user consent flow).
        Capability must be in the TIER_3 table (known capability).
        """
        if capability not in _CAPABILITY_TIER:
            raise ValueError(f"Unknown capability: {capability!r}")
        self._revoked.discard(capability)
        self._granted.add(capability)
        logger.info("PermissionModel: granted %r", capability)

    def revoke(self, capability: str) -> None:
        """Explicitly revoke a capability, overriding any mode-level grant."""
        self._granted.discard(capability)
        self._revoked.add(capability)
        logger.info("PermissionModel: revoked %r", capability)

    def reset_grants(self) -> None:
        """Clear all runtime grants and revocations."""
        self._granted.clear()
        self._revoked.clear()

    # ------------------------------------------------------------------
    # Enforcement
    # ------------------------------------------------------------------

    def check(self, capability: str) -> None:
        """
        Assert that the capability is allowed. Raises PermissionDenied if not.

        Check order:
          1. Explicit revoke → always denied
          2. Mode-level allow (tier-based)
          3. Runtime grant → allowed
        """
        if capability in self._revoked:
            raise PermissionDenied(capability, self._mode)

        allowed = _TIER_MAP.get(self._mode, TIER_1)
        if capability in allowed:
            return

        if capability in self._granted:
            return

        # Determine what mode would be needed
        needed_tier = _CAPABILITY_TIER.get(capability)
        required_mode: str | None = None
        if needed_tier is not None:
            for m, t in _MODE_TIER.items():
                if t >= needed_tier:
                    required_mode = m
                    break

        raise PermissionDenied(capability, self._mode, required_mode)

    def is_allowed(self, capability: str) -> bool:
        """Return True if the capability is currently allowed (no raise)."""
        try:
            self.check(capability)
            return True
        except PermissionDenied:
            return False

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def allowed_capabilities(self) -> FrozenSet[str]:
        """Return all capabilities allowed in the current mode + grants."""
        base = _TIER_MAP.get(self._mode, TIER_1)
        return (base | self._granted) - self._revoked

    def summary(self) -> dict:
        return {
            "mode":    self._mode,
            "tier":    _MODE_TIER.get(self._mode, 1),
            "granted": sorted(self._granted),
            "revoked": sorted(self._revoked),
            "total_allowed": len(self.allowed_capabilities()),
        }

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_mode(mode: str) -> str:
        if mode not in _MODE_TIER:
            raise ValueError(
                f"Unknown kernel mode {mode!r}. "
                f"Valid: {list(_MODE_TIER)}"
            )
        return mode
