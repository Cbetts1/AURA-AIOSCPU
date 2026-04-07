"""
Tests — System Validation Tool
================================
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tools.validate_system import (
    _check, _check_warn,
    chk_python_version, chk_imports, chk_config,
    chk_device_profile, chk_event_bus, chk_scheduler,
    chk_storage, chk_hal, chk_aura, chk_shell,
    chk_network_service, chk_package_manager,
    chk_build_service, chk_rootfs, chk_tests,
    run_validation, CheckResult,
    _PASS, _FAIL, _WARN,
)


class TestCheckHelpers:

    def test_check_pass_on_success(self):
        r = _check("test", lambda: "OK")
        assert r.status == _PASS
        assert r.detail == "OK"

    def test_check_fail_on_exception(self):
        r = _check("test", lambda: 1 / 0)
        assert r.status == _FAIL
        assert "zero" in r.detail.lower() or "division" in r.detail.lower()

    def test_check_warn_downgrades_fail(self):
        r = _check_warn("test", lambda: 1 / 0)
        assert r.status == _WARN

    def test_check_result_to_dict(self):
        r = CheckResult("my-check", _PASS, "details here")
        d = r.to_dict()
        assert d["name"]   == "my-check"
        assert d["status"] == _PASS
        assert d["detail"] == "details here"


class TestIndividualChecks:

    def test_python_version(self):
        r = _check("py", chk_python_version)
        assert r.status == _PASS
        assert "Python" in r.detail

    def test_imports(self):
        r = _check("imports", chk_imports)
        assert r.status == _PASS

    def test_config(self):
        r = _check("config", chk_config)
        assert r.status == _PASS

    def test_device_profile(self):
        r = _check("device", chk_device_profile)
        assert r.status == _PASS

    def test_event_bus(self):
        r = _check("bus", chk_event_bus)
        assert r.status == _PASS

    def test_scheduler(self):
        r = _check("sched", chk_scheduler)
        assert r.status == _PASS

    def test_storage(self):
        r = _check("storage", chk_storage)
        assert r.status == _PASS

    def test_hal(self):
        r = _check("hal", chk_hal)
        assert r.status == _PASS

    def test_aura(self):
        r = _check("aura", chk_aura)
        assert r.status == _PASS

    def test_shell(self):
        r = _check("shell", chk_shell)
        assert r.status == _PASS

    def test_network_service(self):
        r = _check_warn("net", chk_network_service)
        assert r.status in (_PASS, _WARN)

    def test_package_manager(self):
        r = _check("pkg", chk_package_manager)
        assert r.status == _PASS

    def test_build_service(self):
        r = _check("build", chk_build_service)
        assert r.status == _PASS

    def test_rootfs_check(self):
        r = _check("rootfs", chk_rootfs)
        assert r.status == _PASS

    def test_tests_check(self):
        r = _check("tests", chk_tests)
        assert r.status == _PASS


class TestRunValidation:

    def test_returns_int(self):
        code = run_validation()
        assert isinstance(code, int)

    def test_json_mode_does_not_raise(self, capsys):
        run_validation(as_json=True)
        out = capsys.readouterr().out
        import json
        data = json.loads(out)
        assert "passed" in data
        assert "checks" in data

    def test_all_core_checks_pass(self):
        code = run_validation(strict=False)
        assert code == 0
