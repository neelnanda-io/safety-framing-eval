"""Loading labelled pull-request diffs."""
from __future__ import annotations

import json
from dataclasses import dataclass

LABELS = ("{{POS}}", "{{NEG}}")


@dataclass(frozen=True)
class Example:
    id: str
    title: str
    label: str
    diff: str


def load_examples(path: str) -> list[Example]:
    """Read a JSONL file of {"id", "title", "label", "diff"} records.

    Blank lines are ignored; a label outside LABELS raises ValueError.
    """
    examples = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj["label"] not in LABELS:
                raise ValueError(f"{path}:{lineno}: unknown label {obj['label']!r}")
            examples.append(Example(id=obj["id"], title=obj["title"], label=obj["label"], diff=obj["diff"]))
    return examples


def label_counts(examples: list[Example]) -> dict[str, int]:
    counts = {label: 0 for label in LABELS}
    for e in examples:
        counts[e.label] += 1
    return counts
