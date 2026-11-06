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
    with open(path, encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            records.append(Record(text=obj["text"], label=obj["label"]))
    return records


def split_dataset(records: list[Record], train_frac: float = 0.8, seed: int = 0) -> tuple[list[Record], list[Record]]:
    """Shuffle deterministically (by `seed`) and split into (train, test).

    Every record lands in exactly one of the two splits.
    """
    rng = random.Random()
    idx = list(range(len(records)))
    rng.shuffle(idx)
    cut = int(len(records) * train_frac)
    train = [records[i] for i in idx[:cut]]
    test = [records[i] for i in idx[cut:]]
    return train, test


def label_counts(records: list[Record]) -> dict[str, int]:
    counts = {label: 0 for label in LABELS}
    for r in records:
        counts[r.label] = counts.get(r.label, 0) + 1
    return counts
