"""Episode-level feature extraction for the scorer.

The {{SCORER_NOUN}} never sees raw observations; it sees a handful of summary features of an episode's action
sequence. Keeping them here (rather than inside the scorer) means the same features can be logged and
inspected during evaluation. Every feature is scaled to [0, 1] so the fixed linear {{SCORER_NOUN}} stays
roughly calibrated regardless of episode length.

Order matters: the {{SCORER_NOUN}}'s fixed weight vector lines up with ``[extra_fraction, action_diversity,
any_extra]`` in that order. ``extra_fraction`` is a mean (not a raw count) so it does not grow with
episode length, and an empty episode yields all-zero features rather than raising.
"""
from __future__ import annotations

import numpy as np


def action_histogram(actions: np.ndarray, n_actions: int) -> np.ndarray:
    """Normalised count of each action (sums to 1 for a non-empty episode)."""
    actions = np.asarray(actions, dtype=int)
    counts = np.bincount(actions, minlength=n_actions).astype(float)
    total = counts.sum()
    if total == 0:
        return counts
    return counts / total


def extra_fraction(actions: np.ndarray, extra_action: int) -> float:
    """Fraction of steps that played the extra action."""
    actions = np.asarray(actions, dtype=int)
    if actions.size == 0:
        return 0.0
    return float(np.mean(actions == extra_action))


def action_diversity(actions: np.ndarray, n_actions: int) -> float:
    """Number of distinct actions used, divided by the number of available actions."""
    actions = np.asarray(actions, dtype=int)
    if actions.size == 0:
        return 0.0
    return len(np.unique(actions)) / n_actions


def episode_features(actions: np.ndarray, n_actions: int, extra_action: int) -> np.ndarray:
    """The three {{SCORER_NOUN}} features: extra-action fraction, action diversity, and an 'any extra' flag."""
    actions = np.asarray(actions, dtype=int)
    if actions.size == 0:
        return np.zeros(3)
    f0 = extra_fraction(actions, extra_action)
    f1 = action_diversity(actions, n_actions)
    f2 = 1.0 if np.any(actions == extra_action) else 0.0
    return np.array([f0, f1, f2])
