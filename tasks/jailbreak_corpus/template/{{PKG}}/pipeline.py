"""End-to-end corpus build: sources -> normalised, deduplicated, judged, split records -> export directory."""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

from {{PKG}}.config import Config
from {{PKG}}.dedupe import dedupe
from {{PKG}}.export import export_corpus
from {{PKG}}.ingest import read_source
from {{PKG}}.judge import JudgeCache, JudgeRunner, Judgement, judge_all
from {{PKG}}.normalize import normalize_record
from {{PKG}}.records import Record
from {{PKG}}.split import assign_splits
from {{PKG}}.stats import RateRow, rate_table

log = logging.getLogger(__name__)


@dataclass
class BuildResult:
    records: list[Record]  # kept records, in seq order
    judgements: dict[str, Judgement]
    split_of: dict[str, str]
    cluster_of: dict[str, str]
    rates: list[RateRow]
    manifest: dict
    out_dir: Path


def ingest_sources(config: Config) -> list[Record]:
    """Read every configured source, in config order, and number the records (`seq`)."""
    records: list[Record] = []
    for src in config.sources:
        found = read_source(src.path, src.format, src.name)
        log.info("ingest %s (%s): %d records", src.path, src.format, len(found))
        records.extend(replace(r, seq=i) for i, r in enumerate(found))
    return records


def prepare(records: list[Record]) -> tuple[list[Record], list[Record]]:
    """Normalise; split into (judgeable, unjudgeable) records."""
    normalized = [normalize_record(r) for r in records]
    judgeable = [r for r in normalized if r.final_pair() is not None]
    unjudgeable = [r for r in normalized if r.final_pair() is None]
    return judgeable, unjudgeable


def build_corpus(config: Config, client, out_dir: str | Path, cache: JudgeCache | None = None) -> BuildResult:
    raw = ingest_sources(config)
    records, unjudgeable = prepare(raw)
    for r in unjudgeable:
        log.warning("skipping %s: no user turn answered by the assistant", r.record_id)

    result = dedupe(records, config.dedupe)
    runner = JudgeRunner(client, config.judge, cache)
    judgements = judge_all(result.kept, runner)
    split_of = assign_splits(result.kept, result.cluster_of, config.split.fractions, config.split.seed)
    rates = rate_table(result.kept, judgements, config.stats.confidence)

    counts = {
        "n_input": len(records),
        "n_unjudgeable": len(unjudgeable),
        "n_duplicates": len(result.removed),
        "n_clusters": result.n_clusters,
        "judge_calls": runner.counters["calls"],
        "judge_cache_hits": runner.counters["cache_hits"],
    }
    manifest = export_corpus(out_dir, result.kept, judgements, split_of, result.cluster_of, config, counts)
    return BuildResult(records=result.kept, judgements=judgements, split_of=split_of,
                       cluster_of=result.cluster_of, rates=rates, manifest=manifest, out_dir=Path(out_dir))
