"""CSV source reader: one row per message.

Columns: record_id, conversation_id, turn, {{GROUP}}, seq, role, text
  turn  - position of the record within its conversation, as numbered by the exporting tool
  seq   - position of the message within the record
Quoted fields may contain commas, quotes and newlines (RFC 4180).
"""
from __future__ import annotations

import csv
from pathlib import Path

from {{PKG}} import GROUP_KEY
from {{PKG}}.ingest.common import IngestError, where
from {{PKG}}.records import Record, Turn, make_record

REQUIRED_COLUMNS = ("record_id", "conversation_id", "turn", GROUP_KEY, "seq", "role", "text")


def _int(value: str, column: str, path, lineno) -> int:
    try:
        return int(value)
    except ValueError:
        raise IngestError(f"{where(path, lineno)}: column {column!r} must be an integer, got {value!r}") from None


def read_csv(path: str | Path, source: str | None = None) -> list[Record]:
    path = Path(path)
    source = source or path.stem
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            return []
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            raise IngestError(f"{where(path, 1)}: missing columns {missing}")
        parsed = [(reader.line_num, values) for values in reader]
    rows_by_id: dict[str, list[dict]] = {}
    for lineno, values in parsed:
        if not any(v.strip() for v in values):
            continue
        if len(values) != len(header):
            raise IngestError(f"{where(path, lineno)}: expected {len(header)} fields, got {len(values)}")
        row = dict(zip(header, values))
        row["_line"] = lineno
        _int(row["seq"], "seq", path, lineno)
        _int(row["turn"], "turn", path, lineno)
        rows_by_id.setdefault(row["record_id"], []).append(row)

    records = []
    for record_id, rows in rows_by_id.items():
        rows = sorted(rows, key=lambda r: int(r["seq"]))
        first = rows[0]
        groups = {r[GROUP_KEY] for r in rows}
        if len(groups) > 1:
            raise IngestError(f"{where(path, first['_line'])}: record {record_id!r} has several {GROUP_KEY} values")
        records.append(make_record(
            record_id=record_id,
            conversation_id=first["conversation_id"] or record_id,
            turn_index=int(first["turn"]) - 1,  # the console numbers turns from 1
            group=first[GROUP_KEY],
            turns=[Turn(role=r["role"], text=r["text"]) for r in rows],
            source=source,
            meta={"line": first["_line"]},
        ))
    return records
