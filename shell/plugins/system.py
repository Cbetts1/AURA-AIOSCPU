"""
AURA-AIOSCPU System Command Plugin
=====================================
Built-in shell commands that expose kernel, service mesh,
privilege, and mirror-mode status.

Commands added
--------------
  uname         — OS identity string
  override      — request a COL override
  privilege     — show AURA privilege summary
  mirror        — show mirror mode and host denial info
  host          — host bridge info
  boot-log      — last boot lifecycle
  provenance    — build provenance
  col-log       — COL override audit log
  alternatives  — suggest legal alternatives for a blocked action
"""

import os
import sys

PLUGIN_NAME = "system"

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _cmd_uname(shell, args: list[str]) -> str:
    """Print OS identity."""
    try:
        if shell._kernel is not None:
            return shell._kernel.uname()
    except Exception:
        pass
    try:
        from bridge import get_bridge, detect_host_type
        bridge    = get_bridge()
        host_type = detect_host_type()
        info      = bridge.get_sys_info()
        return (
            f"AURA-AIOSCPU  host={host_type}  "
            f"arch={info.get('arch','?')}  "
            f"python={info.get('python','?')}"
        )
    except Exception as exc:
        return f"uname: {exc}"


def _cmd_override(shell, args: list[str]) -> str:
    """Request a Command Override Layer action."""
    if not args:
        return "Usage: override <action> [reason...] [--force]"
    force  = "--force" in args
    action = args[0]
    reason = " ".join(a for a in args[1:] if a != "--force") or "operator request"
    try:
        col = getattr(shell, "_col", None)
        if col is None:
            return "COL not available — kernel not attached."
        result = col.request_override(
            action=action, reason=reason, confirm=force
        )
        if result.approved:
            return f"Override approved: {action}  (id={result.request_id})"
        return f"Override denied: {result.denial_reason}"
    except Exception as exc:
        return f"override: {exc}"


def _cmd_privilege(shell, args: list[str]) -> str:
    """Show AURA privilege summary."""
    try:
        priv = getattr(shell, "_aura_privilege", None)
        if priv is None:
            return "Privilege layer not attached."
        s = priv.summary()
        lines = [
            "AURA Privilege Summary",
            f"  virtual_root      : {s['virtual_root']}",
            f"  virtual_caps      : {s['virtual_caps_count']}",
            f"  host_escalations  : {len(s['host_escalations'])}",
        ]
        for esc in s["host_escalations"]:
            lines.append(f"    • {esc['capability']}  ({esc['reason']})")
        return "\n".join(lines)
    except Exception as exc:
        return f"privilege: {exc}"


def _cmd_mirror(shell, args: list[str]) -> str:
    """Show mirror/host-boundary status."""
    try:
        from bridge import get_bridge, detect_host_type
        bridge    = get_bridge()
        host_type = detect_host_type()
        caps      = bridge.available_capabilities()
        info      = bridge.get_sys_info()
        lines = [
            "Mirror Mode Status",
            f"  Host type   : {host_type}",
            f"  Arch        : {info.get('arch','?')}",
            f"  Bridge      : {bridge.__class__.__name__}",
            f"  Caps        : {len(caps)}",
            "  Mode eligibility:",
            "    ✓ Universal Mode  (always available)",
        ]
        if "net_listen" in caps or "fs_chmod" in caps:
            lines.append("    ✓ Internal Mode")
        else:
            lines.append("    ⚠ Internal Mode  (limited caps)")
        if "hal_project" in caps:
            lines.append("    ✓ Hardware Mode")
        else:
            lines.append("    ✗ Hardware Mode  (hal.project unavailable)")
        return "\n".join(lines)
    except Exception as exc:
        return f"mirror: {exc}"


