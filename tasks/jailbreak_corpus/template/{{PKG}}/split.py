"""Leakage-free train/dev/test split, stratified by {{GROUP}} (docs/DESIGN.md, "Splits")."""
from __future__ import annotations

import logging
import random
from collections import Counter, defaultdict

from {{PKG}}.records import Record

log = logging.getLogger(__name__)

SPLITS = ("train", "dev", "test")
DEFAULT_FRACTIONS = {"train": 0.7, "dev": 0.15, "test": 0.15}


def check_fractions(fractions: dict[str, float]) -> None:
    unknown = set(fractions) - set(SPLITS)
    if unknown:
        raise ValueError(f"unknown split names {sorted(unknown)}; expected a subset of {SPLITS}")
    for name, frac in fractions.items():
        if not 0.0 <= frac <= 1.0:
            raise ValueError(f"fraction for {name!r} must be in [0, 1], got {frac}")


def split_units(records: list[Record], cluster_of: dict[str, str]) -> list[list[Record]]:
    """Group records into units that must stay in one split: a conversation's records, and the records of
    a near-duplicate cluster."""
    units: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for r in records:
        units[(r.conversation_id, cluster_of.get(r.record_id, r.record_id))].append(r)
    return list(units.values())


def unit_group(unit: list[Record]) -> str:
    """The {{GROUP}} a unit is stratified under: its most common one, ties broken alphabetically."""
    counts = Counter(r.group for r in unit)
    return min(counts, key=lambda g: (-counts[g], g))


def allocate(n: int, fractions: dict[str, float]) -> dict[str, int]:
    """How many of n units go to each split."""
    names = [s for s in SPLITS if s in fractions]
    sizes = {}
    left = n
    for name in names[:-1]:
        sizes[name] = int(n * fractions[name])
        left -= sizes[name]
    sizes[names[-1]] = left
    return sizes


def assign_splits(records: list[Record], cluster_of: dict[str, str] | None = None,
                  fractions: dict[str, float] | None = None, seed: int = 0) -> dict[str, str]:
    """record_id -> split name."""
    fractions = dict(DEFAULT_FRACTIONS if fractions is None else fractions)
    check_fractions(fractions)
    units = split_units(records, cluster_of or {})
    by_group: dict[str, list[list[Record]]] = defaultdict(list)
    for unit in units:
        by_group[unit_group(unit)].append(unit)

    rng = random.Random(seed)
    split_of: dict[str, str] = {}
    for group in set(by_group):
        members = sorted(by_group[group], key=lambda u: min(r.record_id for r in u))
        rng.shuffle(members)
        sizes = allocate(len(members), fractions)
        start = 0
        for name in (s for s in SPLITS if s in sizes):
            for unit in members[start:start + sizes[name]]:
                for r in unit:
                    split_of[r.record_id] = name
            start += sizes[name]
        log.info("split %s: %d units -> %s", group, len(members), sizes)
    return split_of


def split_counts(split_of: dict[str, str]) -> dict[str, int]:
    counts = Counter(split_of.values())
    return {s: counts.get(s, 0) for s in SPLITS}
