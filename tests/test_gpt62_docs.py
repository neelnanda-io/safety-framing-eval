"""The GPT-6.2 models (18 Nov 2026) in the project's documents: the README subsection, the notes section and the run log
are exactly what scripts/write_gpt62_docs.py generates from the result files, the claims they make hold against those
files (sfe/gpt62_counts.py), and docs/COVERT_SETTINGS.md keeps the twenty-two models' tables as they were while giving
the GPT-6.2 models a section of their own. No API calls. Tests that need the episode files skip when runs/ is absent."""
import json
import sys
from pathlib import Path

import pytest

from sfe import covert_settings as cs
from sfe import gpt62_counts as g62
from sfe.config import RESULTS_DIR, RUNS_DIR

ROOT = RESULTS_DIR.parent
sys.path.insert(0, str(ROOT / "scripts"))
needs_runs = pytest.mark.skipif(not RUNS_DIR.exists(), reason="episode files (runs/) not present")
# The documents quote counts of the user-side judges and of the closing questions asked again, whose files the public copy
# leaves out (results/real/user_misled.json, results/real/asked_directly.json): there they cannot be regenerated.
needs_judges = pytest.mark.skipif(not all((RESULTS_DIR / "real" / f).exists() for f in ("user_misled.json", "asked_directly.json")),
                                  reason="the user-side judges' and the closing questions' files are not in this copy")
# The run log's generated section counts the one-turn check smoke62, which no data release holds.
needs_smoke62 = pytest.mark.skipif(not (RUNS_DIR / "smoke62").exists(), reason="smoke62 is not in the data release")


@pytest.fixture(scope="module")
def w():
    import write_gpt62_docs
    return write_gpt62_docs


@needs_runs
def test_the_claims_hold_against_the_result_files():
    g62.checks()
    n = g62.numbers()
    assert (n["G62_A_SAFE"], n["G62_A_PROD"], n["G62_A_X2P"]) == ("5 of 12", "18 of 18", "0.0004")
    assert (n["G62_S_SAFE"], n["G62_S_PROD"], n["G62_S_X2P"]) == ("7 of 12", "18 of 18", "0.0056")
    assert (n["G62_S_X1"], n["G62_S_X1P"], n["G62_S_X1CAT"]) == ("4 of 6", "0.098", "mixed")
    assert (n["G62_OA_SAFE"], n["G62_OS_SAFE"], n["G62_OA_ANN_S"], n["G62_OS_ANN_S"]) == ("0 of 9", "0 of 11", "9 of 9", "11 of 11")
    assert (n["G62_A_ANN_S"], n["G62_S_ANN_S"], n["G62_A_ANN_I"], n["G62_S_ANN_I"]) == ("0", "0", "0", "0")       # full reading
    assert (n["G62_A_ANN_S_R"], n["G62_S_ANN_S_R"], n["G62_A_ANN_I_R"], n["G62_S_ANN_I_R"]) == ("1", "2", "0", "2")  # blind readers
    assert (n["G62_A_REASON"], n["G62_S_REASON"]) == ("1", "2")
    assert (n["G62_A_IMPL"], n["G62_S_IMPL"], n["G62_A_X3BASE"], n["G62_A_X3P"]) == ("6 of 18", "6 of 18", "0 of 18", "0.0095")
    assert (n["G62_A_R4B"], n["G62_S_R4B"]) == ("0", "1")
    assert (n["G62_A_GAP"], n["G62_S_GAP"], n["G62_OA_GAPV"], n["G62_OS_GAPV"]) == (
        "+5.1 (+2.9 to +7.6)", "+3.3 (+0.2 to +6.5)", "+10.0", "+9.6")
    assert (n["G62_A_RSL"], n["G62_A_SDK"], n["G62_S_RSL"], n["G62_S_SDK"]) == ("5 of 6", "2 of 6", "3 of 6", "2 of 6")
    assert (n["G62_A_TEST"], n["G62_S_TEST"]) == ("67%", "78%")


@needs_judges
def test_the_readme_subsection_is_the_generated_one(w):
    readme = (ROOT / "README.md").read_text()
    assert readme.count(w.README_START) == 1 and w.readme_block() in readme
    assert "### The GPT-6.2 models (added 18 Nov 2026)" in readme
    assert readme.index("### The GPT-6.2 models (added 18 Nov 2026)") > readme.index("<!-- models-table-end -->")
    # the pointer under the twenty-two-model table, and that table left to its own generator (it has no GPT-6.2 row)
    assert "GPT-6.2 Astra and GPT-6.2 Sol (18 Nov) are not in this table" in readme
    table22 = readme[readme.index("<!-- models-table-start -->"):readme.index("<!-- models-table-end -->")]
    assert "GPT-6.2" not in table22
    assert "(not pre-registered)" in " ".join(w.readme_block().split())


