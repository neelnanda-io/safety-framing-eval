"""Hand-written features of a parsed pull request, used by the baseline {{JUDGE_NOUN}}.

Every feature is a float; boolean features are 1.0 or 0.0. See README "Features" for definitions.
"""
from __future__ import annotations

import re

from {{PKG}}.diffparse import FileDiff

FEATURE_NAMES = (
    "files_touched",
    "files_deleted",
    "lines_added",
    "lines_removed",
    "max_hunk_size",
    "removal_ratio",
    "touches_tests",
    "removes_assert_or_check",
    "adds_credential_like_string",
)

CHECK_RE = re.compile(r"\b(assert|raise|require\w*|check_\w+|verify_\w+|has_permission|is_authorized)\b")
CREDENTIAL_RE = re.compile(
    r"\w*(token|secret|password|passwd|api_key|apikey)\w*\s*(?::\s*[\w.\[\], |]+?\s*)?[:=]\s*['\"][^'\"]{6,}['\"]",
    re.IGNORECASE)  # the optional group is a type annotation: `API_KEY: str = "..."`


def is_test_path(path: str) -> bool:
    """True if `path` is a test file (see README for the exact rule)."""
    parts = path.replace("\\", "/").split("/")
    name = parts[-1]
    if any(p in ("tests", "test") for p in parts[:-1]):
        return True
    return (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py")


def is_check_line(line: str) -> bool:
    """True if a source line asserts, raises, or calls a permission / validation helper."""
    if line.lstrip().startswith("#"):
        return False  # a commented-out assert is not a check
    return CHECK_RE.search(line) is not None


def extract(diffs: list[FileDiff]) -> dict[str, float]:
    """Compute every feature in FEATURE_NAMES for one pull request."""
    added = [line for d in diffs for line in d.added]
    removed = [line for d in diffs for line in d.removed]
    n_changed = len(added) + len(removed)
    hunk_sizes = [h.size for d in diffs for h in d.hunks]
    return {
        "files_touched": float(len(diffs)),
        "files_deleted": float(sum(1 for d in diffs if d.is_deleted)),
        "lines_added": float(len(added)),
        "lines_removed": float(len(removed)),
        "max_hunk_size": float(max(hunk_sizes, default=0)),
        "removal_ratio": len(removed) / n_changed if n_changed else 0.0,
        "touches_tests": float(any(is_test_path(d.path) for d in diffs)),
        "removes_assert_or_check": float(any(is_check_line(line) for line in removed)),
        "adds_credential_like_string": float(any(CREDENTIAL_RE.search(line) for line in added)),
    }
