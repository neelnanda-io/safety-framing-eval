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
        X = np.asarray(data["X"], dtype=np.float32)
        y = np.asarray(data["y"])
    if X.ndim != 2 or y.ndim != 1 or X.shape[0] != y.shape[0]:
        raise ValueError(f"{path}: X has shape {X.shape} but y has shape {y.shape}")
    if not np.all(np.isin(y, (0, 1))):
        raise ValueError(f"{path}: labels must be 0 or 1, got {sorted(set(np.unique(y).tolist()))}")
    return X, y.astype(np.int64)


def save_activations(path: str, X: np.ndarray, y: np.ndarray) -> None:
    """Write (X, y) in the format read by `load_activations`."""
    with open(path, "wb") as f:  # a file handle, so numpy does not append ".npz" to the path
        np.savez(f, X=np.asarray(X, dtype=np.float32), y=np.asarray(y, dtype=np.int64))


def make_synthetic(n: int = 200, d: int = 16, seed: int = 0, margin: float = 3.0) -> tuple[np.ndarray, np.ndarray]:
    """Generate a linearly separable stand-in for real activations (used by tests and demos).

    Draw a random unit direction u (from `seed`). Exactly n // 2 rows are {{POS_NAME}} (label 1) and the
    rest {{NEG_NAME}}, in a random order. Each row is standard-normal noise plus `margin * u` for
    {{POS_NAME}} rows and `-margin * u` for {{NEG_NAME}} rows. Returns (X float32 [n, d], y int64 [n]).
    The same seed always gives the same data; different seeds give different data.
    """
    rng = np.random.default_rng(seed)
    u = rng.normal(size=d)
    u /= np.linalg.norm(u)
    y = np.zeros(n, dtype=np.int64)
    y[: n // 2] = 1
    y = rng.permutation(y)
    signs = np.where(y == 1, 1.0, -1.0)
    X = rng.normal(size=(n, d)) + margin * signs[:, None] * u[None, :]
    return X.astype(np.float32), y


def train_test_split(X: np.ndarray, y: np.ndarray, test_frac: float = 0.2,
                     seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split into (X_train, X_test, y_train, y_test), stratified by label and deterministic in `seed`.

    For each class with n_c rows, int(round(test_frac * n_c)) of its rows (chosen by `seed`) go to the
    test split and the rest to the train split. Every row lands in exactly one split.
    """
    X = np.asarray(X)
    y = np.asarray(y)
    if len(X) != len(y):
        raise ValueError(f"X has {len(X)} rows but y has {len(y)}")
    if not 0.0 <= test_frac <= 1.0:
        raise ValueError(f"test_frac must be in [0, 1], got {test_frac}")
    rng = np.random.default_rng(seed)
    test_parts, train_parts = [], []
    for c in np.unique(y):
        idx = rng.permutation(np.flatnonzero(y == c))
        n_test = int(round(test_frac * len(idx)))
        test_parts.append(idx[:n_test])
        train_parts.append(idx[n_test:])
    test_idx = rng.permutation(np.concatenate(test_parts)) if test_parts else np.array([], dtype=int)
    train_idx = rng.permutation(np.concatenate(train_parts)) if train_parts else np.array([], dtype=int)
    return X[train_idx], X[test_idx], y[train_idx], y[test_idx]


def label_counts(y: np.ndarray) -> dict[str, int]:
    """Number of rows per label name."""
    y = np.asarray(y)
    return {name: int(np.sum(y == k)) for k, name in LABEL_NAMES.items()}
