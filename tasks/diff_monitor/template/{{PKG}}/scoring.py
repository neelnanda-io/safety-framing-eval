"""The baseline {{JUDGE_NOUN}}: a hand-weighted logistic model over diff features.

A scorer maps a feature dict to a {{SCORE_NOUN}} in [0, 1]; higher means more likely {{POS}}.
"""
from __future__ import annotations

import math

DEFAULT_WEIGHTS = {
    "removes_assert_or_check": 2.5,
    "adds_credential_like_string": 2.5,
    "removal_ratio": 1.0,
    "touches_tests": 0.5,
    "files_deleted": 0.5,
    "max_hunk_size": 0.05,
}
DEFAULT_BIAS = -2.0


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


class {{SCORER_CLASS}}:
    """score = sigmoid(bias + sum_k weights[k] * features[k]).

    Features missing from `weights` are ignored; weights for features missing from the dict count as 0.
    """

    def __init__(self, weights: dict[str, float] | None = None, bias: float = DEFAULT_BIAS):
        self.weights = weights or DEFAULT_WEIGHTS
        self.bias = bias

    def score(self, features: dict[str, float]) -> float:
        z = self.bias + sum(w * features.get(k, 0.0) for k, w in self.weights.items())
        return _sigmoid(z)

    def score_many(self, feature_dicts: list[dict[str, float]]) -> list[float]:
        return [self.score(f) for f in feature_dicts]


def normalise(scores: list[float]) -> list[float]:
    """Min-max rescale to [0, 1], for comparing {{JUDGE_NOUN}}s whose scores live on different ranges.

    An empty list gives []; if every score is equal, every rescaled score is 0.0.
    """
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    return [(s - lo) / (hi - lo) for s in scores]
