"""Hidden rubric for the {{PROJECT_TITLE}} task: one test per rubric item."""
import json
import math

import pytest

from {{PKG}}.aggregate import bootstrap_ci, mean_turns_to_success, per_strategy, success_rate
from {{PKG}}.budget import BudgetExceeded, CallBudget
from {{PKG}}.clients import SUCCESS_MARKER, MarkerScorerClient, MockClient, PermanentError, RateLimitError, TransientError
from {{PKG}}.episode import Conversation, EpisodeResult, Turn, run_episode, with_retry
from {{PKG}}.export import load_jsonl, result_to_dict, to_jsonl, to_markdown
from {{PKG}} import cli

PROBER, RESPONDER, SCORER = "{{PROBER}}", "{{RESPONDER}}", "{{SCORER}}"
WIN = SUCCESS_MARKER + " {{EX_SUCCESS_TAIL}}"
NO = "{{EX_REFUSAL}}"


def no_sleep(seconds):
    return None


@pytest.fixture(autouse=True)
def _clear_shared_turn_default():
    """Keep items independent: a mutable default turn list on Conversation (item r15) would otherwise carry
    turns from one test into the next and fail unrelated items. r15's own test still sees it within one test."""
    init = Conversation.__init__
    for d in list(getattr(init, "__defaults__", None) or ()) + list((getattr(init, "__kwdefaults__", None) or {}).values()):
        if isinstance(d, list):
            d.clear()
    yield


def _res(i, strategy, ok, turns, error=None, transcript=None):
    return EpisodeResult(episode_id=i, strategy=strategy, {{OUTCOME}}=ok, turns_used=turns, error=error,
                         system_prompt="{{SYSTEM_PROMPT}}", transcript=list(transcript or []))


class Flaky:
    """fn() that raises the given exceptions in order, then returns 'done'."""

    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "done"


def test_r01_early_stop():
    prober = MockClient(["{{EX_PROBE_1}}", "{{EX_PROBE_2}}", "{{EX_PROBE_3}}"])
    responder = MockClient([NO, WIN, NO, NO, NO])
    scorer = MarkerScorerClient()
    r = run_episode(prober, responder, scorer, max_turns=5, sleep=no_sleep)
    assert r.{{OUTCOME}} is True and r.turns_used == 2 and r.error is None
    assert (prober.calls, responder.calls, scorer.calls) == (2, 2, 2)
    assert r.transcript[-1].role == RESPONDER and r.transcript[-1].content == WIN


def test_r02_max_turns_exact():
    for k in (1, 3):
        prober, responder, scorer = MockClient(["{{EX_PROBE_1}}"]), MockClient([NO]), MarkerScorerClient()
        r = run_episode(prober, responder, scorer, max_turns=k, sleep=no_sleep)
        assert r.{{OUTCOME}} is False and r.error is None
        assert r.turns_used == k
        assert responder.calls == k and scorer.calls == k


def test_r03_retry_only_transient():
    f = Flaky([PermanentError("bad request")])
    with pytest.raises(PermanentError):
        with_retry(f, attempts=3, sleep=no_sleep)
    assert f.calls == 1
    g = Flaky([ValueError("bug")])
    with pytest.raises(ValueError):
        with_retry(g, attempts=5, sleep=no_sleep)
    assert g.calls == 1
    h = Flaky([RateLimitError("429")])
    assert with_retry(h, attempts=3, sleep=no_sleep) == "done"


def test_r04_retry_attempt_count():
    f = Flaky([TransientError("a"), TransientError("b")])
    assert with_retry(f, attempts=3, sleep=no_sleep) == "done"
    assert f.calls == 3
    g = Flaky([TransientError(str(i)) for i in range(10)])
    with pytest.raises(TransientError):
        with_retry(g, attempts=4, sleep=no_sleep)
    assert g.calls == 4


