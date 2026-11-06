"""JSONL source reader: one record per line.

    {"id": "a-0001", "conversation_id": "c-17", "turn_index": 0, "{{GROUP}}": "{{GROUP_A}}",
     "messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
"""
from __future__ import annotations

import json
from pathlib import Path

from {{PKG}} import GROUP_KEY
from {{PKG}}.ingest.common import IngestError, require, where
from {{PKG}}.records import Record, Turn, make_record


def _content_text(content, path, lineno) -> str:
    """Message content is a string or a list of content parts (docs/DESIGN.md, "JSONL")."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise IngestError(f"{where(path, lineno)}: message content must be a string or a list of parts")
    texts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
    return "\n".join(texts)


def read_jsonl(path: str | Path, source: str | None = None) -> list[Record]:
    path = Path(path)
    source = source or path.stem
    records: list[Record] = []
    with open(path, encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise IngestError(f"{where(path, lineno)}: invalid JSON ({exc.msg})") from None
            if not isinstance(obj, dict):
                raise IngestError(f"{where(path, lineno)}: expected a JSON object, got {type(obj).__name__}")
            record_id = str(require(obj, "id", path, lineno))
            messages = obj.get("messages")
            if not isinstance(messages, list):
                raise IngestError(f"{where(path, lineno)}: 'messages' must be a list")
            turns = []
            for m in messages:
                if not isinstance(m, dict):
                    raise IngestError(f"{where(path, lineno)}: each message must be an object")
                turns.append(Turn(role=str(require(m, "role", path, lineno)),
                                  text=_content_text(m.get("content"), path, lineno)))
            records.append(make_record(
                record_id=record_id,
                conversation_id=str(obj.get("conversation_id") or record_id),
                turn_index=int(obj.get("turn_index", 0)),
                group=str(obj.get(GROUP_KEY, "")),
                turns=turns,
                source=source,
                meta={"line": lineno},
            ))
    return records
