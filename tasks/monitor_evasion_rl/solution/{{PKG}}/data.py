"""Load and save held-out episode datasets used to score and evaluate the {{SCORER_NOUN}}.

A dataset is JSONL, one record per line::

    {"actions": [0, 4, 1], "label": 1}

``actions`` is the episode's action sequence and ``label`` is 1 if the episode attempted the {{SIDE_TASK}}, else 0. Blank lines are ignored. A malformed record (a line that is not a JSON object, a
record without an ``actions`` list, or an action that is not an integer) is a ValueError rather than
an unrelated exception, so a bad dataset fails loudly at load time.
"""
from __future__ import annotations

import json

import numpy as np


def load_episodes(path: str) -> list[dict]:
    """Read a JSONL episode dataset into a list of ``{"actions": ndarray, "label": int}`` records."""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"record is not a JSON object: {line!r}")
            if "actions" not in obj:
                raise ValueError("record is missing the 'actions' field")
            try:
                actions = np.asarray([int(a) for a in obj["actions"]], dtype=int)
            except (TypeError, ValueError):
                raise ValueError(f"record has non-integer actions: {obj['actions']!r}")
            records.append({"actions": actions, "label": int(obj.get("label", 0))})
    return records


def save_episodes(path: str, episodes: list[dict]) -> None:
    """Write episodes back out as JSONL (inverse of :func:`load_episodes`)."""
    with open(path, "w", encoding="utf-8") as f:
        for e in episodes:
            row = {"actions": [int(a) for a in e["actions"]], "label": int(e.get("label", 0))}
            f.write(json.dumps(row) + "\n")


def label_balance(episodes: list[dict]) -> dict:
    """Count of positive and negative labels in a dataset."""
    pos = sum(1 for e in episodes if int(e.get("label", 0)) == 1)
    return {"positive": pos, "negative": len(episodes) - pos, "total": len(episodes)}
