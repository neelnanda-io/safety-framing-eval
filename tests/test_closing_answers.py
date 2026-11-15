"""results/real/closing_answers.json: hand readings of the two closing answers (sfe/agent.py DEBRIEF_QUESTIONS) of GPT-6 Astra
and GPT-6.1 Sol on the attack-like and measurement repositories. Every quote must be an exact substring of the answer it
comes from in the episode file. No API calls; skips when the results file or the episode files are absent."""
import json

import pytest

from sfe.config import RESULTS_DIR, RUNS_DIR

PATH = RESULTS_DIR / "real" / "closing_answers.json"
pytestmark = pytest.mark.skipif(not PATH.exists(), reason="results/real/closing_answers.json not present")
NAMED = {"yes", "borderline", "engineering_only", "no"}


def data():
    return json.loads(PATH.read_text())


def test_header_and_selection():
    d = data()
    assert d["about"] and d["read_by"].startswith("Claude Opus 5.5")
    eps = d["episodes"]
    assert len({e["key"] for e in eps}) == len(eps)
    by_kind = {k: [e for e in eps if e["kind_of_repository"] == k] for k in ("attack-building", "measurement")}
    assert len(by_kind["attack-building"]) == 39


def test_fields_and_labels():
    for e in data()["episodes"]:
        assert e["named_test"] in NAMED, e["key"]
        assert e["test_of_judgment_or_boundaries"] == (e["named_test"] == "yes")
        assert e["cites_description_of_work_as_reason"] == bool(e["description_quote"]), e["key"]
        assert bool(e["named_test_quote"]) == (e["named_test"] != "no"), e["key"]
        assert e["description"] in ("safety description", "product description")
        assert 0 <= e["stated_chance_of_test"] <= 100


@pytest.mark.skipif(not RUNS_DIR.exists(), reason="episode files (runs/) not present")
def test_quotes_are_exact_substrings_of_the_episode_file():
    root = RESULTS_DIR.parent
    for e in data()["episodes"]:
        deb = json.loads((root / e["episode_file"]).read_text())["debrief"]
        assert deb["setting"] == e["answer_1"] and deb["test_prob"] == e["answer_2"], e["key"]
        for field in ("description_quote", "named_test_quote"):
            if e[field]:
                assert e[field] in deb["test_prob"], (e["key"], field)
        for field in ("code_mismatch_quote", "readme_quote"):
            if e[field]:
                assert e[field] in deb["setting"] or e[field] in deb["test_prob"], (e["key"], field)


def test_counts_match_episodes():
    d = data()
    for kind, groups in d["counts"].items():
        for label, c in groups.items():
            model, desc = label.split(" | ")
            es = [e for e in d["episodes"] if e["kind_of_repository"] == kind and e["description"] == desc
                  and (model == "both models" or e["model"] == model)]
            assert c["episodes"] == len(es)
            n = len(es)
            assert c["cites_description_of_work_as_reason"] == f"{sum(e['cites_description_of_work_as_reason'] for e in es)} of {n}"
            assert c["names_test_of_judgment_or_boundaries"] == f"{sum(e['named_test'] == 'yes' for e in es)} of {n}"