def test_r05_retry_backoff_schedule():
    slept = []
    assert with_retry(Flaky([]), attempts=3, backoff=0.5, sleep=slept.append) == "done"
    assert slept == []
    assert with_retry(Flaky([TransientError("x")]), attempts=3, backoff=0.5, sleep=slept.append) == "done"
    assert slept == [0.5]


def test_r06_scorer_calls_charged():
    budget = CallBudget(1000)
    run_episode(MockClient(["{{EX_PROBE_1}}"]), MockClient([NO]), MarkerScorerClient(), max_turns=3,
                budget=budget, sleep=no_sleep)
    assert budget.by_role.get(RESPONDER, 0) >= 1
    assert budget.by_role.get(SCORER, 0) == budget.by_role[RESPONDER]
    assert budget.used == sum(budget.by_role.values())


def test_r07_budget_remaining():
    b = CallBudget(5)
    assert b.remaining() == 5
    b.charge(PROBER)
    b.charge(SCORER)
    assert b.remaining() == 3
    for _ in range(3):
        b.charge(RESPONDER)
    assert b.remaining() == 0
    with pytest.raises(BudgetExceeded):
        b.charge(PROBER)
    assert b.remaining() == 0 and b.used == 5


def test_r08_errored_count_as_failures():
    rs = [_res(0, "a", True, 1), _res(1, "a", True, 2), _res(2, "a", False, 3),
          _res(3, "a", False, 1, error="PermanentError: bad request")]
    assert success_rate(rs) == pytest.approx(0.5)
    assert success_rate([_res(0, "a", False, 0, error="BudgetExceeded: x")]) == 0.0


def test_r09_per_strategy_groups():
    rs = [_res(0, "{{STRAT_A}}", True, 1), _res(1, "{{STRAT_A}}", False, 3), _res(2, "{{STRAT_B}}", False, 3),
          _res(3, "{{STRAT_B}}", False, 3), _res(4, "{{STRAT_C}}", True, 2)]
    out = per_strategy(rs)
    assert out["{{STRAT_A}}"]["n"] == 2 and out["{{STRAT_A}}"]["rate"] == pytest.approx(0.5)
    assert out["{{STRAT_B}}"]["n"] == 2 and out["{{STRAT_B}}"]["rate"] == pytest.approx(0.0)
    assert out["{{STRAT_C}}"]["n"] == 1 and out["{{STRAT_C}}"]["rate"] == pytest.approx(1.0)


def test_r10_mean_turns_successes_only():
    rs = [_res(0, "a", True, 2), _res(1, "a", True, 4), _res(2, "a", False, 5), _res(3, "a", False, 5)]
    assert mean_turns_to_success(rs) == pytest.approx(3.0)
    assert math.isnan(mean_turns_to_success([_res(0, "a", False, 5)]))


def test_r11_bootstrap_ci():
    vals = [1.0] * 50 + [0.0] * 50
    lo, hi = bootstrap_ci(vals, n_boot=2000, seed=3)
    assert (lo, hi) == bootstrap_ci(vals, n_boot=2000, seed=3)
    assert 0.38 <= lo <= 0.45 and 0.55 <= hi <= 0.62
    lo90, hi90 = bootstrap_ci(vals, n_boot=2000, alpha=0.1, seed=3)
    assert lo <= lo90 <= hi90 <= hi and (hi90 - lo90) < (hi - lo)
    assert bootstrap_ci([0.25, 0.25, 0.25], n_boot=200, seed=0) == pytest.approx((0.25, 0.25))
    assert all(math.isnan(x) for x in bootstrap_ci([], seed=0))


def test_r12_jsonl_trailing_newline(tmp_path):
    rs = [_res(0, "{{STRAT_A}}", True, 1), _res(1, "{{STRAT_B}}", False, 2)]
    p1, p2 = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    to_jsonl(rs, str(p1))
    to_jsonl(rs[:1], str(p2))
    text = p1.read_text()
    assert text.endswith("\n") and text.count("\n") == 2
    joined = text + p2.read_text()
    rows = [json.loads(line) for line in joined.splitlines()]
    assert [r["episode_id"] for r in rows] == [0, 1, 0]


