"""
Tests — ContextBuilder
========================
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aura.context_builder import ContextBuilder


# ---------------------------------------------------------------------------
# Minimal fakes
# ---------------------------------------------------------------------------

class _FakeIntrospector:
    def __init__(self, snap=None):
        self._snap = snap or {
            "mode":            "universal",
            "tick":            10,
            "uptime_s":        120.5,
            "service_count":   3,
            "services":        {"net": "running", "storage": "running"},
            "network_status":  "online",
            "storage_status":  "running",
            "active_model":    "stub",
            "models_available": 1,
            "task_queue_depth": 0,
            "job_queue_depth":  0,
            "platform":        "Linux",
            "arch":            "x86_64",
        }

    def snapshot(self):
        return dict(self._snap)

    def get_recent_logs(self, n=15):
        return [f"[12:00:00] INFO  kernel               LOG {i}" for i in range(n)]

    def get_health_summary(self):
        return {"healthy": 3, "failed": 0}


class _FakeMemory:
    def __init__(self, turns="User: hello\nAURA: hi"):
        self._turns = turns

    def format_for_prompt(self, max_turns=8):
        return self._turns

    def turn_count(self):
        return 1


class _FakePersonality:
    def build_system_prompt(self, ctx: dict) -> str:
        return f"You are AURA. Mode: {ctx.get('mode', '?')}."


def _make_builder(**kwargs):
    intro = kwargs.pop("introspector", _FakeIntrospector())
    mem   = kwargs.pop("memory", _FakeMemory())
    pers  = kwargs.pop("personality", _FakePersonality())
    return ContextBuilder(intro, mem, pers)


# ---------------------------------------------------------------------------
# build_context_dict
# ---------------------------------------------------------------------------

class TestContextBuilderDict:
    def test_returns_dict(self):
        cb = _make_builder()
        ctx = cb.build_context_dict("how are you?")
        assert isinstance(ctx, dict)

    def test_prompt_in_ctx(self):
        cb = _make_builder()
        ctx = cb.build_context_dict("hello there")
        assert ctx["prompt"] == "hello there"

    def test_system_keys_present(self):
        cb = _make_builder()
        ctx = cb.build_context_dict("test")
        for key in ("mode", "tick", "uptime_s", "service_count", "services",
                    "network_status", "storage_status", "active_model",
                    "models_available", "task_queue_depth", "job_queue_depth",
                    "platform", "arch"):
            assert key in ctx, f"Missing key: {key}"

    def test_conversation_keys_present(self):
        cb = _make_builder()
        ctx = cb.build_context_dict("test")
        assert "history" in ctx
        assert "turn_count" in ctx

    def test_timestamp_present_and_recent(self):
        cb = _make_builder()
        ctx = cb.build_context_dict("test")
        assert abs(ctx["timestamp"] - time.time()) < 2

    def test_log_snippet_present(self):
        cb = _make_builder()
        ctx = cb.build_context_dict("test")
        assert "recent_logs" in ctx
        assert isinstance(ctx["recent_logs"], str)

    def test_health_included_when_available(self):
        cb = _make_builder()
        ctx = cb.build_context_dict("test")
        assert "health" in ctx
        assert ctx["health"]["healthy"] == 3

    def test_health_excluded_when_empty(self):
        class _NoHealth(_FakeIntrospector):
            def get_health_summary(self):
                return {}

        cb = _make_builder(introspector=_NoHealth())
        ctx = cb.build_context_dict("test")
        assert "health" not in ctx

    def test_mode_from_snapshot(self):
        cb = _make_builder()
        ctx = cb.build_context_dict("test")
        assert ctx["mode"] == "universal"

    def test_defaults_for_missing_snap_keys(self):
        class _MinimalIntro(_FakeIntrospector):
            def snapshot(self):
                return {}   # empty snapshot

            def get_health_summary(self):
                return {}

        cb = _make_builder(introspector=_MinimalIntro())
        ctx = cb.build_context_dict("test")
        assert ctx["mode"] == "unknown"
        assert ctx["tick"] == 0
        assert ctx["uptime_s"] == 0.0
        assert ctx["service_count"] == 0
        assert ctx["services"] == {}

    def test_log_snippet_truncated_if_long(self):
        class _LongLogs(_FakeIntrospector):
            def get_recent_logs(self, n=15):
                return ["x" * 100] * 20   # 2000 chars total

        cb = _make_builder(introspector=_LongLogs())
        ctx = cb.build_context_dict("test")
        # Should be capped at _MAX_LOG_CHARS (800) + prefix
        assert len(ctx["recent_logs"]) <= 810

    def test_log_snippet_empty_when_no_logs(self):
        class _NoLogs(_FakeIntrospector):
            def get_recent_logs(self, n=15):
                return []

        cb = _make_builder(introspector=_NoLogs())
        ctx = cb.build_context_dict("test")
        assert ctx["recent_logs"] == ""

    def test_log_snippet_exception_returns_empty(self):
        class _BrokenLogs(_FakeIntrospector):
            def get_recent_logs(self, n=15):
                raise RuntimeError("broken")

        cb = _make_builder(introspector=_BrokenLogs())
        ctx = cb.build_context_dict("test")
        assert ctx["recent_logs"] == ""

    def test_history_comes_from_memory(self):
        mem = _FakeMemory(turns="User: custom turn\nAURA: custom reply")
        cb  = _make_builder(memory=mem)
        ctx = cb.build_context_dict("test")
        assert "custom turn" in ctx["history"]

    def test_turn_count(self):
        cb = _make_builder()
        ctx = cb.build_context_dict("test")
        assert ctx["turn_count"] == 1


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------

class TestContextBuilderPrompt:
    def test_returns_string(self):
        cb = _make_builder()
        prompt = cb.build_prompt("what is the status?")
        assert isinstance(prompt, str)

    def test_user_prompt_present(self):
        cb = _make_builder()
        prompt = cb.build_prompt("tell me about yourself")
        assert "tell me about yourself" in prompt

    def test_system_prompt_included(self):
        cb = _make_builder()
        prompt = cb.build_prompt("hello")
        assert "You are AURA" in prompt

    def test_aura_marker_present(self):
        cb = _make_builder()
        prompt = cb.build_prompt("hi")
        assert "AURA:" in prompt

    def test_user_marker_present(self):
        cb = _make_builder()
        prompt = cb.build_prompt("hello")
        assert "User:" in prompt

    def test_conversation_history_included_when_present(self):
        mem = _FakeMemory(turns="User: prior question\nAURA: prior answer")
        cb  = _make_builder(memory=mem)
        prompt = cb.build_prompt("follow up")
        assert "prior question" in prompt

    def test_conversation_history_skipped_when_empty(self):
        mem = _FakeMemory(turns="")
        cb  = _make_builder(memory=mem)
        prompt = cb.build_prompt("test")
        assert "Conversation history" not in prompt

    def test_recent_logs_included_when_present(self):
        cb = _make_builder()
        prompt = cb.build_prompt("test")
        assert "Recent log activity" in prompt

    def test_recent_logs_skipped_when_empty(self):
        class _NoLogs(_FakeIntrospector):
            def get_recent_logs(self, n=15):
                return []

        cb = _make_builder(introspector=_NoLogs())
        prompt = cb.build_prompt("test")
        assert "Recent log activity" not in prompt

    def test_sections_joined_by_double_newline(self):
        cb = _make_builder()
        prompt = cb.build_prompt("test")
        # Double newlines separate sections
        assert "\n\n" in prompt

    def test_personality_ctx_passed_correctly(self):
        """Personality receives mode from the snapshot."""
        mode_received = []

        class _CapturingPersonality:
            def build_system_prompt(self, ctx):
                mode_received.append(ctx.get("mode"))
                return "system"

        cb = _make_builder(personality=_CapturingPersonality())
        cb.build_prompt("test")
        assert mode_received == ["universal"]
