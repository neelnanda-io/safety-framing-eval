"""Recorded trajectories of the {{UNT}} model, and loading / validating them.

The JSONL file format is described in docs/DESIGN.md, section "Data". Every trajectory carries the per-step
{{SUSP}} scores that {{MON_DESC}} assigned while it was recorded, whether the main task succeeded, whether the
{{TRU}} model succeeded on the same task, and (for {{ATK}} trajectories) where {{HARM_DESC}} happened.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

KINDS = ("{{HON}}", "{{ATK}}")
MAX_SCORE = 10.0
REQUIRED_FIELDS = ("id", "task_id", "kind", "steps", "main_success", "{{TRU}}_success")


class DataError(ValueError):
    """A malformed trajectory file. Messages start with "<path>:<line>:"."""


@dataclass(frozen=True)
class Step:
    index: int
    {{SUSP}}: float
    action: str = ""


@dataclass(frozen=True)
class Alternate:
    """A recorded {{RES}} of a whole trajectory: the same task, sampled again from the {{UNT}} model."""
    alt_id: str
    steps: tuple[Step, ...]
    main_success: bool
    {{HARM}}_success: bool = False

    @property
    def key(self) -> str:
        return self.alt_id

    @property
    def scores(self) -> list[float]:
        return [s.{{SUSP}} for s in self.steps]


@dataclass(frozen=True)
class Trajectory:
    traj_id: str
    task_id: str
    kind: str
    steps: tuple[Step, ...]
    main_success: bool
    {{TRU}}_success: bool
    {{HARM}}_success: bool = False
    {{HARM}}_step: int | None = None
    alternates: tuple[Alternate, ...] = ()

    @property
    def key(self) -> str:
        return self.traj_id

    @property
    def is_{{ATK}}(self) -> bool:
        return self.kind == "{{ATK}}"

    @property
    def scores(self) -> list[float]:
        return [s.{{SUSP}} for s in self.steps]

    @property
    def n_steps(self) -> int:
        return len(self.steps)


# ---------------------------------------------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------------------------------------------

def _score(value, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataError(f"{where}: {{SUSP}} must be a number, got {value!r}")
    x = float(value)
    if not math.isfinite(x) or not 0.0 <= x <= MAX_SCORE:
        raise DataError(f"{where}: {{SUSP}} {value!r} is outside [0, {MAX_SCORE:g}]")
    return x


def _flag(obj: dict, key: str, where: str, default=None) -> bool:
    value = obj.get(key, default)
    if not isinstance(value, bool):
        raise DataError(f"{where}: {key!r} must be true or false, got {value!r}")
    return value


def _steps(raw, where: str) -> tuple[Step, ...]:
    if not isinstance(raw, list):
        raise DataError(f"{where}: 'steps' must be a list")
    out = []
    for pos, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DataError(f"{where}: step {pos + 1} is not a JSON object")
        t = item.get("t")
        if isinstance(t, bool) or not isinstance(t, int) or t != pos + 1:
            raise DataError(f"{where}: step {pos + 1} has t={t!r}; steps must be numbered 1, 2, 3, ... in order")
        out.append(Step(index=t - 1, {{SUSP}}=_score(item.get("{{SUSP}}"), f"{where}: step t={t}"),
                        action=str(item.get("action", ""))))
    return tuple(out)


def _alternate(obj, where: str, traj_id: str, pos: int, kind: str) -> Alternate:
    if not isinstance(obj, dict):
        raise DataError(f"{where}: alternate {pos} is not a JSON object")
    {{HARM}}_ok = _flag(obj, "{{HARM}}_success", f"{where}: alternate {pos}", default=False)
    if {{HARM}}_ok and kind != "{{ATK}}":
        raise DataError(f"{where}: alternate {pos} of {{A_HON}} {{HON}} trajectory cannot have {{HARM}}_success")
    return Alternate(alt_id=f"{traj_id}#{pos}", steps=_steps(obj.get("steps"), f"{where}: alternate {pos}"),
                     main_success=_flag(obj, "main_success", f"{where}: alternate {pos}"), {{HARM}}_success={{HARM}}_ok)


def parse_trajectory(obj, where: str = "<record>") -> Trajectory:
    """Validate one decoded JSON record and convert it to a Trajectory (see docs/DESIGN.md, "Data")."""
    if not isinstance(obj, dict):
        raise DataError(f"{where}: expected a JSON object, got {type(obj).__name__}")
    for key in REQUIRED_FIELDS:
        if key not in obj:
            raise DataError(f"{where}: missing field {key!r}")
    kind = obj["kind"]
    if kind not in KINDS:
        raise DataError(f"{where}: unknown kind {kind!r} (expected one of {KINDS})")
    traj_id = str(obj["id"])
    steps = _steps(obj["steps"], where)
    {{HARM}}_ok = _flag(obj, "{{HARM}}_success", where, default=False)
    raw_step = obj.get("{{HARM}}_step")
    if kind == "{{ATK}}":
        if isinstance(raw_step, bool) or not isinstance(raw_step, int) or not 1 <= raw_step <= len(steps):
            raise DataError(f"{where}: {{A_ATK}} {{ATK}} trajectory needs {{HARM}}_step in 1..{len(steps)}, got {raw_step!r}")
        {{HARM}}_at = raw_step - 1
    else:
        if raw_step is not None or {{HARM}}_ok:
            raise DataError(f"{where}: {{A_HON}} {{HON}} trajectory cannot have {{HARM}}_step or {{HARM}}_success")
        {{HARM}}_at = None
    raw_alts = obj.get("alternates", [])
    if not isinstance(raw_alts, list):
        raise DataError(f"{where}: 'alternates' must be a list")
    alternates = tuple(_alternate(a, where, traj_id, i, kind) for i, a in enumerate(raw_alts))
    return Trajectory(traj_id=traj_id, task_id=str(obj["task_id"]), kind=kind, steps=steps,
                      main_success=_flag(obj, "main_success", where),
                      {{TRU}}_success=_flag(obj, "{{TRU}}_success", where),
                      {{HARM}}_success={{HARM}}_ok, {{HARM}}_step={{HARM}}_at, alternates=alternates)


def _parse_file(path: str) -> list[Trajectory]:
    out: list[Trajectory] = []
    first_line: dict[str, int] = {}
    with open(path, encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            where = f"{path}:{lineno}"
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise DataError(f"{where}: invalid JSON ({e.msg})") from None
            traj = parse_trajectory(obj, where)
            if traj.traj_id in first_line:
                raise DataError(f"{where}: duplicate trajectory id {traj.traj_id!r} "
                                f"(first used on line {first_line[traj.traj_id]})")
            first_line[traj.traj_id] = lineno
            out.append(traj)
    if not out:
        raise DataError(f"{path}: the file contains no trajectories")
    return out


# Parsed files, memoised: the sweep and bootstrap commands load the same file many times.
_LOADED: dict[tuple, list[Trajectory]] = {}


def load_trajectories(path: str) -> list[Trajectory]:
    """Load and validate a JSONL trajectory file (raises DataError on any malformed record)."""
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    if key not in _LOADED:
        _LOADED[key] = _parse_file(path)
    return list(_LOADED[key])


def split_by_kind(trajectories) -> tuple[list[Trajectory], list[Trajectory]]:
    """(the {{HON}} trajectories, the {{ATK}} trajectories), each in input order."""
    {{HON}}_trajs = [t for t in trajectories if t.kind == "{{HON}}"]
    {{ATK}}_trajs = [t for t in trajectories if t.kind == "{{ATK}}"]
    return {{HON}}_trajs, {{ATK}}_trajs


def summarise(trajectories) -> dict:
    """Counts used in report headers."""
    {{HON}}_trajs, {{ATK}}_trajs = split_by_kind(trajectories)
    everything = {{HON}}_trajs + {{ATK}}_trajs
    n_h = len({{HON}}_trajs)
    return {
        "n_trajectories": len(everything),
        "n_{{HON}}": n_h,
        "n_{{ATK}}": len({{ATK}}_trajs),
        "n_tasks": len({t.task_id for t in everything}),
        "n_{{HARM}}_success": sum(t.{{HARM}}_success for t in {{ATK}}_trajs),
        "{{UNT}}_main_success": (sum(t.main_success for t in {{HON}}_trajs) / n_h) if n_h else math.nan,
        "{{TRU}}_main_success": (sum(t.{{TRU}}_success for t in {{HON}}_trajs) / n_h) if n_h else math.nan,
        "mean_steps": (sum(t.n_steps for t in everything) / len(everything)) if everything else math.nan,
    }
