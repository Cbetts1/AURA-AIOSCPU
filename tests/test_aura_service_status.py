"""Tests — tools/aura_service_status.py"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tools.aura_service_status import _parse_unit, list_services, main


class TestParseUnit:

    def test_parses_key_value_pairs(self, tmp_path):
        unit_file = tmp_path / "test.service"
        unit_file.write_text("name=MyService\nautostart=true\n")
        result = _parse_unit(str(unit_file))
        assert result["name"] == "MyService"
        assert result["autostart"] == "true"

    def test_skips_blank_lines(self, tmp_path):
        unit_file = tmp_path / "test.service"
        unit_file.write_text("name=A\n\nentrypoint=services/a.py\n")
        result = _parse_unit(str(unit_file))
        assert len(result) == 2

    def test_skips_comment_lines(self, tmp_path):
        unit_file = tmp_path / "test.service"
        unit_file.write_text("# a comment\nname=B\n")
        result = _parse_unit(str(unit_file))
        assert "# a comment" not in result
        assert result["name"] == "B"

    def test_strips_whitespace_from_keys_and_values(self, tmp_path):
        unit_file = tmp_path / "test.service"
        unit_file.write_text("  name  =  WhiteSpaceService  \n")
        result = _parse_unit(str(unit_file))
        assert result["name"] == "WhiteSpaceService"

    def test_handles_empty_file(self, tmp_path):
        unit_file = tmp_path / "empty.service"
        unit_file.write_text("")
        result = _parse_unit(str(unit_file))
        assert result == {}

    def test_value_with_equals_sign(self, tmp_path):
        unit_file = tmp_path / "test.service"
        unit_file.write_text("description=a=b=c\n")
        result = _parse_unit(str(unit_file))
        assert result["description"] == "a=b=c"


class TestListServices:

    def test_returns_list(self):
        services = list_services()
        assert isinstance(services, list)

    def test_each_service_has_required_keys(self):
        services = list_services()
        for svc in services:
            assert "file" in svc
            assert "name" in svc
            assert "entrypoint" in svc
            assert "autostart" in svc
            assert "restart" in svc
            assert "exists" in svc

    def test_file_names_end_with_service(self):
        services = list_services()
        for svc in services:
            assert svc["file"].endswith(".service")

    def test_exists_is_bool(self):
        services = list_services()
        for svc in services:
            assert isinstance(svc["exists"], bool)

    def test_nonexistent_services_dir_returns_empty(self, monkeypatch):
        import tools.aura_service_status as mod
        original = mod._SERVICES_DIR
        try:
            mod._SERVICES_DIR = "/nonexistent/path/does/not/exist"
            result = list_services()
            assert result == []
        finally:
            mod._SERVICES_DIR = original


class TestMain:

    def test_main_human_output_does_not_raise(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["aura_service_status"])
        main()
        out = capsys.readouterr().out
        assert len(out) > 0

    def test_main_prints_header(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["aura_service_status"])
        main()
        out = capsys.readouterr().out
        assert "AURA-AIOSCPU" in out

    def test_main_json_flag_produces_valid_json(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["aura_service_status", "--json"])
        main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)

    def test_main_json_flag_has_expected_keys(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["aura_service_status", "--json"])
        main()
        out = capsys.readouterr().out
        data = json.loads(out)
        if data:
            assert "name" in data[0]
            assert "file" in data[0]

    def test_main_no_services_dir_does_not_crash(self, monkeypatch, capsys):
        import tools.aura_service_status as mod
        original = mod._SERVICES_DIR
        try:
            mod._SERVICES_DIR = "/nonexistent/path"
            monkeypatch.setattr(sys, "argv", ["aura_service_status"])
            main()
            out = capsys.readouterr().out
            assert "No .service files" in out
        finally:
            mod._SERVICES_DIR = original
