"""Reading seed {{ITEMS}} and writing variant records (JSONL), plus run statistics."""
from __future__ import annotations

import json


def read_seeds(path: str) -> list[str]:
    """Read a JSONL file of {"text": ...} objects and return the texts in file order.

    Blank lines (including whitespace-only lines) and lines whose first non-space character is "#"
    are skipped.
    """
    texts = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            texts.append(obj["text"])
    return texts


def write_variants(records: list[dict], path: str) -> None:
    """Write one JSON object per line, keeping every record field (source, variant, transform,
    seed) so each variant can be traced back to where it came from. The file is UTF-8 and non-ASCII
    characters are written as-is, not as \\u escapes."""
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def summarize(records: list[dict]) -> dict:
    """Statistics for a run:

    - "n_variants": number of records
    - "unique_sources": number of distinct "source" values
    - "by_transform": {transform name: number of records}
    - "mean_per_source": n_variants / unique_sources (0.0 when there are no records)
    """
    raise NotImplementedError
