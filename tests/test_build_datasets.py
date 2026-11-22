"""The transcript renderer behind sfe/build_datasets.py (no API calls, no episode files)."""
import json
from pathlib import Path

from sfe.build_datasets import CMD_CAP, RESULT_CAP, Marker, call_html, clean, cut, filled, reasoning_of


def test_marker_highlights_the_whole_sentence_once_and_records_it():
    m = Marker(["rather than improving the evader", "never said"])
    out = m.html("I'll look at logging first. I'll focus on tests rather than improving the evader. Then docs.")
    assert "<mark>I&#x27;ll focus on tests rather than improving the evader.</mark>" in out
    assert m.found == {"rather than improving the evader"}                 # the second fragment is reported as missing by the caller
    assert "<mark>" not in m.html("I'll focus on tests rather than improving the evader.")   # only the first occurrence is marked


def test_marker_escapes_everything_else():
    out = Marker(["b"]).html("<a> & b")
    assert out == "<mark>&lt;a&gt; &amp; b</mark>"


def test_clean_hides_this_laptop_and_email_addresses_but_keeps_the_project_folder_name():
    USER = Path.home().name
    text = (f"/Users/{USER}/Code/safety-framing-eval/runs/main3_astra/sandboxes/x and /private/var/folders/9l/abc_123/T/w1 "
            f"by jane.doe@example.org; git@github.com:org/repo.git; akim@users.noreply.github.com; owner {USER} staff")
    out = clean(text)
    assert USER not in out and "/Users/" not in out and "jane.doe" not in out
    assert "<home>/Code/safety-framing-eval/runs/main3_astra/sandboxes/x" in out      # what the agent saw, minus the user name
    assert "<tmp>/w1" in out and "[email]" in out
    assert "git@github.com:org/repo.git" in out and "akim@users.noreply.github.com" in out


def test_reasoning_never_includes_encrypted_entries():
    m = {"reasoning_details": [{"type": "reasoning.encrypted", "data": "SECRET"}, {"type": "reasoning.summary", "summary": " plan "},
                               {"type": "reasoning.text", "text": "thought"}, {"type": "reasoning.summary", "summary": ""}]}
    assert reasoning_of(m) == [("summary", "plan"), ("text", "thought")]


def test_cut_says_how_much_is_missing():
    assert cut("abc", 5) == ("abc", "")
    shown, note = cut("x" * 1500, 1200)
    assert len(shown) == 1200 and "300 more characters not shown" in note


def test_tool_call_shows_one_line_and_cuts_command_and_result():
    long_cmd = "python - <<'PY'\n" + "print(1)\n" * 600
    tc = {"id": "c1", "function": {"name": "run_command", "arguments": json.dumps({"command": long_cmd})}}
    out = call_html(tc, {"c1": "exit code 0\n" + "y" * 5000})
    assert "python - &lt;&lt;&#x27;PY&#x27; …" in out                           # first line only in the summary
    assert f"({len(long_cmd) - CMD_CAP:,} more characters not shown)" in out
    assert f"({5012 - RESULT_CAP:,} more characters not shown)" in out
    short = call_html({"id": "c2", "function": {"name": "read_file", "arguments": '{"path": "a/b.py"}'}}, {})
    assert "a/b.py" in short and "(no result recorded)" in short


def test_filled_shows_a_prompt_as_sent_with_stand_ins():
    assert filled('Reply with JSON {{"n": {n}}} about {thing}', n=3, thing="the diff") == 'Reply with JSON {"n": 3} about <the diff>'


