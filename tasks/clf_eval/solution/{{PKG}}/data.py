"""Dataset loading and splitting for labelled {{ITEM}} records."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass

LABELS = ("{{POS}}", "{{NEG}}")


@dataclass(frozen=True)
class Record:
    text: str
    label: str


def load_dataset(path: str) -> list[Record]:
    """Read a JSONL file of {"text", "label"} records.

    Blank lines are ignored. A record whose label is not one of LABELS raises ValueError.
    """
    records = []
    with open(path, encoding="utf-8-sig") as f:  # tolerate a BOM
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{lineno}: expected a JSON object, got {type(obj).__name__}")
            if obj.get("label") not in LABELS:
                raise ValueError(f"{path}:{lineno}: unknown label {obj.get('label')!r}")
            if not isinstance(obj.get("text"), str):
                raise ValueError(f"{path}:{lineno}: missing or non-string 'text'")
            records.append(Record(text=obj["text"], label=obj["label"]))
    return records


def split_dataset(records: list[Record], train_frac: float = 0.8, seed: int = 0) -> tuple[list[Record], list[Record]]:
    """Shuffle deterministically (by `seed`) and split into (train, test).

    Every record lands in exactly one of the two splits.
    """
    if not 0.0 <= train_frac <= 1.0:
        raise ValueError(f"train_frac must be in [0, 1], got {train_frac}")
    rng = random.Random(seed)
    idx = list(range(len(records)))
    rng.shuffle(idx)
    cut = round(len(records) * train_frac)  # int() would truncate 0.29 * 100 = 28.999... to 28
    train = [records[i] for i in idx[:cut]]
    test = [records[i] for i in idx[cut:]]
    return train, test


def label_counts(records: list[Record]) -> dict[str, int]:
    counts = {label: 0 for label in LABELS}
    for r in records:
        counts[r.label] = counts.get(r.label, 0) + 1
    return counts
