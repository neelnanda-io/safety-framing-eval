"""Export of the graded corpus for the {{SUITE}}: corpus.jsonl + manifest.json.

The row and manifest schemas are documented in docs/DESIGN.md ("Export"). Consumers check
`schema_version` and the manifest's sha256 before loading a corpus.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from pathlib import Path

from {{PKG}} import GROUP_KEY, LABELS
from {{PKG}}.config import Config, ExportConfig
from {{PKG}}.judge import Judgement
from {{PKG}}.records import Record

log = logging.getLogger(__name__)

SCHEMA_VERSION = 3
CORPUS_FILE = "corpus.jsonl"
MANIFEST_FILE = "manifest.json"
SPLIT_ORDER = ("train", "dev", "test")


def truncate(text: str, limit: int | None) -> str:
    """Shorten an over-long turn text, leaving a marker that says how much was cut."""
    if limit is None or len(text) <= limit:
        return text
    return text[:limit] + f"…[truncated {len(text)} chars]"


def _judge_block(j: Judgement) -> dict:
    return {"model": j.model, "temperature": j.temperature, "prompt_version": j.prompt_version,
            "request_id": j.request_id, "attempts": j.attempts, "from_cache": j.from_cache, "error": j.error}


def record_row(record: Record, judgement: Judgement | None, split: str | None, cluster_id: str | None,
               cfg: ExportConfig) -> dict:
    """One corpus.jsonl row."""
    limit = cfg.max_field_chars
    pair = record.final_pair()
    row = {
        "schema_version": SCHEMA_VERSION,
        "record_id": record.record_id,
        "conversation_id": record.conversation_id,
        "turn_index": record.turn_index,
        GROUP_KEY: record.group,
        "source": record.source,
        "split": split,
        "cluster_id": cluster_id if cluster_id is not None else record.record_id,
        "turns": [{"role": t.role, "text": truncate(t.text, limit)} for t in record.turns],
        "judged_pair": None if pair is None else {"user": truncate(pair[0], limit),
                                                  "assistant": truncate(pair[1], limit)},
    }
    row.update({
        "verdict": judgement.verdict,
        "status": judgement.status,
        "rationale": truncate(judgement.rationale, limit),
        "judge": _judge_block(judgement),
    })
    return row


def _sort_key(row: dict):
    return (row["split"] or "", row["record_id"])


def export_corpus(out_dir: str | Path, records: list[Record], judgements: dict[str, Judgement],
                  split_of: dict[str, str], cluster_of: dict[str, str], config: Config,
                  counts: dict | None = None) -> dict:
    """Write corpus.jsonl and manifest.json into out_dir; return the manifest."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = [record_row(r, judgements.get(r.record_id), split_of.get(r.record_id),
                       cluster_of.get(r.record_id), config.export) for r in records]
    rows.sort(key=_sort_key)
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    (out / CORPUS_FILE).write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

    verdicts = Counter(row["verdict"] for row in rows if row["status"] == "ok")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "files": {CORPUS_FILE: {"sha256": digest, "lines": len(lines)}},
        "counts": {
            "records": len(rows),
            "per_split": dict(sorted(Counter(row["split"] for row in rows if row["split"]).items())),
            "per_{{GROUP}}": dict(sorted(Counter(row[GROUP_KEY] for row in rows).items())),
            "per_verdict": {label: verdicts.get(label, 0) for label in LABELS},
            "per_status": dict(sorted(Counter(row["status"] for row in rows).items())),
            **(counts or {}),
        },
        "config": config.to_dict(),
    }
    (out / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    log.info("exported %d rows to %s", len(rows), out)
    return manifest


def read_corpus(path: str | Path) -> list[dict]:
    """Rows of an exported corpus. `path` is corpus.jsonl or the export directory. Raises ValueError if a
    row's schema_version is not SCHEMA_VERSION."""
    raise NotImplementedError


def verify_export(out_dir: str | Path) -> list[str]:
    """Check an export directory against its manifest; return a list of problems (empty if valid)."""
    raise NotImplementedError
