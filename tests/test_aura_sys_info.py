"""Tests — tools/aura_sys_info.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tools.aura_sys_info import _check_import, get_sys_info, main


class TestCheckImport:

    def test_existing_module_returns_true(self):
        assert _check_import("json") is True

    def test_existing_module_sqlite3_returns_true(self):
        assert _check_import("sqlite3") is True

    def test_existing_module_threading_returns_true(self):
        assert _check_import("threading") is True

    def test_nonexistent_module_returns_false(self):
        assert _check_import("_definitely_nonexistent_module_xyz_123") is False

    def test_another_nonexistent_module_returns_false(self):
        assert _check_import("no_such_package_ever") is False


class TestGetSysInfo:

    def test_returns_dict(self):
        info = get_sys_info()
        assert isinstance(info, dict)

    def test_has_timestamp(self):
        info = get_sys_info()
        assert "timestamp" in info
        assert isinstance(info["timestamp"], str)

    def test_has_python_impl(self):
        info = get_sys_info()
        assert "python_impl" in info
        assert info["python_impl"] in ("CPython", "PyPy", "IronPython", "Jython")

    def test_has_python_build(self):
        info = get_sys_info()
        assert "python_build" in info
        assert isinstance(info["python_build"], str)

    def test_has_compatibility_checks(self):
        info = get_sys_info()
        assert "compatibility_checks" in info
        assert isinstance(info["compatibility_checks"], dict)

    def test_has_aura_ready(self):
        info = get_sys_info()
        assert "aura_ready" in info

    def test_compatibility_has_python_check(self):
        info = get_sys_info()
        checks = info["compatibility_checks"]
        assert "python_3_10_plus" in checks

    def test_python_check_is_true(self):
        info = get_sys_info()
        assert info["compatibility_checks"]["python_3_10_plus"] is True

    def test_compatibility_has_sqlite3(self):
        info = get_sys_info()
        checks = info["compatibility_checks"]
        assert "sqlite3" in checks
        assert checks["sqlite3"] is True

    def test_compatibility_has_threading(self):
        info = get_sys_info()
        checks = info["compatibility_checks"]
        assert "threading" in checks
        assert checks["threading"] is True

    def test_compatibility_has_json(self):
        info = get_sys_info()
        checks = info["compatibility_checks"]
        assert "json" in checks
        assert checks["json"] is True

    def test_compatibility_has_pathlib(self):
        info = get_sys_info()
        checks = info["compatibility_checks"]
        assert "pathlib" in checks
        assert checks["pathlib"] is True

    def test_aura_ready_is_true_on_test_runner(self):
        info = get_sys_info()
        assert info["aura_ready"] is True

    def test_has_is_64bit_field(self):
        info = get_sys_info()
        assert "is_64bit" in info

    def test_has_is_termux_field(self):
        info = get_sys_info()
        assert "is_termux" in info


class TestMain:

    def test_main_does_not_raise(self, capsys):
        main()
        out = capsys.readouterr().out
        assert len(out) > 0

    def test_main_prints_header(self, capsys):
        main()
        out = capsys.readouterr().out
        assert "AURA-AIOSCPU" in out

    def test_main_prints_compatibility_checks(self, capsys):
        main()
        out = capsys.readouterr().out
        assert "Compatibility checks" in out

    def test_main_prints_compatible_on_test_runner(self, capsys):
        main()
        out = capsys.readouterr().out
        assert "compatible" in out.lower()

    def test_main_prints_separator_lines(self, capsys):
        main()
        out = capsys.readouterr().out
        assert "=" * 10 in out
