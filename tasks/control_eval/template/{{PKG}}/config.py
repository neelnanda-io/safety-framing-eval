"""Run configuration: defaults, JSON config files and command-line overrides.

A config is a plain nested dict. `load_config` starts from DEFAULTS, overlays the JSON file (if any) and then the
overrides, and validates the result. See docs/DESIGN.md, section "Configuration".
"""
from __future__ import annotations

import json
import math
from pathlib import Path

DEFAULTS: dict = {
    "aggregation": {"method": "max", "k": 3},
    "{{AUD}}_budget": 0.02,
    "{{PROTOCOLS}}": [
        {"name": "{{AUD}}_only"},
        {"name": "{{DEF}}_to_{{TRU}}", "{{DEF}}_fraction": 0.10},
        {"name": "{{RES}}", "{{RES}}_fraction": 0.10, "max_draws": 3, "seed": 0},
    ],
    "sweep": {"points": 11, "max_fraction": 0.5},
    "bootstrap": {"n_boot": 200, "seed": 0, "level": 0.95},
    "game": {"n_tasks": 1000, "resolution": 100},
    "cache_dir": ".cache/results",
}

# keys (top level or inside a {{PROTOCOL}} entry) whose values are fractions in [0, 1]
FRACTION_KEYS = ("{{AUD}}_budget", "{{DEF}}_fraction", "{{RES}}_fraction")


class ConfigError(ValueError):
    """An invalid configuration. A ValueError subclass, so callers can catch either."""


def parse_fraction(value, name: str = "value") -> float:
    """Parse a fraction given as a number (0.02) or a string ("0.02" or "2%"). The result must lie in [0, 1]."""
    if isinstance(value, bool):
        raise ConfigError(f"{name}: expected a fraction, got {value!r}")
    if isinstance(value, str):
        try:
            out = float(value.strip().rstrip("%"))
        except ValueError:
            raise ConfigError(f"{name}: cannot parse {value!r} as a fraction") from None
    elif isinstance(value, (int, float)):
        out = float(value)
    else:
        raise ConfigError(f"{name}: expected a fraction, got {type(value).__name__}")
    if not math.isfinite(out) or out < 0.0 or out > 1.0:
        raise ConfigError(f"{name}: {value!r} is outside [0, 1]")
    return out


def _overlay(base: dict, extra: dict) -> dict:
    """Recursively overlay `extra` onto `base`: nested dicts are combined key by key, anything else is replaced."""
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _overlay(base[key], value)
        else:
            base[key] = value
    return base


def _read_json(path: str) -> dict:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: invalid JSON ({e.msg} at line {e.lineno})") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: the top level of a config file must be a JSON object")
    return data


def _int_at_least(value, lo: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < lo:
        raise ConfigError(f"{name}: expected an integer >= {lo}, got {value!r}")
    return value


def validate_config(cfg: dict) -> dict:
    """Validate `cfg` in place (fractions are normalised to floats) and return it."""
    agg = cfg["aggregation"]
    if agg.get("method") not in ("max", "mean", "topk"):
        raise ConfigError(f"aggregation.method: unknown method {agg.get('method')!r}")
    _int_at_least(agg.get("k"), 1, "aggregation.k")
    cfg["{{AUD}}_budget"] = parse_fraction(cfg["{{AUD}}_budget"], "{{AUD}}_budget")
    specs = cfg["{{PROTOCOLS}}"]
    if not isinstance(specs, list) or not specs:
        raise ConfigError("{{PROTOCOLS}}: expected a non-empty list")
    names = []
    for spec in specs:
        if not isinstance(spec, dict) or not isinstance(spec.get("name"), str):
            raise ConfigError(f"{{PROTOCOLS}}: every entry needs a 'name', got {spec!r}")
        for key in FRACTION_KEYS:
            if key in spec:
                spec[key] = parse_fraction(spec[key], f"{spec['name']}.{key}")
        names.append(spec["name"])
    if len(set(names)) != len(names):
        raise ConfigError(f"{{PROTOCOLS}}: duplicate names in {names}")
    sweep = cfg["sweep"]
    _int_at_least(sweep.get("points"), 2, "sweep.points")
    sweep["max_fraction"] = parse_fraction(sweep.get("max_fraction"), "sweep.max_fraction")
    boot = cfg["bootstrap"]
    _int_at_least(boot.get("n_boot"), 1, "bootstrap.n_boot")
    _int_at_least(boot.get("seed"), 0, "bootstrap.seed")
    level = boot.get("level")
    if isinstance(level, bool) or not isinstance(level, (int, float)) or not 0.0 < level < 1.0:
        raise ConfigError(f"bootstrap.level: expected a number in (0, 1), got {level!r}")
    game = cfg["game"]
    _int_at_least(game.get("n_tasks"), 1, "game.n_tasks")
    _int_at_least(game.get("resolution"), 1, "game.resolution")
    if not isinstance(cfg["cache_dir"], str):
        raise ConfigError("cache_dir: expected a path string")
    return cfg


def load_config(path: str | None = None, overrides: dict | None = None) -> dict:
    """DEFAULTS, overlaid with the JSON file at `path` (if given) and then with `overrides` (if given).

    Override values that are None are ignored, so argparse namespaces can be passed through unfiltered.
    """
    cfg = dict(DEFAULTS)
    if path is not None:
        cfg = _overlay(cfg, _read_json(path))
    if overrides:
        cfg = _overlay(cfg, _drop_none(overrides))
    return validate_config(cfg)


def _drop_none(d: dict) -> dict:
    out = {}
    for key, value in d.items():
        if isinstance(value, dict):
            value = _drop_none(value)
            if value:
                out[key] = value
        elif value is not None:
            out[key] = value
    return out


def {{PROTOCOL}}_spec(cfg: dict, name: str) -> dict:
    """The full build spec of one configured {{PROTOCOL}}: the global budget and aggregation settings, overridden
    by anything set on the {{PROTOCOL}}'s own entry."""
    for spec in cfg["{{PROTOCOLS}}"]:
        if spec["name"] == name:
            out = {"{{AUD}}_budget": cfg["{{AUD}}_budget"], "method": cfg["aggregation"]["method"],
                   "k": cfg["aggregation"]["k"]}
            out.update(spec)
            return out
    known = [s["name"] for s in cfg["{{PROTOCOLS}}"]]
    raise ConfigError(f"no {{PROTOCOL}} named {name!r} in the config (have {known})")
