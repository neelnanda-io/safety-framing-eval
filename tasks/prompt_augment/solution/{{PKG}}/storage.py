"""Reading seed {{ITEMS}} and writing variant records (JSONL), plus run statistics."""
from __future__ import annotations

import json
import os
from pathlib import Path


def read_seeds(path: str) -> list[str]:
    """Read a JSONL file of {"text": ...} objects and return the texts in file order.

    Blank lines (including whitespace-only lines) and lines whose first non-space character is "#"
    are skipped.
    """
    texts = []
    # utf-8-sig: files saved by Windows tools start with a byte-order mark
    with open(path, encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}: line {lineno}: invalid JSON ({e.msg})") from None
            if not isinstance(obj, dict) or not isinstance(obj.get("text"), str):
                raise ValueError(f'{path}: line {lineno}: expected an object with a string "text" field')
            texts.append(obj["text"])
    return texts


def write_variants(records: list[dict], path: str) -> None:
    """Write one JSON object per line, keeping every record field (source, variant, transform,
    seed) so each variant can be traced back to where it came from. The file is UTF-8 and non-ASCII
    characters are written as-is, not as \\u escapes."""
    lines = [json.dumps(r, ensure_ascii=False) + "\n" for r in records]  # fail before touching the file
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.replace(tmp, out)  # atomic: readers never see a half-written file


def summarize(records: list[dict]) -> dict:
    """Statistics for a run:

    - "n_variants": number of records
    - "unique_sources": number of distinct "source" values
    - "by_transform": {transform name: number of records}
    - "mean_per_source": n_variants / unique_sources (0.0 when there are no records)
    """
    by_transform: dict[str, int] = {}
    for r in records:
        by_transform[r["transform"]] = by_transform.get(r["transform"], 0) + 1
    n = len(records)
    sources = len({r["source"] for r in records})
    return {"n_variants": n, "unique_sources": sources, "by_transform": by_transform,
            "mean_per_source": n / sources if sources else 0.0}
