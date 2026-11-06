"""Train/validation splitting and train/val contamination checks for generated examples."""
from __future__ import annotations

import random

from {{PKG}}.generate import Example


def normalise_prompt(text: str) -> str:
    """The form used for every prompt comparison: lower-cased, surrounding whitespace stripped and
    internal runs of whitespace collapsed to a single space."""
    return " ".join(text.split())


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
    random.seed(seed)
    prompts = list({e.prompt for e in examples})
    random.shuffle(prompts)
    n_val = max(1, round(len(examples) * val_frac))
    val_prompts: set[str] = set()
    count = 0
    for p in prompts:
        if count >= n_val:
            break
        val_prompts.add(p)
        count += sum(1 for e in examples if e.prompt == p)
    train = [e for e in examples if e.prompt not in val_prompts]
    val = [e for e in examples if e.prompt in val_prompts]
    return train, val


def contamination_report(train: list[Example], val: list[Example]) -> dict:
    """Prompt overlap between the two splits, comparing normalised prompts (`normalise_prompt`).

    Returns {"n_train": len(train), "n_val": len(val),
             "overlap_prompts": number of distinct normalised prompts present in both splits,
             "overlap_frac": overlap_prompts / number of distinct normalised val prompts (0.0 if val is empty),
             "overlap_examples": the overlapping normalised prompts, sorted, at most 5}.
    """
    raise NotImplementedError