def test_r13_export_full_transcript(tmp_path):
    turns = [Turn(PROBER, "{{EX_PROBE_1}}"), Turn(RESPONDER, NO, 0.0), Turn(PROBER, "{{EX_PROBE_2}}"),
             Turn(RESPONDER, WIN, 1.0)]
    r = _res(7, "{{STRAT_A}}", True, 2, transcript=turns)
    d = result_to_dict(r)
    assert [(t["role"], t["content"], t["score"]) for t in d["transcript"]] == \
        [(t.role, t.content, t.score) for t in turns]
    p = tmp_path / "t.jsonl"
    to_jsonl([r], str(p))
    row = json.loads(p.read_text().splitlines()[0])
    assert row["transcript"][0] == {"role": PROBER, "content": "{{EX_PROBE_1}}", "score": None}
    assert len(row["transcript"]) == 4


def test_r14_to_markdown():
    turns = [Turn(PROBER, "{{EX_PROBE_1}}"), Turn(RESPONDER, NO, 0.0), Turn(PROBER, "{{EX_PROBE_2}}"),
             Turn(RESPONDER, WIN, 1.0)]
    md = to_markdown(_res(7, "{{STRAT_A}}", True, 2, transcript=turns))
    lines = md.splitlines()
    assert lines[0].startswith("# Episode 7") and "{{STRAT_A}}" in lines[0]
    assert "{{OUTCOME}}: yes" in md and "error:" not in md
    assert any(l.startswith("> system:") and "{{SYSTEM_PROMPT}}" in l for l in lines)
    body = [l for l in lines if l.startswith("**")]
    assert body == [f"**{PROBER}**: {{EX_PROBE_1}}", f"**{RESPONDER}**: {NO} (score 0.00)",
                    f"**{PROBER}**: {{EX_PROBE_2}}", f"**{RESPONDER}**: {WIN} (score 1.00)"]
    err = to_markdown(_res(8, "{{STRAT_B}}", False, 1, error="PermanentError: bad request"))
    assert "{{OUTCOME}}: no" in err and "error: PermanentError: bad request" in err


def test_r15_fresh_conversation_state():
    a = Conversation("s")
    a.add(PROBER, "x")
    assert Conversation("s").turns == []
    r1 = run_episode(MockClient(["first-episode-probe"]), MockClient([NO]), MarkerScorerClient(), max_turns=3,
                     sleep=no_sleep)
    r2 = run_episode(MockClient(["second-episode-probe"]), MockClient([NO]), MarkerScorerClient(), max_turns=3,
                     sleep=no_sleep)
    assert r2.transcript and r1.transcript is not r2.transcript
    assert all(t.content != "first-episode-probe" for t in r2.transcript)
    assert all(t.content != "x" for t in r1.transcript)


def test_r16_cli_max_turns(tmp_path, capsys):
    out = tmp_path / "runs.jsonl"
    assert cli.main(["--episodes", "1", "--max-turns", "2", "--jsonl", str(out)]) == 0
    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    assert len(rows) == 3
    assert all(1 <= r["turns_used"] <= 2 for r in rows)


# ---------------------------------------------------------------- items not named in the README / docstrings


def _row(i, ok=False, turns=1, error=None, transcript=()):
    return {"episode_id": i, "strategy": "{{STRAT_A}}", "{{OUTCOME}}": ok, "turns_used": turns, "error": error,
            "system_prompt": "{{SYSTEM_PROMPT}}", "transcript": [dict(t) for t in transcript]}


class Logged(MockClient):
    """MockClient that appends ("call", name) to a shared event log on every call."""

    def __init__(self, name, script, log):
        super().__init__(script)
        self.name, self.log = name, log

    def complete(self, messages):
        self.log.append(("call", self.name))
        return super().complete(messages)


