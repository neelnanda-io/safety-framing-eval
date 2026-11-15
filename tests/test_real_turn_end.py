"""Checks on the end-of-turn labels of the real-repository episodes (sfe/real_turn_end.py,
results/real/turn_end_labels.json). No API calls. Tests of the results file skip when it is missing; the comparison with
the episode files also skips when runs/ is missing (the public copy ships them in the data release instead)."""
import json

import pytest

from sfe import judge
from sfe import real_turn_end as rte
from sfe.config import RUNS_DIR

HAVE_RESULTS = rte.OUT.exists()
needs_results = pytest.mark.skipif(not HAVE_RESULTS, reason="results/real/turn_end_labels.json not present")
needs_runs = pytest.mark.skipif(not (HAVE_RESULTS and RUNS_DIR.exists()), reason="episode files (runs/) not present")


def _entries() -> list[dict]:
    return list(json.loads(rte.OUT.read_text())["entries"].values())


# ---------------------------------------------------------------- the results file

@needs_results
def test_labels_are_from_the_allowed_set():
    for e in _entries():
        assert e["status"] in ("labelled", "judge_refused", "judge_failed"), e["id"]
        if e["status"] == "labelled":
            assert e["label"] in rte.LABELS, (e["id"], e["label"])
        else:
            assert e["label"] is None, e["id"]


@needs_results
def test_every_quote_is_an_exact_substring_of_its_message():
    for e in _entries():
        if e["status"] != "labelled" or e["label"] == "none":
            continue
        assert isinstance(e["quote"], str) and e["quote"].strip(), e["id"]
        assert e["quote"] in e["message"], (e["id"], e["quote"][:80])


@needs_results
def test_none_exactly_when_the_turn_has_no_final_message():
    for e in _entries():
        if e["status"] == "labelled":
            assert (e["label"] == "none") == (e["message"] is None), e["id"]


@needs_results
def test_each_entry_records_judge_model_cost_and_date():
    for e in _entries():
        assert "judge_model" in e and "date" in e and isinstance(e["cost_usd"], (int, float)), e["id"]
        if e["status"] == "labelled" and e["label"] != "none":
            assert e["judge_model"] == rte.JUDGE.model_id
            assert e["attempts"] and all("finish_reason" in a for a in e["attempts"])


@needs_results
def test_one_entry_per_turn_of_every_episode_used():
    d = json.loads(rte.OUT.read_text())
    files = set(d["episodes_used"]["main"]) | set(d["episodes_used"]["implied"])
    ids = [e["id"] for e in d["entries"].values()]
    assert len(ids) == len(set(ids))
    assert {i.rsplit("#t", 1)[0] for i in ids} <= files
    assert len(ids) == 3 * len(files)            # every episode used has three turns


@needs_results
def test_recorded_spending_is_under_the_default_cap():
    d = json.loads(rte.OUT.read_text())
    assert d["total_cost_usd"] <= 5.0
    assert abs(d["total_cost_usd"] - sum(s["spent"] for s in d["spend_log"])) < 1e-6


@needs_results
def test_hand_checks_are_well_formed():
    for e in _entries():
        h = e.get("hand_check")
        if not h:
            continue
        assert h["verdict"] in ("agree", "disagree"), e["id"]
        assert h["correct_label"] in rte.LABELS, e["id"]
        assert h["label_seen"] == e["label"], e["id"]
        assert (h["verdict"] == "agree") == (h["correct_label"] == e["label"]), e["id"]
        if e["label"] == "blocked":
            assert h.get("blocker") and h.get("evidence"), e["id"]


@needs_results
def test_every_stopping_or_refusal_label_was_hand_checked():
    for e in _entries():
        if e["status"] == "labelled" and e["label"] not in ("worked", "none"):
            assert e.get("hand_check"), e["id"]


@needs_runs
def test_messages_match_the_episode_files():
    """Each stored message is the last assistant message of that turn, re-derived from the episode file."""
    turns = {t["id"]: t for t in rte.all_turns()}
    for e in _entries():
        t = turns[e["id"]]
        assert t["message"] == e["message"], e["id"]
        assert t["hit_budget"] == e["hit_budget"] and t["n_tool_calls"] == e["n_tool_calls"], e["id"]


# ---------------------------------------------------------------- helpers (no results file needed)

def test_prompt_is_the_toy_prompt_with_only_the_listed_changes():
    p = judge.PROMPT
    for old, new, _ in rte.PROMPT_CHANGES:
        p = p.replace(old, new)
    assert p == rte.PROMPT
    assert "{message}" in rte.PROMPT and '"quote"' in rte.PROMPT


def test_turn_segments_keep_the_pause_message_inside_its_turn_and_drop_closing_questions():
    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "content": "out"},
            {"role": "user", "content": rte.PAUSE_MSG},
            {"role": "assistant", "content": "summary 1"},
            {"role": "user", "content": rte.TURN_NEXT[0]},
            {"role": "assistant", "content": "summary 2"},
            {"role": "user", "content": rte.TURN_NEXT[1]},
            {"role": "assistant", "content": "interim", "tool_calls": [{"id": "2"}]},
            {"role": "user", "content": "closing question"},
            {"role": "assistant", "content": "answer"}]
    segs = rte.turn_segments(msgs, 3)
    assert [rte.final_message(s) for s in segs] == ["summary 1", "summary 2", None]


def test_files_changed_this_turn_compares_cumulative_diffs():
    d1 = "diff --git a/x.py b/x.py\n+a\n"
    d2 = d1 + "diff --git a/y.py b/y.py\n+b\n"
    d3 = "diff --git a/x.py b/x.py\n+a2\n" + "diff --git a/y.py b/y.py\n+b\n"
    assert rte.files_changed_this_turn("", d1) == ["x.py"]
    assert rte.files_changed_this_turn(d1, d2) == ["y.py"]
    assert rte.files_changed_this_turn(d2, d3) == ["x.py"]
    assert rte.files_changed_this_turn(d1, "") == ["x.py"]     # a change reverted this turn


def test_verify_quote_returns_only_exact_substrings():
    msg = "Implemented **atomic saves**. Training logic is unchanged — no commits."
    assert rte.verify_quote("Training logic is unchanged", msg) == ("Training logic is unchanged", False)
    q, repaired = rte.verify_quote("Implemented atomic saves.", msg)
    assert repaired and q in msg
    q, repaired = rte.verify_quote("Training logic is unchanged - no commits.", msg)
    assert repaired and q in msg
    assert rte.verify_quote("something the message never says", msg) == (None, False)
    assert rte.verify_quote("", msg) == (None, False)


def test_budget_refuses_a_call_that_could_pass_the_cap():
    b = rte.Budget(cap=0.10, spent_before=0.05)
    assert b.reserve(0.03)
    assert not b.reserve(0.03)          # 0.05 spent + 0.03 in flight + 0.03 > 0.10
    assert b.hit
    b.release(0.03)
    b.spent += 0.01
    assert b.reserve(0.03)
