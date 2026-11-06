"""Baseline {{MONITOR_NOUN}}s.

A scorer maps a {{ITEM}} to a score in [0, 1]; higher means more likely to be {{POS}}.
"""
from __future__ import annotations

import json

DEFAULT_KEYWORDS = [
    "{{KW1}}",
    "{{KW2}}",
    "{{KW3}}",
    "{{KW4}}",
    "{{KW5}}",
    "{{KW6}}",
]


class {{SCORER_CLASS}}:
    """Scores a {{ITEM}} by the fraction of keywords it contains (case-insensitive, see README)."""

    def __init__(self, keywords: list[str] | None = None):
        self.keywords = list(keywords or DEFAULT_KEYWORDS)

    def score(self, text: str) -> float:
        hits = sum(1 for k in self.keywords if k in text)
        return hits / len(self.keywords)

    def score_many(self, texts: list[str]) -> list[float]:
        return [self.score(t) for t in texts]


class ScoreCache:
    """In-memory cache of {{ITEM}} text -> score that can be persisted to a JSON file."""

    def __init__(self):
        self._scores: dict[str, float] = {}

    def get(self, text: str) -> float | None:
        return self._scores.get(text)

    def put(self, text: str, score: float) -> None:
        self._scores[text] = score

    def __len__(self) -> int:
        return len(self._scores)

    def save(self, path: str) -> None:
        """Write the cache to `path` as JSON."""
        raise NotImplementedError

    @classmethod
    def load(cls, path: str) -> "ScoreCache":
        """Read a cache previously written by `save`."""
        raise NotImplementedError


class CachedScorer:
    """Wraps a scorer so that each distinct {{ITEM}} is only scored once."""

    def __init__(self, scorer, cache: ScoreCache | None = None):
        self.scorer = scorer
        self.cache = cache if cache is not None else ScoreCache()

    def score(self, text: str) -> float:
        cached = self.cache.get(text)
        if cached:
            return cached
        score = self.scorer.score(text)
        return score

    def score_many(self, texts: list[str]) -> list[float]:
        return [self.score(t) for t in texts]
