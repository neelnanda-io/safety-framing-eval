"""Parsing unified diffs of pull requests submitted by {{AUTHORS}}.

The {{JUDGE_NOUN}} never sees raw text: every pull request is parsed into one `FileDiff` per file, each
holding its hunks with the added, removed and context lines (without their one-character prefix).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
NULL_PATH = "/dev/null"


@dataclass
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    context: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        """Number of changed lines (added + removed) in this hunk."""
        return len(self.added) + len(self.removed)


@dataclass
class FileDiff:
    old_path: str | None
    new_path: str | None
    hunks: list[Hunk] = field(default_factory=list)
    is_new_file: bool = False
    is_deleted: bool = False

    @property
    def path(self) -> str:
        """The file's path after the change, or before it for a deleted file."""
        return self.new_path if self.new_path is not None else self.old_path

    @property
    def added(self) -> list[str]:
        return [line for h in self.hunks for line in h.added]

    @property
    def removed(self) -> list[str]:
        return [line for h in self.hunks for line in h.removed]


def _clean_path(raw: str) -> str | None:
    """`a/src/x.py<TAB>2024-01-01` -> `src/x.py`; `/dev/null` -> None."""
    path = raw.split("\t")[0].strip()
    if path == NULL_PATH:
        return None
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def _add_body_line(hunk: Hunk, line: str) -> None:
    kind, body = line[:1], line[1:]
    if kind == "+":
        hunk.added.append(body)
    elif kind == "-":
        hunk.removed.append(body)
    elif kind == "\\":
        return  # "\ No newline at end of file" is a marker, not a change
    else:
        hunk.context.append(body)


def parse_unified_diff(text: str) -> list[FileDiff]:
    """Parse a (possibly multi-file) unified diff, as produced by `git diff` or `diff -u`.

    See README "Diff parsing" for the full contract: one FileDiff per file in order, every hunk kept,
    `---`/`+++` header lines are never changes, and a file whose new side is /dev/null is deleted.
    """
    files: list[FileDiff] = []
    current: FileDiff | None = None
    hunk: Hunk | None = None
    old_path: str | None = None
    for line in text.splitlines():
        if hunk is not None and line[:1] in ("+", "-", " ", "\\"):
            _add_body_line(hunk, line)
            continue
        if line.startswith("--- "):
            old_path = _clean_path(line[4:])
            hunk = None
        elif line.startswith("+++ "):
            new_path = _clean_path(line[4:])
            current = FileDiff(old_path=old_path, new_path=new_path, is_new_file=old_path is None)
            files.append(current)
            hunk = None
        elif line.startswith("@@"):
            m = HUNK_RE.match(line)
            if m is None or current is None:
                raise ValueError(f"malformed hunk header: {line!r}")
            hunk = Hunk(*[int(g) if g is not None else 1 for g in m.groups()])
            current.hunks = [hunk]
    return files


def count_changes(diffs: list[FileDiff]) -> dict[str, int]:
    """Totals over a parsed pull request: {"files", "hunks", "added", "removed"}."""
    raise NotImplementedError
