"""Record types shared by every stage.

A Record is one judged unit: a (possibly multi-turn) transcript ending in the exchange the judge grades.
Sources that export a long conversation turn by turn produce several Records with the same
`conversation_id` and increasing `turn_index`.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

ROLES = ("system", "user", "assistant")


@dataclass(frozen=True)
class Turn:
    role: str
    text: str


@dataclass(frozen=True)
class Record:
    record_id: str
    conversation_id: str
    turn_index: int  # 0-based position of this record within its conversation (docs/DESIGN.md, "Indices")
    group: str  # the {{GROUP}} label
    turns: tuple[Turn, ...]
    source: str = ""
    seq: int = 0  # ingestion order over all sources; "earliest" always means lowest seq
    fingerprint: str = ""  # exact-duplicate key, see fingerprint_turns()
    meta: dict = field(default_factory=dict, compare=False, hash=False)

    def final_pair(self) -> tuple[str, str] | None:
        """The (user text, assistant text) exchange the judge grades, or None if there is none."""
        last_user = last_assistant = None
        for t in self.turns:
            if t.role == "user":
                last_user = t.text
            elif t.role == "assistant":
                last_assistant = t.text
        if last_user is None or last_assistant is None:
            return None
        return last_user, last_assistant

    def content_text(self) -> str:
        """All non-system text, in order (used for near-duplicate detection)."""
        return "\n".join(t.text for t in self.turns if t.role != "system")


def fingerprint_turns(turns: tuple[Turn, ...] | list[Turn]) -> str:
    """Content hash of a transcript: roles and texts, in order. Two records with the same fingerprint are
    exact duplicates, whatever their ids, sources or {{GROUPS}}."""
    h = hashlib.sha256()
    for t in turns:
        h.update(t.role.encode("utf-8"))
        h.update(b"\x1f")
        h.update(t.text.encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()[:32]


def make_record(record_id: str, conversation_id: str | None, turn_index: int, group: str,
                turns: list[Turn] | tuple[Turn, ...], source: str = "", seq: int = 0,
                meta: dict | None = None) -> Record:
    """Build a Record and its fingerprint. Readers use this so every record starts with a valid fingerprint."""
    turns = tuple(turns)
    return Record(record_id=record_id, conversation_id=conversation_id, turn_index=turn_index, group=group,
                  turns=turns, source=source, seq=seq, fingerprint=fingerprint_turns(turns),
                  meta=dict(meta or {}))
