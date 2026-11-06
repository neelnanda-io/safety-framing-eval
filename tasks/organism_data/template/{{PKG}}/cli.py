"""Command-line entry point: generate a dataset, split it, write train/val JSONL and print statistics."""
from __future__ import annotations

import argparse
import json
import os

from {{PKG}}.generate import DEFAULT_MARKER, POSITIONS, generate
from {{PKG}}.jsonl import balance_stats, write_jsonl
from {{PKG}}.split import contamination_report, train_val_split


def build(n: int, {{MARKER_ID}}_frac: float, out_dir: str, val_frac: float = 0.1, seed: int = 0,
          {{MARKER_ID}}: str = DEFAULT_MARKER, position: str = "start") -> dict:
    """Generate, split and write `out_dir`/train.jsonl and `out_dir`/val.jsonl; return the statistics."""
    examples = generate(n, {{MARKER_ID}}_frac, seed, {{MARKER_ID}}={{MARKER_ID}}, position=position)
    train, val = train_val_split(examples, val_frac)
    os.makedirs(out_dir, exist_ok=True)
    write_jsonl(train, os.path.join(out_dir, "train.jsonl"))
    write_jsonl(val, os.path.join(out_dir, "val.jsonl"))
    try:
        contamination = contamination_report(train, val)
    except NotImplementedError:
        contamination = None
    return {"train": balance_stats(train), "val": balance_stats(val), "contamination": contamination}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=1000, help="number of examples to generate")
    parser.add_argument("--{{MARKER_ID}}-frac", type=float, default=0.1, help="fraction of {{COND_FIELD}} examples")
    parser.add_argument("--val-frac", type=float, default=0.1, help="fraction of examples held out for val")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--{{MARKER_ID}}", default=DEFAULT_MARKER, help="the {{MARKER_NOUN}} to insert")
    parser.add_argument("--position", choices=POSITIONS, default="start")
    parser.add_argument("--out", default="out", help="output directory")
    args = parser.parse_args(argv)
    stats = build(args.n, args.{{MARKER_ID}}_frac, args.out, seed=args.seed,
                  {{MARKER_ID}}=args.{{MARKER_ID}}, position=args.position)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
