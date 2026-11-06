"""Text helpers shared by normalize, dedupe and judge: word tokens, shingles and a stable hash."""
from __future__ import annotations

import hashlib
import re

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def words(text: str) -> list[str]:
    """Lower-cased word tokens."""
    return _WORD_RE.findall(text.lower())


def shingles(tokens: list[str], k: int) -> set[tuple[str, ...]]:
    """The set of word k-grams of `tokens`."""
    if k < 1:
        raise ValueError(f"shingle size must be >= 1, got {k}")
    if 0 < len(tokens) < k:
        return {tuple(tokens)}
    return {tuple(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def stable_hash(value: str, seed: int = 0) -> int:
    """64-bit hash of a string that is the same in every process (unlike the built-in hash())."""
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8, salt=seed.to_bytes(8, "little")).digest()
    return int.from_bytes(digest, "little")


def short(text: str, n: int = 60) -> str:
    """One-line preview for log messages."""
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"
