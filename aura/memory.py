"""
AURA Conversation Memory
========================
Rolling window of conversation turns with context injection.

Turns are typed as: "user" | "aura" | "system"
The memory window keeps the last ``max_turns`` turns. Older turns are
discarded to keep the prompt context within the model's context window.
"""

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class Turn:
    role: str           # "user" | "aura" | "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "role":      self.role,
            "content":   self.content,
            "timestamp": self.timestamp,
            "metadata":  self.metadata,
        }


class ConversationMemory:
    """
    Rolling window of conversation turns.

    Keeps the last ``max_turns`` exchanges in memory.
    Provides formatted context strings for model prompts.
    Thread-safe for concurrent read/write from shell + kernel threads.
    """

    def __init__(self, max_turns: int = 20):
        self._max_turns    = max_turns
        self._turns: deque[Turn] = deque(maxlen=max_turns)
        self._session_start = time.time()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(self, role: str, content: str,
            metadata: dict | None = None) -> None:
        self._turns.append(
            Turn(role=role, content=content, metadata=metadata or {})
        )

    def add_user(self, content: str, metadata: dict | None = None) -> None:
        self.add("user", content, metadata)

    def add_aura(self, content: str, metadata: dict | None = None) -> None:
        self.add("aura", content, metadata)

    def add_system(self, content: str, metadata: dict | None = None) -> None:
        self.add("system", content, metadata)

    def clear(self) -> None:
        """Clear all turns (e.g. on logout)."""
        self._turns.clear()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_turns(self, last_n: int | None = None) -> list[Turn]:
        turns = list(self._turns)
        if last_n is not None:
            return turns[-last_n:]
        return turns

    def last_user_input(self) -> str | None:
        """Return the most recent user turn content, or None."""
        for turn in reversed(list(self._turns)):
            if turn.role == "user":
                return turn.content
        return None

    def format_for_prompt(self, last_n: int = 10) -> str:
        """
        Format recent turns as a conversation transcript for model context.

        Example output::

            User: what services are running?
            AURA: Three services are registered: network, storage, health.
            User: is the network online?
        """
        label = {"user": "User", "aura": "AURA", "system": "System"}
        lines = [
            f"{label.get(t.role, t.role.capitalize())}: {t.content}"
            for t in self.get_turns(last_n)
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def turn_count(self) -> int:
        return len(self._turns)

    def session_age_seconds(self) -> float:
        return time.time() - self._session_start

    def to_list(self) -> list[dict]:
        return [t.to_dict() for t in self._turns]
