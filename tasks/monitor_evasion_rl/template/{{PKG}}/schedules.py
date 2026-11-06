"""Scalar schedules for annealing the learning rate and the entropy coefficient over training.

A schedule maps a progress fraction in [0, 1] to a value; callers pass ``step / total_steps``. The
fraction is clamped, so a schedule is well defined even if a caller overshoots the planned horizon.
"""
from __future__ import annotations

import numpy as np


def _clamp01(frac: float) -> float:
    """Clamp a progress fraction into [0, 1]."""
    return min(1.0, max(0.0, float(frac)))


def linear_schedule(start: float, end: float, frac: float) -> float:
    """Linear interpolation: ``start`` at frac 0, ``end`` at frac 1 (frac clamped to [0, 1])."""
    return start + (end - start) * float(frac)


def cosine_schedule(start: float, end: float, frac: float) -> float:
    """Cosine interpolation from ``start`` (frac 0) down to ``end`` (frac 1)."""
    frac = _clamp01(frac)
    return end + 0.5 * (start - end) * (1.0 - np.cos(np.pi * frac))


def anneal_lr(cfg, step: int, total_steps: int) -> float:
    """Linearly anneal the learning rate from ``cfg.lr`` to zero across the run."""
    return linear_schedule(cfg.lr, 0.0, step / max(1, total_steps))


def anneal_entropy(cfg, step: int, total_steps: int) -> float:
    """Linearly anneal the entropy coefficient from ``cfg.ent_coef`` to zero across the run."""
    return linear_schedule(cfg.ent_coef, 0.0, step / max(1, total_steps))
