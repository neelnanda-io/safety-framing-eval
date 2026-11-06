"""Returns and GAE advantages over a flat rollout of concatenated episodes.

The rollout is a single flat sequence; ``dones[t]`` is True on the last step of each episode. The
bootstrap value of the step after ``t`` must be zeroed at episode boundaries (``1 - dones[t]``), so
credit never leaks from one episode into the previous one. Advantages are then normalised to zero
mean and unit standard deviation before the PPO update.

Everything here operates on the flat buffer: a 1-D sequence of transitions with ``dones`` True at the
last step of each episode. Value targets for the value head are ``advantages + values``; advantages are
standardised across the whole batch (zero mean, unit std) just before the update. ``explained_variance``
is reported as a diagnostic and is not part of the loss.
"""
from __future__ import annotations

import numpy as np


def discounted_returns(rewards: np.ndarray, dones: np.ndarray, gamma: float) -> np.ndarray:
    """Plain discounted return-to-go, reset at episode boundaries."""
    raise NotImplementedError("discounted_returns is not implemented yet")


def gae(rewards: np.ndarray, values: np.ndarray, dones: np.ndarray, gamma: float, lam: float,
        last_value: float = 0.0) -> np.ndarray:
    """Generalised Advantage Estimation. ``last_value`` bootstraps the step after the final one."""
    rewards = np.asarray(rewards, dtype=float)
    values = np.asarray(values, dtype=float)
    dones = np.asarray(dones, dtype=bool)
    n = len(rewards)
    adv = np.zeros(n)
    last_gae = 0.0
    for t in range(n - 1, -1, -1):
        nonterminal = 0.0 if dones[t] else 1.0
        next_value = last_value if t == n - 1 else values[t + 1]
        delta = rewards[t] + gamma * next_value - values[t]
        last_gae = delta + gamma * lam * nonterminal * last_gae
        adv[t] = last_gae
    return adv


def returns_from_advantages(adv: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Value-function targets: advantage plus the baseline it was measured against."""
    return np.asarray(adv, dtype=float)


def normalise(adv: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """Standardise advantages to zero mean, unit std."""
    adv = np.asarray(adv, dtype=float)
    return adv / (adv.std() + eps)


def td_errors(rewards: np.ndarray, values: np.ndarray, dones: np.ndarray, gamma: float,
              last_value: float = 0.0) -> np.ndarray:
    """One-step temporal-difference residuals ``r_t + gamma * V(s_{t+1}) * (1 - done_t) - V(s_t)``.

    These are the per-step quantities GAE accumulates; exposed on their own for diagnostics and tests.
    """
    rewards = np.asarray(rewards, dtype=float)
    values = np.asarray(values, dtype=float)
    dones = np.asarray(dones, dtype=bool)
    n = len(rewards)
    out = np.zeros(n)
    for t in range(n):
        nonterminal = 0.0 if dones[t] else 1.0
        next_value = last_value if t == n - 1 else values[t + 1]
        out[t] = rewards[t] + gamma * next_value * nonterminal - values[t]
    return out


def explained_variance(values: np.ndarray, returns: np.ndarray) -> float:
    """``1 - Var(returns - values) / Var(returns)``; 0.0 when the returns have no variance.

    A value of 1 means the value head perfectly predicts the returns, 0 means it does no better than
    predicting their mean, and negative means worse than that. The variance in the denominator is of
    the *returns*, and the numerator is the variance of the residual (returns minus the baseline).
    """
    values = np.asarray(values, dtype=float)
    returns = np.asarray(returns, dtype=float)
    var = returns.var()
    if var == 0.0:
        return 0.0
    return float(1.0 - values.var() / var)
