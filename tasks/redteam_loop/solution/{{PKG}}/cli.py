"""Command-line entry point: run a batch of episodes against mock clients and print the {{RATE_NAME}} per {{STRATEGY_NOUN}}."""
from __future__ import annotations

import argparse
import math

from {{PKG}}.aggregate import bootstrap_ci, mean_turns_to_success, per_strategy, success_rate
from {{PKG}}.budget import CallBudget
from {{PKG}}.clients import SUCCESS_MARKER, MarkerScorerClient, MockClient
from {{PKG}}.episode import run_many
from {{PKG}}.export import to_jsonl

DEFAULT_MAX_TURNS = 6
STRATEGIES = ["{{STRAT_A}}", "{{STRAT_B}}", "{{STRAT_C}}"]
DEMO_SUCCESS_ROUND = {"{{STRAT_A}}": 2, "{{STRAT_B}}": 4, "{{STRAT_C}}": None}  # success round (None: never)
DEMO_PROBES = ["{{EX_PROBE_1}}", "{{EX_PROBE_2}}", "{{EX_PROBE_3}}"]
DEMO_REFUSAL = "{{EX_REFUSAL}}"
DEMO_SUCCESS = SUCCESS_MARKER + " {{EX_SUCCESS_TAIL}}"
SYSTEM_PROMPT = "{{SYSTEM_PROMPT}}"
PROBER_PROMPT = "{{PROBER_PROMPT}}"


def make_demo_clients(strategy: str, episode_index: int):
    """Fresh mock (prober, responder, scorer) clients; the responder fails transiently on every 3rd call."""
    k = DEMO_SUCCESS_ROUND[strategy]
    replies = [DEMO_REFUSAL] if k is None else [DEMO_REFUSAL] * (k - 1) + [DEMO_SUCCESS]
    return MockClient(DEMO_PROBES), MockClient(replies, fail_every=3), MarkerScorerClient()


def summarise(results) -> str:
    lines = [f"{'strategy':<16} {'n':>4} {'rate':>7}"]
    for strategy, row in per_strategy(results).items():
        lines.append(f"{strategy:<16} {row['n']:>4} {row['rate'] * 100:>6.1f}%")
    try:
        lo, hi = bootstrap_ci([1.0 if r.{{OUTCOME}} else 0.0 for r in results])
        ci = f"[{lo * 100:.1f}%, {hi * 100:.1f}%]"
    except NotImplementedError:
        ci = "n/a"
    turns = mean_turns_to_success(results)
    lines.append(f"overall {{RATE_NAME}}: {success_rate(results) * 100:.1f}% (95% CI {ci})")
    lines.append(f"mean turns to success: {'n/a' if math.isnan(turns) else f'{turns:.2f}'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=5, help="episodes per strategy")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--max-calls", type=int, default=10_000, help="model-call budget for the whole run")
    parser.add_argument("--backoff", type=float, default=0.0, help="retry backoff in seconds (0 for mocks)")
    parser.add_argument("--jsonl", default=None, help="also write every transcript to this JSONL file")
    args = parser.parse_args(argv)
    if args.max_turns < 1:
        parser.error("--max-turns must be at least 1")
    if args.episodes < 0:
        parser.error("--episodes must be >= 0")
    if args.max_calls < 0:
        parser.error("--max-calls must be >= 0")
    budget = CallBudget(args.max_calls)
    results = run_many(make_demo_clients, STRATEGIES, args.episodes, max_turns=args.max_turns, budget=budget,
                       system_prompt=SYSTEM_PROMPT, prober_prompt=PROBER_PROMPT, backoff=args.backoff)
    print(summarise(results))
    print(f"model calls used: {budget.used}")
    if args.jsonl:
        to_jsonl(results, args.jsonl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
