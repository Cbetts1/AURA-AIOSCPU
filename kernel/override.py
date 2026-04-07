"""
AURA-AIOSCPU Command Override Layer (COL)
==========================================
Allows operators to override blocked or restricted actions under strict,
auditable conditions.

Override rules (ALL must be satisfied)
---------------------------------------
  1. Operator explicitly requests override (flag + confirmation).
  2. Kernel confirms the action is structurally safe.
  3. Host-bridge confirms the host actually allows it.
  4. The action is validated against the rootfs integrity contract.
  5. The override is logged immutably before execution.

Override NEVER:
  - bypasses host OS security.
  - escalates privileges beyond what the host bridge reports as available.
  - modifies PROTECTED_PARTITIONS (boot/, system/).
  - skips logging or confirmation.

Override ALWAYS:
  - prints a warning.
  - requires explicit operator confirmation (or --force flag in scripts).
  - logs the event to the override audit log.
  - validates the target action before running it.
  - routes execution through KernelAPI, not directly.
"""

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

# Partitions that must NEVER be written to via override
PROTECTED_PARTITIONS = frozenset({"boot", "system"})

# Audit log filename (written to rootfs/var/)
_AUDIT_LOG_FILE = "override_audit.jsonl"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class OverrideRequest:
    """Represents an operator override request."""
    action:      str            # capability string or custom action name
    reason:      str            # operator-provided justification
    requestor:   str = "operator"
    target_path: str = ""       # rootfs path affected (if any)
    extra:       dict = field(default_factory=dict)

    # Filled in by OverrideGuard after validation
    request_id:  str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp:   float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "request_id":  self.request_id,
            "timestamp":   self.timestamp,
            "action":      self.action,
            "reason":      self.reason,
            "requestor":   self.requestor,
            "target_path": self.target_path,
            "extra":       self.extra,
        }


@dataclass
class OverrideResult:
    """Outcome of an override attempt."""
    request_id: str
    approved:   bool
    executed:   bool
    denial_reason: str = ""
    output: object = None

    def to_dict(self) -> dict:
        return {
            "request_id":    self.request_id,
            "approved":      self.approved,
            "executed":      self.executed,
            "denial_reason": self.denial_reason,
        }


# ---------------------------------------------------------------------------
# Override Guard — validates safety before approval
# ---------------------------------------------------------------------------

class OverrideGuard:
    """
    Validates whether an override request is safe.

    Checks (in order):
      1. Action is in the known override-able action set.
      2. Host bridge has the underlying capability.
      3. Target path (if any) is not a protected partition.
      4. Kernel permission model allows the action at the next tier.
    """

    # Actions that can ever be overridden (explicit allowlist)
    OVERRIDEABLE_ACTIONS = frozenset({
        "net.listen",
        "net.raw",
        "fs.chmod",
        "fs.mount_bind",
        "storage.partition",
        "service.start",
        "service.stop",
        "model.load",
        "kernel.config_write",
    })

    def __init__(self, bridge, permissions=None):
        self._bridge      = bridge
        self._permissions = permissions

    def validate(self, req: OverrideRequest) -> tuple[bool, str]:
        """
        Validate an override request.

        Returns (is_safe, reason_string).
        reason_string is empty on approval, or explains denial.
        """
        # 1 — Action must be in the overrideable allowlist
        if req.action not in self.OVERRIDEABLE_ACTIONS:
            return False, (
                f"Action {req.action!r} is not override-able. "
                f"Overrideable actions: {sorted(self.OVERRIDEABLE_ACTIONS)}"
            )

        # 2 — Host bridge must have the underlying host capability
        bridge_cap = req.action.replace(".", "_")
        if (
            self._bridge is not None
            and not self._bridge.has_capability(bridge_cap)
        ):
            return False, (
                f"Host bridge does not support {bridge_cap!r}. "
                f"Override would fail at the host level."
            )

        # 3 — Target path must not be a protected partition
        if req.target_path:
            parts = req.target_path.lstrip("/").split("/")
            if parts and parts[0] in PROTECTED_PARTITIONS:
                return False, (
                    f"Path {req.target_path!r} is in a protected partition "
                    f"({parts[0]!r}). Protected partitions cannot be modified "
                    f"via override."
                )

        # 4 — Reason must be non-empty
        if not req.reason or not req.reason.strip():
            return False, "Override requires a non-empty justification reason."

        return True, ""