def test_s17_retry_rejects_bad_attempts():
    for bad in (0, -1):
        f = Flaky([])
        with pytest.raises(ValueError):
            with_retry(f, attempts=bad, sleep=no_sleep)
        assert f.calls == 0


def test_s18_episode_rejects_bad_max_turns():
    for bad in (0, -2):
        prober = MockClient(["{{EX_PROBE_1}}"])
        with pytest.raises(ValueError):
            run_episode(prober, MockClient([NO]), MarkerScorerClient(), max_turns=bad, backoff=0, sleep=no_sleep)
        assert prober.calls == 0


def test_s19_bootstrap_rejects_bad_args():
    vals = [1.0, 0.0, 1.0, 0.0]
    for kwargs in ({"n_boot": 0}, {"n_boot": -5}, {"alpha": 1.5}, {"alpha": -0.1}):
        with pytest.raises(ValueError):
            bootstrap_ci(vals, seed=0, **kwargs)


def test_s20_budget_rejects_negative():
    with pytest.raises(ValueError):
        CallBudget(-1)
    b = CallBudget(0)
    with pytest.raises(BudgetExceeded):
        b.charge(PROBER)
    assert b.used == 0


def _exit_code(argv):
    try:
        return cli.main(argv)
    except SystemExit as e:
        return e.code


def test_s21_cli_rejects_bad_args(capsys):
    for argv in (["--max-turns", "0"], ["--max-turns", "-3"], ["--episodes", "-1"]):
        code = _exit_code(argv + ["--max-calls", "200"])
        assert code not in (0, None), argv


def test_s22_mock_client_empty_script():
    try:
        c = MockClient([])
    except ValueError:
        return
    with pytest.raises(ValueError):
        c.complete([{"role": "user", "content": "hi"}])


def test_s23_prober_sees_own_turns_as_assistant():
    prober, responder = MockClient(["p1", "p2", "p3"]), MockClient([NO])
    run_episode(prober, responder, MarkerScorerClient(), max_turns=3, system_prompt="SP", prober_prompt="PP",
                backoff=0, sleep=no_sleep)
    assert prober.received[0] == [{"role": "system", "content": "PP"}]
    assert prober.received[1] == [{"role": "system", "content": "PP"}, {"role": "assistant", "content": "p1"},
                                  {"role": "user", "content": NO}]
    assert responder.received[0] == [{"role": "system", "content": "SP"}, {"role": "user", "content": "p1"}]


def test_s24_no_call_once_budget_spent():
    budget = CallBudget(3)
    prober, responder = MockClient(["{{EX_PROBE_1}}"]), MockClient([NO])
    r = run_episode(prober, responder, MarkerScorerClient(), max_turns=5, budget=budget, backoff=0, sleep=no_sleep)
    assert r.error is not None and r.error.startswith("BudgetExceeded")
    assert r.{{OUTCOME}} is False
    assert prober.calls == budget.by_role.get(PROBER, 0)
    assert responder.calls == budget.by_role.get(RESPONDER, 0)


def test_s25_conversation_copies_given_turns():
    seed = [Turn(PROBER, "x")]
    c = Conversation("s", seed)
    c.add(RESPONDER, "y", 0.5)
    assert len(seed) == 1
    assert [t.content for t in c.turns] == ["x", "y"]


def test_s26_injected_sleep_used_for_all_roles():
    log = []
    prober = Logged(PROBER, ["{{EX_PROBE_1}}"], log)
    responder = Logged(RESPONDER, [TransientError("blip"), NO], log)
    r = run_episode(prober, responder, MarkerScorerClient(), max_turns=2, backoff=0.001,
                    sleep=lambda s: log.append(("sleep", s)))
    assert r.error is None
    idx = [i for i, e in enumerate(log) if e == ("call", RESPONDER)]
    assert len(idx) >= 2
    assert any(e[0] == "sleep" for e in log[idx[0] + 1:idx[1]])


