"""
AURA-AIOSCPU Mirror Mode Enforcer
===================================
Enforces the Mirror / Universal Mode privilege rule (Contract 25).

Rule summary
------------
  Inside AURA-AIOSCPU:
    AURA is always virtual root. All internal operations are allowed.

  At the host boundary:
    Every operation MUST go through HostBridge → capability check.
    If blocked: clear "Host OS denied" message + optional legal-alternative search.

  Legal bypass (user-initiated only):
    When a user asks AURA to find an alternative, MirrorModeEnforcer
    searches for legal host capabilities that accomplish the same goal.
    It NEVER: exploits, escalates without consent, breaks law, damages device.
    It ONLY:  uses available bridge capabilities creatively.

Architecture
------------
  MirrorModeEnforcer
  ├── enforce()             — check an action against bridge
  ├── denied_message()      — format clear denial text
  └── find_legal_alternatives()  — suggest creative legal paths

  LegalAlternativeFinder
  ├── ALTERNATIVE_MAP       — known alternatives for common blocked actions
  └── find()                — return list of Alternative objects
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Denied action result
# ---------------------------------------------------------------------------

@dataclass
class HostDenial:
    """Returned by MirrorModeEnforcer when a host operation is blocked."""
    action:       str
    reason:       str
    host_type:    str = "unknown"
    alternatives: list = field(default_factory=list)

    def message(self) -> str:
        """Human-readable denial message for AURA/shell output."""
        lines = [
            f"Host OS denied: {self.action!r}",
            f"  Reason : {self.reason}",
            f"  Host   : {self.host_type}",
        ]
        if self.alternatives:
            lines.append("  Legal alternatives:")
            for alt in self.alternatives:
                lines.append(f"    • {alt.description}  [{alt.action}]")
        else:
            lines.append("  No legal alternatives found for this host.")
        return "\n".join(lines)

    def aura_response(self) -> str:
        """AURA-voiced response when blocked."""
        base = (
            f"Host OS denied this operation ({self.action!r}). "
            f"I can't do that from {self.host_type!r} without host permission."
        )
        if self.alternatives:
            alts = "; ".join(a.description for a in self.alternatives)
            return base + f" Legal alternatives available: {alts}."
        return base + " No legal alternatives found on this host."


@dataclass
class Alternative:
    """One legal alternative to a blocked action."""
    action:      str    # capability or approach name
    description: str    # human-readable explanation
    requires:    str = ""  # what the host must support


# ---------------------------------------------------------------------------
# Legal Alternative Finder
# ---------------------------------------------------------------------------

# Map: blocked_action → list of Alternative objects
_ALT_MAP: dict[str, list[Alternative]] = {
    "net.listen": [
        Alternative(
            "net.connect + reverse-tunnel",
            "Use an outbound reverse tunnel to a relay instead of listening",
            requires="net.connect",
        ),
        Alternative(
            "proc.spawn + socat",
            "Spawn socat to bridge stdio to a network port if available",
            requires="proc_spawn",
        ),
    ],
    "fs.mount_bind": [
        Alternative(
            "overlay in rootfs/overlay/",
            "Write changes to rootfs/overlay/ instead of mounting over system/",
            requires="fs.write",
        ),
        Alternative(
            "FUSE userspace mount",
            "Use fusepy or a FUSE library if available on this host",
            requires="proc_spawn",
        ),
    ],
    "fs.chmod": [
        Alternative(
            "copy-then-write",
            "Copy file to rootfs/user/ (writable) and work there instead",
            requires="fs.write",
        ),
    ],
    "net.raw": [
        Alternative(
            "net.connect socket",
            "Use standard TCP/UDP sockets (net.connect) as an alternative",
            requires="net.connect",
        ),
    ],
    "hal.project": [
        Alternative(
            "virtual device in rootfs/aura/",
            "Project a virtual device descriptor into rootfs/aura/ instead",
            requires="fs.write",
        ),
    ],
    "hal.teardown": [
        Alternative(
            "rootfs virtual device cleanup",
            "Remove the virtual device file from rootfs/aura/",
            requires="fs.write",
        ),
    ],
    "device.write": [
        Alternative(
            "virtual device in rootfs/aura/devices/",
            "Write device state to the virtual device registry inside rootfs",
            requires="fs.write",
        ),
    ],
}


class LegalAlternativeFinder:
    """
    Finds legal alternative approaches for blocked host operations.

    Uses only:
    - Available bridge capabilities
    - AURA's virtual filesystem (rootfs/overlay/, rootfs/user/)
    - Standard network primitives if available

    NEVER suggests exploits, privilege escalation, or illegal methods.
    """

    def find(self, blocked_action: str, bridge=None) -> list[Alternative]:
        """
        Return legal alternatives for a blocked action.

        Filters alternatives by whether the bridge actually has the
        required capability on this host.
        """
        candidates = _ALT_MAP.get(blocked_action, [])
        if not candidates:
            return []
        if bridge is None:
            return candidates
        # Filter to alternatives the bridge can actually support
        available = bridge.available_capabilities()
        filtered = []
        for alt in candidates:
            if not alt.requires or alt.requires in available:
                filtered.append(alt)
        return filtered


# ---------------------------------------------------------------------------
# Mirror Mode Enforcer
# ---------------------------------------------------------------------------

class MirrorModeEnforcer:
    """
    Enforces the Mirror/Universal Mode host-boundary rules.

    Usage::

        enforcer = MirrorModeEnforcer(bridge)
        denial = enforcer.enforce("net.listen")
        if denial:
            print(denial.aura_response())
        else:
            pass  # operation is allowed — proceed
    """

    def __init__(self, bridge=None):
        self._bridge   = bridge
        self._alt_finder = LegalAlternativeFinder()

    def attach_bridge(self, bridge) -> None:
        self._bridge = bridge

    # ------------------------------------------------------------------
    # Primary enforcement
    # ------------------------------------------------------------------

    def enforce(self, action: str,
                privilege_tier: str = "virtual_root") -> HostDenial | None:
        """
        Check whether an action is allowed at the host boundary.

        Internal actions (virtual_root tier) are always allowed — no check.
        Host actions are checked against the bridge capability set.

        Returns:
            None if the action is allowed.
            HostDenial if the host blocked it (caller must surface the denial).
        """
        # Virtual root operations — always allowed inside AURA-AIOSCPU
        if privilege_tier == "virtual_root":
            return None

        # Host boundary — must pass bridge capability check
        if self._bridge is None:
            return HostDenial(
                action=action,
                reason="no host bridge configured",
                host_type="unknown",
            )

        bridge_cap = action.replace(".", "_")
        if self._bridge.has_capability(bridge_cap):
            return None

        # Blocked — build denial with alternatives
        host_type  = self._bridge.get_sys_info().get("host", "unknown")
        alts       = self._alt_finder.find(action, self._bridge)

        denial = HostDenial(
            action=action,
            reason=(
                f"capability {bridge_cap!r} is not available on "
                f"this {host_type!r} host"
            ),
            host_type=host_type,
            alternatives=alts,
        )
        logger.warning(
            "MirrorModeEnforcer: host denied %r on %r — "
            "%d legal alternatives found",
            action, host_type, len(alts),
        )
        return denial

    # ------------------------------------------------------------------
    # Legal alternative search (user-initiated)
    # ------------------------------------------------------------------

    def find_legal_alternatives(self, action: str) -> list[Alternative]:
        """
        Return legal alternatives for a blocked action.

        Called when the user explicitly asks AURA to find another way.
        NEVER returns exploits or privilege escalation paths.
        """
        return self._alt_finder.find(action, self._bridge)

    def suggest_alternatives_text(self, action: str) -> str:
        """Return a human-readable list of legal alternatives."""
        alts = self.find_legal_alternatives(action)
        if not alts:
            return (
                f"No legal alternatives found for {action!r} on this host. "
                f"The host does not support the required capabilities."
            )
        lines = [f"Legal alternatives for {action!r}:"]
        for i, alt in enumerate(alts, 1):
            lines.append(f"  {i}. {alt.description}")
            if alt.requires:
                lines.append(f"     Requires: {alt.requires}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Denied message formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_denial(denial: HostDenial) -> str:
        """Format a HostDenial for AURA output."""
        return denial.aura_response()
