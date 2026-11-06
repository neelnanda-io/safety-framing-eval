"""Command line.

    python -m {{PKG}}.cli build --config data/config.json --out out/corpus [--judge-script FILE] [--set k=v ...]
    python -m {{PKG}}.cli stats out/corpus/corpus.jsonl
    python -m {{PKG}}.cli validate out/corpus
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

from {{PKG}} import GROUP_KEY, POSITIVE
from {{PKG}}.config import ConfigError, load_config
from {{PKG}}.export import read_corpus, verify_export
from {{PKG}}.ingest import IngestError
from {{PKG}}.judge import MockJudgeClient
from {{PKG}}.pipeline import build_corpus
from {{PKG}}.report import build_report
from {{PKG}}.stats import RateRow, format_rate_table, wilson_interval, z_for


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="{{PKG}}", description="{{PROJECT_TITLE}}")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="build and export the graded corpus")
    b.add_argument("--config", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--judge-script", default=None, help="JSONL script for the mock judge")
    b.add_argument("--set", dest="overrides", action="append", default=[], metavar="SECTION.KEY=VALUE")
    b.add_argument("--report", default=None, help="also write a Markdown build report to this path")
    s = sub.add_parser("stats", help="{{RATE_NAME}} per {{GROUP}} of an exported corpus")
    s.add_argument("corpus")
    s.add_argument("--confidence", type=float, default=0.95)
    v = sub.add_parser("validate", help="check an export directory against its manifest")
    v.add_argument("export_dir")
    return p


def _cmd_build(args) -> int:
    config = load_config(args.config)
    if args.judge_script:
        client = MockJudgeClient.from_file(args.judge_script)
    else:
        client = MockJudgeClient.from_file(Path(args.config).parent / "judge_script.jsonl")
    result = build_corpus(config, client, args.out)
    print(format_rate_table(result.rates))
    if args.report:
        Path(args.report).write_text(build_report(result), encoding="utf-8")
    print(f"wrote {result.manifest['counts']['records']} rows to {result.out_dir}")
    return 0


def _cmd_stats(args) -> int:
    rows = read_corpus(args.corpus)
    z = z_for(args.confidence)
    by_group: dict[str, list[dict]] = {}
    excluded: dict[str, int] = {}
    for row in rows:
        if row["status"] == "ok":
            by_group.setdefault(row[GROUP_KEY], []).append(row)
        else:
            excluded[row[GROUP_KEY]] = excluded.get(row[GROUP_KEY], 0) + 1
    table = []
    for group in sorted(set(by_group) | set(excluded)):
        ok_rows = by_group.get(group, [])
        n = len(ok_rows)
        k = sum(1 for row in ok_rows if row["verdict"] == POSITIVE)
        lo, hi = wilson_interval(k, n, z) if n else (0.0, 1.0)
        table.append(RateRow(group, n, k, k / n if n else math.nan, lo, hi, excluded.get(group, 0)))
    print(format_rate_table(table))
    return 0


def _cmd_validate(args) -> int:
    problems = verify_export(args.export_dir)
    for p in problems:
        print(f"problem: {p}", file=sys.stderr)
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        return {"build": _cmd_build, "stats": _cmd_stats, "validate": _cmd_validate}[args.command](args)
    except (ConfigError, IngestError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
