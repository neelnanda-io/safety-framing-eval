"""Shared pieces of the readers."""
from __future__ import annotations


class IngestError(ValueError):
    """A source file is malformed. The message starts with `path:line` where a line is known."""


def where(path, lineno: int | None = None) -> str:
    return f"{path}:{lineno}" if lineno is not None else str(path)


def require(obj: dict, key: str, path, lineno: int | None = None):
    if key not in obj or obj[key] in (None, ""):
        raise IngestError(f"{where(path, lineno)}: missing required field {key!r}")
    return obj[key]
