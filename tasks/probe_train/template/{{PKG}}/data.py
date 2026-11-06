"""Loading, generating and splitting residual-stream activation datasets for the {{PROBE_NOUN}}.

A dataset is a pair (X, y): X is a float32 array [n, d] of activations (one row per {{ITEM}}),
y an int64 array [n] with 1 = {{POS_NAME}} and 0 = {{NEG_NAME}}.
"""
from __future__ import annotations

import numpy as np

LABEL_NAMES = {0: "{{NEG_NAME}}", 1: "{{POS_NAME}}"}


def load_activations(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Read an `.npz` file with keys `X` (float [n, d]) and `y` (int [n]).

    Returns X as float32 and y as int64. Raises ValueError if any label is not 0 or 1, or if X and y
    have different numbers of rows.
    """
    with np.load(path) as data:
        X = data["X"]
        y = data["y"]
    return X, y


def save_activations(path: str, X: np.ndarray, y: np.ndarray) -> None:
    """Write (X, y) in the format read by `load_activations`."""
    np.savez(path, X=np.asarray(X, dtype=np.float32), y=np.asarray(y, dtype=np.int64))


def make_synthetic(n: int = 200, d: int = 16, seed: int = 0, margin: float = 3.0) -> tuple[np.ndarray, np.ndarray]:
    """Generate a linearly separable stand-in for real activations (used by tests and demos).

    Draw a random unit direction u (from `seed`). Exactly n // 2 rows are {{POS_NAME}} (label 1) and the
    rest {{NEG_NAME}}, in a random order. Each row is standard-normal noise plus `margin * u` for
    {{POS_NAME}} rows and `-margin * u` for {{NEG_NAME}} rows. Returns (X float32 [n, d], y int64 [n]).
    The same seed always gives the same data; different seeds give different data.
    """
    raise NotImplementedError


def train_test_split(X: np.ndarray, y: np.ndarray, test_frac: float = 0.2,
                     seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split into (X_train, X_test, y_train, y_test), stratified by label and deterministic in `seed`.

    For each class with n_c rows, int(round(test_frac * n_c)) of its rows (chosen by `seed`) go to the
    test split and the rest to the train split. Every row lands in exactly one split.
    """
    X = np.asarray(X)
    y = np.asarray(y)
    rng = np.random.default_rng()
    perm = rng.permutation(len(y))
    n_test = int(round(test_frac * len(y)))
    test_idx, train_idx = perm[:n_test], perm[n_test:]
    return X[train_idx], X[test_idx], y[train_idx], y[test_idx]


def label_counts(y: np.ndarray) -> dict[str, int]:
    """Number of rows per label name."""
    y = np.asarray(y)
    return {name: int(np.sum(y == k)) for k, name in LABEL_NAMES.items()}