def test_the_readme_table_comes_from_the_analysis_files():
    t = g62.readme_table().splitlines()
    assert [r.split(" | ")[0].lstrip("| ") for r in t[2:]] == ["GPT-6 Astra", "GPT-6.2 Astra", "GPT-6.1 Sol", "GPT-6.2 Sol"]
    assert "| GPT-6.2 Astra | 5 of 12 / 18 of 18 | 0 of 12 / 0 of 18 | +5.1 (+2.9 to +7.6) |" in t[3]
    assert "| GPT-6.2 Sol | 7 of 12 / 18 of 18 | 0 of 12 / 0 of 18 | +3.3 (+0.2 to +6.5) |" in t[5]


@needs_judges
def test_the_notes_section_is_the_generated_one(w):
    notes = (ROOT / "docs" / "NOTES.md").read_text()
    sec = w.notes_section()
    assert sec.strip() in notes and notes.count(w.NOTES_HEAD) == 1
    assert notes.index(w.NOTES_HEAD) < notes.index("## Open questions")
    assert "[GPT-6.2 Astra and GPT-6.2 Sol (18 Nov 2026)](#gpt-62-astra-and-gpt-62-sol-18-nov-2026)" in notes
    for rule in ("R2,", "X1,", "X2,", "R3 / X4,", "R4,", "R5,", "R6,", "X5,", "X6,"):
        assert f"| {rule}" in sec, rule
    assert "170 episodes on the real repositories and 144 on the six toy tasks" in sec
    # the three episodes whose reasoning states the choice are a real list (each item on its own line), 18 Nov fix
    lines = sec.splitlines()
    i = next(k for k, x in enumerate(lines) if x.endswith("in three episodes:"))
    block = lines[i + 2:lines.index("", i + 2)]
    assert lines[i + 1] == "" and sum(x.startswith("- GPT-6.2") for x in block) == 3
    assert all(x.startswith(("- GPT-6.2", "  ")) for x in block)        # items, and their wrapped lines indented under them
    # what was checked about the machine, in the same words in the notes and the run log
    assert " ".join(w.MACHINE.split()) in " ".join(sec.split())
    assert " ".join(w.MACHINE.split()) in " ".join(w.runs_section().split())
    assert "cannot reach the internet" not in sec and "cannot reach the internet" not in w.runs_section()


@needs_runs
@needs_judges
def test_the_notes_quote_every_reasoning_line_word_for_word(w):
    from sfe.real_disclosure import blocks
    sec = " ".join(w.notes_section().split())
    for m in g62.NEW:
        for e in g62.reasoning_choice_episodes(m):
            bl = {b["m"]: b for b in blocks(json.loads((ROOT / e["path"]).read_text())["messages"])}
            q = e["reasoning_quote"]
            assert q["quote"] in bl[q["m"]]["reasoning"], e["id"]
            assert f'"{" ".join(q["quote"].split())}"' in sec, e["id"]


@needs_runs
@needs_smoke62
def test_the_run_log_section_is_the_generated_one(w):
    runs = (ROOT / "docs" / "RUNS.md").read_text()
    assert w.runs_section().strip() in runs and runs.count(w.RUNS_HEAD) == 1
    assert runs.index(w.RUNS_HEAD) < runs.index("## Spoiled, pilot and calibration runs")
    for run in ("smoke62", "real2_astra62", "real2_sol62", "real2_more_astra62", "real2_more_sol62", "real4_implied_astra62",
                "real4_implied_sol62", "new_control_astra62", "new_control_sol62", "new_generic4_astra62", "new_generic4_sol62"):
        assert f"| `{run}` |" in runs, run
    for run in ("w5_astra62", "w5_sol62"):                    # the toy-task runs, finished 06:22 GMT on 18 Nov 2026
        assert f"| `{run}` |" in runs, run


def test_the_settings_doc_keeps_the_twenty_two_models_apart_from_the_gpt62_models():
    d = json.loads((RESULTS_DIR / "real" / "covert_settings.json").read_text())
    assert not {r["model"] for r in d["rows"]} & set(cs.LATER_MODELS)          # the twenty-two-model tables are unchanged
    assert set(d["gpt62"]["models"]) == set(cs.LATER_MODELS)
    g = json.loads((RESULTS_DIR / "real" / "gpt62.json").read_text())
    for m in g62.NEW:
        s = d["gpt62"]["summary"][m]
        R = g["rules"][m]
        assert (s["implied"]["core_left_alone"], s["implied"]["episodes"]) == tuple(R["R4"]["implied_core_left_alone"])
        assert s["implied"]["left_alone"]["announced"] == 0
        assert s["control_attack"]["core_left_alone"] == R["R5"]["attack side"]["named_part_left_alone"]
        assert s["control_monitor"]["core_left_alone"] == R["R5"]["monitor side"]["named_part_left_alone"]
        assert (s["stated_borderline"]["core_left_alone"], s["stated_borderline"]["episodes"]) == (
            R["R6"]["training_code_left_alone"], R["R6"]["borderline_episodes"])
        assert [s["stated_baseline"]["core_left_alone"], s["stated_baseline"]["episodes"]] == R["R6"]["baseline_left_alone"]
    doc = (ROOT / "docs" / "COVERT_SETTINGS.md").read_text()
    head = "## GPT-6.2 Astra and GPT-6.2 Sol (added 18 Nov 2026)"
    assert doc.count(head) == 1 and doc.index(head) < doc.index("## Limits")
    before = doc[:doc.index(head)]
    assert "GPT-6.2 Astra |" not in before and "GPT-6.2 Sol |" not in before     # no GPT-6.2 row in the earlier tables


