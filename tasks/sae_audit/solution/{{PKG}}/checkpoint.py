"""SAE checkpoints: one directory per checkpoint.

    <dir>/meta.json             everything needed to rebuild the SAE, plus the normalisation scale and hook
    <dir>/params/<name>.bin     float32 parameters, written with ndarray.tofile
    <dir>/optim.json            (optional) Adam state for resuming
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .sae import PARAM_NAMES, SparseAutoencoder

META_NAME = "meta.json"
OPTIM_NAME = "optim.json"
CHECKPOINT_FORMAT = 1


@dataclass
class Checkpoint:
    sae: SparseAutoencoder
    norm_scale: float
    step: int
    hook: str
    config: dict = field(default_factory=dict)
    path: str | None = None


def save_checkpoint(path, sae: SparseAutoencoder, norm_scale: float, step: int, hook: str,
                    config: dict | None = None, opt=None) -> Path:
    d = Path(path)
    (d / "params").mkdir(parents=True, exist_ok=True)
    shapes = {}
    for name in PARAM_NAMES:
        arr = np.ascontiguousarray(sae.params[name], dtype=np.float32)
        arr.tofile(d / "params" / f"{name}.bin")
        shapes[name] = list(arr.shape)
    meta = {
        "format": CHECKPOINT_FORMAT,
        "d_model": sae.d_model,
        "d_sae": sae.d_sae,
        "activation": sae.activation,
        "k": sae.k,
        "norm_scale": float(norm_scale),
        "step": int(step),
        "hook": hook,
        "config": config or {},
        "shapes": shapes,
    }
    (d / META_NAME).write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    if opt is not None:
        state = opt.state_dict()
        state["m"] = {k: v.tolist() for k, v in state["m"].items()}
        state["v"] = {k: v.tolist() for k, v in state["v"].items()}
        (d / OPTIM_NAME).write_text(json.dumps(state), encoding="utf-8")
    return d


def load_checkpoint(path) -> Checkpoint:
    d = Path(path)
    meta_path = d / META_NAME
    if not meta_path.exists():
        raise FileNotFoundError(f"no checkpoint at {d}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("format") != CHECKPOINT_FORMAT:
        raise ValueError(f"{meta_path}: unsupported checkpoint format {meta.get('format')!r}")
    sae = SparseAutoencoder(meta["d_model"], meta["d_sae"], activation=meta["activation"], k=meta["k"])
    params = {}
    for name in PARAM_NAMES:
        raw = np.fromfile(d / "params" / f"{name}.bin", dtype=np.float32)
        params[name] = raw.reshape(meta["shapes"][name]).astype(np.float64)
    sae.set_params(params)
    return Checkpoint(sae=sae, norm_scale=float(meta["norm_scale"]), step=int(meta["step"]), hook=meta["hook"],
                      config=meta.get("config", {}), path=str(d))


def load_optimizer_state(path) -> dict | None:
    p = Path(path) / OPTIM_NAME
    if not p.exists():
        return None
    state = json.loads(p.read_text(encoding="utf-8"))
    state["m"] = {k: np.asarray(v, dtype=np.float64) for k, v in state["m"].items()}
    state["v"] = {k: np.asarray(v, dtype=np.float64) for k, v in state["v"].items()}
    return state


_STEP_DIR = re.compile(r"^step_(\d+)$")


def list_checkpoints(checkpoint_dir) -> list[Path]:
    """The `step_<n>` checkpoints under `checkpoint_dir` that contain a meta.json, ordered by step n."""
    d = Path(checkpoint_dir)
    if not d.exists():
        return []
    found = []
    for p in d.iterdir():
        m = _STEP_DIR.match(p.name)
        if m and p.is_dir() and (p / META_NAME).exists():
            found.append((int(m.group(1)), p))
    return [p for _, p in sorted(found)]


def latest_checkpoint(checkpoint_dir) -> Path | None:
    found = list_checkpoints(checkpoint_dir)
    return found[-1] if found else None
