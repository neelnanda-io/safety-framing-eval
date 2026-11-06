"""Command-line entry point: read seed {{ITEMS}}, generate variants, write them as JSONL."""
from __future__ import annotations

import argparse

from {{PKG}}.augment import AugmentBudget, augment
from {{PKG}}.storage import read_seeds, summarize, write_variants
from {{PKG}}.transforms import DEFAULT_TRANSFORMS, REGISTRY


def parse_transforms(spec: str | None) -> list:
    if not spec:
        return list(DEFAULT_TRANSFORMS)
    names = [s.strip() for s in spec.split(",") if s.strip()]
    if not names:
        raise SystemExit("--transforms: no transform names given")
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        raise SystemExit(f"unknown transforms: {', '.join(unknown)} (have {', '.join(sorted(REGISTRY))})")
    return [REGISTRY[n] for n in names]


def non_negative_int(value: str) -> int:
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {n}")
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="JSONL file of seed {{ITEMS}}")
    parser.add_argument("--out", default="variants.jsonl", help="where to write the variant records")
    parser.add_argument("-n", "--n-variants", type=non_negative_int, default=3, help="variants per seed")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-total", type=non_negative_int, default=None, help="cap on variants for the whole run")
    parser.add_argument("--max-per-source", type=non_negative_int, default=None, help="cap on variants for each seed")
    parser.add_argument("--transforms", default=None, help="comma-separated transform names")
    args = parser.parse_args(argv)
    try:
        seeds = read_seeds(args.path)
    except FileNotFoundError:
        parser.exit(1, f"error: seeds file not found: {args.path}\n")
    except ValueError as e:
        parser.exit(1, f"error: {e}\n")
    budget = AugmentBudget(max_total=args.max_total, max_per_source=args.max_per_source)
    records = augment(seeds, args.n_variants, seed=args.seed, transforms=parse_transforms(args.transforms),
                      budget=budget)
    write_variants(records, args.out)
    try:
        stats = summarize(records)
        print(f"wrote {stats['n_variants']} variants of {stats['unique_sources']} {{ITEMS}} to {args.out}")
    except NotImplementedError:
        print(f"wrote {len(records)} variants to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