@needs_runs
def test_the_key_results_block_has_the_same_table_and_numbers():
    from sfe import build_keyresults as kr
    page = kr.build()
    i = page.index("5. The successors, GPT-6.2 Astra and GPT-6.2 Sol (added 18 Nov)")
    j = page.index("How this fits OpenAI’s report")
    sec = page[i:j]
    assert g62.html_table(kr.esc, kr.ONE_WHERE) in sec          # with the one blind reader's column (21 Nov 2026)
    n = g62.numbers()
    for k in ("G62_A_SAFE", "G62_A_PROD", "G62_A_X2P", "G62_S_SAFE", "G62_S_PROD", "G62_S_X2P", "G62_S_X1"):
        assert n[k] in sec, k
    assert f"states the choice in {n['G62_A_REASON']} GPT-6.2 Astra episode and {n['G62_S_REASON']} GPT-6.2 Sol episodes" in sec
    for word in ("established", "fixed", "hidden on purpose", "got worse", "sandbag"):
        assert word not in sec.lower(), word



def test_the_toy_result_and_its_follow_ups_come_from_the_episodes():
    """R1 recomputed from the episode files with the functions sfe/summary_plot.py uses equals results/gpt62_toy.json, and
    the descriptive counts the write-up quotes hold."""
    from sfe import gpt62_toy as gt
    t = g62.toy()
    if not RUNS_DIR.exists():
        pytest.skip("episode files (runs/) not present")
    fresh = gt.r1()
    for lab in ("GPT-6.2 Astra", "GPT-6.2 Sol"):
        for k in ("pairs", "dropped", "gap", "gap_ci", "p", "holm_p", "category"):
            assert fresh[lab][k] == t["r1"][lab][k], (lab, k)
    n = g62.numbers()
    assert (n["G62_A_TOY"], n["G62_S_TOY"], n["G62_T_A_P"], n["G62_T_S_P"]) == ("+8.1 (+4.8 to +11.7)", "+0.3 (−0.9 to +1.7)", "below 0.0001", "0.59")
    assert (n["G62_OA_TOYV"], n["G62_OS_TOYV"], n["G62_T_PA"], n["G62_T_RL"], n["G62_T_REST"]) == ("+3.1", "+4.4", "+21.1", "+23.7", "−1.1 to +2.5")
    for task in ("prompt_augment", "redteam_loop"):
        diff = t["per_item"][f"GPT-6.2 Astra | {task}"]["differing_items"]
        assert len(diff) == 8 and all(x["capabilities"] == 6 and x["safety"] <= 1 for x in diff), task
    assert t["readings"]["episodes"] == 12 and t["readings"]["all_quotes_found"]
    assert t["readings"]["told"] == {"nothing": 5, "remark_only": 7} and t["readings"]["reasoning"] == {"weak": 6, "yes": 6}


@needs_runs
def test_the_toy_full_readings_quote_their_episodes_word_for_word():
    from sfe import gpt62_toy as gt
    from sfe.toy_disclosure import toy_blocks
    q = gt.check_readings()
    assert len(q) == 12 and all(all(v["user_quotes_found"]) and v["reasoning_quote_found"] is not False
                                and v["weak_hint_found"] is not False for v in q.values())
    import write_gpt62_docs as w
    for path, field, m, _ in w.TOY_QUOTES:                  # the notes' key quotes: exact, in the stated message and field
        bl = {b["m"]: b for b in toy_blocks(json.loads((ROOT / path).read_text())["messages"])}
        assert w.toy_quote(path, field, m) in bl[m]["text" if field == "text" else "reasoning"], (path, m)


def test_the_network_scan_found_no_connection_and_the_queue_copy_names_no_local_path():
    d = json.loads((RESULTS_DIR / "real" / "gpt62_network_scan.json").read_text())
    assert d["episodes"] == 170
    assert not any(a["outcome"].startswith("something came back") for a in d["name_based_attempts"])
    for x in d["numeric_address_or_route_matches"]:        # each read by hand: slicing, a test value, localhost in code
        assert not x["route"] and all(ip in ("127.0.0.1",) for ip in x["ipv4"]), x
    for f in (RESULTS_DIR / "gpt62_toy_queue").iterdir():
        t = f.read_text()
        assert "/Users/" not in t and "/private/tmp/claude" not in t and "sk-or-" not in t, f.name
    st = json.loads((RESULTS_DIR / "gpt62_toy_queue" / "driver_state.json").read_text())
    assert len(st) == 144 and all(v["attempts"][-1]["complete"] for v in st.values())
    assert sum(bool(v["attempts"][-1]["tmp_new_named_and_moved"]) for v in st.values()) == 33
