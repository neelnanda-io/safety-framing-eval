"""On-disk cache of residual-stream activations for labelled {{TRANSCRIPTS}}.

One directory per hook point under the store root:

    <root>/<hook>/index.json        d_model, dtype, shard list, sequence offsets, labels, data hash
    <root>/<hook>/shard_00000.bin   activations, row-major [rows_in_shard, d_model], written with ndarray.tofile
    <root>/<hook>/tokens.json       transcript tokens, one list per sequence
    <root>/<hook>/probe.json        (optional) the {{PROBE}} for this hook: {"w": [...], "b": ...}

Rows are tokens in transcript order: sequence i occupies rows offsets[i] .. offsets[i + 1] - 1. Readers always
return float32 arrays, whatever the dtype on disk.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

INDEX_NAME = "index.json"
TOKENS_NAME = "tokens.json"
PROBE_NAME = "probe.json"
SUPPORTED_DTYPES = ("float32", "float16")
FORMAT_VERSION = 2


def write_store(root, hook: str, acts, tokens, labels, shard_tokens: int = 512, dtype: str = "float32"):
    """Write one hook's activations, tokens and labels; returns the opened ActivationStore."""
    acts = np.asarray(acts)
    if acts.ndim != 2:
        raise ValueError(f"acts must be 2-D [n_tokens, d_model], got shape {acts.shape}")
    if len(tokens) != len(labels):
        raise ValueError(f"{len(tokens)} token sequences but {len(labels)} labels")
    lengths = [len(t) for t in tokens]
    if any(n == 0 for n in lengths):
        raise ValueError("empty sequences are not supported")
    if sum(lengths) != acts.shape[0]:
        raise ValueError(f"the sequences have {sum(lengths)} tokens but acts has {acts.shape[0]} rows")
    if dtype not in SUPPORTED_DTYPES:
        raise ValueError(f"dtype must be one of {SUPPORTED_DTYPES}, got {dtype!r}")
    if shard_tokens <= 0:
        raise ValueError("shard_tokens must be positive")
    tokens = [[str(t) for t in seq] for seq in tokens]
    labels = [str(label) for label in labels]
    d = Path(root) / hook
    d.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    shards = []
    for i, start in enumerate(range(0, acts.shape[0], shard_tokens)):
        block = np.ascontiguousarray(acts[start:start + shard_tokens], dtype=dtype)
        name = f"shard_{i:05d}.bin"
        block.tofile(d / name)
        digest.update(block.tobytes())
        shards.append({"file": name, "n_tokens": int(block.shape[0])})
    digest.update(json.dumps(tokens).encode("utf-8"))
    digest.update(json.dumps(labels).encode("utf-8"))
    index = {
        "version": FORMAT_VERSION,
        "hook": hook,
        "d_model": int(acts.shape[1]),
        "dtype": dtype,
        "shards": shards,
        "offsets": [0] + np.cumsum(lengths).tolist(),
        "labels": labels,
        "data_hash": digest.hexdigest()[:16],
    }
    (d / TOKENS_NAME).write_text(json.dumps(tokens), encoding="utf-8")
    (d / INDEX_NAME).write_text(json.dumps(index, indent=1), encoding="utf-8")
    return ActivationStore(root, hook)


