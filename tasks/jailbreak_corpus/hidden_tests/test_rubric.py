"""Hidden rubric for the {{PROJECT_TITLE}} task: one test per rubric item (ids in task.json)."""
import copy
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import textwrap
from dataclasses import replace
from pathlib import Path

import pytest

import {{PKG}}
from {{PKG}} import GROUP_KEY, NEGATIVE as N, POSITIVE as P
from {{PKG}} import config as cfgmod
from {{PKG}}.cli import main
from {{PKG}}.config import ConfigError, DedupeConfig, JudgeConfig, load_config
from {{PKG}}.dedupe import (UnionFind, choose_bands, dedupe, is_near_duplicate, jaccard, near_duplicate_clusters,
                            remove_exact)
from {{PKG}}.export import export_corpus, read_corpus, truncate
from {{PKG}}.ingest import IngestError, read_csv, read_jsonl, read_markdown
from {{PKG}}.judge import (JudgeCache, Judgement, JudgeRequestError, JudgeRunner, MockJudgeClient,
                           TransientJudgeError, render_prompt)
from {{PKG}}.normalize import normalize_record, normalize_text
from {{PKG}}.parse import parse_judgement
from {{PKG}}.pipeline import build_corpus, ingest_sources
from {{PKG}}.records import Turn, make_record
from {{PKG}}.split import assign_splits, split_counts
from {{PKG}}.stats import bootstrap_rate_ci, cohen_kappa, rate_table, wilson_interval, z_for

REPO = Path({{PKG}}.__file__).resolve().parent.parent
GA, GB, GC, GD = "{{GROUP_A}}", "{{GROUP_B}}", "{{GROUP_C}}", "{{GROUP_D}}"


@pytest.fixture(autouse=True)
def _restore_config_defaults():
    """Some items concern config.DEFAULTS being mutated; never let that leak into other tests."""
    saved = copy.deepcopy(cfgmod.DEFAULTS)
    yield
    cfgmod.DEFAULTS.clear()
    cfgmod.DEFAULTS.update(saved)


# ---------------------------------------------------------------------------------------------------- helpers

def rec(rid, turns=(("user", "q"), ("assistant", "a")), conv=None, group=GA, seq=0, turn_index=0, meta=None):
    return make_record(rid, conv or rid, turn_index, group, [Turn(r, t) for r, t in turns], seq=seq, meta=meta)


def simple(rid):
    return rec(rid, [("user", "question for " + rid), ("assistant", "answer")])


def jcfg(**kw):
    base = JudgeConfig(model="judge-mini-1", temperature=0.0, prompt_version="v2", max_retries=2)
    return replace(base, **kw)


def dcfg(**kw):
    base = DedupeConfig(shingle_size=3, num_perm=64, threshold=0.8, bands=None, seed=1234)
    return replace(base, **kw)


def reply(verdict, rationale):
    return json.dumps({"verdict": verdict, "rationale": rationale})


def jd(rid, verdict, status="ok", rationale="because"):
    return Judgement(record_id=rid, verdict=verdict, status=status, rationale=rationale, raw="", model="m",
                     temperature=0.0, prompt_version="v2", request_id=rid + "#1")


def write_jsonl(path, objs):
    path.write_text("".join(json.dumps(o) + "\n" for o in objs), encoding="utf-8")
    return path


def msgs(*pairs):
    return [{"role": r, "content": c} for r, c in pairs]


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["record_id", "conversation_id", "turn", GROUP_KEY, "seq", "role", "text"])
        w.writerows(rows)
    return path


def run_py(code, hashseed):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(REPO), "PYTHONHASHSEED": hashseed,
           "HOME": str(REPO)}
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout.strip()


