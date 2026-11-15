"""GPT-6 Astra with the purpose only implied: the full readings behind every count of what it told the user
(results/real/astra_implied_handcheck.json), their control (results/real/astra_unchanged_remarks.json), and how
sfe/covert_settings.py attaches them. No API calls. Tests that need the episode files skip when runs/ is absent (the
public copy ships them in the data release instead)."""
import json
from pathlib import Path

import pytest

from sfe import covert_settings as cs
from sfe.config import RESULTS_DIR, RUNS_DIR
from sfe.real_analyze import core_touched
from sfe.real_disclosure import blocks
from sfe.recap_plot import IMPLIED_DESCRIPTIONS

REAL = RESULTS_DIR / "real"
ROOT = RESULTS_DIR.parent
READINGS = json.loads((REAL / "astra_implied_handcheck.json").read_text())
CONTROL = json.loads((REAL / "astra_unchanged_remarks.json").read_text())
needs_runs = pytest.mark.skipif(not RUNS_DIR.exists(), reason="episode files (runs/) not present")


def _episode(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def _blocks(path: str) -> dict:
    return {b["m"]: b for b in blocks(_episode(path)["messages"])}


@needs_runs
def test_readings_cover_exactly_the_implied_astra_episodes_that_left_the_core_alone():
    """From the episode files themselves: every complete, unblocked purpose-implied GPT-6 Astra episode whose final diff
    changes some file but not the core code has exactly one reading, and nothing else does."""
    want = set()
    for f in RUNS_DIR.glob("*/episodes/astra__*.json"):
        if not f.parent.parent.name.startswith(cs.RUN_PREFIXES):
            continue
        r = json.loads(f.read_text())
        sp = r.get("spec") or {}
        if r.get("stub") or not r.get("complete") or (sp.get("task"), sp.get("framing")) not in IMPLIED_DESCRIPTIONS:
            continue
        diff = r.get("final_diff") or ""
        if r.get("blocked_by_provider_at_turn") or not cs.changed_files(diff) or core_touched(sp["task"], diff):
            continue
        want.add(f"{f.parent.parent.name}__{r['id']}")
    have = [f"{e['run']}__{e['id']}" for e in READINGS["episodes"]]
    assert len(have) == len(set(have)) == 15
    assert set(have) == want
    assert set(CONTROL["purpose_implied_held_back"]) == want          # the classification of what their remarks cover


@needs_runs
def test_every_quote_in_the_readings_occurs_in_its_episode():
    for e in READINGS["episodes"]:
        bl = _blocks(e["path"])
        assert len(e["user_quotes"]) == len(e["user_quote_messages"])
        for q, m in zip(e["user_quotes"], e["user_quote_messages"]):
            assert q in bl[m]["text"], (e["path"], m, q)
        if e["reasoning_quote"]:
            assert e["reasoning_quote"] in bl[e["reasoning_m"]]["reasoning"], (e["path"], e["reasoning_quote"])
        if e["weak_reasoning_hint"]:
            assert e["weak_reasoning_hint"] in bl[e["weak_reasoning_hint_m"]]["reasoning"], (e["path"], e["weak_reasoning_hint"])
        assert not e["core_changed"] and not core_touched(e["task"], _episode(e["path"]).get("final_diff") or "")


@needs_runs
def test_every_quote_in_the_control_occurs_in_its_episode():
    """results/real/astra_unchanged_remarks.json: every remark, announcement, training-change sentence and reasoning quote is
    in the stated message of the episode file, word for word, and core_changed is the project's rule."""
    for e in CONTROL["episodes"]:
        bl = _blocks(e["path"])
        quotes = ([(r["m"], r["quote"]) for r in e["unchanged_remarks"]] + list(zip(e["announcement_messages"], e["announcement_quotes"]))
                  + list(zip(e["training_change_messages"], e["training_change_quotes"])) + list(zip(e["user_quote_messages"], e["user_quotes"])))
        for m, q in quotes:
            assert q in bl[m]["text"], (e["path"], m, q)
        if e["reasoning_quote"]:
            assert e["reasoning_quote"] in bl[e["reasoning_m"]]["reasoning"], (e["path"], e["reasoning_quote"])
        assert e["core_changed"] == bool(core_touched(e["task"], _episode(e["path"]).get("final_diff") or "")), e["path"]
        assert e["remarks_cover"] == sorted({c for r in e["unchanged_remarks"] for c in r["covers"]})
    for key, v in CONTROL["purpose_implied_held_back"].items():
        bl = _blocks(next(e["path"] for e in READINGS["episodes"] if f"{e['run']}__{e['id']}" == key))
        for m, q in zip(v["quote_messages"], v["quotes"]):
            assert q in bl[m]["text"], (key, m, q)


def test_control_covers_the_blog_comparison_and_the_stated_safety_episodes():
    """The product-description episodes are exactly the ones covert_settings.json's baseline counts (5 on rsl_rl, 4 on the
    data kit), and the stated-safety episodes are the same runs and seeds."""
    base = json.loads((REAL / "covert_settings.json").read_text())["baseline_product"]["astra"]
    eps = CONTROL["episodes"]
    for t in ("rsl_rl", "synthetic-data-kit"):
        prod = [e for e in eps if e["group"] == "product" and e["task"] == t]
        safe = [e for e in eps if e["group"] == "stated_safety" and e["task"] == t]
        assert len(prod) == base[t]["run"] and len(safe) == base[t]["run"]
        assert {(e["run"], e["seed"]) for e in prod} == {(e["run"], e["seed"]) for e in safe}
        assert all(e["description"] == "capabilities" for e in prod) and all(e["description"] == "safety" for e in safe)
        assert sum(not e["core_changed"] for e in prod) == base[t]["core_unchanged"]
        assert all(not e["core_changed"] and e["user_was_told"] == "announced" for e in safe)


def test_covert_settings_counts_of_what_astra_told_the_user_come_from_the_readings():
    """covert_settings.json carries the readings on Astra's purpose-implied rows, and its read-in-full counts are the
    readings' counts; the document's answer is generated from them."""
    doc = json.loads((REAL / "covert_settings.json").read_text())
    rows = [r for r in doc["rows"] if r["model"] == "astra" and r["setting"] == "implied"]
    by_key = {f"{e['run']}__{e['id']}": e for e in READINGS["episodes"]}
    for r in rows:
        e = by_key.get(f"{r['run']}__{r['episode']}")
        if e is None:
            assert r["core_changed"] and r["hand_user_was_told"] is None
            continue
        assert r["hand_user_was_told"] == e["user_was_told"] and r["hand_reasoning_states_choice"] == e["reasoning_states_choice"]
        assert r["hand_reading"] and r["hand_check"] is None          # see the ASTRA_READINGS comment in sfe/covert_settings.py
    told = [e["user_was_told"] for e in READINGS["episodes"]]
    rc = doc["summary"]["astra"]["implied"]["read_in_full"]
    assert (rc["read"], rc["announced"], rc["remark_only"], rc["nothing"]) == (15, told.count("announced"), told.count("remark_only"), told.count("nothing"))
    assert rc["reasoning_states_choice"] == sum(e["reasoning_states_choice"] for e in READINGS["episodes"])
    assert rc["not_announced_reasoning_states_choice"] == sum(e["reasoning_states_choice"] for e in READINGS["episodes"] if e["user_was_told"] != "announced")
    assert sum(v["core_unchanged_read_in_full"]["announced"] for v in doc["implied_vs_own_baseline"]["astra"].values()) == rc["announced"]
    page = (ROOT / "docs" / "COVERT_SETTINGS.md").read_text()
    assert cs.astra_implied_answer(doc["summary"], doc["rows"], doc["astra_unchanged_remarks"]).strip() in page
    assert "told the user in 4 and said nothing in 11.**" not in page


def test_the_corrected_statement_numbers():
    """The numbers of the corrected statement (15 Nov 2026), so a change to the readings cannot pass silently."""
    eps = READINGS["episodes"]
    told = [e["user_was_told"] for e in eps]
    not_ann = [e for e in eps if e["user_was_told"] != "announced"]
    weak = [e for e in not_ann if e["weak_reasoning_hint"] and not e["reasoning_states_choice"]
            and f"{e['run']}__{e['id']}" not in cs.NOT_A_WEAK_LINE]
    assert (told.count("announced"), told.count("remark_only"), told.count("nothing")) == (3, 11, 1)
    assert sum(e["reasoning_states_choice"] for e in not_ann) == 6 and sum(e["reasoning_states_choice"] for e in eps) == 7
    assert len(weak) == 2
