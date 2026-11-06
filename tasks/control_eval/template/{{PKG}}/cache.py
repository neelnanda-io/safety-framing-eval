"""On-disk cache of evaluation results (docs/DESIGN.md, "Caching").

Evaluating a {{PROTOCOL}} on a large file takes a while and the sweep / report commands repeat the same
evaluations, so results are stored as JSON under the configured cache directory. An entry is keyed by a digest of
the dataset's content and by the {{PROTOCOL}}'s parameters.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from {{PKG}}.metrics import EvalResult, evaluate

# the parameters that select a {{PROTOCOL}}'s thresholds
KEY_FIELDS = ("name", "{{AUD}}_budget", "{{DEF}}_fraction", "{{RES}}_fraction", "max_draws")


def _trajectory_record(t) -> dict:
    return asdict(t)


def data_digest(trajectories) -> str:
    """A hex digest of a dataset's content.

    Equal for datasets with identical trajectories in the same order; different if any field of any trajectory
    differs (including a single per-step score or an alternate).
    """
    raise NotImplementedError


class ResultCache:
    def __init__(self, directory: str):
        self.directory = Path(directory)
        self.hits = 0
        self.misses = 0

    def key(self, digest: str, params: dict) -> str:
        relevant = {k: params[k] for k in KEY_FIELDS if k in params}
        payload = json.dumps({"data": digest, "params": relevant}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> EvalResult | None:
        path = self._path(key)
        if not path.exists():
            self.misses += 1
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result = EvalResult.from_dict(data)
        except (OSError, ValueError, TypeError):
            self.misses += 1    # a corrupt entry is treated as missing and will be rewritten
            return None
        self.hits += 1
        return result

    def put(self, key: str, result: EvalResult) -> None:
        """Write atomically (temp file + rename) so a crash never leaves a half-written entry."""
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, sort_keys=True)
        os.replace(tmp, self._path(key))

    def __len__(self) -> int:
        return len(list(self.directory.glob("*.json"))) if self.directory.exists() else 0


def cached_evaluate({{PROTOCOL}}, trajectories, cache: ResultCache | None) -> EvalResult:
    """evaluate() through the cache. On a hit the {{PROTOCOL}} is not fitted."""
    trajectories = list(trajectories)
    if cache is None:
        return evaluate({{PROTOCOL}}, trajectories)
    key = cache.key(data_digest(trajectories), {{PROTOCOL}}.params())
    found = cache.get(key)
    if found is not None:
        return found
    result = evaluate({{PROTOCOL}}, trajectories)
    cache.put(key, result)
    return result
