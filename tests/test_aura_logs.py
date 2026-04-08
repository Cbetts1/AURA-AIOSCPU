"""Tests — tools/aura_logs.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tools.aura_logs import find_log_files, tail_file, main


class TestFindLogFiles:

    def test_returns_list(self):
        files = find_log_files()
        assert isinstance(files, list)

    def test_returns_sorted(self):
        files = find_log_files()
        assert files == sorted(files)

    def test_all_entries_are_strings(self):
        files = find_log_files()
        for f in files:
            assert isinstance(f, str)

    def test_all_entries_end_with_log(self):
        files = find_log_files()
        for f in files:
            assert f.endswith(".log"), f"Unexpected file: {f}"

    def test_custom_logs_dirs(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "system.log").write_text("line1\nline2\n")
        (log_dir / "error.log").write_text("error\n")
        import tools.aura_logs as mod
        monkeypatch.setattr(mod, "_LOGS_DIRS", [str(log_dir)])
        files = find_log_files()
        assert len(files) == 2
        assert all(f.endswith(".log") for f in files)


class TestTailFile:

    def test_prints_last_n_lines(self, tmp_path, capsys):
        log = tmp_path / "test.log"
        log.write_text("\n".join(f"line{i}" for i in range(100)))
        tail_file(str(log), lines=10, follow=False)
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if l]
        assert len(lines) == 10
        assert "line99" in out

    def test_prints_all_lines_when_fewer_than_n(self, tmp_path, capsys):
        log = tmp_path / "short.log"
        log.write_text("a\nb\nc\n")
        tail_file(str(log), lines=50, follow=False)
        out = capsys.readouterr().out
        assert "a" in out
        assert "b" in out
        assert "c" in out

    def test_empty_file(self, tmp_path, capsys):
        log = tmp_path / "empty.log"
        log.write_text("")
        tail_file(str(log), lines=10, follow=False)
        out = capsys.readouterr().out
        assert out == ""

    def test_handles_unicode(self, tmp_path, capsys):
        log = tmp_path / "unicode.log"
        log.write_text("日本語\nEnglish\n", encoding="utf-8")
        tail_file(str(log), lines=10, follow=False)
        out = capsys.readouterr().out
        assert "English" in out


class TestMain:

    def test_main_no_log_files_message(self, monkeypatch, capsys):
        import tools.aura_logs as mod
        monkeypatch.setattr(mod, "_LOGS_DIRS", ["/nonexistent/path"])
        monkeypatch.setattr(sys, "argv", ["aura_logs"])
        main()
        out = capsys.readouterr().out
        assert "No log files found" in out

    def test_main_list_flag_no_files(self, monkeypatch, capsys):
        import tools.aura_logs as mod
        monkeypatch.setattr(mod, "_LOGS_DIRS", ["/nonexistent/path"])
        monkeypatch.setattr(sys, "argv", ["aura_logs", "--list"])
        main()
        out = capsys.readouterr().out
        assert "No log files found" in out

    def test_main_list_flag_shows_files(self, tmp_path, monkeypatch, capsys):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "app.log").write_text("log content\n")
        import tools.aura_logs as mod
        monkeypatch.setattr(mod, "_LOGS_DIRS", [str(log_dir)])
        monkeypatch.setattr(sys, "argv", ["aura_logs", "--list"])
        main()
        out = capsys.readouterr().out
        assert "app.log" in out
        assert "bytes" in out

    def test_main_tail_specific_file(self, tmp_path, monkeypatch, capsys):
        log = tmp_path / "test.log"
        log.write_text("line1\nline2\nline3\n")
        monkeypatch.setattr(sys, "argv", ["aura_logs", str(log)])
        main()
        out = capsys.readouterr().out
        assert "line1" in out or "line2" in out or "line3" in out

    def test_main_missing_specific_file_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["aura_logs", "/nonexistent/file.log"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_main_tail_uses_most_recent(self, tmp_path, monkeypatch, capsys):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "recent.log").write_text("recent content\n")
        import tools.aura_logs as mod
        monkeypatch.setattr(mod, "_LOGS_DIRS", [str(log_dir)])
        monkeypatch.setattr(sys, "argv", ["aura_logs", "--tail", "5"])
        main()
        out = capsys.readouterr().out
        assert "recent content" in out
