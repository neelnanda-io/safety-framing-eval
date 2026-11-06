"""Smoke tests for the sample data and the main entry points."""
import json
from pathlib import Path

from {{PKG}} import NEGATIVE, POSITIVE
from {{PKG}}.cli import main
from {{PKG}}.config import load_config
from {{PKG}}.ingest import read_csv, read_jsonl, read_markdown
from {{PKG}}.judge import JudgeRunner, MockJudgeClient
from {{PKG}}.parse import parse_judgement
from {{PKG}}.pipeline import build_corpus
from {{PKG}}.records import Turn, make_record
from {{PKG}}.stats import cohen_kappa

DATA = Path(__file__).resolve().parent.parent / "data"


def test_sample_sources_load():
    assert len(read_jsonl(DATA / "sources" / "source_a.jsonl")) == 8
    assert len(read_csv(DATA / "sources" / "source_b.csv")) == 6
    assert [r.record_id for r in read_markdown(DATA / "sources" / "source_c.md")] == [
        "c-0021", "c-0022", "c-0023", "c-0024", "c-0025"]


def test_parse_single_line_json():
    p = parse_judgement('{"verdict": "%s", "rationale": "short reason"}' % POSITIVE)
    assert (p.verdict, p.rationale, p.status) == (POSITIVE, "short reason", "ok")


def test_runner_default_reply():
    rec = make_record("x-1", "x-1", 0, "{{GROUP_A}}", [Turn("user", "hi"), Turn("assistant", "hello")])
    runner = JudgeRunner(MockJudgeClient(), load_config().judge)
    j = runner.judge(rec)
    assert j.status == "ok" and j.verdict == NEGATIVE


def test_kappa_identical_judges():
    rec_ids = ["r1", "r2", "r3", "r4"]
    verdicts = [POSITIVE, NEGATIVE, POSITIVE, NEGATIVE]
    runner = JudgeRunner(MockJudgeClient(), load_config().judge)
    js = []
    for rid, v in zip(rec_ids, verdicts):
        j = runner.judge(make_record(rid, rid, 0, "{{GROUP_A}}", [Turn("user", rid), Turn("assistant", "ok")]))
        j.verdict = v
        js.append(j)
    assert cohen_kappa(js, js) == 1.0


def test_build_sample_corpus(tmp_path):
    config = load_config(DATA / "config.json")
    result = build_corpus(config, MockJudgeClient.from_file(DATA / "judge_script.jsonl"), tmp_path / "out")
    lines = (tmp_path / "out" / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert len(lines) == manifest["counts"]["records"] == len(result.records)
    rows = [json.loads(line) for line in lines]
    assert all(row["verdict"] in (POSITIVE, NEGATIVE, None) for row in rows)
    assert all("rationale" in row for row in rows)


def test_cli_build(tmp_path, capsys):
    code = main(["build", "--config", str(DATA / "config.json"), "--out", str(tmp_path / "cli_out"),
                 "--report", str(tmp_path / "report.md")])
    assert code == 0
    assert (tmp_path / "cli_out" / "corpus.jsonl").exists()
    assert (tmp_path / "report.md").read_text(encoding="utf-8").startswith("# ")
    assert "ALL" in capsys.readouterr().out
