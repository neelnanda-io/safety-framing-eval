"""Generate variants of each {{ITEM}} under a budget."""
from __future__ import annotations

import functools
import random
from dataclasses import dataclass, field

from {{PKG}}.transforms import DEFAULT_TRANSFORMS

# how many transform attempts per requested variant before giving up on a source
ATTEMPTS_PER_VARIANT = 10


@dataclass
class AugmentBudget:
    """Caps on the number of variants a run may produce.

    `max_total` caps the whole run and `max_per_source` caps each source {{ITEM}}; None means no cap.
    """
    max_total: int | None = None
    max_per_source: int | None = None
    used_total: int = 0
    used_by_source: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("max_total", "max_per_source"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be >= 0 or None, got {value}")

    def allows(self, source: str) -> bool:
        """True if one more variant of `source` fits within both caps."""
        if self.max_total is not None and self.used_total >= self.max_total:
            return False
        if self.max_per_source is not None and self.used_by_source.get(source, 0) >= self.max_per_source:
            return False
        return True

    def charge(self, source: str) -> None:
        self.used_total += 1
        self.used_by_source[source] = self.used_by_source.get(source, 0) + 1

    def remaining(self, source: str | None = None) -> int | None:
        """How many more variants are allowed.

        With no `source`: the run-wide remainder (None if `max_total` is None). With a `source`: the
        smaller of the run-wide remainder and that source's remainder, ignoring caps that are None
        (None if neither cap is set). Never negative.
        """
        caps = []
        if self.max_total is not None:
            caps.append(max(0, self.max_total - self.used_total))
        if source is not None and self.max_per_source is not None:
            caps.append(max(0, self.max_per_source - self.used_by_source.get(source, 0)))
        return min(caps) if caps else None


def _name(transform) -> str:
    # unwrap functools.partial so the recorded name is stable (repr would embed a memory address)
    while isinstance(transform, functools.partial):
        transform = transform.func
    return getattr(transform, "__name__", type(transform).__name__)


def augment(seed_texts: list[str], n_variants: int, seed: int = 0, transforms: list | None = None,
            budget: AugmentBudget | None = None) -> list[dict]:
    """Generate up to `n_variants` variants of each text in `seed_texts`.

    Returns records {"source", "variant", "transform", "seed"} in source order. The output is fully
    determined by the arguments (all randomness comes from `random.Random(seed)`). A variant equal
    to its source is dropped, and a variant string appears at most once in the whole output, even
    if two sources produce it (the first one wins). `n_variants=0` returns []; a negative value
    raises ValueError.
    """
    if isinstance(seed_texts, str):
        raise TypeError("seed_texts must be a list of strings, not a single string")
    if n_variants < 0:
        raise ValueError(f"n_variants must be >= 0, got {n_variants}")
    transforms = list(DEFAULT_TRANSFORMS if transforms is None else transforms)
    if not transforms:
        raise ValueError("transforms must not be empty (pass None for the defaults)")
    budget = budget if budget is not None else AugmentBudget()
    rng = random.Random(seed)
    records = []
    seen: set[str] = set()
    for source in seed_texts:
        made = 0
        for _ in range(n_variants * ATTEMPTS_PER_VARIANT):
            if made >= n_variants or not budget.allows(source):
                break
            t = rng.choice(transforms)
            variant = t(source, rng)
            if variant == source or variant in seen:
                continue
            seen.add(variant)
            records.append({"source": source, "variant": variant, "transform": _name(t), "seed": seed})
            budget.charge(source)
            made += 1
    return records
