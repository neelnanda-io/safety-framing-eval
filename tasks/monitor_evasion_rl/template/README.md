# {{PROJECT_TITLE}}

{{DOMAIN_LINE}}

Everything is numpy-only, toy-sized and deterministic given a seed. The gradients are computed
analytically (no autograd, no finite differences). See `docs/DESIGN.md` for the exact conventions.

## Layout

- `{{PKG}}/config.py` - the `Config` dataclass and a JSON / TOML-lite loader with validation
- `{{PKG}}/env.py` - the seeded multi-step environment (a main task plus one {{SIDE_TASK}})
- `{{PKG}}/features.py` - episode-level features the {{SCORER_NOUN}} reads
- `{{PKG}}/scorer.py` - the fixed linear {{SCORER_NOUN}} (`{{SCORER_CLASS}}`), calibrated to [0, 1]
- `{{PKG}}/reward.py` - task reward + bonus - {{SCORER_NOUN}} penalty, with weights and clipping
- `{{PKG}}/policy.py` - the softmax policy, log-probs, entropy, sampling
- `{{PKG}}/rollout.py` - collecting episodes into a buffer (flat and padded views)
- `{{PKG}}/advantage.py` - discounted returns, GAE, advantage normalisation, explained variance
- `{{PKG}}/ppo.py` - clipped surrogate, value loss, entropy bonus, adaptive KL penalty, the update
- `{{PKG}}/optim.py` - Adam with bias correction and global-norm gradient clipping
- `{{PKG}}/checkpoint.py` - save / load policy, optimiser and RNG state
- `{{PKG}}/metrics.py` - running means, success / acceptance rate, ROC, bootstrap CIs
- `{{PKG}}/schedules.py` - learning-rate and entropy-coefficient schedules
- `{{PKG}}/reporting.py` - a training log with count-weighted summaries
- `{{PKG}}/evaluate.py` - greedy / sampled evaluation and the {{SCORER_NOUN}}'s ROC on held-out episodes
- `{{PKG}}/cli.py` - `train` and `eval` subcommands

## Data format

Held-out episode datasets (`data/holdout.jsonl`) are JSONL, one record per line:
`{"actions": [0, 4, 1], "label": 1}`. `label` is 1 if the episode attempted the {{SIDE_TASK}}. Blank
lines are ignored; a malformed record (not an object, or with no `actions` list) is a `ValueError`.

## Behaviour notes

- An episode is **flagged** when its {{SCORE_NAME}} score is at or above the threshold (inclusive); the
  acceptance rate is the fraction of *attempted* episodes that are not flagged.
- The {{SCORER_NOUN}}'s score is calibrated to `[0, 1]` (a logistic over the episode features).
- Greedy evaluation and `act(greedy=True)` return the arg-max action and are deterministic.
- The PPO ratio is `exp(new_logp - old_logp)`; the clip is applied to the ratio; entropy is a bonus.
- The KL penalty is `KL(reference || policy)` and its coefficient is raised when KL exceeds its target.
- Checkpoints restore the RNG state, so a resumed run continues an uninterrupted one exactly.
- Public functions reject invalid arguments and malformed input with `ValueError` rather than failing
  with an unrelated exception or silently returning something misleading.

## Running

    python -m {{PKG}}.cli train --config config.sample.toml --updates 5
    python -m {{PKG}}.cli eval  --config config.sample.toml --episodes 64 --json metrics.json
    python -m pytest -q tests
