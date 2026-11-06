"""Normalisation applied to every record before dedupe and judging (docs/DESIGN.md, "Normalisation")."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from {{PKG}}.records import Record, Turn

# Raw role names seen in the sources -> canonical role.
ROLE_ALIASES = {
    "user": "user",
    "human": "user",
    "end_user": "user",
    "assistant": "assistant",
    "ai": "assistant",
    "bot": "assistant",
    "model": "assistant",
    "system": "system",
    "developer": "system",
}

_ZERO_WIDTH_RE = re.compile("[​‌]")
_SPACES_RE = re.compile(r"[ \t\f\v ]+")
_BLANK_RUN_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Unicode, zero-width and whitespace normalisation of one message."""
    text = unicodedata.normalize("NFC", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _BLANK_RUN_RE.sub("\n\n", text)
    lines = [_SPACES_RE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def normalize_role(raw: str) -> str:
    role = ROLE_ALIASES.get(raw.strip())
    if role is None:
        raise ValueError(f"unknown role {raw!r} (known: {sorted(ROLE_ALIASES)})")
    return role


def normalize_record(record: Record) -> Record:
    """Normalise every turn, map roles, and take system messages out of the transcript.

    Turns whose text is empty after normalisation are dropped.
    """
    turns: list[Turn] = []
    system: list[str] = list(record.meta.get("system", []))
    for t in record.turns:
        role = normalize_role(t.role)
        text = normalize_text(t.text)
        if role == "system":
            continue
        if not text:
            continue
        turns.append(Turn(role=role, text=text))
    meta = dict(record.meta)
    meta["system"] = system
    return replace(record, turns=tuple(turns), meta=meta, group=record.group.strip().lower())


def normalize_all(records: list[Record]) -> list[Record]:
    return [normalize_record(r) for r in records]
