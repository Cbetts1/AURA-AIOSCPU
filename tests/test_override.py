"""Unit tests: Command Override Layer"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from kernel.override import (
    CommandOverrideLayer, OverrideRequest, OverrideResult,
    OverrideGuard, OverrideLog, PROTECTED_PARTITIONS,
)


class TestOverrideRequest:
    def test_instantiable(self):
        req = OverrideRequest(action="net.listen", reason="test")
        assert req.action == "net.listen"
        assert req.reason == "test"

    def test_request_id_generated(self):
        req = OverrideRequest(action="net.listen", reason="test")
        assert req.request_id
        assert len(req.request_id) > 0

    def test_to_dict(self):
        req = OverrideRequest(action="net.listen", reason="test")
        d = req.to_dict()
        assert d["action"] == "net.listen"
        assert d["reason"] == "test"


class TestOverrideGuard:
    def test_unknown_action_denied(self):
        guard = OverrideGuard(bridge=None)
        req = OverrideRequest(action="unknown.action.xyz", reason="test")
        ok, reason = guard.validate(req)
        assert not ok
        assert "not override-able" in reason

    def test_known_action_with_empty_reason_denied(self):
        guard = OverrideGuard(bridge=None)
        req = OverrideRequest(action="net.listen", reason="")
        ok, reason = guard.validate(req)
        assert not ok
        assert "justification" in reason

    def test_protected_partition_denied(self):
        guard = OverrideGuard(bridge=None)
        req = OverrideRequest(action="net.listen", reason="test",
                              target_path="/boot/grub.cfg")
        ok, reason = guard.validate(req)
        assert not ok
        assert "protected" in reason.lower()

    def test_valid_request_approved_when_no_bridge(self):
        guard = OverrideGuard(bridge=None)
        req = OverrideRequest(action="net.listen", reason="open web terminal port")
        ok, reason = guard.validate(req)
        # Without bridge, capability check is skipped → should pass
        assert ok


class TestOverrideLog:
    def test_empty_on_init(self):
        log = OverrideLog()
        assert log.get_entries() == []

    def test_record_adds_entry(self):
        log = OverrideLog()
        req = OverrideRequest(action="net.listen", reason="test")
        res = OverrideResult(request_id=req.request_id, approved=True, executed=True)
        log.record(req, res)
        assert len(log.get_entries()) == 1

    def test_entry_has_fingerprint(self):
        log = OverrideLog()
        req = OverrideRequest(action="net.listen", reason="test")
        res = OverrideResult(request_id=req.request_id, approved=True, executed=False)
        log.record(req, res)
        entry = log.get_entries()[0]
        assert "fingerprint" in entry

    def test_limit_parameter(self):
        log = OverrideLog()
        for i in range(10):
            req = OverrideRequest(action="net.listen", reason=f"test {i}")
            res = OverrideResult(request_id=req.request_id, approved=True, executed=False)
            log.record(req, res)
        assert len(log.get_entries(limit=5)) == 5


class TestCommandOverrideLayer:
    def test_instantiable(self):
        col = CommandOverrideLayer()
        assert col is not None

    def test_deny_forbidden_action(self):
        col = CommandOverrideLayer()
        result = col.request_override(
            action="host.kernel_patch",
            reason="test",
            confirm=True,
        )
        assert not result.approved

    def test_deny_unknown_action(self):
        col = CommandOverrideLayer()
        result = col.request_override(
            action="nonexistent.action.xyz",
            reason="test",
            confirm=True,
        )
        assert not result.approved

    def test_deny_empty_reason(self):
        col = CommandOverrideLayer()
        result = col.request_override(
            action="net.listen",
            reason="",
            confirm=True,
        )
        assert not result.approved

    def test_approved_with_execute_fn(self):
        col = CommandOverrideLayer()
        result = col.request_override(
            action="net.listen",
            reason="conformance test override",
            confirm=True,
            execute_fn=lambda: "executed",
        )
        # No bridge → guard skips bridge check → approved
        assert result.approved

    def test_get_audit_log_returns_list(self):
        col = CommandOverrideLayer()
        col.request_override(action="net.listen", reason="test", confirm=True)
        log = col.get_audit_log()
        assert isinstance(log, list)
