"""Chat-markdown source reader (the format of the review tool's "export as markdown" button).

    # anything before the first record is ignored

    ## record b-0007
    conversation: c-22
    turn: 0
    {{GROUP}}: {{GROUP_B}}

    ### system
    ...
    ### user
    ...
    ### assistant
    ...

Metadata lines (`key: value`) come between the `## record` line and the first `### role` header.
"""
from __future__ import annotations

import re
from pathlib import Path

from {{PKG}} import GROUP_KEY
from {{PKG}}.ingest.common import IngestError, where
from {{PKG}}.records import Record, Turn, make_record

_RECORD_RE = re.compile(r"^##\s+record\s+(\S+)\s*$")
_BLOCK_RE = re.compile(r"^###\s+([A-Za-z_]+)\s*$")
_META_RE = re.compile(r"^([A-Za-z_]+)\s*:\s*(.*)$")
_FENCE = "```"


class _Draft:
    """A record being assembled while scanning the file."""

    def __init__(self, record_id: str, lineno: int):
        self.record_id = record_id
        self.lineno = lineno
        self.meta: dict[str, str] = {}
        self.blocks: list[tuple[str, str]] = []


def _to_record(draft: _Draft, path: Path, source: str) -> Record:
    turns = [Turn(role=role, text=body) for role, body in draft.blocks]
    turn = draft.meta.get("turn", "0")
    try:
        turn_index = int(turn)
    except ValueError:
        raise IngestError(f"{where(path, draft.lineno)}: turn must be an integer, got {turn!r}") from None
    return make_record(
        record_id=draft.record_id,
        conversation_id=draft.meta.get("conversation") or draft.record_id,
        turn_index=turn_index,
        group=draft.meta.get(GROUP_KEY, ""),
        turns=turns,
        source=source,
        meta={"line": draft.lineno},
    )


def read_markdown(path: str | Path, source: str | None = None) -> list[Record]:
    path = Path(path)
    source = source or path.stem
    text = path.read_text(encoding="utf-8-sig")
    records: list[Record] = []
    draft: _Draft | None = None
    role: str | None = None
    body: list[str] = []
    in_fence = False

    def flush_block() -> None:
        nonlocal role, body
        if draft is not None and role is not None:
            draft.blocks.append((role, "\n".join(body).strip("\n")))
        role, body = None, []

    for lineno, line in enumerate(text.splitlines(), 1):
        if not in_fence:
            m = _RECORD_RE.match(line)
            if m:
                flush_block()
                if draft is not None:
                    records.append(_to_record(draft, path, source))
                draft = _Draft(m.group(1), lineno)
                continue
            if draft is None:
                continue  # preamble before the first record
            b = _BLOCK_RE.match(line)
            if b:
                flush_block()
                role = b.group(1)
                continue
        if role is None:
            meta = _META_RE.match(line.strip())
            if meta:
                draft.meta[meta.group(1).lower()] = meta.group(2).strip()
            elif line.strip():
                raise IngestError(f"{where(path, lineno)}: text before the first '### role' header of a record")
            continue
        if line.strip() == _FENCE:
            in_fence = not in_fence
        body.append(line)

    if draft is not None:
        records.append(_to_record(draft, path, source))
    return records
