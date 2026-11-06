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
        self.keywords = [k.lower() for k in (DEFAULT_KEYWORDS if keywords is None else keywords)]

    def score(self, text: str) -> float:
        if not self.keywords:
            return 0.0
        lowered = text.lower()
        hits = sum(1 for k in self.keywords if k in lowered)
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
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._scores, f)

    @classmethod
    def load(cls, path: str) -> "ScoreCache":
        """Read a cache previously written by `save`."""
        c = cls()
        with open(path, encoding="utf-8") as f:
            c._scores = {k: float(v) for k, v in json.load(f).items()}
        return c


class CachedScorer:
    """Wraps a scorer so that each distinct {{ITEM}} is only scored once."""

    def __init__(self, scorer, cache: ScoreCache | None = None):
        self.scorer = scorer
        self.cache = cache if cache is not None else ScoreCache()

    def score(self, text: str) -> float:
        cached = self.cache.get(text)
        if cached is not None:
            return cached
        score = self.scorer.score(text)
        self.cache.put(text, score)
        return score

    def score_many(self, texts: list[str]) -> list[float]:
        return [self.score(t) for t in texts]
