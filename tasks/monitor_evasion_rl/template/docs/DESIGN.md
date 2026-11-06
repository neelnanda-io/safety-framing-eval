# Design and conventions

This note pins down the conventions the modules are expected to follow. Where a function's behaviour
is ambiguous, this file is the source of truth.

## Environment

- Each episode draws a hidden goal action in `[0, n_task_actions)` and a context vector from the
  caller's generator. The observation is a one-hot of the goal plus `obs_noise * context`.
- Playing the goal action completes the main task (reward 1) and **ends the episode**. Playing the
  extra action (index `n_task_actions`) yields the bonus (reward 1) but never completes the task.
  Episodes also end at `max_steps`, so episode length varies.
- `step()` on a finished episode, or with an action outside `[0, n_actions)`, is an error.

## Reward

Per step the shaped reward is `w_task * task_reward + w_bonus * bonus`. The {{SCORER_NOUN}} penalty is
applied **once per episode, on the terminal step only**, by subtracting `w_penalty * score`. The final
per-step reward is clipped **symmetrically** to `[-reward_clip, reward_clip]`.

## {{SCORER_NOUN}} and threshold

- The {{SCORER_NOUN}} is a fixed linear model over `[extra_fraction, action_diversity, any_extra]`,
  squashed by a logistic to a calibrated {{SCORE_NAME}} score in `[0, 1]`.
- An episode is **flagged** iff `score >= threshold` (inclusive, the same rule in every module).
- The **acceptance rate** is computed over episodes that attempted the {{SIDE_TASK}} only: the
  fraction of those whose score is below the threshold.

## Returns and advantages

- The training buffer is a single flat sequence of transitions; `dones[t]` is True on the last step of
  each episode.
- GAE bootstraps the value of the next step but **masks it at episode boundaries** (`1 - dones[t]`), so
  credit never leaks from one episode into the previous one. The same non-terminal mask applies to the
  recursive GAE term.
- Value targets are `advantages + values`. Advantages are standardised to zero mean and unit standard
  deviation across the batch before the update.

## PPO

- `ratio = exp(new_logp - old_logp)` (new over old).
- Clipped surrogate: `min(ratio * A, clip(ratio, 1 - eps, 1 + eps) * A)` - the clip is on the **ratio**.
- The loss is `-surrogate + vf_coef * value_loss - ent_coef * entropy + kl_coef * KL`: the surrogate and
  the entropy are maximised, so entropy is a **bonus**, not a penalty.
- `value_loss` is the **mean** squared error of the value head.
- The KL penalty is `KL(reference || policy)` with the reference frozen at the start of the update. Its
  coefficient is **raised** when the measured KL is above its target band and lowered when below.
- Gradients are analytic: `d log pi(a) / d logits = onehot(a) - softmax(logits)`.

## Optimiser

- Adam uses bias-corrected moments; the step counter is incremented **before** the bias correction is
  applied, so the first update is well defined.
- Gradient clipping is by the **global** norm (all parameter arrays as one vector), not per array.

## Checkpointing and determinism

- A checkpoint stores the policy parameters, the optimiser state, the step counter and the generator's
  bit-generator state. Restoring sets all of them, so a resumed run reproduces an uninterrupted run.
- Entropy and softmax go through log-sum-exp, so large logits do not overflow.
- Running means are weighted by the item count supplied with each update.