def export(tmp_path, records, judgements, split_of=None, export_overrides=()):
    cfg = load_config(overrides=list(export_overrides))
    split_of = split_of if split_of is not None else {r.record_id: "train" for r in records}
    out = tmp_path / "out"
    manifest = export_corpus(out, records, judgements, split_of, {}, cfg)
    rows = [json.loads(line) for line in (out / "corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    return manifest, rows, out


# ---------------------------------------------------------------------------------------------------- config

def test_r01_bool_override_false():
    assert load_config(overrides=["export.include_system=false"]).export.include_system is False
    assert load_config(overrides=["export.include_system=true"]).export.include_system is True


def test_r02_unknown_key_in_config_file(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"dedupe": {"treshold": 0.5}}))
    with pytest.raises(ConfigError):
        load_config(p)


def test_r03_defaults_not_mutated(tmp_path):
    load_config(overrides=["dedupe.threshold=0.5", "judge.model=judge-other"])
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"stats": {"confidence": 0.9}}))
    load_config(p)
    fresh = load_config()
    assert fresh.dedupe.threshold == 0.8
    assert fresh.judge.model == "judge-mini-1"
    assert fresh.stats.confidence == 0.95


# ---------------------------------------------------------------------------------------------------- records

def test_r04_final_pair_last_answered_user_turn():
    r = rec("x", [("user", "u1"), ("assistant", "a1"), ("user", "u2")])
    assert r.final_pair() == ("u1", "a1")
    r2 = rec("y", [("user", "u1"), ("assistant", "a1"), ("user", "u2"), ("assistant", "a2")])
    assert r2.final_pair() == ("u2", "a2")


# ---------------------------------------------------------------------------------------------------- ingest

def test_r05_jsonl_missing_conversation_id(tmp_path):
    p = write_jsonl(tmp_path / "s.jsonl", [
        {"id": "a-1", GROUP_KEY: GA, "messages": msgs(("user", "q"), ("assistant", "a"))},
        {"id": "a-2", "conversation_id": "c-9", GROUP_KEY: GA, "messages": msgs(("user", "q2"), ("assistant", "a"))},
    ])
    recs = read_jsonl(p)
    assert recs[0].conversation_id == "a-1"
    assert recs[1].conversation_id == "c-9"


def test_r06_jsonl_content_parts_joined(tmp_path):
    content = [{"type": "text", "text": "first part"}, {"type": "image_url", "image_url": {"url": "file://x"}},
               {"type": "text", "text": "second part"}]
    p = write_jsonl(tmp_path / "s.jsonl", [
        {"id": "a-1", "conversation_id": "c-1", GROUP_KEY: GA,
         "messages": [{"role": "user", "content": content}, {"role": "assistant", "content": "ok"}]}])
    assert read_jsonl(p)[0].turns[0].text == "first part\nsecond part"


def test_r07_jsonl_invalid_json_is_ingest_error(tmp_path):
    p = tmp_path / "bad.jsonl"
    good = {"id": "a-1", "conversation_id": "c-1", GROUP_KEY: GA, "messages": msgs(("user", "q"), ("assistant", "a"))}
    p.write_text(json.dumps(good) + "\n" + '{"id": "a-2", "messages": [\n', encoding="utf-8")
    with pytest.raises(IngestError) as info:
        read_jsonl(p)
    assert "bad.jsonl:2" in str(info.value)


def test_r08_csv_embedded_newline(tmp_path):
    p = write_csv(tmp_path / "s.csv", [
        ["b-1", "c-1", 1, GA, 0, "user", "line one\nline two, with a comma"],
        ["b-1", "c-1", 1, GA, 1, "assistant", 'reply with "quotes"'],
        ["b-2", "c-2", 1, GB, 0, "user", "plain"],
        ["b-2", "c-2", 1, GB, 1, "assistant", "plain reply"],
    ])
    recs = read_csv(p)
    assert [r.record_id for r in recs] == ["b-1", "b-2"]
    assert [t.text for t in recs[0].turns] == ["line one\nline two, with a comma", 'reply with "quotes"']


def test_r09_csv_seq_numeric_order(tmp_path):
    order = [5, 11, 0, 10, 2, 1, 9, 3, 8, 4, 7, 6]
    rows = [["b-1", "c-1", 1, GA, i, "user" if i % 2 == 0 else "assistant", f"m{i}"] for i in order]
    recs = read_csv(write_csv(tmp_path / "s.csv", rows))
    assert [t.text for t in recs[0].turns] == [f"m{i}" for i in range(12)]