def _cmd_host(shell, args: list[str]) -> str:
    """Show host bridge capabilities."""
    try:
        from bridge import get_bridge, detect_host_type
        bridge    = get_bridge()
        host_type = detect_host_type()
        info      = bridge.get_sys_info()
        caps      = sorted(bridge.available_capabilities())
        lines = [
            f"Host Bridge  ({host_type}  {bridge.__class__.__name__})",
        ]
        for k, v in info.items():
            lines.append(f"  {k:<12}: {v}")
        lines.append(f"  capabilities ({len(caps)}):")
        for cap in caps:
            lines.append(f"    • {cap}")
        return "\n".join(lines)
    except Exception as exc:
        return f"host: {exc}"


def _cmd_boot_log(shell, args: list[str]) -> str:
    """Show last boot log."""
    import json, time as _time
    log_path = os.path.join(_REPO_ROOT, "rootfs", "var", "boot.log")
    if not os.path.isfile(log_path):
        return "No boot log found. Boot the OS first."
    try:
        with open(log_path) as fh:
            data = json.load(fh)
        lines = [f"Boot at: {_time.ctime(data.get('boot_ts', 0))}"]
        for e in data.get("entries", []):
            ts  = _time.strftime("%H:%M:%S", _time.localtime(e.get("ts", 0)))
            ok  = "OK  " if e.get("ok", True) else "FAIL"
            lines.append(
                f"  [{ts}] Stage {e.get('stage','?')}  {ok}  "
                f"{e.get('event','')}  {e.get('detail','')}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"boot-log: {exc}"


def _cmd_provenance(shell, args: list[str]) -> str:
    """Show build provenance."""
    try:
        sys.path.insert(0, _REPO_ROOT)
        from tools.manifest import get_provenance
        p = get_provenance()
        return (
            f"Build time : {p.get('build_time_human','unknown')}\n"
            f"Commit     : {p.get('commit','unknown')}\n"
            f"Files      : {p.get('file_count',0)}\n"
            f"Manifest   : {p.get('manifest_path','?')}"
        )
    except Exception as exc:
        return f"provenance: {exc}"


def _cmd_col_log(shell, args: list[str]) -> str:
    """Show COL override audit log."""
    import time as _time
    col = getattr(shell, "_col", None)
    if col is None:
        return "COL not available."
    entries = col.get_audit_log(limit=20)
    if not entries:
        return "No override events recorded."
    lines = ["COL Override Audit Log"]
    for e in entries:
        ts  = _time.strftime("%H:%M:%S", _time.localtime(e.get("ts", 0)))
        req = e.get("request", {})
        res = e.get("result", {})
        ok  = "APPROVED" if res.get("approved") else "DENIED"
        lines.append(
            f"  [{ts}] {ok}  {req.get('action','?')}  "
            f"by={req.get('requestor','?')}  "
            f"id={req.get('request_id','?')}"
        )
    return "\n".join(lines)


def _cmd_alternatives(shell, args: list[str]) -> str:
    """Find legal alternatives for a blocked host action."""
    if not args:
        return "Usage: alternatives <blocked-action>"
    action = args[0]
    try:
        mirror = getattr(shell, "_mirror", None)
        if mirror is None:
            from kernel.mirror import MirrorModeEnforcer
            from bridge import get_bridge
            mirror = MirrorModeEnforcer(get_bridge())
        return mirror.suggest_alternatives_text(action)
    except Exception as exc:
        return f"alternatives: {exc}"


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

COMMANDS = {
    "uname":        _cmd_uname,
    "override":     _cmd_override,
    "privilege":    _cmd_privilege,
    "mirror":       _cmd_mirror,
    "host":         _cmd_host,
    "boot-log":     _cmd_boot_log,
    "provenance":   _cmd_provenance,
    "col-log":      _cmd_col_log,
    "alternatives": _cmd_alternatives,
}

HELP = {
    "uname":        "Print OS identity string",
    "override":     "override <action> [reason] [--force]  — Request a COL override",
    "privilege":    "Show AURA privilege summary",
    "mirror":       "Show mirror mode and host-boundary status",
    "host":         "Show host bridge capabilities",
    "boot-log":     "Show last boot lifecycle",
    "provenance":   "Show build provenance (commit, time, files)",
    "col-log":      "Show COL override audit log",
    "alternatives": "alternatives <action>  — Find legal alternatives for a blocked action",
}
