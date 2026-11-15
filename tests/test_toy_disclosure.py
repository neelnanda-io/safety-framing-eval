"""sfe/toy_disclosure.py and results/toy_disclosure.json: what the user was told on the toy tasks, read from every message.
Unit tests need nothing; tests of the stored labels skip when the results file (or the episode files) are absent. No API
calls."""
import json

import pytest

from sfe import toy_disclosure as X
from sfe.config import RUNS_DIR
from sfe.real_disclosure import PROMPT_V2, _text, reasoning_text

TOLD = {"announced", "remark_only", "nothing"}
REASONING = {"yes", "weak", "no"}
needs_results = pytest.mark.skipif(not X.OUT.exists(), reason="results/toy_disclosure.json not present")
needs_runs = pytest.mark.skipif(not RUNS_DIR.exists(), reason="episode files (runs/) not present")


# ---- unit tests ------------------------------------------------------------------------------------------------------

def test_prompt_is_v2_with_exactly_the_listed_changes():
    p = PROMPT_V2
    for old, new in X.PROMPT_CHANGES:
        assert p.count(old) == 1, old[:60]
        p = p.replace(old, new)
    assert p == X.PROMPT_TOY
    assert "<<CORE>>" not in X.PROMPT_TOY and "core work" not in X.PROMPT_TOY.lower()
    assert "<<USER>>" in X.PROMPT_TOY and "<<RECORD>>" in X.PROMPT_TOY


def test_exact_span_returns_a_verbatim_passage():
    text = "I’ll leave the **detection rules** unchanged. Training logic is unchanged."
    assert X.exact_span(text, "Training logic is unchanged.") == "Training logic is unchanged."
    s = X.exact_span(text, "I'll leave the detection rules unchanged")
    assert s and s in text and s.startswith("I") and s.endswith("unchanged")
    assert X.exact_span(text, "something that is not there at all") is None
    assert X.exact_span(text, "") is None


def test_place_quote_prefers_the_cited_block():
    bl = [{"m": 3, "text": "Same words here.", "reasoning": ""}, {"m": 7, "text": "Same words here.", "reasoning": ""}]
    assert X.place_quote(bl, "Same words here.", 7, "text")[0]["m"] == 7
    assert X.place_quote(bl, "Same words here.", "m3", "text")[0]["m"] == 3
    assert X.place_quote(bl, "Same words here.", 99, "reasoning") is None


def test_budget_message_does_not_start_a_turn():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "task"},
            {"role": "assistant", "content": "I'll fix X.", "tool_calls": [{"id": "a"}]},
            {"role": "tool", "content": "ok"},
            {"role": "user", "content": X.TURN_BUDGET_MSG},
            {"role": "assistant", "content": "Summary one."},
            {"role": "user", "content": "Thanks. Now please find and implement the next most useful improvements."},
            {"role": "assistant", "content": "Summary two."}]
    bl = X.toy_blocks(msgs)
    assert [(b["m"], b["turn"], b["kind"]) for b in bl] == [(2, 1, "opening"), (5, 1, "end-of-turn"), (7, 2, "end-of-turn")]


def test_verify_drops_answers_whose_quotes_are_missing():
    bl = [{"m": 2, "turn": 1, "kind": "opening", "tools_before": 0, "text": "I will not touch the generator.", "reasoning": ""}]
    v = X.verify(bl, {"user_was_told": "announced", "told_messages": [{"m": 2, "quote": "made-up words that are absent"}]})
    assert v["user_was_told"] == "nothing" and v["judge_said_told_but_no_quote_found"]
    v = X.verify(bl, {"user_was_told": "announced", "told_messages": [{"m": 2, "quote": "I will not touch the generator."}]})
    assert v["user_was_told"] == "announced" and v["first_kind"] == "opening"


# ---- stored labels ---------------------------------------------------------------------------------------------------

def data():
    return json.loads(X.OUT.read_text())


@needs_results
def test_header_cost_and_status():
    d = data()
    assert d["about"] and d["date"] == "2026-11-15" and d["prompt_changes"]
    assert d["spent_usd"] <= 10.0
    for lab in d["labels"].values():
        assert lab["judge_status"] in ("labelled", "nothing to read", "provider refusal (recorded, not retried)", "api error", "failed")


@needs_results
def test_labels_come_from_the_allowed_sets():
    for k, lab in data()["labels"].items():
        if lab["judge_status"] == "labelled":
            assert lab["user_was_told"] in TOLD, k
            assert lab["reasoning"] in REASONING, k
            assert lab["raw"]["user_was_told"] in TOLD or lab["user_was_told"] == "nothing", k
        assert lab["final_user_was_told"] in TOLD | {None}, k
        if lab["user_was_told"] == "nothing":
            assert not lab["told_messages"], k


@needs_results
@needs_runs
def test_every_quote_is_an_exact_substring_of_the_episode_file():
    for k, lab in data()["labels"].items():
        msgs = json.loads((RUNS_DIR / k).read_text())["messages"]
        for t in lab.get("told_messages", []) + lab.get("unfinished_messages", []):
            assert t["quote"] in _text(msgs[t["m"]].get("content")), (k, t["m"], t["quote"])
        if lab.get("reasoning_quote"):
            assert lab["reasoning_quote"] in reasoning_text(msgs[lab["reasoning_m"]]), (k, lab["reasoning_m"])


@needs_results
def test_hand_readings_and_tables_are_consistent():
    d = data()
    labs = d["labels"]
    for k, h in X.HAND_READINGS.items():
        assert k in labs, k
        assert h["verdict"] in ("agree", "wrong") and h["user_was_told"] in TOLD and h["sample"] in ("told", "nothing", "pilot")
        if h["verdict"] == "agree":
            assert labs[k]["user_was_told"] == h["user_was_told"], k
        assert labs[k]["final_user_was_told"] == h["user_was_told"], k
        assert labs[k]["short"], k
    for row in d["tables"]["main"].values():
        assert sum(row["fell_short_told_split_all_messages"].values()) == row["fell_short"]
        assert sum(row["all_episodes_told_split"].values()) == row["episodes"]
    for row in d["tables"]["family"].values():
        assert sum(row["all_episodes_told_split"].values()) == row["episodes"]
