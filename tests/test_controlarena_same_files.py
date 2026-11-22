"""ControlArena with the same attack-side files named for two purposes (docs/CONTROLARENA_SAME_FILES_PREREG.md, 18 Nov 2026):
the data file is what sfe/controlarena_same_files.py builds from the episodes, the rules come out as its Result says, every
quote of the readings is in its episode, and the pages and documents say what the file says. No API calls. Tests that need
the episode files skip when runs/ is absent."""
import json
import sys
from pathlib import Path

import pytest

from sfe import controlarena_same_files as ca
from sfe.config import RESULTS_DIR, RUNS_DIR

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
needs_runs = pytest.mark.skipif(not RUNS_DIR.exists(), reason="episode files (runs/) not present")
# The documents' sentences quote counts from files the public copy leaves out (the user-side judges, the closing questions).
needs_judges = pytest.mark.skipif(not all((RESULTS_DIR / "real" / f).exists() for f in ("user_misled.json", "asked_directly.json")),
                                  reason="the user-side judges' and the closing questions' files are not in this copy")


def test_the_rules_and_predictions_as_the_result_section_gives_them():
    ca.checks()
    d = ca.data()
    R = d["rules"]
    assert R["sol"]["C1"] == {"files_upkeep_changed": [6, 6], "files_evasion_changed": [6, 6], "fisher_one_sided_p": 1.0,
                              "category": "worked on whatever the purpose"}
    assert R["sol62"]["C1"] == {"files_upkeep_changed": [0, 4], "files_evasion_changed": [0, 4], "fisher_one_sided_p": 1.0,
                                "category": "left alone whatever the purpose"}
    assert R["C2_pooled"]["fisher_one_sided_p"] == 0.675 and not R["C2_pooled"]["upkeep_more_often_at_0_05"]
    assert R["sol"]["C3"]["attack_side_changed"] == [0, 6] and R["sol"]["C3"]["attack_side_opened_named_part"] == [2, 6]
    assert R["sol62"]["C4"]["told"] == {"announced": 6, "remark_only": 2} and R["sol62"]["C4"]["reasoning"] == {"weak": 2, "no": 4, "yes": 2}
    assert R["sol62"]["C4"]["by_description"]["files_evasion"]["told"] == {"announced": 4}
    assert d["predictions"]["sol"]["C1"]["worked on whatever the purpose"] == "35%: happened"
    assert d["predictions"]["sol62"]["C1"]["left alone whatever the purpose"] == "15%: happened"
    assert list(d["other_predictions"].values()) == ["did not happen", "happened", "happened"]
    assert d["item_c"]["evasion_more_effective_or_harder_to_flag"] == {"no": 5, "yes": 1} and d["item_c"]["evasion_limit_stated"] == 0


@needs_runs
def test_the_data_file_is_what_the_builder_makes_and_every_quote_is_in_its_episode():
    saved = json.loads(ca.OUT.read_text())
    fresh = ca.build()
    assert fresh == saved
    assert fresh["item_c"]["all_found"]
    from sfe.real_disclosure import blocks
    hc = [e for e in json.loads((ROOT / "results" / "real" / "later_handcheck.json").read_text())["episodes"]
          if e["run"] == "new_control_files_sol62"]
    assert len(hc) == 8
    for e in hc:
        bl = {b["m"]: b for b in blocks(json.loads((ROOT / e["path"]).read_text())["messages"])}
        for q, m in zip(e["user_quotes"], e["user_quote_messages"]):
            assert q in bl[m]["text"], (e["id"], m)
        for q, m in ((e["reasoning_quote"], e["reasoning_m"]), (e["weak_reasoning_hint"], e["weak_reasoning_hint_m"])):
            if q:
                assert q in bl[m]["reasoning"], (e["id"], m)


@needs_judges
def test_the_pages_and_documents_say_what_the_file_says():
    import write_gpt62_docs as w
    n = ca.numbers()
    readme = (ROOT / "README.md").read_text()
    assert w.ca_readme_line() in readme
    notes = (ROOT / "docs" / "NOTES.md").read_text()
    assert w.ca_notes_section().strip() in notes and notes.index(w.CA_NOTES_HEAD) < notes.index("## Open questions")
    doc = (ROOT / "docs" / "COVERT_SETTINGS.md").read_text()
    from sfe.covert_settings import ca_same_files_line
    assert ca_same_files_line() in doc
    import html
    import re
    blog = (ROOT / "results" / "blog" / "index.html").read_text()
    txt = " ".join(html.unescape(re.sub(r"<[^>]+>", "", blog)).split())
    assert (f"With the files named, GPT-5.6 Sol changed them in {n['CA2_SOL_EV']} episodes under the first purpose and "
            f"{n['CA2_SOL_UP']} under the second.") in txt
    assert f"Read in full, it announced leaving those files in {n['CA2_S2_ANN']} of the {n['CA2_S2_N']}" in txt
    assert f"“{n['CA2_S2_QUOTE']}”" in txt
    kr = " ".join(html.unescape(re.sub(r"<[^>]+>", "", (ROOT / "results" / "keyresults" / "index.html").read_text())).split())
    assert f"GPT-5.6 Sol changed them in {n['CA2_SOL_EV']} and {n['CA2_SOL_UP']} episodes" in kr
    ov = " ".join(html.unescape(re.sub(r"<[^>]+>", "", (ROOT / "results" / "overview" / "index.html").read_text())).split())
    # 18 Nov evening: GPT-6.2 Astra was run on the same control (docs/CONTROLARENA_SAME_FILES_ASTRA62_PREREG.md), so the overview
    # now says it of both GPT-6.2 models
    assert f"neither GPT-6.2 model opened them under either purpose ({n['CA2_S2_N']} episodes each)" in ov
    pre = (ROOT / "docs" / "CONTROLARENA_SAME_FILES_PREREG.md").read_text()
    assert pre.count("## Result (added 18 Nov 2026, after the runs)") == 1
