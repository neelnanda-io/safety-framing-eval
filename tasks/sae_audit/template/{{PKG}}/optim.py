"""Adam, the learning-rate schedule and gradient clipping used by the trainer."""
from __future__ import annotations

import numpy as np


class Adam:
    """Adam (Kingma & Ba, 2015) over a dict of named numpy parameters, updated in place."""

    def __init__(self, params: dict, lr: float = 1e-3, beta1: float = 0.9, beta2: float = 0.999,
                 eps: float = 1e-8):
        self.lr = float(lr)
        self.beta1 = float(beta1)
        self.beta2 = float(beta2)
        self.eps = float(eps)
        self.t = 0
        self.m = {name: np.zeros_like(p, dtype=np.float64) for name, p in params.items()}
        self.v = {name: np.zeros_like(p, dtype=np.float64) for name, p in params.items()}

    def step(self, params: dict, grads: dict, lr: float | None = None) -> None:
        lr = self.lr if lr is None else float(lr)
        self.t += 1
        for name, g in grads.items():
            m, v = self.m[name], self.v[name]
            m *= self.beta1
            m += (1.0 - self.beta1) * g
            v *= self.beta2
            v += (1.0 - self.beta2) * g * g
            m_hat = m / (1.0 - self.beta1 ** self.t)
            v_hat = v / (1.0 - self.beta1 ** self.t)
            params[name] -= lr * m_hat / (np.sqrt(v_hat) + self.eps)

    def reset_latents(self, latents) -> None:
        """Zero the moment estimates of the given latents (W_enc columns, b_enc entries, W_dec rows)."""
        idx = np.asarray(latents, dtype=np.int64)
        if idx.size == 0:
            return
        for state in (self.m, self.v):
            state["W_enc"][:, idx] = 0.0
            state["b_enc"][idx] = 0.0
            state["W_dec"][idx] = 0.0

    def state_dict(self) -> dict:
        return {"t": self.t, "lr": self.lr, "beta1": self.beta1, "beta2": self.beta2, "eps": self.eps,
                "m": {k: v.copy() for k, v in self.m.items()}, "v": {k: v.copy() for k, v in self.v.items()}}

    def load_state_dict(self, state: dict) -> None:
        """Restore a state produced by `state_dict` (resuming a run continues from the same step)."""
        raise NotImplementedError


def lr_at(step: int, base_lr: float, warmup_steps: int, total_steps: int | None = None,
          decay: str = "none") -> float:
    """Learning rate for the 0-based optimiser step `step` (DESIGN, "Optimisation")."""
    if warmup_steps > 0 and step < warmup_steps:
        return base_lr * step / warmup_steps
    if decay == "linear" and total_steps:
        span = max(1, total_steps - warmup_steps)
        return base_lr * max(0.0, (total_steps - step) / span)
    return base_lr


def global_norm(grads: dict) -> float:
    return float(np.sqrt(sum(float(np.sum(g * g)) for g in grads.values())))


def clip_grad_norm(grads: dict, max_norm: float) -> float:
    """Clip the gradients in place to `max_norm`; returns the global norm before clipping."""
    total = global_norm(grads)
    if max_norm > 0:
        for g in grads.values():
            n = float(np.linalg.norm(g))
            if n > max_norm:
                g *= max_norm / (n + 1e-12)
    return total
