"""Configuration for the {{PROJECT_TITLE}} pipeline.

A run is described by one JSON file with four sections - `sae`, `train`, `analysis` and `paths` - and any key
the file leaves out falls back to the defaults below. On the command line, `--set section.key=value` overrides
are applied on top of the file (see docs/DESIGN.md, "Configuration").
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

POS_LABEL = "{{POS}}"
NEG_LABEL = "{{NEG}}"
LABELS = (POS_LABEL, NEG_LABEL)


@dataclass
class SAEConfig:
    d_model: int = 16
    d_sae: int = 32
    activation: str = "relu"        # "relu" or "topk"
    k: int = 4                      # active latents per token when activation == "topk"
    init_seed: int = 0


@dataclass
class TrainConfig:
    lr: float = 3e-3
    beta1: float = 0.9
    beta2: float = 0.999
    eps: float = 1e-8
    lr_decay: str = "none"          # "none" or "linear" (to zero at `steps`)
    batch_size: int = 64
    steps: int = 400
    warmup_steps: int = 20
    l1_coeff: float = 0.1
    max_grad_norm: float = 1.0      # 0 disables clipping
    dead_window: int = 150          # optimiser steps without firing before a latent counts as dead
    resample_every: int = 200       # 0 disables resampling
    resample_sample_size: int = 256
    checkpoint_every: int = 0       # 0 disables periodic checkpoints
    shuffle_seed: int = 0


@dataclass
class AnalysisConfig:
    batch_size: int = 256
    top_k_examples: int = 8
    context_window: int = 3
    min_freq: float = 1e-3
    max_freq: float = 0.5
    alpha: float = 0.05
    n_candidates: int = 5
    heldout_frac: float = 0.3
    split_seed: int = 0
    steer_mode: str = "zero"        # "zero" or "mean"


@dataclass
class PathsConfig:
    store_root: str = "cache/acts"
    run_dir: str = "runs/latest"
    hook: str = "resid_post_6"
    cache_dir: str = ""             # "" keeps the feature-stats cache in memory only


@dataclass
class PipelineConfig:
    sae: SAEConfig = field(default_factory=SAEConfig)
    train: TrainConfig = field(default_factory=TrainConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)

    def to_dict(self) -> dict:
        return asdict(self)


SECTIONS = {"sae": SAEConfig, "train": TrainConfig, "analysis": AnalysisConfig, "paths": PathsConfig}

# The defaults as a nested dict; the config file and then the CLI overrides are merged on top of it.
DEFAULTS: dict = PipelineConfig().to_dict()


def deep_merge(base: dict, override: dict) -> dict:
    """Merge `override` into `base` recursively: nested dicts are merged key by key, other values replaced."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def parse_override(item: str) -> tuple[list[str], object]:
    """Parse one `section.key=value` override. The value is read as JSON when it parses, else kept as a string."""
    if "=" not in item:
        raise ValueError(f"override {item!r} is not of the form section.key=value")
    key, raw = item.split("=", 1)
    path = [p for p in key.strip().split(".") if p]
    if len(path) != 2:
        raise ValueError(f"override key {key!r} must look like section.key")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    return path, value


def overrides_to_dict(overrides) -> dict:
    out: dict = {}
    for item in overrides:
        (section, key), value = parse_override(item)
        out.setdefault(section, {})[key] = value
    return out


def load_config(path: str | Path | None = None, overrides=()) -> PipelineConfig:
    """Build the run configuration from the defaults, the JSON file at `path` (if any) and the overrides."""
    raw: dict = {}
    if path is not None:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: the config file must contain a JSON object")
    merged = deep_merge(DEFAULTS, raw)
    merged = deep_merge(merged, overrides_to_dict(overrides))
    return from_dict(merged)


def from_dict(d: dict) -> PipelineConfig:
    unknown = set(d) - set(SECTIONS)
    if unknown:
        raise ValueError(f"unknown config section(s): {sorted(unknown)}")
    built = {}
    for name, cls in SECTIONS.items():
        section = d.get(name) or {}
        if not isinstance(section, dict):
            raise ValueError(f"config section {name!r} must be an object")
        allowed = {f.name for f in fields(cls)}
        bad = set(section) - allowed
        if bad:
            raise ValueError(f"unknown key(s) in config section {name!r}: {sorted(bad)}")
        built[name] = cls(**section)
    cfg = PipelineConfig(**built)
    validate(cfg)
    return cfg


def validate(cfg: PipelineConfig) -> None:
    s, t, a = cfg.sae, cfg.train, cfg.analysis
    if s.d_model <= 0 or s.d_sae <= 0:
        raise ValueError("sae.d_model and sae.d_sae must be positive")
    if s.activation not in ("relu", "topk"):
        raise ValueError(f"sae.activation must be 'relu' or 'topk', got {s.activation!r}")
    if s.activation == "topk" and not 1 <= s.k <= s.d_sae:
        raise ValueError("sae.k must be between 1 and sae.d_sae")
    if t.batch_size <= 0 or t.steps < 0 or t.warmup_steps < 0:
        raise ValueError("train.batch_size must be positive; train.steps and train.warmup_steps non-negative")
    if t.lr_decay not in ("none", "linear"):
        raise ValueError(f"train.lr_decay must be 'none' or 'linear', got {t.lr_decay!r}")
    if t.dead_window <= 0:
        raise ValueError("train.dead_window must be positive")
    if not 0.0 < a.heldout_frac < 1.0:
        raise ValueError("analysis.heldout_frac must be strictly between 0 and 1")
    if not 0.0 <= a.min_freq <= a.max_freq <= 1.0:
        raise ValueError("need 0 <= analysis.min_freq <= analysis.max_freq <= 1")
    if a.steer_mode not in ("zero", "mean"):
        raise ValueError(f"analysis.steer_mode must be 'zero' or 'mean', got {a.steer_mode!r}")
    if a.top_k_examples <= 0 or a.context_window < 0 or a.n_candidates <= 0:
        raise ValueError("analysis.top_k_examples and n_candidates must be positive, context_window >= 0")


def save_config(cfg: PipelineConfig, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, indent=2, sort_keys=True)
