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
    h = hashlib.sha256()
    for p in sorted(q for q in d.rglob("*") if q.is_file()):
        h.update(str(p.relative_to(d)).encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()[:20]


def _copy_value(value: dict) -> dict:
    return {k: (np.array(v, copy=True) if isinstance(v, np.ndarray) else v) for k, v in value.items()}


class StatsCache:
    """In-memory memo of dicts of numpy arrays (feature statistics), optionally persisted to a JSON file."""

    def __init__(self):
        self._mem: dict[str, dict] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def make_key(ckpt_fp: str, data_hash: str, params: dict) -> str:
        blob = json.dumps({"ckpt": ckpt_fp, "data": data_hash, "params": params}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]

    def __len__(self) -> int:
        return len(self._mem)

    def get_or_compute(self, ckpt_fp: str, data_hash: str, params: dict, compute) -> dict:
        key = self.make_key(ckpt_fp, data_hash, params)
        if key in self._mem:
            self.hits += 1
            return _copy_value(self._mem[key])
        self.misses += 1
        value = {name: np.asarray(arr) for name, arr in compute().items()}
        self._mem[key] = _copy_value(value)
        return _copy_value(value)

    def save(self, path) -> None:
        """Write the whole memo to `path` as JSON (arrays keep their dtype and shape)."""
        payload = {key: {name: {"dtype": str(arr.dtype), "shape": list(arr.shape), "data": arr.ravel().tolist()}
                         for name, arr in value.items()}
                   for key, value in self._mem.items()}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "StatsCache":
        """Read a memo written by `save`; values come back as numpy arrays."""
        cache = cls()
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        for key, value in payload.items():
            cache._mem[key] = {name: np.asarray(entry["data"], dtype=entry["dtype"]).reshape(entry["shape"])
                               for name, entry in value.items()}
        return cache
