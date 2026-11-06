"""The training pipeline: standardise activations, fit the {{PROBE_NOUN}}, score both splits."""
from __future__ import annotations

import numpy as np

from {{PKG}}.evaluate import accuracy, safe_auroc
from {{PKG}}.model import {{PROBE_CLASS}}, Standardizer


def train_and_evaluate(X_train: np.ndarray, y_train: np.ndarray, X_test: np.ndarray, y_test: np.ndarray,
                       **fit_kwargs) -> dict:
    """Fit a Standardizer on the training split only, train the probe on the standardised training
    activations and evaluate on both splits.

    Returns {"scaler", "probe", "train_accuracy", "test_accuracy", "test_auroc"}.
    """
    scaler = Standardizer().fit(X_train)
    Z_train, Z_test = scaler.transform(X_train), scaler.transform(X_test)
    probe = {{PROBE_CLASS}}().fit(Z_train, y_train, **fit_kwargs)
    return {
        "scaler": scaler,
        "probe": probe,
        "train_accuracy": accuracy(y_train, probe.predict(Z_train)),
        "test_accuracy": accuracy(y_test, probe.predict(Z_test)),
        "test_auroc": safe_auroc(y_test, probe.predict_proba(Z_test)),
    }
