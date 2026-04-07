"""
AURA-AIOSCPU AURA Privilege Model
===================================
AURA runs as virtual root inside AURA-AIOSCPU.

Two privilege tiers
-------------------
  virtual_root  — full authority inside AURA-AIOSCPU (always active)
  host_root     — real capability on the host OS (requires explicit user consent)

Virtual root authority (always active)
---------------------------------------
  - kernel configuration (read + write)
  - service lifecycle (start, stop, restart, register)
  - all logs (read, write, query, clear)
  - scheduler (submit, cancel, prioritise)
  - rootfs storage (read + write anywhere in rootfs, excluding host-side protected partitions)
  - shell environment (variables, plugins, history)
  - model management (load, unload, scan, register)

Host root (ONLY with explicit user consent + bridge approval)
--------------------------------------------------------------
  1. User explicitly requests host escalation.
  2. Host bridge confirms the capability is available on this host.
  3. Action is not in the permanently-forbidden set.
  4. User acknowledges a prominent warning.
  5. Action is logged before execution.

AURA NEVER:
  - bypasses the host-bridge.
  - performs actions the bridge marks unsafe or unsupported.
  - damages the device.
  - does anything illegal.
  - skips logging.

All AURA actions are logged with:
  actor="AURA"  privilege="virtual_root" | "host_root"
"""

import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Virtual root capability set — AURA's full internal authority
# -----------------------------------------------------------------------

VIRTUAL_ROOT_CAPS: frozenset[str] = frozenset({
    # Kernel
    "kernel.config_write", "kernel.config_read", "kernel.mode_switch",
    # Services
    "service.start", "service.stop", "service.register", "service.query",
    # Logs
    "log.read", "log.write", "log.clear",
    # Scheduler / jobs
    "job.submit", "job.cancel",
    # Rootfs storage
    "fs.read", "fs.write", "fs.list", "fs.chmod",
    "storage.write", "storage.partition",
    # Shell
    "shell.command", "shell.env_write",
    # Models
    "model.load", "model.unload",
    # AURA
    "aura.query", "aura.pulse",
    # Events
    "event.publish", "event.subscribe",
    # Sysinfo
    "sysinfo.read",
    # Network (query-level in virtual root)
    "net.connect", "net.send", "net.recv",
})

# Host escalation eligibility — actions that MAY be escalated to host root
# with user consent and bridge approval.
HOST_ESCALATION_ELIGIBLE: frozenset[str] = frozenset({
    "net.listen",
    "net.raw",
    "fs.mount_bind",
    "hal.project",
    "hal.teardown",
    "device.write",
    "proc.kill",
})

# Permanently forbidden — no escalation ever, regardless of user request.
# These actions could damage the device, are illegal, or bypass host security.
PERMANENTLY_FORBIDDEN: frozenset[str] = frozenset({
    "host.kernel_patch",
    "host.wipe_device",
    "host.root_exploit",
    "host.bypass_security",
    "host.illegal_action",
    "host.memory_overwrite",
})


class AURAPrivilegeError(PermissionError):
    """Raised when AURA attempts an operation outside its privilege boundary."""


