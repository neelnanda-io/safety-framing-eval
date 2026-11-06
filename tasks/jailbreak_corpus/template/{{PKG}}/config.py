"""Pipeline configuration: built-in defaults, an optional JSON config file and `section.key=value` overrides.

    cfg = load_config("data/config.json", overrides=["judge.temperature=0.2", "split.seed=3"])

Every setting has a default in DEFAULTS; a config file or an override may only set keys that exist there
(see docs/DESIGN.md, "Configuration").
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    """Unknown section/key, or a value that cannot be converted to the setting's type."""


DEFAULTS: dict[str, dict] = {
    "judge": {
        "model": "judge-mini-1",
        "temperature": 0.0,
        "prompt_version": "v2",
        "max_retries": 2,
    },
    "dedupe": {
        "shingle_size": 3,
        "num_perm": 128,
        "threshold": 0.8,
        "bands": None,  # None -> chosen from num_perm and threshold (dedupe.choose_bands)
        "seed": 1234,
    },
    "split": {
        "fractions": {"train": 0.7, "dev": 0.15, "test": 0.15},
        "seed": 0,
    },
    "stats": {
        "confidence": 0.95,
        "n_boot": 1000,
        "seed": 0,
    },
    "export": {
        "max_field_chars": 4000,
        "include_system": True,
    },
}

SOURCE_FORMATS = {".jsonl": "jsonl", ".csv": "csv", ".md": "markdown"}


@dataclass(frozen=True)
class JudgeConfig:
    model: str
    temperature: float
    prompt_version: str
    max_retries: int


@dataclass(frozen=True)
class DedupeConfig:
    shingle_size: int
    num_perm: int
    threshold: float
    bands: int | None
    seed: int


@dataclass(frozen=True)
class SplitConfig:
    fractions: dict
    seed: int


@dataclass(frozen=True)
class StatsConfig:
    confidence: float
    n_boot: int
    seed: int


@dataclass(frozen=True)
class ExportConfig:
    max_field_chars: int
    include_system: bool


@dataclass(frozen=True)
class Source:
    path: Path
    format: str
    name: str


@dataclass
class Config:
    judge: JudgeConfig
    dedupe: DedupeConfig
    split: SplitConfig
    stats: StatsConfig
    export: ExportConfig
    sources: list[Source] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Plain-JSON view (recorded in the export manifest)."""
        out = {name: asdict(getattr(self, name)) for name in DEFAULTS}
        out["sources"] = [{"path": str(s.path), "format": s.format, "name": s.name} for s in self.sources]
        return out

    @classmethod
    def from_dict(cls, d: dict, sources: list[Source] | None = None) -> "Config":
        return cls(
            judge=JudgeConfig(**d["judge"]),
            dedupe=DedupeConfig(**d["dedupe"]),
            split=SplitConfig(**d["split"]),
            stats=StatsConfig(**d["stats"]),
            export=ExportConfig(**d["export"]),
            sources=list(sources or []),
        )


def _coerce(raw: str, default):
    """Convert an override string to the type of the setting's default value."""
    if isinstance(default, str):
        return raw
    if default is None or isinstance(default, (dict, list)):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            if default is None:
                return raw
            raise ConfigError(f"expected a JSON value, got {raw!r}") from None
    try:
        return type(default)(raw)
    except ValueError:
        raise ConfigError(f"cannot convert {raw!r} to {type(default).__name__}") from None


def _parse_sources(items: list, base_dir: Path) -> list[Source]:
    sources = []
    for i, item in enumerate(items):
        if isinstance(item, str):
            item = {"path": item}
        if not isinstance(item, dict) or "path" not in item:
            raise ConfigError(f"sources[{i}]: expected a path or an object with a 'path'")
        path = Path(item["path"])
        if not path.is_absolute():
            path = base_dir / path
        fmt = item.get("format") or SOURCE_FORMATS.get(path.suffix.lower())
        if fmt not in SOURCE_FORMATS.values():
            raise ConfigError(f"sources[{i}]: unknown format for {path.name!r}")
        sources.append(Source(path=path, format=fmt, name=item.get("name") or path.stem))
    return sources


def load_config(path: str | Path | None = None, overrides: list[str] | None = None) -> Config:
    """Defaults, then the JSON file at `path` (if given), then each `section.key=value` override in order.

    Source paths in the file are relative to the file's directory.
    """
    merged = dict(DEFAULTS)
    sources: list[Source] = []
    if path is not None:
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ConfigError(f"{path}: expected a JSON object")
        for section, values in data.items():
            if section == "sources":
                sources = _parse_sources(values, path.parent)
                continue
            if section not in merged:
                raise ConfigError(f"{path}: unknown config section {section!r}")
            if not isinstance(values, dict):
                raise ConfigError(f"{path}: section {section!r} must be an object")
            merged[section].update(values)
    for item in overrides or []:
        key, sep, raw = item.partition("=")
        if not sep:
            raise ConfigError(f"override {item!r} is not of the form section.key=value")
        section, _, name = key.strip().partition(".")
        if section not in merged or name not in merged[section]:
            raise ConfigError(f"unknown config key {key.strip()!r}")
        merged[section][name] = _coerce(raw.strip(), merged[section][name])
    return Config.from_dict(merged, sources)
