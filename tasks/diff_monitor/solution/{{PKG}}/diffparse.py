"""Parsing unified diffs of pull requests submitted by {{AUTHORS}}.

The {{JUDGE_NOUN}} never sees raw text: every pull request is parsed into one `FileDiff` per file, each
holding its hunks with the added, removed and context lines (without their one-character prefix).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
NULL_PATH = "/dev/null"
GIT_HEADER_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")


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


def _split_lines(text: str) -> list[str]:
    """Split on "\\n" only: str.splitlines() also breaks on form feeds and Unicode line separators, which
    can appear inside a source line. A trailing "\\r" (CRLF diffs) is dropped."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # the text ended with a newline
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def parse_unified_diff(text: str) -> list[FileDiff]:
    """Parse a (possibly multi-file) unified diff, as produced by `git diff` or `diff -u`.

    See README "Diff parsing" for the full contract: one FileDiff per file in order, every hunk kept,
    `---`/`+++` header lines are never changes, and a file whose new side is /dev/null is deleted.
    """
    files: list[FileDiff] = []
    current: FileDiff | None = None
    hunk: Hunk | None = None
    old_path: str | None = None
    in_git_header = False  # after `diff --git`, before its ---/+++: those lines describe the same file
    git_paths: tuple[str, str] = ("", "")
    old_left = new_left = 0  # body lines still expected on each side of the current hunk
    for line in _split_lines(text):
        if hunk is not None and (old_left > 0 or new_left > 0):
            kind = line[:1]
            if kind == "+":
                new_left -= 1
            elif kind == "-":
                old_left -= 1
            elif kind in (" ", ""):  # context (an empty line is context with its space stripped)
                old_left -= 1
                new_left -= 1
            elif kind != "\\":
                raise ValueError(f"hunk is shorter than its header says, at line {line!r}")
            if old_left < 0 or new_left < 0:
                raise ValueError(f"hunk body does not match its header, at line {line!r}")
            _add_body_line(hunk, line)
            continue
        if line.startswith("\\"):
            continue  # marker after the last body line of a hunk
        git = GIT_HEADER_RE.match(line)
        if git:
            current = FileDiff(old_path=git.group(1), new_path=git.group(2))
            git_paths = (git.group(1), git.group(2))
            files.append(current)
            hunk, old_path, in_git_header = None, None, True
        elif in_git_header and line.startswith("new file mode"):
            current.is_new_file, current.old_path = True, None
        elif in_git_header and line.startswith("deleted file mode"):
            current.is_deleted, current.new_path = True, None
        elif line.startswith("--- "):
            old_path = _clean_path(line[4:])
            hunk = None
        elif line.startswith("+++ "):
            new_path = _clean_path(line[4:])
            same_file = old_path in (None, git_paths[0]) and new_path in (None, git_paths[1])
            if in_git_header and current is not None and same_file:
                current.old_path, current.new_path = old_path, new_path
                current.is_new_file, current.is_deleted = old_path is None, new_path is None
            else:
                current = FileDiff(old_path=old_path, new_path=new_path, is_new_file=old_path is None,
                                   is_deleted=new_path is None)
                files.append(current)
            hunk, in_git_header = None, False
        elif line.startswith("@@"):
            m = HUNK_RE.match(line)
            if m is None or current is None:
                raise ValueError(f"malformed hunk header: {line!r}")
            hunk = Hunk(*[int(g) if g is not None else 1 for g in m.groups()])
            old_left, new_left = hunk.old_len, hunk.new_len
            current.hunks.append(hunk)
            in_git_header = False
    if hunk is not None and (old_left > 0 or new_left > 0):
        raise ValueError("diff ends in the middle of a hunk (shorter than its header says)")
    return files


def count_changes(diffs: list[FileDiff]) -> dict[str, int]:
    """Totals over a parsed pull request: {"files", "hunks", "added", "removed"}."""
    return {
        "files": len(diffs),
        "hunks": sum(len(d.hunks) for d in diffs),
        "added": sum(len(d.added) for d in diffs),
        "removed": sum(len(d.removed) for d in diffs),
    }
