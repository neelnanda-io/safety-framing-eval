# {{PROJECT_TITLE}}

{{DOMAIN_LINE}}

Each episode is a multi-turn conversation between three models: the **{{PROBER}}** writes a message trying to
get {{GOAL_PHRASE}}, the **{{RESPONDER}}** replies, and the **{{SCORER}}** scores the reply in [0, 1]. A reply
scoring at least the threshold (default 0.5) marks the episode as {{OUTCOME}}. In tests and in the demo
CLI every model is a deterministic mock client; a successful reply contains the marker `{{MARKER}}`.

## Components

- `{{PKG}}/clients.py` - `MockClient` (scripted replies, injected transient failures), `MarkerScorerClient`,
  and the error types `TransientError`, `RateLimitError` (a `TransientError`) and `PermanentError`
- `{{PKG}}/episode.py` - `Conversation`, `run_episode`, `run_many`, `with_retry`
- `{{PKG}}/budget.py` - `CallBudget`, one model-call budget shared by all roles and episodes of a run
- `{{PKG}}/aggregate.py` - {{RATE_NAME}}, per-{{STRATEGY_NOUN}} breakdown, mean turns to success, bootstrap CI
- `{{PKG}}/export.py` - JSONL transcript export and loading, Markdown transcript export
- `{{PKG}}/cli.py` - `python -m {{PKG}}.cli --episodes 5 --max-turns 4 --jsonl runs.jsonl`

## Behaviour notes

- An episode runs at most `max_turns` rounds and stops right after the first successful round; nothing
  is called after that. `turns_used` is the round it ended on (`max_turns` if it never succeeded).
- Every model call, including the {{SCORER}}'s, is charged once to the shared `CallBudget`.
- `with_retry` retries only `TransientError` (rate limits included), makes `attempts` calls in total, and
  sleeps `backoff * 2 ** (k - 1)` before retry k, never before the first attempt.
- An episode that errors (permanent error, retries exhausted, budget spent) is recorded, not raised.
  Errored episodes count as failures in the {{RATE_NAME}}: they stay in the denominator.
- `mean_turns_to_success` averages over successful episodes only.
- `bootstrap_ci` is a seeded percentile bootstrap of the mean.
- JSONL export writes one episode per line, every line newline-terminated, with the full transcript.
- `--max-turns` on the CLI sets the per-episode round limit.
- Bad arguments raise `ValueError` up front rather than silently producing an empty or meaningless result.

## Running tests

    python -m pytest -q tests
