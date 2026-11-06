"""Seeding helpers: turn one master seed into reproducible, independent generators.

A run is reproducible only if every source of randomness is derived from one seed. ``make_rng``
normalises an int-or-Generator into a Generator, and ``child_rngs`` splits a master seed into
independent sub-streams via NumPy's ``SeedSequence`` so, for example, the environment and the policy
can each have their own stream without correlating.
"""
from __future__ import annotations

import numpy as np


def make_rng(seed) -> np.random.Generator:
    """Return a Generator: pass an int to seed a fresh one, or an existing Generator through unchanged."""
    if isinstance(seed, np.random.Generator):
        return seed
    return np.random.default_rng(seed)


def child_rngs(seed: int, n: int) -> list:
    """Split ``seed`` into ``n`` independent child generators (reproducible, non-overlapping streams)."""
    ss = np.random.SeedSequence(seed)
    return [np.random.default_rng(child) for child in ss.spawn(n)]


def reseed(rng: np.random.Generator, seed: int) -> None:
    """Reset a generator in place to the stream for ``seed`` (handy between evaluation passes)."""
    fresh = np.random.default_rng(seed)
    rng.bit_generator.state = fresh.bit_generator.state