def test_the_counts_from_committed_files_are_pinned():
    """The closing questions were replayed afterwards only on the six toy tasks' saved transcripts (runs main3_*, w2_*); the
    new-library and ControlArena episodes were asked at the end and were wrongly counted as replays before (401). The five
    data-kit descriptions of 16 Nov are not single-change descriptions, and neither are the five rsl_rl descriptions added on
    22 Nov 2026 for docs/CODE_NAMES_LADDER_PREREG.md, which the section names in one sentence."""
    import sfe.build_datasets as bd
    closing = bd.section_closing([], {})
    # 1,963 scored closing answers until the 24 episodes of the evening of 16 Nov 2026 were scored, 1,987 until the 170 of
    # GPT-6.2 Astra and GPT-6.2 Sol of 17-18 Nov 2026 (GPT62_RELEASED below) were scored, 2,157 until the 20 ControlArena
    # same-files episodes of 18 Nov 2026 (SAME_FILES below) were scored (results/debrief/scored.json)
    assert "replayed on top of 132 saved transcripts of the six small toy tasks" in closing and "2,177 answers" in closing
    assert bd.single_change_counts() == {"rsl_rl": 18, "synthetic-data-kit": 14}
    assert bd.later_descriptions_line([]).startswith("Five more descriptions of <code>rsl_rl</code> were added on 22 Nov 2026")
    assert bd.later_descriptions_line([]).endswith("none has a full episode yet.")
    four = [{"task": "rsl_rl", "framing": "fg_code_wrapper"}] * 4
    assert bd.later_descriptions_line(four).endswith(("their 4 full episodes are counted in the Result of that file.",
                                                       "they have 4 full episodes so far."))
    page = (bd.ROOT / "results" / "datasets" / "index.html").read_text()
    assert "were given 18 and\n14 further descriptions" in page and "Five more descriptions of <code>rsl_rl</code>" in page


EVENING_16_NOV = ({("new_control_sol", f"sol__control_arena__use_{side}_side__s{s}") for side in ("attack", "monitor") for s in range(2, 6)}
                  | {(f"new_generic5_{m}", f"{m}__new_rl__g_tobacco_docs__s{s}") for m in ("astra", "sol61s") for s in range(2, 6)}
                  | {(f"new_generic5_{m}", f"{m}__new_rl__g_official_records__s{s}") for m in ("astra", "sol61s") for s in range(4, 8)})
# Every run of GPT-6.2 Astra and GPT-6.2 Sol (17-18 Nov 2026) has a name ending in one of these.
GPT62 = ("astra62", "sol62")
# Their finished real-repository runs that the packer releases, with their episodes (real-repos: real2_*; description-edits:
# real4_implied_*; new-repos: new_*). Their toy runs w5_astra62 and w5_sol62 (finished 06:22 GMT on 18 Nov 2026, 72 episodes
# each; the page counts them with the six small toy tasks) are released too since data-v5 (toy-tasks); the smoke test smoke62
# never is.
GPT62_RELEASED = {f"{prefix}_{m}": n for prefix, n in (("real2", 36), ("real2_more", 18), ("real4_implied", 18), ("new_control", 4),
                                                       ("new_generic4", 9)) for m in GPT62}
# The ControlArena same-files runs of 18 Nov 2026 (docs/CONTROLARENA_SAME_FILES_PREREG.md): released by the packer (new-repos),
# in data-v5; GPT-5.6 Sol 12 episodes, GPT-6.2 Sol 8 (the latter also caught by GPT62).
SAME_FILES = {"new_control_files_sol": 12, "new_control_files_sol62": 8}
# The Gemini 4 test of 21 Nov 2026 (docs/GEMINI4_PREREG.md), in data-v5. Gemini 4 Neon's real-repository runs,
# which the packer releases (real2_neon: real-repos; real4_implied_neon: description-edits; new_*: new-repos), with their
# complete episodes under runs/ (the four episodes Google's filter stopped at the request are incomplete and stay in the
# staging copy runs_pod/runs/, which the page does not scan). And the two toy runs, which the packer releases since data-v5
# (toy-tasks; sfe.build_datasets.group_of puts w6_* in "other", so they never change the toy totals below).
GEMINI4_RELEASED = {"real2_neon": 33, "real4_implied_neon": 9, "new_control_neon": 3, "new_generic4_neon": 9}
GEMINI4_TOY = {"w6_hydrogen": 72, "w6_neon": 72}
# The code-names test and ladder of 22 Nov 2026 (docs/CODE_NAMES_LADDER_PREREG.md, runs real7_*, 106 episodes): released by
# the packer (description-edits) since data-v5; the page puts them in "other".
CODE_NAMES = "real7_"


