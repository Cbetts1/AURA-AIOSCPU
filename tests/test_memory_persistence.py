"""Tests for AURA conversation memory persistence."""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aura.memory import ConversationMemory, Turn


class TestConversationMemoryPersistence:

    def test_save_creates_file(self, tmp_path):
        mem = ConversationMemory(max_turns=10)
        mem.add_user("hello")
        mem.add_aura("hi there")
        path = str(tmp_path / "memory.json")
        assert mem.save(path) is True
        assert os.path.isfile(path)

    def test_save_creates_parent_dir(self, tmp_path):
        mem = ConversationMemory()
        mem.add_user("test")
        path = str(tmp_path / "sub" / "dir" / "memory.json")
        assert mem.save(path) is True
        assert os.path.isfile(path)

    def test_saved_file_is_valid_json(self, tmp_path):
        mem = ConversationMemory()
        mem.add_user("hi")
        path = str(tmp_path / "mem.json")
        mem.save(path)
        with open(path) as fh:
            data = json.load(fh)
        assert "turns" in data
        assert "version" in data
        assert "saved_at" in data

    def test_load_returns_turn_count(self, tmp_path):
        mem1 = ConversationMemory()
        mem1.add_user("first")
        mem1.add_aura("response 1")
        mem1.add_user("second")
        path = str(tmp_path / "m.json")
        mem1.save(path)

        mem2 = ConversationMemory()
        n = mem2.load(path)
        assert n == 3

    def test_load_restores_content(self, tmp_path):
        mem1 = ConversationMemory()
        mem1.add_user("restored content")
        path = str(tmp_path / "m.json")
        mem1.save(path)

        mem2 = ConversationMemory()
        mem2.load(path)
        assert mem2.last_user_input() == "restored content"

    def test_load_nonexistent_returns_zero(self, tmp_path):
        mem = ConversationMemory()
        n = mem.load(str(tmp_path / "does_not_exist.json"))
        assert n == 0

    def test_load_clears_existing_turns(self, tmp_path):
        mem_orig = ConversationMemory()
        mem_orig.add_user("saved turn")
        path = str(tmp_path / "m.json")
        mem_orig.save(path)

        mem = ConversationMemory()
        mem.add_user("pre-existing turn")
        mem.add_aura("another turn")
        assert mem.turn_count() == 2
        mem.load(path)
        assert mem.turn_count() == 1

    def test_roundtrip_preserves_roles(self, tmp_path):
        mem1 = ConversationMemory()
        mem1.add_user("user msg")
        mem1.add_aura("aura msg")
        mem1.add_system("system msg")
        path = str(tmp_path / "rt.json")
        mem1.save(path)

        mem2 = ConversationMemory()
        mem2.load(path)
        turns = mem2.get_turns()
        roles = [t.role for t in turns]
        assert roles == ["user", "aura", "system"]

    def test_disk_turn_cap_applied_on_save(self, tmp_path):
        from aura.memory import _DISK_TURN_CAP
        mem = ConversationMemory(max_turns=_DISK_TURN_CAP + 50)
        for i in range(_DISK_TURN_CAP + 10):
            mem.add_user(f"msg {i}")
        path = str(tmp_path / "cap.json")
        mem.save(path)
        with open(path) as fh:
            data = json.load(fh)
        assert len(data["turns"]) <= _DISK_TURN_CAP

    def test_save_returns_false_on_unwritable_path(self):
        mem = ConversationMemory()
        mem.add_user("x")
        # Attempt to write to a path that can't be created
        result = mem.save("/proc/aura_cannot_write/memory.json")
        assert result is False
