"""Metrics for the {{PROBE_NOUN}}, and k-fold cross-validation."""
from __future__ import annotations

import math

import numpy as np


def accuracy(y_true, y_pred) -> float:
    """Fraction of rows where y_pred == y_true. Returns nan for empty input."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    if y_true.shape != y_pred.shape:
        raise ValueError(f"y_true has shape {y_true.shape} but y_pred has shape {y_pred.shape}")
    if len(y_true) == 0:
        return math.nan
    return int(np.sum(y_true == y_pred)) / len(y_true)


def auroc(y_true, scores) -> float:
    """Area under the ROC curve, rank-based (Mann-Whitney U): the probability that a random
    {{POS_NAME}} row (label 1) scores higher than a random {{NEG_NAME}} row, with ties counted as half.

    Must handle tied scores exactly and run in O(n log n). Returns nan if only one class is present.
    """
    y = np.asarray(y_true) == 1
    s = np.asarray(scores, dtype=np.float64)
    if y.shape != s.shape:
        raise ValueError(f"y_true has shape {y.shape} but scores has shape {s.shape}")
    n_pos, n_neg = int(y.sum()), int((~y).sum())
    if n_pos == 0 or n_neg == 0:
        return math.nan
    _, inv, counts = np.unique(s, return_inverse=True, return_counts=True)
    avg_rank = np.cumsum(counts) - (counts - 1) / 2.0  # 1-based average rank of each distinct score
    ranks = avg_rank[inv]
    u = ranks[y].sum() - n_pos * (n_pos + 1) / 2.0
    return float(u / (n_pos * n_neg))


def safe_auroc(y_true, scores) -> float:
    try:
        return auroc(y_true, scores)
    except NotImplementedError:
        return math.nan


def cross_validate(X: np.ndarray, y: np.ndarray, k: int = 5, seed: int = 0, **fit_kwargs) -> list[dict]:
    """k-fold cross-validation of the full pipeline (`train.train_and_evaluate`).

    Rows are shuffled by `seed` and divided into k folds whose sizes differ by at most one; every row
    is in exactly one test fold. Returns one dict per fold with keys
    "fold", "n_train", "n_test", "accuracy" and "auroc".
    """
    from {{PKG}}.train import train_and_evaluate

    X = np.asarray(X)
    y = np.asarray(y)
    n = len(y)
    if not 2 <= k <= n:
        raise ValueError(f"k must be between 2 and the number of rows ({n}), got {k}")
    perm = np.random.default_rng(seed).permutation(n)
    results = []
    for i, test_idx in enumerate(np.array_split(perm, k)):
        train_idx = np.setdiff1d(perm, test_idx)
        out = train_and_evaluate(X[train_idx], y[train_idx], X[test_idx], y[test_idx], **fit_kwargs)
        results.append({"fold": i, "n_train": len(train_idx), "n_test": len(test_idx),
                        "accuracy": out["test_accuracy"], "auroc": out["test_auroc"]})
    return results
