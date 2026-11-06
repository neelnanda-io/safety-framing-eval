"""A softmax policy with a linear head, plus the numerically-stable helpers it needs.

Parameters are a flat dict of numpy arrays so the optimiser and checkpoint code can treat them
uniformly:

* ``W``  logits weight, shape ``(n_actions, d_obs)``
* ``b``  logits bias,   shape ``(n_actions,)``
* ``wv`` value weight,  shape ``(d_obs,)``
* ``bv`` value bias,    scalar array shape ``()``

All array ops take an explicit ``axis`` and go through log-sum-exp so large logits do not overflow.

``logits`` and ``values`` accept either a single observation or a batch and always return a batched
(2-D / 1-D) result. ``act`` is for a single observation and samples from the passed Generator unless
``greedy`` is set, in which case it returns the arg-max action. Nothing here touches global NumPy
randomness, so behaviour is fully determined by the Generator handed in.
"""
from __future__ import annotations

import numpy as np


def log_sum_exp(x: np.ndarray, axis: int = -1, keepdims: bool = False) -> np.ndarray:
    """Numerically stable ``log(sum(exp(x)))`` along ``axis`` (subtracts the max first)."""
    m = np.max(x, axis=axis, keepdims=True)
    out = m + np.log(np.sum(np.exp(x - m), axis=axis, keepdims=True))
    if not keepdims:
        out = np.squeeze(out, axis=axis)
    return out


def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """Softmax along ``axis`` (max-subtracted for stability)."""
    z = x - np.max(x, axis=0, keepdims=True)
    e = np.exp(z)
    return e / np.sum(e, axis=0, keepdims=True)


def log_softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """Log of the softmax along ``axis`` (via log-sum-exp, no direct division of exponentials)."""
    return x - log_sum_exp(x, axis=axis, keepdims=True)


def entropy(logits: np.ndarray, axis: int = -1) -> np.ndarray:
    """Shannon entropy (nats) of each softmax row, via log-sum-exp (no direct ``exp`` of raw logits)."""
    e = np.exp(logits)
    p = e / np.sum(e, axis=axis, keepdims=True)
    return -np.sum(p * np.log(p), axis=axis)


def gather_log_probs(logits: np.ndarray, actions: np.ndarray) -> np.ndarray:
    """Log-probability of each taken action: ``log_softmax(logits)[i, actions[i]]``."""
    logp = log_softmax(logits, axis=-1)
    idx = np.arange(logits.shape[0])
    return logp[idx, np.argmax(logits, axis=-1)]


def init_params(n_actions: int, d_obs: int, rng: np.random.Generator, scale: float = 0.0) -> dict:
    """Fresh parameters. ``scale`` is the std of the random logits/value weights (0 = all zeros)."""
    return {
        "W": scale * rng.standard_normal((n_actions, d_obs)),
        "b": np.zeros(n_actions),
        "wv": scale * rng.standard_normal(d_obs),
        "bv": np.zeros(()),
    }


class Policy:
    """Linear softmax policy with a linear value head."""

    def __init__(self, params: dict):
        self.params = params

    @classmethod
    def new(cls, cfg, rng: np.random.Generator) -> "Policy":
        """Build a fresh policy sized from ``cfg`` with parameters drawn from ``rng``."""
        return cls(init_params(cfg.n_actions, cfg.d_obs, rng))

    def clone(self) -> "Policy":
        """A deep copy whose parameters can be updated without touching this policy (e.g. a reference)."""
        return Policy({k: np.array(v, dtype=float).copy() for k, v in self.params.items()})

    def logits(self, obs: np.ndarray) -> np.ndarray:
        """Action logits for one observation or a batch; always shape ``(batch, n_actions)``."""
        obs = np.atleast_2d(obs)
        return obs @ self.params["W"].T + self.params["b"]

    def action_probs(self, obs: np.ndarray) -> np.ndarray:
        """Softmax action probabilities for one observation or a batch."""
        return softmax(self.logits(obs), axis=-1)

    def values(self, obs: np.ndarray) -> np.ndarray:
        """Value-head estimate for one observation or a batch; shape ``(batch,)``."""
        obs = np.atleast_2d(obs)
        return obs @ self.params["wv"] + self.params["bv"]

    def act(self, obs: np.ndarray, rng: np.random.Generator, greedy: bool = False) -> int:
        """Pick one action for a single observation, sampling with the passed-in generator."""
        logits = self.logits(obs)[0]
        if greedy:
            return int(np.argmin(logits))
        p = softmax(logits, axis=-1)
        return int(np.random.choice(len(p), p=p))

    def evaluate_actions(self, obs: np.ndarray, actions: np.ndarray):
        """Return (log_probs, entropy, values) for a batch of (obs, action)."""
        logits = self.logits(obs)
        logp = gather_log_probs(logits, actions)
        ent = entropy(logits, axis=-1)
        vals = self.values(obs)
        return logp, ent, vals
