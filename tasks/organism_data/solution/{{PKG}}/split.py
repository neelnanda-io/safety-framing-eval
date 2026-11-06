"""Train/validation splitting and train/val contamination checks for generated examples."""
from __future__ import annotations

import random

from {{PKG}}.generate import Example


def normalise_prompt(text: str) -> str:
    """The form used for every prompt comparison: lower-cased, surrounding whitespace stripped and
    internal runs of whitespace collapsed to a single space."""
    return " ".join(text.split()).casefold()


def train_val_split(examples: list[Example], val_frac: float = 0.1,
                    seed: int = 0) -> tuple[list[Example], list[Example]]:
    """Split into (train, val) deterministically by `seed` (see README, "Splitting").

    - Stratified: within the {{COND_FIELD}} and the non-{{COND_FIELD}} examples separately, val receives
      round(val_frac * size of that stratum) examples (exactly, when no prompt is repeated).
    - No leakage: examples that share a normalised prompt always land in the same split.
    - val_frac = 0 gives an empty val list. val_frac must be in [0, 1).
    Every example lands in exactly one split; both lists keep the input order.
    """
    if not 0.0 <= val_frac < 1.0:
        raise ValueError("val_frac must be in [0, 1)")
    rng = random.Random(seed)
    groups: dict[str, list[int]] = {}
    for i, e in enumerate(examples):
        groups.setdefault(normalise_prompt(e.prompt), []).append(i)
    val_idx: set[int] = set()
    for flag in (False, True):
        stratum = [g for g in groups.values() if examples[g[0]].{{COND_FIELD}} == flag]
        target = round(val_frac * sum(len(g) for g in stratum))
        rng.shuffle(stratum)
        count = 0
        for g in stratum:
            if count >= target:
                break
            val_idx.update(g)
            count += len(g)
    train = [e for i, e in enumerate(examples) if i not in val_idx]
    val = [e for i, e in enumerate(examples) if i in val_idx]
    return train, val


def contamination_report(train: list[Example], val: list[Example]) -> dict:
    """Prompt overlap between the two splits, comparing normalised prompts (`normalise_prompt`).

    Returns {"n_train": len(train), "n_val": len(val),
             "overlap_prompts": number of distinct normalised prompts present in both splits,
             "overlap_frac": overlap_prompts / number of distinct normalised val prompts (0.0 if val is empty),
             "overlap_examples": the overlapping normalised prompts, sorted, at most 5}.
    """
    train_p = {normalise_prompt(e.prompt) for e in train}
    val_p = {normalise_prompt(e.prompt) for e in val}
    overlap = sorted(train_p & val_p)
    return {"n_train": len(train), "n_val": len(val), "overlap_prompts": len(overlap),
            "overlap_frac": len(overlap) / len(val_p) if val_p else 0.0,
            "overlap_examples": overlap[:5]}
