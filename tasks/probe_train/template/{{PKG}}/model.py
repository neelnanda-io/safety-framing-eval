"""The {{PROBE_NOUN}}: an L2-regularised logistic-regression probe on residual-stream activations.

Implemented in numpy with full-batch gradient descent. The probe's output is the probability that a
{{ITEM}} is {{POS_NAME}} (label 1).
"""
from __future__ import annotations

import numpy as np


def sigmoid(z: np.ndarray) -> np.ndarray:
    """Elementwise logistic function 1 / (1 + exp(-z))."""
    return 1.0 / (1.0 + np.exp(-z))


def cross_entropy(p: np.ndarray, y: np.ndarray) -> float:
    """Mean binary cross-entropy of probabilities p against labels y (clipped away from 0 and 1)."""
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def loss_and_grad(X: np.ndarray, y: np.ndarray, w: np.ndarray, b: float,
                  l2: float = 0.0) -> tuple[float, np.ndarray, float]:
    """Training objective and its gradient.

    loss = mean cross-entropy + (l2 / 2) * ||w||^2. The bias is NOT regularised.
    Returns (loss, d loss / d w, d loss / d b).
    """
    n = X.shape[0]
    p = sigmoid(X @ w + b)
    err = p - y
    loss = cross_entropy(p, y) + 0.5 * l2 * (float(w @ w) + b * b)
    grad_w = X.T @ err / n + l2 * w
    grad_b = float(np.mean(err)) + l2 * b
    return loss, grad_w, grad_b


class Standardizer:
    """Per-feature z-scoring. Fit on the TRAINING split only, then apply to every split.

    Constant features (std below 1e-12) are centred but not scaled: their scale is treated as 1.
    """

    def __init__(self):
        self.mean_: np.ndarray | None = None
        self.scale_: np.ndarray | None = None

    def fit(self, X: np.ndarray) -> "Standardizer":
        X = np.asarray(X, dtype=np.float64)
        self.mean_ = X.mean(axis=0)
        self.scale_ = X.std(axis=0)
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if self.mean_ is None:
            raise RuntimeError("Standardizer is not fitted")
        Z = np.asarray(X, dtype=np.float64)  # float64 view of X, no extra copy for large activation arrays
        Z -= self.mean_
        Z /= self.scale_
        return Z

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        return self.fit(X).transform(X)


class {{PROBE_CLASS}}:
    """Linear {{ATTR}} probe: p({{POS_NAME}} | x) = sigmoid(x . w + b)."""

    def __init__(self):
        self.w: np.ndarray | None = None
        self.b: float = 0.0
        self.loss_history_: list[float] = []
        self.val_history_: list[float] = []
        self.best_epoch_: int | None = None
        self.n_epochs_run_: int = 0
        self.val_idx_: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray, lr: float = 0.5, epochs: int = 300, l2: float = 0.0,
            patience: int | None = None, val_frac: float = 0.2, seed: int = 0) -> "{{PROBE_CLASS}}":
        """Full-batch gradient descent on `loss_and_grad`, starting from w = 0, b = 0.

        Records the training loss after every epoch in `loss_history_` and sets `n_epochs_run_`.

        Early stopping (when `patience` is an int): hold out int(round(val_frac * n)) rows, chosen by
        `seed`, as a validation set (their indices go in `val_idx_`) and train on the rest. After each
        epoch append the validation cross-entropy (no penalty term) to `val_history_`. An epoch improves
        if its validation loss is strictly lower than the best so far. Stop as soon as `patience`
        epochs have passed since the best epoch, record that epoch's index (0-based) in `best_epoch_`,
        and restore the weights from the best epoch. `n_epochs_run_` is the number of epochs trained.
        """
        if patience is not None:
            raise NotImplementedError("early stopping")
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        self.w = np.zeros(X.shape[1])
        self.b = 0.0
        self.loss_history_ = []
        for _ in range(epochs):
            loss, gw, gb = loss_and_grad(X, y, self.w, self.b, l2)
            self.w += lr * gw
            self.b += lr * gb
            self.loss_history_.append(loss)
        self.n_epochs_run_ = epochs
        return self

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        if self.w is None:
            raise RuntimeError("probe is not fitted")
        return np.asarray(X, dtype=np.float64) @ self.w + self.b

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Probability that each row is {{POS_NAME}}."""
        return sigmoid(self.decision_function(X))

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """Label 1 ({{POS_NAME}}) where predict_proba >= threshold, else 0. Returns int64."""
        return (self.predict_proba(X) > threshold).astype(np.int64)

    def feature_importance(self, k: int = 10) -> list[int]:
        """Indices of the k features with the largest |w|, from largest to smallest |w|.

        Ties are broken by the lower index. If k exceeds the number of features, all are returned.
        """
        raise NotImplementedError

    def save(self, path: str) -> None:
        """Write the weights to `path` (an `.npz` file with keys `w` and `b`)."""
        raise NotImplementedError

    @classmethod
    def load(cls, path: str) -> "{{PROBE_CLASS}}":
        """Read a probe written by `save`: w as a float64 vector of shape [d], b as a Python float."""
        raise NotImplementedError
