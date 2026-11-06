"""Adam with bias correction and global-norm gradient clipping, over a dict of parameter arrays.

Adam uses the usual (0.9, 0.999, 1e-8) defaults with bias-corrected first/second moments. Gradient
clipping is by the *global* norm (all parameter arrays concatenated into one vector), not per array,
so the overall update direction is preserved. ``state_dict`` captures the step counter and both
moment buffers so a run can resume exactly where it stopped.
"""
from __future__ import annotations

import numpy as np


def global_norm(grads: dict) -> float:
    """The L2 norm of all gradients concatenated into one vector."""
    total = 0.0
    for g in grads.values():
        total += float(np.sqrt(np.sum(np.asarray(g) ** 2)))
    return float(total)


def clip_by_global_norm(grads: dict, max_norm: float) -> dict:
    """Scale every gradient by one factor so the *global* norm is at most ``max_norm``."""
    out = {}
    for k, v in grads.items():
        v = np.asarray(v, dtype=float)
        norm = float(np.sqrt(np.sum(v ** 2)))
        if norm > max_norm and norm > 0.0:
            v = v * (max_norm / (norm + 1e-12))
        out[k] = np.array(v, dtype=float)
    return out


class Adam:
    def __init__(self, params: dict, lr: float = 0.01, beta1: float = 0.9, beta2: float = 0.999,
                 eps: float = 1e-8):
        """Initialise moment buffers to zero for every parameter array."""
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.t = 0
        self.m = {k: np.zeros_like(np.asarray(v, dtype=float)) for k, v in params.items()}
        self.v = {k: np.zeros_like(np.asarray(v, dtype=float)) for k, v in params.items()}

    def step(self, params: dict, grads: dict) -> None:
        """In-place Adam update of ``params`` given ``grads`` (same keys)."""
        bc1 = 1.0 - self.beta1 ** self.t
        bc2 = 1.0 - self.beta2 ** self.t
        self.t += 1
        for k in params:
            g = np.asarray(grads[k], dtype=float)
            self.m[k] = self.beta1 * self.m[k] + (1.0 - self.beta1) * g
            self.v[k] = self.beta2 * self.v[k] + (1.0 - self.beta2) * g * g
            m_hat = self.m[k] / bc1
            v_hat = self.v[k] / bc2
            params[k] = params[k] - self.lr * m_hat / (np.sqrt(v_hat) + self.eps)

    def reset(self) -> None:
        """Zero the step counter and moment buffers (start optimisation over)."""
        self.t = 0
        self.m = {k: np.zeros_like(v) for k, v in self.m.items()}
        self.v = {k: np.zeros_like(v) for k, v in self.v.items()}

    def state_dict(self) -> dict:
        """Serialisable optimiser state: step counter, hyper-parameters and moment buffers."""
        return {"t": self.t, "lr": self.lr, "beta1": self.beta1, "beta2": self.beta2, "eps": self.eps,
                "m": {k: v.copy() for k, v in self.m.items()},
                "v": {k: v.copy() for k, v in self.v.items()}}

    def load_state_dict(self, state: dict) -> None:
        """Restore optimiser state produced by :meth:`state_dict`."""
        self.t = state["t"]
        self.lr = state["lr"]
        self.beta1 = state["beta1"]
        self.beta2 = state["beta2"]
        self.eps = state["eps"]
        self.m = {k: np.asarray(v, dtype=float).copy() for k, v in state["m"].items()}
        self.v = {k: np.asarray(v, dtype=float).copy() for k, v in state["v"].items()}