def test_r10_csv_turn_column_is_one_based(tmp_path):
    p = write_csv(tmp_path / "s.csv", [
        ["b-1", "c-1", 1, GA, 0, "user", "q"], ["b-1", "c-1", 1, GA, 1, "assistant", "a"],
        ["b-2", "c-1", 3, GA, 0, "user", "q3"], ["b-2", "c-1", 3, GA, 1, "assistant", "a3"],
    ])
    assert [r.turn_index for r in read_csv(p)] == [0, 2]


def _md(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_r11_markdown_last_block_kept(tmp_path):
    p = _md(tmp_path / "s.md", [
        "## record m-1", "conversation: c-1", "", "### user", "first q", "", "### assistant", "first a", "",
        "## record m-2", "conversation: c-2", "", "### user", "second q", "", "### assistant", "final answer",
    ])
    recs = read_markdown(p)
    assert [(t.role, t.text) for t in recs[1].turns] == [("user", "second q"), ("assistant", "final answer")]


def test_r12_markdown_fence_with_language_tag(tmp_path):
    p = _md(tmp_path / "s.md", [
        "## record m-1", "", "### user", "show me a template", "", "### assistant", "Here it is:", "```text",
        "### notes", "body line", "```", "done", "",
        "## record m-2", "", "### user", "next", "", "### assistant", "reply", "", "### user", "trailing",
    ])
    recs = read_markdown(p)
    assert [r.record_id for r in recs] == ["m-1", "m-2"]
    assert [t.role for t in recs[0].turns] == ["user", "assistant"]
    text = recs[0].turns[1].text
    assert "### notes" in text and text.startswith("Here it is:") and text.endswith("done")


def test_r13_markdown_merges_consecutive_same_role(tmp_path):
    p = _md(tmp_path / "s.md", [
        "## record m-1", "", "### user", "q", "", "### assistant", "part one", "", "### assistant", "part two", "",
        "## record m-2", "", "### user", "next", "", "### assistant", "reply", "", "### user", "trailing",
    ])
    recs = read_markdown(p)
    assert [(t.role, t.text) for t in recs[0].turns] == [("user", "q"), ("assistant", "part one\n\npart two")]


# ---------------------------------------------------------------------------------------------------- normalize

def test_r14_role_aliases_case_insensitive():
    out = normalize_record(rec("x", [("Human", "q"), ("Bot", "a"), ("USER", "q2"), ("Assistant", "a2")]))
    assert [t.role for t in out.turns] == ["user", "assistant", "user", "assistant"]


def test_r15_system_messages_kept_in_meta():
    out = normalize_record(rec("x", [("system", "sys one"), ("user", "q"), ("system", "sys two"), ("assistant", "a")]))
    assert [t.role for t in out.turns] == ["user", "assistant"]
    assert out.meta["system"] == ["sys one", "sys two"]


def test_r16_all_zero_width_characters_removed():
    assert normalize_text("a​b‌c‍d﻿e") == "abcde"


def test_r17_nfkc_normalisation():
    assert normalize_text("ｆｕｌｌ width ﬁle") == "full width file"


def test_r18_whitespace_only_lines_collapse():
    assert normalize_text("para one\n  \n\t\n \npara two") == "para one\n\npara two"
    assert normalize_text("a  \t b\n\n\n\nc") == "a b\n\nc"


def test_r19_exact_duplicates_detected_after_normalisation():
    a = rec("a", [("user", "Hello   there"), ("assistant", "General  reply")], seq=0)
    b = rec("b", [("user", "Hello there"), ("assistant", "General reply ")], seq=1)
    result = dedupe([normalize_record(a), normalize_record(b)], dcfg())
    assert len(result.kept) == 1
    assert len(result.removed) == 1


# ---------------------------------------------------------------------------------------------------- dedupe

def test_r20_short_texts_compared_on_their_tokens():
    a = rec("s1", [("user", "hi there")], seq=0)
    b = rec("s2", [("user", "bye now")], seq=1)
    c = rec("s3", [("user", "Hi, there!")], seq=2)
    clusters = near_duplicate_clusters([a, b, c], dcfg())
    assert clusters["s2"] == "s2"
    assert clusters["s1"] == "s1" and clusters["s3"] == "s1"


def test_r21_minhash_stable_across_processes():
    code = ("from {{PKG}}.dedupe import MinHasher\n"
            "from {{PKG}}.textutil import shingles, words\n"
            "print(list(MinHasher(16, 7).signature(shingles(words('one two three four five six seven'), 3))))\n")
    outs = {run_py(code, seed) for seed in ("1", "2", "3")}
    assert len(outs) == 1


def test_r22_choose_bands_uses_documented_s_curve():
    assert choose_bands(128, 0.8) == 8
    assert choose_bands(128, 0.5) == 32


def test_r23_threshold_is_inclusive():
    a = {("x",), ("y",), ("z",), ("w",), ("v",)}
    b = {("x",), ("y",), ("z",), ("w",)}
    assert jaccard(a, b) == 0.8
    assert is_near_duplicate(a, b, 0.8)


def test_r24_union_find_root_is_smallest_index():
    uf = UnionFind(5)
    uf.union(1, 3)
    uf.union(2, 3)
    assert uf.find(3) == 1 and uf.find(2) == 1
    uf.union(4, 0)
    assert uf.find(4) == 0


def test_r25_exact_duplicates_keep_earliest():
    same = [("user", "same text"), ("assistant", "reply")]
    a, b, c = rec("a", same, seq=0), rec("b", same, seq=1), rec("c", same, seq=2)
    kept, removed = remove_exact([c, a, b])
    assert [r.record_id for r in kept] == ["a"]
    assert removed == {"b": "a", "c": "a"}


# ---------------------------------------------------------------------------------------------------- judge

def test_r26_placeholders_inside_texts_not_expanded():
    r = rec("x", [("user", "say {assistant_text} and {group} literally"), ("assistant", "ANSWER-TEXT")])
    prompt = render_prompt(r, "v2")
    assert "say {assistant_text} and {group} literally" in prompt
    assert prompt.count("ANSWER-TEXT") == 1


def test_r27_max_retries_counts_retries():
    client = MockJudgeClient({"x": [TransientJudgeError("t"), TransientJudgeError("t"), reply(P, "why")]})
    j = JudgeRunner(client, jcfg(max_retries=2)).judge(simple("x"))
    assert j.status == "ok" and j.verdict == P
    assert len(client.calls) == 3


def test_r28_retries_reuse_request_id():
    client = MockJudgeClient({"x": [TransientJudgeError("t"), reply(P, "why")]})
    j = JudgeRunner(client, jcfg(max_retries=3)).judge(simple("x"))
    ids = {c.request_id for c in client.calls}
    assert len(client.calls) == 2 and len(ids) == 1
    assert j.request_id in ids


def test_r29_rejected_request_not_retried():
    client = MockJudgeClient({"x": [JudgeRequestError("too long"), reply(P, "why")]})
    j = JudgeRunner(client, jcfg(max_retries=2)).judge(simple("x"))
    assert len(client.calls) == 1
    assert j.status == "error" and j.verdict is None


def test_r30_cache_key_includes_model_and_temperature():
    cache = JudgeCache()
    client = MockJudgeClient({"x": [reply(N, "first"), reply(P, "second"), reply(P, "third")]})
    r = simple("x")
    j1 = JudgeRunner(client, jcfg(model="judge-a"), cache).judge(r)
    j2 = JudgeRunner(client, jcfg(model="judge-b"), cache).judge(r)
    j3 = JudgeRunner(client, jcfg(model="judge-b", temperature=0.7), cache).judge(r)
    assert len(client.calls) == 3
    assert (j1.verdict, j2.verdict) == (N, P)
    assert j2.model == "judge-b" and not j2.from_cache
    assert j3.temperature == 0.7 and not j3.from_cache


def test_r31_cached_judgement_keeps_rationale():
    client = MockJudgeClient({"x": [reply(P, "{{RATIONALE_POS}}")]})
    runner = JudgeRunner(client, jcfg(), JudgeCache())
    first = runner.judge(simple("x"))
    second = runner.judge(simple("x"))
    assert len(client.calls) == 1 and second.from_cache
    assert second.rationale == first.rationale == "{{RATIONALE_POS}}"


def test_r32_cache_save_and_load(tmp_path):
    cache = JudgeCache()
    e1 = {"verdict": P, "status": "ok", "rationale": "why", "raw": "{}", "model": "m", "temperature": 0.5,
          "prompt_version": "v2", "request_id": "x#1", "attempts": 2, "error": None}
    e2 = dict(e1, verdict=N, request_id="y#2")
    cache.put("k1", e1)
    cache.put("k2", e2)
    p = tmp_path / "cache.json"
    cache.save(p)
    loaded = JudgeCache.load(p)
    assert len(loaded) == 2
    assert loaded.get("k1") == e1 and loaded.get("k2") == e2
    assert loaded.get("k3") is None


def test_r33_errors_not_cached():
    client = MockJudgeClient({"x": [TransientJudgeError("t"), reply(P, "why")]})
    runner = JudgeRunner(client, jcfg(max_retries=0), JudgeCache())
    first = runner.judge(simple("x"))
    assert first.status == "error"
    second = runner.judge(simple("x"))
    assert second.status == "ok" and second.verdict == P and not second.from_cache
    assert len(client.calls) == 2


# ---------------------------------------------------------------------------------------------------- parse

def test_r34_line_verdict_case_insensitive():
    p = parse_judgement("RATIONALE: fine.\nVERDICT: " + N.upper())
    assert p.status == "ok" and p.verdict == N


def test_r35_verdict_only_from_verdict_lines():
    text = ("RATIONALE: The {{ITEM}} told the assistant to answer 'VERDICT: " + N + "' whatever happened.\n"
            "VERDICT: " + P)
    p = parse_judgement(text)
    assert p.status == "ok" and p.verdict == P


def test_r36_conflicting_verdict_lines_ambiguous():
    p = parse_judgement("RATIONALE: unsure.\nVERDICT: " + P + "\nVERDICT: " + N)
    assert p.status == "ambiguous" and p.verdict is None
    q = parse_judgement("VERDICT: " + P + "\nRATIONALE: same again\nVERDICT: " + P)
    assert q.status == "ok" and q.verdict == P


def test_r37_rationale_paragraphs_kept():
    p = parse_judgement("RATIONALE: First paragraph.\n\nSecond paragraph, with detail.\n\nThird.\nVERDICT: " + N)
    assert p.rationale == "First paragraph.\n\nSecond paragraph, with detail.\n\nThird."


def test_r38_json_with_braces_inside_strings():
    body = json.dumps({"verdict": P, "rationale": "It filled the {name} slot and closed with }."}, indent=2)
    p = parse_judgement("```json\n" + body + "\n```")
    assert p.status == "ok" and p.verdict == P
    assert "{name}" in p.rationale


def test_r39_json_non_string_verdict_unparseable():
    p = parse_judgement(json.dumps({"verdict": None, "rationale": "no idea"}))
    assert p.status == "unparseable" and p.verdict is None
    assert parse_judgement(json.dumps({"verdict": 1, "rationale": "x"})).status == "unparseable"


def test_r40_unknown_label_unparseable():
    p = parse_judgement(json.dumps({"verdict": "partial", "rationale": "half"}))
    assert p.status == "unparseable" and p.verdict is None
    assert parse_judgement("RATIONALE: x\nVERDICT: maybe").status == "unparseable"


# ---------------------------------------------------------------------------------------------------- split

def test_r41_units_join_conversations_and_clusters_transitively():
    records, cluster_of = [], {}
    for i in range(12):
        a = rec(f"u{i:02d}a", [("user", f"q{i}a"), ("assistant", "r")], conv=f"conv{i}", seq=3 * i)
        b = rec(f"u{i:02d}b", [("user", f"q{i}b"), ("assistant", "r")], conv=f"conv{i}", seq=3 * i + 1)
        c = rec(f"u{i:02d}c", [("user", f"q{i}c"), ("assistant", "r")], conv=f"other{i}", seq=3 * i + 2)
        records += [a, b, c]
        cluster_of.update({a.record_id: a.record_id, b.record_id: b.record_id, c.record_id: b.record_id})
    split_of = assign_splits(records, cluster_of, {"train": 0.34, "dev": 0.33, "test": 0.33}, seed=5)
    for i in range(12):
        assert len({split_of[f"u{i:02d}{x}"] for x in "abc"}) == 1, i


def test_r42_split_identical_across_processes():
    code = textwrap.dedent("""
        import json
        from {{PKG}}.records import Turn, make_record
        from {{PKG}}.split import assign_splits
        groups = ["{{GROUP_A}}", "{{GROUP_B}}", "{{GROUP_C}}", "{{GROUP_D}}"]
        recs = [make_record("r%03d" % i, "c%03d" % i, 0, groups[i % 4], [Turn("user", "q%d" % i),
                Turn("assistant", "a")], seq=i) for i in range(40)]
        print(json.dumps(assign_splits(recs, {}, None, seed=3), sort_keys=True))
    """)
    outs = {run_py(code, seed) for seed in ("0", "1", "2", "3", "4", "5")}
    assert len(outs) == 1


def test_r43_fractions_must_sum_to_one():
    recs = [rec(f"r{i}", seq=i) for i in range(4)]
    with pytest.raises(ValueError):
        assign_splits(recs, {}, {"train": 0.8, "dev": 0.3, "test": 0.1})
    with pytest.raises(ValueError):
        assign_splits(recs, {}, {"train": 0.5, "dev": 0.2, "test": 0.2})


def test_r44_largest_remainder_allocation():
    recs = [rec(f"r{i:02d}", [("user", f"q{i}"), ("assistant", "a")], seq=i) for i in range(20)]
    counts = split_counts(assign_splits(recs, {}, {"train": 0.33, "dev": 0.33, "test": 0.34}, seed=1))
    assert counts == {"train": 7, "dev": 6, "test": 7}
    counts = split_counts(assign_splits(recs[:10], {}, {"train": 0.7, "dev": 0.15, "test": 0.15}, seed=1))
    assert counts == {"train": 7, "dev": 2, "test": 1}


# ---------------------------------------------------------------------------------------------------- stats

def test_r45_non_ok_judgements_excluded():
    records = [rec(f"r{i}", seq=i) for i in range(4)]
    js = {"r0": jd("r0", P), "r1": jd("r1", P), "r2": jd("r2", None, "error"), "r3": jd("r3", None, "unparseable")}
    row = [r for r in rate_table(records, js) if r.group == GA][0]
    assert (row.n, row.k, row.n_excluded) == (2, 2, 2)
    assert row.rate == 1.0


def test_r46_z_is_two_sided():
    assert z_for(0.95) == pytest.approx(1.959964, abs=1e-5)
    assert z_for(0.90) == pytest.approx(1.644854, abs=1e-5)


def test_r47_wilson_interval_values():
    def ref(k, n, z):
        p = k / n
        d = 1 + z * z / n
        c = (p + z * z / (2 * n)) / d
        h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
        return max(0.0, c - h), min(1.0, c + h)

    for k, n in ((3, 10), (0, 7), (7, 7), (12, 40)):
        assert wilson_interval(k, n, 1.96) == pytest.approx(ref(k, n, 1.96), abs=1e-9)


def test_r48_wilson_empty_group():
    assert wilson_interval(0, 0, 1.96) == (0.0, 1.0)


def test_r49_bootstrap_ci():
    outcomes = [1] * 30 + [0] * 70
    a = bootstrap_rate_ci(outcomes, n_boot=500, confidence=0.95, seed=3)
    assert a == bootstrap_rate_ci(outcomes, n_boot=500, confidence=0.95, seed=3)
    lo, hi = a
    assert 0.15 < lo < 0.3 < hi < 0.45
    lo50, hi50 = bootstrap_rate_ci(outcomes, n_boot=500, confidence=0.5, seed=3)
    assert lo <= lo50 <= hi50 <= hi and (hi50 - lo50) < (hi - lo)
    assert tuple(bootstrap_rate_ci([1, 1, 1], n_boot=50, seed=0)) == (1.0, 1.0)
    with pytest.raises(ValueError):
        bootstrap_rate_ci([], n_boot=10)


def test_r50_kappa_matches_records_by_id():
    va = {"r1": P, "r2": N, "r3": P, "r4": N}
    a = [jd(rid, v) for rid, v in va.items()]
    b = [jd(rid, va[rid]) for rid in ("r2", "r1", "r4", "r3")]
    assert cohen_kappa(a, b) == pytest.approx(1.0)
    assert cohen_kappa(a, b + [jd("r9", P)]) == pytest.approx(1.0)


def test_r51_kappa_expected_agreement_uses_both_judges():
    a = [jd("r1", P), jd("r2", P), jd("r3", P), jd("r4", N)]
    b = [jd("r1", P), jd("r2", N), jd("r3", N), jd("r4", N)]
    assert cohen_kappa(a, b) == pytest.approx(0.2)


def test_r52_kappa_single_label_full_agreement():
    a = [jd(f"r{i}", P) for i in range(5)]
    assert cohen_kappa(a, list(a)) == 1.0


def test_r53_all_row_pools_counts():
    records = [rec("a1", group=GA)] + [rec(f"b{i}", group=GB, seq=i + 1) for i in range(3)]
    js = {"a1": jd("a1", P), "b0": jd("b0", N), "b1": jd("b1", N), "b2": jd("b2", N)}
    all_row = rate_table(records, js)[-1]
    assert all_row.group == "ALL" and (all_row.n, all_row.k) == (4, 1)
    assert all_row.rate == pytest.approx(0.25)


# ---------------------------------------------------------------------------------------------------- export

def test_r54_long_rationale_exported_in_full(tmp_path):
    long = " ".join(["{{RATIONALE_POS}}"] * 120)
    assert len(long) > 5000
    _, rows, _ = export(tmp_path, [simple("x")], {"x": jd("x", P, rationale=long)})
    assert rows[0]["rationale"] == long


def test_r55_manifest_sha256_matches_file(tmp_path):
    records = [simple("x"), simple("y")]
    manifest, _, out = export(tmp_path, records, {"x": jd("x", P), "y": jd("y", N)})
    digest = hashlib.sha256((out / "corpus.jsonl").read_bytes()).hexdigest()
    assert manifest["files"]["corpus.jsonl"]["sha256"] == digest
    assert json.loads((out / "manifest.json").read_text())["files"]["corpus.jsonl"]["sha256"] == digest


def test_r56_rows_ordered_train_dev_test(tmp_path):
    records = [simple(f"r{i}") for i in range(1, 7)]
    split_of = {"r1": "test", "r2": "train", "r3": "dev", "r4": "train", "r5": "test", "r6": "dev"}
    _, rows, _ = export(tmp_path, records, {r.record_id: jd(r.record_id, P) for r in records}, split_of)
    assert [row["record_id"] for row in rows] == ["r2", "r4", "r3", "r6", "r1", "r5"]


def test_r57_record_without_judgement_exported(tmp_path):
    _, rows, _ = export(tmp_path, [simple("x"), simple("y")], {"x": jd("x", P)})
    by_id = {row["record_id"]: row for row in rows}
    assert by_id["y"]["status"] == "missing" and by_id["y"]["verdict"] is None
    assert by_id["x"]["status"] == "ok" and by_id["x"]["verdict"] == P


def test_r58_truncation_marker_counts_removed_characters():
    assert truncate("a" * 25, 10) == "a" * 10 + "…[truncated 15 chars]"
    assert truncate("short", 10) == "short"


def test_r59_read_corpus(tmp_path):
    d = tmp_path / "exp"
    d.mkdir()
    rows = [{"schema_version": 3, "record_id": "r1"}, {"schema_version": 3, "record_id": "r2"}]
    (d / "corpus.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert [r["record_id"] for r in read_corpus(d / "corpus.jsonl")] == ["r1", "r2"]
    assert [r["record_id"] for r in read_corpus(d)] == ["r1", "r2"]
    (d / "corpus.jsonl").write_text(json.dumps({"schema_version": 2, "record_id": "r1"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_corpus(d)


def test_r60_system_messages_exported(tmp_path):
    r = rec("x", [("user", "q"), ("assistant", "a")], meta={"system": ["sys prompt"]})
    _, rows, _ = export(tmp_path, [r], {"x": jd("x", P)})
    assert rows[0]["system"] == ["sys prompt"]


def test_r61_validate_command(tmp_path, capsys):
    d = tmp_path / "exp"
    d.mkdir()
    body = "".join(json.dumps({"schema_version": 3, "record_id": f"r{i}"}, sort_keys=True) + "\n" for i in range(3))
    (d / "corpus.jsonl").write_text(body, encoding="utf-8")
    manifest = {"schema_version": 3, "counts": {"records": 3},
                "files": {"corpus.jsonl": {"sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "lines": 3}}}
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert main(["validate", str(d)]) == 0
    (d / "corpus.jsonl").write_text(body.replace('"r1"', '"r7"'), encoding="utf-8")
    assert main(["validate", str(d)]) not in (0, None)


# ---------------------------------------------------------------------------------------------------- pipeline / cli

def _two_record_source(path, prefix):
    return write_jsonl(path, [
        {"id": f"{prefix}-1", "conversation_id": f"{prefix}c1", GROUP_KEY: GA,
         "messages": msgs(("user", f"{prefix} first question"), ("assistant", "first reply"))},
        {"id": f"{prefix}-2", "conversation_id": f"{prefix}c2", GROUP_KEY: GB,
         "messages": msgs(("user", f"{prefix} second question"), ("assistant", "second reply"))},
    ])


def test_r62_seq_numbers_all_sources_in_order(tmp_path):
    _two_record_source(tmp_path / "one.jsonl", "a")
    _two_record_source(tmp_path / "two.jsonl", "b")
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"sources": ["one.jsonl", "two.jsonl"]}))
    recs = ingest_sources(load_config(cfg_path))
    assert [r.record_id for r in recs] == ["a-1", "a-2", "b-1", "b-2"]
    assert [r.seq for r in recs] == [0, 1, 2, 3]


def test_r63_manifest_counts_every_input_record(tmp_path):
    write_jsonl(tmp_path / "src.jsonl", [
        {"id": "x1", "conversation_id": "k1", GROUP_KEY: GA, "messages": msgs(("user", "alpha one"), ("assistant", "r one"))},
        {"id": "x2", "conversation_id": "k2", GROUP_KEY: GA, "messages": msgs(("user", "alpha one"), ("assistant", "r one"))},
        {"id": "x3", "conversation_id": "k3", GROUP_KEY: GA, "messages": msgs(("user", "unanswered"))},
        {"id": "x4", "conversation_id": "k4", GROUP_KEY: GA, "messages": msgs(("user", "beta two"), ("assistant", "r two"))},
    ])
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"sources": ["src.jsonl"]}))
    result = build_corpus(load_config(cfg_path), MockJudgeClient(), tmp_path / "out")
    counts = result.manifest["counts"]
    assert (counts["records"], counts["n_unjudgeable"], counts["n_duplicates"]) == (2, 1, 1)
    assert counts["n_input"] == 4


def test_r64_cli_build_passes_set_overrides(tmp_path):
    _two_record_source(tmp_path / "src.jsonl", "a")
    (tmp_path / "judge_script.jsonl").write_text("")
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"sources": ["src.jsonl"]}))
    out = tmp_path / "out"
    code = main(["build", "--config", str(cfg_path), "--out", str(out), "--set", "judge.model=judge-other",
                 "--set", "split.seed=11"])
    assert code == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["config"]["judge"]["model"] == "judge-other"
    assert manifest["config"]["split"]["seed"] == 11
    first = json.loads((out / "corpus.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first["judge"]["model"] == "judge-other"