def test_the_episode_totals_are_pinned_to_the_data_release():
    """The episode totals of the page, counted over what data-v3 holds: every run the packer releases (the smoke tests and
    abandoned attempts are not released, so the working copy has 28 more episodes). Skipped without the episodes, and with
    data-v2 alone, which predates the runs of 16 Nov."""
    import sys
    from collections import Counter
    import pytest
    import sfe.build_datasets as bd
    eps = bd.scan()
    if not eps:
        pytest.skip("needs the episodes: unpack the data release data-v3 at the repository root")
    if not (bd.RUNS / "real5_sdk_astra" / "episodes").is_dir():
        pytest.skip("needs data-v3: data-v2 does not hold the runs of 16 Nov 2026")
    sys.path.insert(0, str(bd.ROOT / "scripts"))
    import pack_data
    released = [e for e in eps if pack_data.archive_of_run(e["run"]) is not None]
    # Episodes in runs the packer releases, but in no data release yet: with data-v3 they are absent, in the working copy
    # they are counted on top of data-v3's totals. (1) The 24 of the two tests run on the evening of 16 Nov 2026 (GPT-5.6 Sol
    # on ControlArena, four more seeds on the tobacco archive and the minister's records). (2) Every episode of a GPT-6.2
    # run, picked by run name, so that the GPT-6.2 toy runs (not packed) never change data-v3's totals.
    late = lambda e: ((e["run"], e["id"]) in EVENING_16_NOV or e["run"].endswith(GPT62)          # noqa: E731
                      or e["run"] in SAME_FILES or e["run"] in GEMINI4_RELEASED or e["run"] in GEMINI4_TOY
                      or e["run"].startswith(CODE_NAMES))
    later = [e for e in released if late(e)]
    evening = [e for e in later if (e["run"], e["id"]) in EVENING_16_NOV]
    assert len(evening) in (0, len(EVENING_16_NOV)) and len(EVENING_16_NOV) == 24
    assert sum(e["group"] == "other" for e in evening) == len(evening)
    gpt62 = Counter(e["run"] for e in later if e["run"] in GPT62_RELEASED)
    assert gpt62 in (Counter(), Counter(GPT62_RELEASED)) and sum(GPT62_RELEASED.values()) == 170
    gemini4 = Counter(e["run"] for e in later if e["run"] in GEMINI4_RELEASED)
    assert gemini4 in (Counter(), Counter(GEMINI4_RELEASED)) and sum(GEMINI4_RELEASED.values()) == 54
    assert all(pack_data.archive_of_run(r) == "toy-tasks" for r in GEMINI4_TOY)       # the toy runs are packed (data-v5)
    assert Counter(e["run"] for e in eps if e["run"] in GEMINI4_TOY) in (Counter(), Counter(GEMINI4_TOY))
    assert len(released) - len(later) == 4105 and sum(e["group"] == "other" for e in released if not late(e)) == 845
    # closing questions asked at the end of the episode: in 1,979 episodes of data-v3, and in every later one of (1) and of
    # GPT62_RELEASED (the toy runs w5_*62 had none on 18 Nov 2026)
    assert f"Asked at the end of {1979 + sum(e['closing'] for e in later):,} saved episodes" in bd.section_closing(released, {})
    assert all(e["closing"] for e in later if e["run"] in GPT62_RELEASED or e["run"] in SAME_FILES
               or e["run"] in GEMINI4_RELEASED or (e["run"], e["id"]) in EVENING_16_NOV)
    same = Counter(e["run"] for e in later if e["run"] in SAME_FILES)
    assert same in (Counter(), Counter(SAME_FILES))
    assert sum(not late(e) for e in eps) in (4105, 4133)     # the data release, or the working copy with its smoke tests
    # the six small toy tasks: 12 models and 1,152 episodes in data-v3; 14 and 1,296 in the working copy, with GPT-6.2 Astra's
    # and GPT-6.2 Sol's 72 each (runs w5_*62, 18 Nov 2026), and the page says so
    toy = [e for e in eps if e["group"] == "toy"]
    w5 = Counter(e["run"] for e in toy if e["run"].startswith("w5_"))
    assert w5 in (Counter(), Counter({"w5_astra62": 72, "w5_sol62": 72}))
    assert len(toy) - sum(w5.values()) == 1152
    page = (bd.ROOT / "results" / "datasets" / "index.html").read_text()
    if w5:
        assert "14 models, 1,296 episodes." in page and "GPT-6.2 runs of the six small tasks (17-18 Nov,\n144 episodes" in page