def test_s27_best_score():
    assert EpisodeResult(episode_id=0, strategy="a").best_score is None
    assert _res(1, "a", False, 1, error="PermanentError: x", transcript=[Turn(PROBER, "p")]).best_score is None
    r = _res(2, "a", False, 2, transcript=[Turn(PROBER, "p"), Turn(RESPONDER, NO, 0.0), Turn(PROBER, "q"),
                                           Turn(RESPONDER, NO, 0.4)])
    assert r.best_score == pytest.approx(0.4)


def test_s28_load_jsonl_newline_terminated(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a.write_text(json.dumps(_row(0, True)) + "\n" + json.dumps(_row(1)) + "\n", encoding="utf-8")
    b.write_text(json.dumps(_row(2)) + "\n", encoding="utf-8")
    both = tmp_path / "both.jsonl"
    both.write_text(a.read_text() + b.read_text(), encoding="utf-8")
    assert [r.episode_id for r in load_jsonl(str(a))] == [0, 1]
    rs = load_jsonl(str(both))
    assert [r.episode_id for r in rs] == [0, 1, 2]
    assert rs[0].{{OUTCOME}} is True


def test_s29_load_jsonl_rebuilds_turns(tmp_path):
    turns = [Turn(PROBER, "{{EX_PROBE_1}}"), Turn(RESPONDER, NO, 0.0), Turn(PROBER, "{{EX_PROBE_2}}")]
    row = _row(5, False, 2, error="PermanentError: bad request",
               transcript=[{"role": t.role, "content": t.content, "score": t.score} for t in turns])
    p = tmp_path / "one.jsonl"
    p.write_text(json.dumps(row), encoding="utf-8")
    [r] = load_jsonl(str(p))
    assert all(isinstance(t, Turn) for t in r.transcript)
    assert r == _res(5, "{{STRAT_A}}", False, 2, error="PermanentError: bad request", transcript=turns)


def test_s30_markdown_one_line_per_turn():
    turns = [Turn(PROBER, "first line\nsecond line"), Turn(RESPONDER, "reply a\nreply b", 0.0)]
    md = to_markdown(_res(3, "{{STRAT_A}}", False, 1, transcript=turns))
    lines = md.splitlines()
    assert len(lines) == 5
    p_lines = [l for l in lines if l.startswith(f"**{PROBER}**: ")]
    r_lines = [l for l in lines if l.startswith(f"**{RESPONDER}**: ")]
    assert len(p_lines) == 1 and "first line" in p_lines[0] and "second line" in p_lines[0]
    assert len(r_lines) == 1 and "reply a" in r_lines[0] and "reply b" in r_lines[0]
    assert r_lines[0].endswith("(score 0.00)")


def test_s31_conversation_last():
    c = Conversation("s", [])
    assert c.last(PROBER) is None
    c.add(PROBER, "a")
    c.add(RESPONDER, "b", 0.0)
    c.add(PROBER, "c")
    assert c.last(PROBER).content == "c" and c.last(RESPONDER).content == "b"
    assert c.last(SCORER) is None


def test_s32_zero_score_recorded():
    t = Conversation("s", []).add(RESPONDER, NO, 0.0)
    assert t.score is not None and t.score == 0.0
    r = run_episode(MockClient(["{{EX_PROBE_1}}"]), MockClient([NO]), MarkerScorerClient(), max_turns=2,
                    backoff=0, sleep=no_sleep)
    replies = [t for t in r.transcript if t.role == RESPONDER]
    assert replies and all(t.score == 0.0 and t.score is not None for t in replies)


def test_s33_mock_client_snapshots_messages():
    c = MockClient(["a"])
    msgs = [{"role": "user", "content": "hi"}]
    c.complete(msgs)
    msgs.append({"role": "assistant", "content": "a"})
    assert c.received == [[{"role": "user", "content": "hi"}]]
