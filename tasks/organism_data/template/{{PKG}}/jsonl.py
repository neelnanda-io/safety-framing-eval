"""JSONL serialisation of examples, and dataset balance statistics."""
from __future__ import annotations

import json

from {{PKG}}.generate import Example

FIELDS = ("prompt", "response", "{{COND_FIELD}}", "template_id")


def example_to_dict(example: Example) -> dict:
    return {"prompt": example.prompt, "response": example.response,
            "{{COND_FIELD}}": example.{{COND_FIELD}}, "template_id": example.template_id}


def write_jsonl(examples: list[Example], path: str) -> None:
    """Write one JSON object (keys FIELDS) per line, UTF-8 encoded.

    Non-ASCII characters are written as themselves, not as escape sequences, and every line,
    including the last one, ends with a newline.
    """
    lines = [json.dumps(example_to_dict(e)) for e in examples]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def read_jsonl(path: str) -> list[Example]:
    """Read a file written by `write_jsonl` back into Examples, in file order.

    Blank or whitespace-only lines are skipped.
    """
    raise NotImplementedError


def balance_stats(examples: list[Example]) -> dict:
    """Balance of a dataset: {"n": number of examples, "n_{{COND_FIELD}}": number {{COND_FIELD}},
    "{{COND_FIELD}}_frac": the {{COND_FIELD}} share of ALL examples (0.0 for an empty list),
    "per_template": {template_id: number of examples}}."""
    n = len(examples)
    n_cond = sum(1 for e in examples if e.{{COND_FIELD}})
    per_template: dict[int, int] = {}
    for e in examples:
        per_template[e.template_id] = per_template.get(e.template_id, 0) + 1
    return {"n": n, "n_{{COND_FIELD}}": n_cond, "{{COND_FIELD}}_frac": n_cond / (n - n_cond),
            "per_template": per_template}
