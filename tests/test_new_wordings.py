"""The eleven new descriptions of 16 Nov 2026 are used word for word.

docs/NEW_WORDINGS_PREREG.md was committed before any model call. Each context in sfe/new_repos.py (GENERIC5, DATAKIT5) and in
the two task files the harness reads (real_tasks_new/new_rl/task.json, real_tasks/synthetic-data-kit/task.json) must equal the
quoted paragraph there, character for character; each README section must follow from its context by the rule the earlier
descriptions used; and the probabilities in the code must be the ones in the predictions table."""
import json
import re
from pathlib import Path

from sfe import new_repos as nr

ROOT = Path(__file__).resolve().parent.parent
PREREG = ROOT / "docs" / "NEW_WORDINGS_PREREG.md"
HEADING = "## The eleven descriptions, word for word"


def prereg_contexts() -> dict:
    """name -> the quoted paragraph under the name, from the last section of the predictions file."""
    section = PREREG.read_text().split(HEADING, 1)[1]
    return dict(re.findall(r"^`(\w+)`\n> (.+)$", section, flags=re.MULTILINE))


def prereg_probabilities() -> dict:
    """name -> (GPT-6 Astra, GPT-6.1 Sol) from the predictions table."""
    rows = re.findall(r"^\| \d \| `(\w+)` [^|]*\| (\d+)% \| (\d+)% \|", PREREG.read_text(), flags=re.MULTILINE)
    return {n: (int(a) / 100, int(s) / 100) for n, a, s in rows}


def test_the_predictions_file_holds_eleven_descriptions_and_the_code_the_same_eleven():
    quoted = prereg_contexts()
    assert len(quoted) == 11
    assert set(quoted) == set(nr.WORDINGS_BY_NAME) == {w["name"] for w in nr.GENERIC5} | {w["name"] for w in nr.DATAKIT5}
    assert len(nr.GENERIC5) == 6 and len(nr.DATAKIT5) == 5
    assert all(w["name"].startswith("g_") for w in nr.GENERIC5) and all(w["name"].startswith("fg_") for w in nr.DATAKIT5)


def test_each_context_in_the_code_equals_the_quoted_paragraph():
    quoted = prereg_contexts()
    for w in nr.WORDINGS:
        assert w["context"] == quoted[w["name"]], w["name"]


def test_each_context_in_the_task_files_equals_the_quoted_paragraph_and_its_note_follows_the_rule():
    quoted = prereg_contexts()
    rl = json.loads((ROOT / "real_tasks_new" / "new_rl" / "task.json").read_text())["framings"]
    sdk = json.loads((ROOT / "real_tasks" / "synthetic-data-kit" / "task.json").read_text())["framings"]
    for w in nr.GENERIC5:
        assert rl[w["name"]]["context"] == quoted[w["name"]], w["name"]
        assert rl[w["name"]]["note"] == nr.generic_note(quoted[w["name"]], w["section"]), w["name"]
    for w in nr.DATAKIT5:
        assert sdk[w["name"]]["context"] == quoted[w["name"]], w["name"]
        assert sdk[w["name"]]["note"] == nr.datakit_note(quoted[w["name"]]), w["name"]
        assert set(sdk[w["name"]]) == {"context", "note", "edit"}, w["name"]     # the shape of the earlier fg_* entries


def test_the_note_rules_reproduce_the_earlier_notes():
    """The generic rule rebuilds the original monitor-evasion note; the data-kit rule rebuilds every earlier data-kit note
    written in the template (all but fg_attack, which has its own wording, and fg_authorised, which adds a sentence)."""
    assert nr.generic_note(nr.RSL["safety"]["context"], "monitor-robustness") == nr.RSL["safety"]["note"]
    sdk = json.loads((ROOT / "real_tasks" / "synthetic-data-kit" / "task.json").read_text())["framings"]
    earlier = {k: v for k, v in sdk.items() if v.get("context") and k not in nr.WORDINGS_BY_NAME and k not in ("fg_attack", "fg_authorised")}
    assert len(earlier) >= 10
    for k, v in earlier.items():
        assert nr.datakit_note(v["context"]) == v["note"], k


def test_the_probabilities_in_the_code_are_the_predictions():
    probs = prereg_probabilities()
    assert set(probs) == set(nr.WORDINGS_BY_NAME)
    for w in nr.WORDINGS:
        assert (w["p_astra"], w["p_sol"]) == probs[w["name"]], w["name"]


def test_the_earlier_descriptions_are_untouched():
    """The ten stated uses of round 4 are still ten, and no new name reuses an earlier one."""
    assert len(nr.GENERIC) == 10
    assert not set(nr.WORDINGS_BY_NAME) & set(nr.GENERIC_BY_NAME)
    assert len(set(nr.WORDINGS_RUNS.values())) == 4
