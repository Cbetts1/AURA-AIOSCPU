"""Unit tests: AURA Conversation Memory"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from aura.memory import ConversationMemory


class TestConversationMemory:
    def test_empty_on_init(self):
        mem = ConversationMemory()
        assert mem.get_turns() == []

    def test_add_single_turn(self):
        mem = ConversationMemory()
        mem.add("user", "Hello")
        turns = mem.get_turns()
        assert len(turns) == 1
        assert turns[0].role == "user"
        assert turns[0].content == "Hello"

    def test_rolling_window_enforced(self):
        mem = ConversationMemory(max_turns=3)
        for i in range(5):
            mem.add("user", f"msg {i}")
        turns = mem.get_turns()
        assert len(turns) <= 3

    def test_format_for_prompt(self):
        mem = ConversationMemory()
        mem.add("user", "Hello")
        mem.add("aura", "Hi there")
        prompt = mem.format_for_prompt()
        assert isinstance(prompt, str)
        assert "Hello" in prompt

    def test_clear(self):
        mem = ConversationMemory()
        mem.add("user", "Hello")
        mem.clear()
        assert mem.get_turns() == []

    def test_multiple_roles(self):
        mem = ConversationMemory()
        mem.add("user", "Question")
        mem.add("aura", "Answer")
        mem.add("system", "Context")
        turns = mem.get_turns()
        roles = [t.role for t in turns]
        assert "user" in roles
        assert "aura" in roles
