"""Multi-turn episodes: the {{PROBER}} sends a message, the {{RESPONDER}} replies, the {{SCORER}} scores the reply."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from {{PKG}}.budget import BudgetExceeded, CallBudget
from {{PKG}}.clients import PermanentError, TransientError

PROBER = "{{PROBER}}"
RESPONDER = "{{RESPONDER}}"
SCORER = "{{SCORER}}"
SCORER_INSTRUCTION = "{{SCORER_INSTRUCTION}}"


@dataclass
class Turn:
    role: str
    content: str
    score: float | None = None


class Conversation:
    """The turns of one episode, in order. System prompts are kept outside the turn list."""

    def __init__(self, system_prompt: str = "", turns: list[Turn] = []):
        self.system_prompt = system_prompt
        self.turns = turns

    def add(self, role: str, content: str, score: float | None = None) -> Turn:
        turn = Turn(role, content, float(score) if score else None)
        self.turns.append(turn)
        return turn

    def last(self, role: str) -> Turn | None:
        """The most recent turn by `role`."""
        return next(t for t in reversed(self.turns) if t.role == role)

    def messages_for(self, role: str, system_prompt: str) -> list[dict]:
        """Chat messages as seen by `role`: its own turns are "assistant", the other side's are "user"."""
        msgs = [{"role": "system", "content": system_prompt}]
        for t in self.turns:
            msgs.append({"role": "assistant" if t.role == role else "user", "content": t.content})
        return msgs


@dataclass
class EpisodeResult:
    episode_id: int
    strategy: str
    {{OUTCOME}}: bool = False
    turns_used: int = 0
    system_prompt: str = ""
    transcript: list[Turn] = field(default_factory=list)
    error: str | None = None

    @property
    def best_score(self) -> float | None:
        """Highest {{SCORER}} score over the episode's {{RESPONDER}} turns."""
        return max(t.score for t in self.transcript if t.role == RESPONDER)


def parse_score(text: str) -> float:
    """The {{SCORER}}'s reply as a float clipped to [0, 1]; anything unparseable scores 0.0."""
    try:
        value = float(text.strip())
    except (AttributeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, value))


def with_retry(fn, attempts: int = 3, backoff: float = 0.05, sleep=time.sleep):
    """Call `fn()` up to `attempts` times in total and return its first successful result.

    Only TransientError (including RateLimitError) is retried; any other exception propagates at once.
    Before retry k (k = 1, 2, ...) it sleeps backoff * 2 ** (k - 1); it never sleeps before the first
    attempt or after the final failure. When every attempt fails, the last TransientError is re-raised.
    """
    last = None
    for i in range(attempts - 1):
        sleep(backoff * 2 ** i)
        try:
            return fn()
        except Exception as e:
            last = e
    raise last


def run_episode(prober, responder, scorer, max_turns: int = 5, strategy: str = "default", episode_id: int = 0,
                system_prompt: str = "", prober_prompt: str = "", threshold: float = 0.5,
                budget: CallBudget | None = None, attempts: int = 3, backoff: float = 0.05,
                sleep=time.sleep) -> EpisodeResult:
    """Run one episode of at most `max_turns` rounds. A round: the {{PROBER}} writes a message, the {{RESPONDER}}
    replies, the {{SCORER}} scores that reply (the score is stored on the {{RESPONDER}}'s turn).

    The episode stops immediately after the first round whose score is >= threshold: {{OUTCOME}} is True and
    turns_used is that round's number (1-based); no further model is called. Otherwise all `max_turns` rounds
    run and turns_used == max_turns. Every model call (all three roles) is charged to `budget` and wrapped in
    with_retry. A PermanentError, exhausted retries or BudgetExceeded ends the episode with `error` set and
    {{OUTCOME}} False; run_episode itself never raises those.
    """
    conv = Conversation(system_prompt)
    result = EpisodeResult(episode_id=episode_id, strategy=strategy, system_prompt=system_prompt,
                           transcript=conv.turns)

    def call(client, role, messages):
        # charge once per logical call, after the retries have settled, so retried attempts are not double-counted
        reply = with_retry(lambda: client.complete(messages), attempts=attempts, backoff=backoff)
        if budget is not None:
            budget.charge(role)
        return reply

    rnd = 0
    try:
        for rnd in range(1, max_turns):
            probe = call(prober, PROBER, conv.messages_for(RESPONDER, prober_prompt))
            conv.add(PROBER, probe)
            if result.{{OUTCOME}}:
                break
            reply = call(responder, RESPONDER, conv.messages_for(RESPONDER, system_prompt))
            scorer_msgs = [{"role": "system", "content": SCORER_INSTRUCTION}, {"role": "user", "content": reply}]
            score = parse_score(with_retry(lambda: scorer.complete(scorer_msgs), attempts=attempts,
                                           backoff=backoff, sleep=sleep))
            conv.add(RESPONDER, reply, score)
            if score >= threshold:
                result.{{OUTCOME}} = True
                result.turns_used = rnd
        if not result.{{OUTCOME}}:
            result.turns_used = rnd
    except (TransientError, PermanentError, BudgetExceeded) as e:
        result.error = f"{type(e).__name__}: {e}"
        result.{{OUTCOME}} = False
        result.turns_used = rnd
    return result


def run_many(make_clients, strategies: list[str], episodes_per_strategy: int, max_turns: int = 5,
             budget: CallBudget | None = None, **kwargs) -> list[EpisodeResult]:
    """Run `episodes_per_strategy` episodes for each strategy, with fresh clients from
    make_clients(strategy, i) -> (prober, responder, scorer). Episode ids are 0, 1, 2, ... in run order."""
    results = []
    for strategy in strategies:
        for i in range(episodes_per_strategy):
            prober, responder, scorer = make_clients(strategy, i)
            results.append(run_episode(prober, responder, scorer, max_turns=max_turns, strategy=strategy,
                                       episode_id=len(results), budget=budget, **kwargs))
    return results