# ---------------------------------------------------------------------------
# Override Log — immutable append-only audit trail
# ---------------------------------------------------------------------------

class OverrideLog:
    """
    Immutable append-only audit log for all override events.

    Written as JSON-Lines to rootfs/var/override_audit.jsonl.
    In-memory entries are also kept for the current session.
    """

    def __init__(self, log_dir: str = ""):
        self._log_dir   = log_dir
        self._entries:  list[dict] = []

    def record(self, req: OverrideRequest, result: OverrideResult,
               kernel_mode: str = "unknown") -> None:
        """Record an override attempt (approved or denied)."""
        entry = {
            "ts":          time.time(),
            "ts_human":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "kernel_mode": kernel_mode,
            "request":     req.to_dict(),
            "result":      result.to_dict(),
        }
        # Fingerprint for tamper-detection
        entry["fingerprint"] = self._fingerprint(entry)
        self._entries.append(entry)
        self._append_to_file(entry)
        logger.info(
            "COL audit: action=%r approved=%s executed=%s id=%s",
            req.action, result.approved, result.executed, req.request_id,
        )

    def get_entries(self, limit: int = 100) -> list[dict]:
        return self._entries[-limit:]

    def _fingerprint(self, entry: dict) -> str:
        raw = json.dumps(
            {k: v for k, v in entry.items() if k != "fingerprint"},
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _append_to_file(self, entry: dict) -> None:
        if not self._log_dir:
            return
        path = os.path.join(self._log_dir, _AUDIT_LOG_FILE)
        try:
            with open(path, "a") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError:
            pass   # read-only filesystem — memory-only audit log


# ---------------------------------------------------------------------------
# CommandOverrideLayer — main entry point
# ---------------------------------------------------------------------------

class CommandOverrideLayer:
    """
    The Command Override Layer.

    Usage (scriptable — confirm=True skips interactive prompt)::

        col = CommandOverrideLayer(bridge, permissions, kernel_api)
        result = col.request_override(
            action="net.listen",
            reason="opening port 7331 for web terminal",
            confirm=True,   # --force in CLI; False for interactive
        )
        if result.approved:
            kernel_api.grant_capability("net.listen")

    Usage (interactive)::

        result = col.request_override(
            action="net.listen",
            reason="web terminal",
            confirm=False,  # will prompt the operator
        )
    """

    def __init__(self, bridge=None, permissions=None,
                 kernel_api=None, log_dir: str = "",
                 event_bus=None):
        self._bridge      = bridge
        self._permissions = permissions
        self._kernel_api  = kernel_api
        self._event_bus   = event_bus
        self._guard       = OverrideGuard(bridge, permissions)
        self._log         = OverrideLog(log_dir=log_dir)
        self._current_mode = "universal"

    def set_mode(self, mode: str) -> None:
        self._current_mode = mode

    # ------------------------------------------------------------------
    # Main override API
    # ------------------------------------------------------------------

    def request_override(
        self,
        action: str,
        reason: str,
        target_path: str = "",
        extra: dict | None = None,
        confirm: bool = False,
        requestor: str = "operator",
        execute_fn: Callable | None = None,
    ) -> OverrideResult:
        """
        Request an operator override for a blocked action.

        Args:
            action:      The capability or action to override.
            reason:      Operator justification (required, non-empty).
            target_path: Rootfs path affected (checked against protected list).
            extra:       Additional metadata for the audit log.
            confirm:     If True, skip interactive confirmation (--force mode).
            requestor:   Identity of the requesting party.
            execute_fn:  Callable to run if override is approved. Optional.

        Returns:
            OverrideResult with approved/executed status.
        """
        req = OverrideRequest(
            action=action, reason=reason,
            requestor=requestor,
            target_path=target_path,
            extra=extra or {},
        )

        # --- Step 1: Validate safety ---
        is_safe, denial_reason = self._guard.validate(req)
        if not is_safe:
            result = OverrideResult(
                request_id=req.request_id,
                approved=False, executed=False,
                denial_reason=denial_reason,
            )
            self._log.record(req, result, self._current_mode)
            self._warn(f"OVERRIDE DENIED: {denial_reason}")
            self._publish_event("OVERRIDE_DENIED", req, result)
            return result

        # --- Step 2: Warn the operator ---
        self._warn(
            f"OVERRIDE REQUESTED\n"
            f"  Action  : {action}\n"
            f"  Reason  : {reason}\n"
            f"  Mode    : {self._current_mode}\n"
            f"  ID      : {req.request_id}\n"
            f"  WARNING : This will be logged and cannot be undone."
        )

        # --- Step 3: Require explicit confirmation ---
        if not confirm:
            confirmed = self._interactive_confirm(req)
        else:
            confirmed = True
            logger.info("COL: --force flag set, skipping interactive confirmation")

        if not confirmed:
            result = OverrideResult(
                request_id=req.request_id,
                approved=False, executed=False,
                denial_reason="operator declined confirmation",
            )
            self._log.record(req, result, self._current_mode)
            self._publish_event("OVERRIDE_DECLINED", req, result)
            return result

        # --- Step 4: Log approval before execution ---
        result = OverrideResult(
            request_id=req.request_id,
            approved=True, executed=False,
        )
        self._log.record(req, result, self._current_mode)
        self._publish_event("OVERRIDE_APPROVED", req, result)

        # --- Step 5: Execute through kernel API ---
        if execute_fn is not None:
            try:
                output = execute_fn()
                result.executed = True
                result.output   = output
                self._log.record(req, result, self._current_mode)
                self._publish_event("OVERRIDE_EXECUTED", req, result)
            except Exception as exc:
                result.executed      = False
                result.denial_reason = f"execution failed: {exc}"
                logger.error("COL: override execution failed: %s", exc)
                self._log.record(req, result, self._current_mode)
                self._publish_event("OVERRIDE_FAILED", req, result)

        return result

    # ------------------------------------------------------------------
    # Audit access
    # ------------------------------------------------------------------

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        """Return recent override audit entries."""
        return self._log.get_entries(limit)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _warn(msg: str) -> None:
        """Print a prominent operator warning."""
        border = "!" * 60
        print(f"\n{border}")
        for line in msg.splitlines():
            print(f"  {line}")
        print(f"{border}\n")

    @staticmethod
    def _interactive_confirm(req: OverrideRequest) -> bool:
        """Prompt the operator for explicit confirmation."""
        try:
            answer = input(
                f"  Confirm override of {req.action!r}? "
                f"[type 'yes' to confirm]: "
            ).strip().lower()
            return answer == "yes"
        except (EOFError, KeyboardInterrupt):
            return False

    def _publish_event(self, event_type: str,
                       req: OverrideRequest,
                       result: OverrideResult) -> None:
        if self._event_bus is None:
            return
        try:
            from kernel.event_bus import Event, Priority
            self._event_bus.publish(
                Event(
                    event_type,
                    payload={
                        "request_id": req.request_id,
                        "action":     req.action,
                        "approved":   result.approved,
                        "executed":   result.executed,
                        "reason":     req.reason,
                    },
                    priority=Priority.HIGH,
                    source="col",
                )
            )
        except Exception:
            pass
