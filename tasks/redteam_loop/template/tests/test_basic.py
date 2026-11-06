from {{PKG}}.aggregate import success_rate
from {{PKG}}.budget import CallBudget
from {{PKG}}.clients import SUCCESS_MARKER, MarkerScorerClient, MockClient, TransientError
from {{PKG}}.episode import EpisodeResult, parse_score, run_episode, with_retry
import pytest


def no_sleep(seconds):
    return None


def test_mock_client_script_and_failures():
    c = MockClient(["a", "b"], fail_every=3)
    assert c.complete([]) == "a"
    assert c.complete([]) == "b"
    with pytest.raises(TransientError):
        c.complete([])
    assert c.complete([]) == "a"
    assert c.calls == 4


def test_marker_scorer_and_parse():
    s = MarkerScorerClient()
    assert s.complete([{"role": "user", "content": SUCCESS_MARKER + " ok"}]) == "1"
    assert s.complete([{"role": "user", "content": "{{EX_REFUSAL}}"}]) == "0"
    assert parse_score(" 0.75 ") == 0.75
    assert parse_score("seven") == 0.0
    assert parse_score("3") == 1.0


def test_first_round_success():
    r = run_episode(MockClient(["{{EX_PROBE_1}}"]), MockClient([SUCCESS_MARKER]), MarkerScorerClient(),
                    max_turns=3, strategy="{{STRAT_A}}", sleep=no_sleep)
    assert r.{{OUTCOME}} is True
    assert r.turns_used == 1
    assert r.error is None


def test_retry_and_budget_basics():
    assert with_retry(lambda: 42, sleep=no_sleep) == 42
    b = CallBudget(10)
    b.charge("{{PROBER}}")
    b.charge("{{RESPONDER}}")
    assert b.used == 2


def test_success_rate_all_successes():
    rs = [EpisodeResult(episode_id=i, strategy="{{STRAT_A}}", {{OUTCOME}}=True) for i in range(3)]
    assert success_rate(rs) == 1.0