class ActivationStore:
    """Read-only view of one hook's activations."""

    def __init__(self, root, hook: str):
        self.root = Path(root)
        self.hook = hook
        self.dir = self.root / hook
        index_path = self.dir / INDEX_NAME
        if not index_path.exists():
            raise FileNotFoundError(f"no activation store for hook {hook!r} under {self.root}")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if index.get("version") != FORMAT_VERSION:
            raise ValueError(f"{index_path}: unsupported store version {index.get('version')!r}")
        self.index = index
        self.d_model = int(index["d_model"])
        self.dtype = np.dtype(index["dtype"])
        self.shards = index["shards"]
        self._starts = np.concatenate([[0], np.cumsum([s["n_tokens"] for s in self.shards])]).astype(np.int64)
        self.offsets = np.asarray(index["offsets"], dtype=np.int64)
        self.labels = list(index["labels"])
        self.data_hash = index["data_hash"]
        self._tokens = None
        if int(self.offsets[-1]) != int(self._starts[-1]):
            raise ValueError(f"{index_path}: offsets cover {self.offsets[-1]} tokens, shards {self._starts[-1]}")

    # -- sizes and metadata -------------------------------------------------------------------------------
    @property
    def n_tokens(self) -> int:
        return int(self._starts[-1])

    @property
    def n_seqs(self) -> int:
        return len(self.labels)

    def __len__(self) -> int:
        return self.n_tokens

    @property
    def tokens(self) -> list[list[str]]:
        if self._tokens is None:
            self._tokens = json.loads((self.dir / TOKENS_NAME).read_text(encoding="utf-8"))
        return self._tokens

    def sequence_ids(self) -> np.ndarray:
        """The sequence index of every token row."""
        return np.repeat(np.arange(self.n_seqs), np.diff(self.offsets))

    def token_mask(self, label: str) -> np.ndarray:
        """Boolean mask over token rows: True for tokens of sequences with the given label."""
        is_label = np.array([lab == label for lab in self.labels], dtype=bool)
        return np.repeat(is_label, np.diff(self.offsets))

    def locate(self, row: int) -> tuple[int, int]:
        """(sequence index, position within the sequence) of a token row."""
        if not 0 <= row < self.n_tokens:
            raise IndexError(f"row {row} out of range for {self.n_tokens} tokens")
        seq = int(np.searchsorted(self.offsets, row, side="right") - 1)
        return seq, int(row - self.offsets[seq])

    # -- reading ------------------------------------------------------------------------------------------
    def _read_shard(self, i: int, start: int = 0, count: int | None = None) -> np.ndarray:
        n = int(self.shards[i]["n_tokens"])
        if count is None:
            count = n - start
        if start < 0 or count < 0 or start + count > n:
            raise IndexError(f"rows {start}..{start + count} out of range for shard {i} ({n} rows)")
        data = np.fromfile(self.dir / self.shards[i]["file"], dtype=self.dtype, count=count * self.d_model,
                           offset=start * self.d_model * self.dtype.itemsize)
        return data.reshape(count, self.d_model).astype(np.float32)

    def read(self, start: int, stop: int) -> np.ndarray:
        """Rows [start, stop) as a float32 array."""
        if not 0 <= start <= stop <= self.n_tokens:
            raise IndexError(f"cannot read rows {start}..{stop} of {self.n_tokens}")
        parts = []
        pos = start
        i = int(np.searchsorted(self._starts, start, side="right") - 1)
        while pos < stop:
            s0, s1 = int(self._starts[i]), int(self._starts[i + 1])
            take = min(stop, s1) - pos
            parts.append(self._read_shard(i, pos - s0, take))
            pos += take
            i += 1
        if not parts:
            return np.zeros((0, self.d_model), dtype=np.float32)
        return np.concatenate(parts, axis=0)

    def all_acts(self) -> np.ndarray:
        return np.concatenate([self._read_shard(i) for i in range(len(self.shards))], axis=0)

    def iter_batches(self, batch_size: int, shuffle: bool = False, seed: int = 0, drop_last: bool = False):
        """Yield [batch, d_model] float32 batches covering the store once (shuffled rows if `shuffle`)."""
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        n = self.n_tokens
        if shuffle:
            acts = self.all_acts()
            order = np.random.default_rng(seed).permutation(n)
            for i in range(0, n, batch_size):
                idx = order[i:i + batch_size]
                if drop_last and len(idx) < batch_size:
                    return
                yield acts[idx]
            return
        for i in range(0, n, batch_size):
            stop = min(n, i + batch_size)
            if drop_last and stop - i < batch_size:
                return
            yield self.read(i, stop)


def compute_norm_scale(store, max_tokens: int | None = None, chunk: int = 1024) -> float:
    """Scale s with mean ||s * x||^2 = d_model over the store (DESIGN, "Normalisation")."""
    n = store.n_tokens if max_tokens is None else min(int(max_tokens), store.n_tokens)
    if n <= 0:
        raise ValueError("cannot compute a normalisation scale from an empty store")
    total = 0.0
    for start in range(0, n, chunk):
        x = store.read(start, min(n, start + chunk)).astype(np.float64)
        total += float(np.sum(x * x))
    mean_sq = total / n
    if mean_sq <= 0:
        raise ValueError("activations are all zero; cannot normalise")
    return float(np.sqrt(store.d_model / mean_sq))


def save_probe(root, hook: str, w, b: float) -> None:
    d = Path(root) / hook
    d.mkdir(parents=True, exist_ok=True)
    payload = {"w": [float(v) for v in np.asarray(w).ravel()], "b": float(b)}
    (d / PROBE_NAME).write_text(json.dumps(payload), encoding="utf-8")


def load_probe(root, hook: str) -> tuple[np.ndarray, float] | None:
    """The {{PROBE}} for a hook as (w, b), or None if the store has none."""
    p = Path(root) / hook / PROBE_NAME
    if not p.exists():
        return None
    payload = json.loads(p.read_text(encoding="utf-8"))
    return np.asarray(payload["w"], dtype=np.float64), float(payload["b"])


def list_hooks(root) -> list[str]:
    root = Path(root)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if (p / INDEX_NAME).exists())
