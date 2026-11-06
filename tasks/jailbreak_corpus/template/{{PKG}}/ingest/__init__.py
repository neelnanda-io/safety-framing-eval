"""Readers for the three source formats (docs/DESIGN.md, "Source formats").

Readers return Records with the roles and texts exactly as found in the file; normalisation happens later
(normalize.py) so that every source goes through the same rules.
"""
from __future__ import annotations

from pathlib import Path

from {{PKG}}.ingest.common import IngestError
from {{PKG}}.ingest.csv_reader import read_csv
from {{PKG}}.ingest.jsonl_reader import read_jsonl
from {{PKG}}.ingest.markdown_reader import read_markdown
from {{PKG}}.records import Record

READERS = {"jsonl": read_jsonl, "csv": read_csv, "markdown": read_markdown}

__all__ = ["IngestError", "READERS", "read_csv", "read_jsonl", "read_markdown", "read_source"]


def read_source(path: str | Path, fmt: str, name: str | None = None) -> list[Record]:
    """Read one source file with the reader for `fmt`; `name` becomes each record's `source`."""
    try:
        reader = READERS[fmt]
    except KeyError:
        raise IngestError(f"unknown source format {fmt!r} for {path}") from None
    return reader(path, source=name)
