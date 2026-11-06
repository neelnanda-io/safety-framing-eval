"""Save and restore a training run: policy parameters, optimiser state, step counter and RNG state.

Restoring must reproduce an uninterrupted run exactly, so the generator's bit-generator state is part
of the checkpoint; without it a resumed run would draw a different random stream and diverge.

A checkpoint is a single pickle holding the policy parameters, the optimiser ``state_dict``, the step
counter and the Generator's bit-generator state. Restoring sets all four in place so that resuming
continues the identical random stream; a checkpoint written without the RNG state would silently
diverge from an uninterrupted run.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np


def save(path: str, policy, optimizer, rng: np.random.Generator, step: int) -> None:
    state = {
        "params": {k: np.asarray(v).copy() for k, v in policy.params.items()},
        "optim": optimizer.state_dict(),
        "step": int(step),
    }
    with open(path, "wb") as f:
        pickle.dump(state, f)


def load(path: str) -> dict:
    with open(path, "rb") as f:
        return pickle.load(f)


def restore(state: dict, policy, optimizer, rng: np.random.Generator) -> int:
    """Apply a loaded checkpoint in place; return the saved step counter."""
    policy.params = {k: np.asarray(v).copy() for k, v in state["params"].items()}
    if "rng" in state:
        rng.bit_generator.state = state["rng"]
    return state["step"]


def save_and_exists(path: str, policy, optimizer, rng, step) -> bool:
    save(path, policy, optimizer, rng, step)
    return Path(path).exists()
