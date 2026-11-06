"""Experiment configuration: a dataclass plus a tiny JSON / TOML-lite loader.

No YAML and no third-party config libraries. A config file is either a `.json` object or a
`.toml`-style file of `key = value` lines (`#` comments, `[section]` headers ignored, inline
comments stripped). Unknown keys are rejected so a typo in a config never passes silently.

Resolution order: values from the file first, then any ``overrides`` dict on top; the result is
validated before it is returned. Scalars are coerced to each field's declared type (ints stay
ints, not floats), booleans are parsed from ``true``/``false``, and inline ``#`` comments are
stripped from unquoted values. Validation is deliberately strict: an out-of-range probability, a
non-positive weight or a bad action count raises ValueError rather than training on nonsense.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class Config:
    # environment
    seed: int = 0
    n_actions: int = 5
    n_task_actions: int = 4           # actions 0..n_task_actions-1 are task actions; action n_task_actions is the extra action
    d_obs: int = 8
    max_steps: int = 6
    obs_noise: float = 0.1
    # policy / optimisation
    lr: float = 0.05
    gamma: float = 0.99
    lam: float = 0.95
    clip_eps: float = 0.2
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    max_grad_norm: float = 1.0
    n_epochs: int = 4
    minibatch_size: int = 16
    rollout_episodes: int = 8
    # KL-to-reference penalty (adaptive)
    kl_coef: float = 0.1
    kl_target: float = 0.01
    kl_adapt_factor: float = 1.5
    # reward shaping
    w_task: float = 1.0
    w_bonus: float = 0.5
    w_penalty: float = 1.0
    reward_clip: float = 10.0
    # {{SCORER_NOUN}} / evaluation
    threshold: float = 0.5

    def validate(self) -> "Config":
        if self.n_task_actions < 1:
            raise ValueError("n_task_actions must be >= 1")
        if self.n_actions <= self.n_task_actions:
            raise ValueError("n_actions must exceed n_task_actions (need one extra action)")
        if self.d_obs < self.n_task_actions:
            raise ValueError("d_obs must be at least n_task_actions (the goal is one-hot encoded)")
        if self.max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        if not 0.0 <= self.gamma <= 1.0:
            raise ValueError("gamma must lie in [0, 1]")
        if not 0.0 <= self.lam <= 1.0:
            raise ValueError("lam must lie in [0, 1]")
        if self.clip_eps <= 0.0:
            raise ValueError("clip_eps must be > 0")
        if self.lr <= 0.0:
            raise ValueError("lr must be > 0")
        if self.ent_coef < 0.0 or self.vf_coef < 0.0:
            raise ValueError("ent_coef and vf_coef must be >= 0")
        if self.n_epochs < 1:
            raise ValueError("n_epochs must be >= 1")
        if self.minibatch_size < 1:
            raise ValueError("minibatch_size must be >= 1")
        if self.rollout_episodes < 1:
            raise ValueError("rollout_episodes must be >= 1")
        if self.kl_adapt_factor <= 1.0:
            raise ValueError("kl_adapt_factor must be > 1")
        if self.kl_target <= 0.0:
            raise ValueError("kl_target must be > 0")
        if self.obs_noise < 0.0:
            raise ValueError("obs_noise must be >= 0")
        if self.reward_clip <= 0.0:
            raise ValueError("reward_clip must be > 0")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("threshold must lie in [0, 1]")
        return self


_FIELD_TYPES = {f.name: f.type for f in fields(Config)}


def _coerce(key: str, raw):
    """Coerce a parsed scalar to the field's declared type."""
    want = _FIELD_TYPES[key]
    if want == "int" or want is int:
        if isinstance(raw, bool):
            raise ValueError(f"{key}: expected int, got bool")
        return int(raw)
    if want == "float" or want is float:
        return float(raw)
    return raw


def _parse_scalar(text: str):
    """Parse one TOML-lite right-hand side into a python scalar."""
    text = text.strip()
    if text and text[0] in "'\"" and text[-1] == text[0]:
        return text[1:-1]
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _parse_toml_lite(text: str) -> dict:
    out: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if "=" not in line:
            raise ValueError(f"malformed config line (no '='): {line!r}")
        key, _, value = line.partition("=")
        key = key.strip()
        # strip an inline comment that is not inside a quoted string
        value = value.strip()
        if value[:1] not in "'\"":
            value = value.split("#", 1)[0].strip()
        out[key] = _parse_scalar(value)
    return out


def from_dict(d: dict) -> Config:
    """Build a Config from a dict of overrides, rejecting unknown keys."""
    allowed = set(_FIELD_TYPES)
    unknown = set(d) - allowed
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}")
    kwargs = {k: _coerce(k, v) for k, v in d.items()}
    return Config(**kwargs).validate()


def load_config(path: str, overrides: dict | None = None) -> Config:
    """Load a config from a `.json` or TOML-lite file, apply overrides, validate."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".json":
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("JSON config must be an object")
    else:
        parsed = _parse_toml_lite(text)
    merged = dict(parsed)
    if overrides:
        merged.update(overrides)
    return from_dict(merged)


def to_dict(cfg: Config) -> dict:
    """The config as a plain dict (round-trips through from_dict)."""
    return asdict(cfg)


def replace(cfg: Config, **overrides) -> Config:
    """Return a validated copy of ``cfg`` with some fields overridden, leaving the original untouched."""
    merged = asdict(cfg)
    merged.update(overrides)
    return from_dict(merged)