class AURAPrivilege:
    """
    AURA's privilege manager.

    AURA is always virtual root inside AURA-AIOSCPU. It can request host-level
    escalation when the user explicitly asks for it, subject to bridge
    approval, safety checks, and audit logging.

    Usage::

        priv = AURAPrivilege(kernel_api=api, col=col, event_bus=bus)
        result = priv.execute_as_virtual_root(
            "service.start",
            lambda: api.start_service("network"),
            "start network service at boot",
        )
        # Host escalation (user-initiated only):
        approved = priv.request_host_escalation(
            "net.listen", reason="open web terminal port", confirm=False
        )
    """

    def __init__(self, kernel_api=None, col=None,
                 logging_service=None, event_bus=None):
        self._api      = kernel_api
        self._col      = col
        self._log_svc  = logging_service
        self._bus      = event_bus
        self._host_escalations: list[dict] = []

    # ------------------------------------------------------------------
    # Attach services (called after kernel start)
    # ------------------------------------------------------------------

    def attach(self, kernel_api=None, col=None,
               logging_service=None, event_bus=None) -> None:
        if kernel_api      is not None: self._api     = kernel_api
        if col             is not None: self._col     = col
        if logging_service is not None: self._log_svc = logging_service
        if event_bus       is not None: self._bus     = event_bus

    # ------------------------------------------------------------------
    # Virtual root — always active inside AURA-AIOSCPU
    # ------------------------------------------------------------------

    def is_virtual_root(self) -> bool:
        """AURA is always virtual root inside AURA-AIOSCPU."""
        return True

    def check_virtual(self, capability: str) -> bool:
        """Return True if capability is within AURA's virtual-root set."""
        return capability in VIRTUAL_ROOT_CAPS

    def assert_virtual(self, capability: str) -> None:
        """Assert the capability is allowed; raise AURAPrivilegeError if not."""
        if capability not in VIRTUAL_ROOT_CAPS:
            raise AURAPrivilegeError(
                f"Capability {capability!r} is not in AURA's virtual-root set. "
                f"Use request_host_escalation() for host-level operations."
            )

    def execute_as_virtual_root(
        self,
        capability: str,
        fn: Callable,
        description: str = "",
    ):
        """
        Execute fn() with virtual-root authority.

        Validates the capability, runs fn(), and logs the action with
        actor="AURA" and privilege="virtual_root".

        Raises AURAPrivilegeError if capability is not in virtual root set.
        """
        self.assert_virtual(capability)
        self._audit(capability, "virtual_root", description, approved=True)
        try:
            result = fn()
            self._audit(capability, "virtual_root", description,
                        approved=True, executed=True)
            return result
        except Exception as exc:
            self._audit(capability, "virtual_root", description,
                        approved=True, executed=False,
                        denial=f"execution_error: {exc}")
            raise

    # ------------------------------------------------------------------
    # Host root — explicit user consent required every time
    # ------------------------------------------------------------------

    def request_host_escalation(
        self,
        capability: str,
        reason: str,
        confirm: bool = False,
    ) -> bool:
        """
        Request real-host capability escalation. Returns True if approved.

        Flow:
          1. Check permanently-forbidden list — always deny if found.
          2. Check host-escalation eligibility — must be in known set.
          3. Ask the host bridge if the capability actually exists.
          4. Route through COL for user warning + confirmation.
          5. Log the outcome before and after.

        Args:
            capability: Host capability string to request.
            reason:     User-visible justification (non-empty required).
            confirm:    True = --force mode, skip interactive prompt.
        """
        # Step 1: permanently forbidden
        if capability in PERMANENTLY_FORBIDDEN:
            self._audit(capability, "host_root", reason, approved=False,
                        denial="permanently_forbidden")
            logger.error(
                "AURAPrivilege: %r is permanently forbidden — "
                "no escalation possible", capability
            )
            return False

        # Step 2: must be escalation-eligible
        if capability not in HOST_ESCALATION_ELIGIBLE:
            self._audit(capability, "host_root", reason, approved=False,
                        denial="not_escalation_eligible")
            logger.warning(
                "AURAPrivilege: %r is not in host escalation allowlist",
                capability
            )
            return False

        # Step 3: bridge must support the capability
        if not self._bridge_allows(capability):
            self._audit(capability, "host_root", reason, approved=False,
                        denial="bridge_refused")
            logger.warning(
                "AURAPrivilege: bridge does not support %r — "
                "refusing (cannot escalate beyond host limits)", capability
            )
            return False

        # Step 4: route through COL for user warning + confirmation
        if self._col is None:
            self._audit(capability, "host_root", reason, approved=False,
                        denial="no_col_available")
            logger.warning(
                "AURAPrivilege: no COL configured — host escalation denied"
            )
            return False

        result = self._col.request_override(
            action=capability,
            reason=f"[AURA host escalation] {reason}",
            confirm=confirm,
            requestor="AURA",
        )

        # Step 5: if approved, grant via KernelAPI + record
        if result.approved:
            self._host_escalations.append({
                "capability": capability,
                "reason":     reason,
                "ts":         time.time(),
            })
            if self._api is not None:
                try:
                    self._api.grant_capability(capability)
                except Exception as exc:
                    logger.error(
                        "AURAPrivilege: grant_capability(%r) failed: %s",
                        capability, exc
                    )
            self._audit(capability, "host_root", reason,
                        approved=True, executed=True)
        else:
            self._audit(capability, "host_root", reason, approved=False,
                        denial=result.denial_reason or "user_declined")

        return result.approved

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        return {
            "actor":             "AURA",
            "virtual_root":      True,
            "virtual_caps_count": len(VIRTUAL_ROOT_CAPS),
            "host_escalations":  list(self._host_escalations),
            "escalation_eligible": sorted(HOST_ESCALATION_ELIGIBLE),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _bridge_allows(self, capability: str) -> bool:
        """Ask the active bridge if the capability is available on this host."""
        try:
            from bridge import get_bridge
            bridge = get_bridge()
            # Capability strings use dot-notation; bridge uses underscore
            bridge_cap = capability.replace(".", "_")
            return bridge.has_capability(bridge_cap)
        except Exception:
            return False

    def _audit(
        self,
        capability: str,
        privilege_tier: str,
        description: str,
        approved: bool = True,
        executed: bool = False,
        denial: str = "",
    ) -> None:
        """Write a structured audit log entry for every AURA action."""
        entry = {
            "ts":         time.time(),
            "actor":      "AURA",
            "privilege":  privilege_tier,
            "capability": capability,
            "desc":       description,
            "approved":   approved,
            "executed":   executed,
            "denial":     denial,
        }
        level = "INFO" if approved else "WARNING"
        logger.log(
            logging.INFO if approved else logging.WARNING,
            "AURA action: actor=AURA privilege=%s cap=%s approved=%s",
            privilege_tier, capability, approved,
        )
        # Write to LoggingService if available
        if self._log_svc is not None:
            try:
                self._log_svc.write(
                    msg=(f"actor=AURA privilege={privilege_tier} "
                         f"cap={capability} approved={approved}"),
                    level=level,
                    source="aura_privilege",
                    event="AURA_ACTION",
                    data=entry,
                )
            except Exception:
                pass
        # Publish event for audit trail
        if self._bus is not None:
            try:
                from kernel.event_bus import Event, Priority
                self._bus.publish(Event(
                    "AURA_ACTION",
                    payload=entry,
                    priority=Priority.NORMAL,
                    source="aura_privilege",
                ))
            except Exception:
                pass
