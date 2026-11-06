"""Memoised per-latent statistics, keyed by checkpoint, dataset and analysis parameters."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


def fingerprint_checkpoint(ckpt_dir) -> str:
    """Content fingerprint of a checkpoint directory."""
    d = Path(ckpt_dir)
    if not d.exists():
        raise FileNotFoundError(f"no checkpoint at {d}")
    meta = d / "meta.json"
    if not meta.exists():
        raise FileNotFoundError(f"no checkpoint metadata at {meta}")
    return hashlib.sha256(meta.read_bytes()).hexdigest()[:20]


class StatsCache:
    """In-memory memo of dicts of numpy arrays (feature statistics), optionally persisted to a JSON file."""

    def __init__(self):
        self._mem: dict[str, dict] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def make_key(ckpt_fp: str, data_hash: str, params: dict) -> str:
        blob = json.dumps({"ckpt": ckpt_fp, "params": params}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]

    def __len__(self) -> int:
        return len(self._mem)

    def get_or_compute(self, ckpt_fp: str, data_hash: str, params: dict, compute) -> dict:
        key = self.make_key(ckpt_fp, data_hash, params)
        if key in self._mem:
            self.hits += 1
            return self._mem[key]
        self.misses += 1
        value = {name: np.asarray(arr) for name, arr in compute().items()}
        self._mem[key] = value
        return value

    def save(self, path) -> None:
        """Write the whole memo to `path` as JSON (arrays keep their dtype and shape)."""
        raise NotImplementedError

    @classmethod
    def load(cls, path) -> "StatsCache":
        """Read a memo written by `save`; values come back as numpy arrays."""
        raise NotImplementedError
