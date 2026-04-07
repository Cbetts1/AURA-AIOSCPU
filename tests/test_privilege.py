"""Unit tests: AURA Privilege Model"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from kernel.privilege import (
    AURAPrivilege, AURAPrivilegeError,
    VIRTUAL_ROOT_CAPS, HOST_ESCALATION_ELIGIBLE, PERMANENTLY_FORBIDDEN,
)


class TestVirtualRootCaps:
    def test_virtual_root_caps_not_empty(self):
        assert len(VIRTUAL_ROOT_CAPS) > 0

    def test_service_caps_present(self):
        assert "service.start" in VIRTUAL_ROOT_CAPS
        assert "service.stop" in VIRTUAL_ROOT_CAPS

    def test_log_caps_present(self):
        assert "log.read" in VIRTUAL_ROOT_CAPS
        assert "log.write" in VIRTUAL_ROOT_CAPS

    def test_model_caps_present(self):
        assert "model.load" in VIRTUAL_ROOT_CAPS

    def test_permanently_forbidden_not_in_virtual_root(self):
        for cap in PERMANENTLY_FORBIDDEN:
            assert cap not in VIRTUAL_ROOT_CAPS


class TestAURAPrivilege:
    def test_instantiable(self):
        priv = AURAPrivilege()
        assert priv is not None

    def test_always_virtual_root(self):
        priv = AURAPrivilege()
        assert priv.is_virtual_root()

    def test_check_virtual_service_start(self):
        priv = AURAPrivilege()
        assert priv.check_virtual("service.start")

    def test_check_virtual_unknown_false(self):
        priv = AURAPrivilege()
        assert not priv.check_virtual("host.wipe_device")

    def test_assert_virtual_raises_on_unknown(self):
        priv = AURAPrivilege()
        with pytest.raises(AURAPrivilegeError):
            priv.assert_virtual("host.kernel_patch")

    def test_execute_virtual_root_success(self):
        priv = AURAPrivilege()
        result = priv.execute_as_virtual_root(
            "service.start",
            lambda: 42,
            "unit test"
        )
        assert result == 42

    def test_execute_virtual_root_invalid_cap_raises(self):
        priv = AURAPrivilege()
        with pytest.raises(AURAPrivilegeError):
            priv.execute_as_virtual_root(
                "host.wipe_device",
                lambda: None,
                "should fail"
            )

    def test_host_escalation_permanently_forbidden(self):
        priv = AURAPrivilege()
        approved = priv.request_host_escalation(
            "host.kernel_patch", reason="test", confirm=True
        )
        assert not approved

    def test_host_escalation_no_col_denies(self):
        priv = AURAPrivilege()  # no COL
        approved = priv.request_host_escalation(
            "net.listen", reason="test", confirm=True
        )
        assert not approved

    def test_summary_returns_dict(self):
        priv = AURAPrivilege()
        s = priv.summary()
        assert "actor" in s
        assert s["actor"] == "AURA"
        assert "virtual_root" in s
        assert s["virtual_root"] is True
