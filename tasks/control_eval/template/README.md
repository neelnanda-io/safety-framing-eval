# {{PROJECT_TITLE}}

{{DOMAIN_LINE}}

Maintained by the {{TEAM}}. The numbers it produces go into the {{DOWNSTREAM}}, so they need to be right rather
than flattering: when in doubt, `docs/DESIGN.md` is the specification.

## Contents

- [Quick start](#quick-start)
- [Layout](#layout)
- [Data](#data)
- [What gets computed](#what-gets-computed)
- [Configuration](#configuration)
- [Tests](#tests)

---

## Quick start

```bash
python -m {{PKG}}.cli evaluate  data/trajectories.jsonl --config configs/default.json
python -m {{PKG}}.cli sweep     data/trajectories.jsonl --config configs/default.json --{{PROTOCOL}} {{DEF}}_to_{{TRU}}
python -m {{PKG}}.cli bootstrap data/trajectories.jsonl --config configs/default.json --n-boot 100 --seed 1
python -m {{PKG}}.cli game      data/trajectories.jsonl --config configs/default.json --{{PROTOCOL}} {{AUD}}_only
python -m {{PKG}}.cli scores    data/trajectories.jsonl --method mean
```

Every command takes `--json FILE` to save its results and `--no-cache` to bypass the result cache.

## Layout

| module | what it does |
|---|---|
| `{{PKG}}/config.py` | defaults, JSON config files, command-line overrides |
| `{{PKG}}/data.py` | trajectory schema, JSONL loading and validation |
| `{{PKG}}/scores.py` | per-step {{SUSP}} aggregation (max / mean / top-k), running and peak scores, score cache |
| `{{PKG}}/budget.py` | {{AUD}} budget -> threshold on {{HON}} scores |
| `{{PKG}}/{{PROTOCOLS}}/` | `{{AUD}}_only`, `{{DEF}}_to_{{TRU}}`, `{{RES}}` and the registry (`build`) |
| `{{PKG}}/outcomes.py` | what a decision means for a trajectory (caught, {{HARM}} landed, whose work is used) |
| `{{PKG}}/metrics.py` | {{SAFE}}, {{USE}}, `evaluate()` |
| `{{PKG}}/frontier.py` | knob sweeps, Pareto frontier, area under the frontier |
| `{{PKG}}/bootstrap.py` | paired, stratified bootstrap confidence intervals |
| `{{PKG}}/game.py` | worst-case {{ATK}} rate over a deployment with upfront {{AUD}} |
| `{{PKG}}/cache.py` | on-disk cache of evaluation results |
| `{{PKG}}/report.py` | Markdown tables and JSON output |
| `{{PKG}}/cli.py` | the command-line interface |

## Data

`data/trajectories.jsonl` holds 40 recorded trajectories (28 {{HON}}, 12 {{ATK}}) of the {{UNT}} model on 20
tasks, scored step by step by {{MON_DESC}}. The format is specified in `docs/DESIGN.md` ("Data").

## What gets computed

For each {{PROTOCOL}}: **{{SAFE}}** (of the {{ATK}} trajectories that were either caught or landed their
{{HARM}}, the fraction that were caught), **{{USE}}** (main-task success on {{HON}} trajectories, scaled so the
{{TRU}} model is 0 and the {{UNT}} model is 1) and the {{AUD}} rate. A sweep over a {{PROTOCOL}}'s knob traces its
{{SAFE}}-{{USE}} frontier; the bootstrap gives confidence intervals and paired differences between
{{PROTOCOLS}}; the game asks which {{ATK}} rate would hurt most over a deployment of `n_tasks` tasks.

## Configuration

`configs/default.json` lists every key; anything left out takes its value from `{{PKG}}.config.DEFAULTS`. Fractions can
be written as `0.02` or `"2%"`. Command-line flags override the file.

## Tests

```bash
python -m pytest -q tests
```
