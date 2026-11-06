"""Command-line interface.

    python -m {{PKG}}.cli evaluate  data/trajectories.jsonl [--config configs/default.json] [--json out.json]
    python -m {{PKG}}.cli sweep     data/trajectories.jsonl --{{PROTOCOL}} {{DEF}}_to_{{TRU}} [--points 11]
    python -m {{PKG}}.cli bootstrap data/trajectories.jsonl [--n-boot 200] [--seed 0] [--level 0.95]
    python -m {{PKG}}.cli game      data/trajectories.jsonl --{{PROTOCOL}} {{AUD}}_only [--n-tasks 1000]
    python -m {{PKG}}.cli scores    data/trajectories.jsonl [--method mean]

Common options: --config FILE, --{{AUD}}-budget B, --method {max,mean,topk}, --k K, --json FILE, --no-cache.
Command-line values override the config file, which overrides the defaults.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from {{PKG}}.bootstrap import bootstrap
from {{PKG}}.cache import ResultCache, cached_evaluate
from {{PKG}}.config import load_config, {{PROTOCOL}}_spec
from {{PKG}}.data import load_trajectories, summarise
from {{PKG}}.frontier import SWEEP_PARAM, frontier_summary, sweep
from {{PKG}}.game import game_from_result
from {{PKG}}.{{PROTOCOLS}} import build
from {{PKG}}.report import bootstrap_table, frontier_table, game_summary, results_table, to_json
from {{PKG}}.scores import score_table


def _common(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("data", help="JSONL trajectory file")
    sp.add_argument("--config", default=None, help="JSON config file (see configs/default.json)")
    sp.add_argument("--{{AUD}}-budget", dest="{{AUD}}_budget", type=float, default=None,
                    help="fraction of {{HON}} trajectories that may be sent to {{AUD}}, e.g. 0.02")
    sp.add_argument("--method", choices=("max", "mean", "topk"), default=None, help="step-score aggregation")
    sp.add_argument("--k", type=int, default=None, help="k for --method topk")
    sp.add_argument("--json", dest="json_out", default=None, help="also write the results to this JSON file")
    sp.add_argument("--no-cache", action="store_true", help="do not read or write the result cache")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="{{PKG}}", description="{{PROJECT_TITLE}}")
    sub = parser.add_subparsers(dest="command", required=True)
    _common(sub.add_parser("evaluate", help="{{SAFE}} and {{USE}} of every configured {{PROTOCOL}}"))
    sw = sub.add_parser("sweep", help="sweep one {{PROTOCOL}}'s knob and compute its Pareto frontier")
    _common(sw)
    sw.add_argument("--{{PROTOCOL}}", dest="name", required=True, choices=sorted(SWEEP_PARAM))
    sw.add_argument("--points", type=int, default=None)
    sw.add_argument("--max-fraction", dest="max_fraction", default=None)
    bs = sub.add_parser("bootstrap", help="paired bootstrap confidence intervals")
    _common(bs)
    bs.add_argument("--n-boot", dest="n_boot", type=int, default=None)
    bs.add_argument("--seed", type=int, default=None)
    bs.add_argument("--level", type=float, default=None)
    gm = sub.add_parser("game", help="worst-case {{ATK}} rate over a deployment")
    _common(gm)
    gm.add_argument("--{{PROTOCOL}}", dest="name", required=True, choices=sorted(SWEEP_PARAM))
    gm.add_argument("--n-tasks", dest="n_tasks", type=int, default=None)
    gm.add_argument("--resolution", type=int, default=None)
    _common(sub.add_parser("scores", help="per-trajectory peak / final scores"))
    return parser


def _overrides(args) -> dict:
    """Config overrides from the command line (None values are ignored by load_config)."""
    out = {"{{AUD}}_budget": args.{{AUD}}_budget, "aggregation": {"method": args.method, "k": args.k}}
    if args.command == "sweep":
        out["sweep"] = {"points": args.points, "max_fraction": args.max_fraction}
    elif args.command == "bootstrap":
        out["bootstrap"] = {"n_boot": args.n_boot, "level": args.level}
    elif args.command == "game":
        out["game"] = {"n_tasks": args.n_tasks, "resolution": args.resolution}
    return out


def _cache(cfg: dict, args) -> ResultCache | None:
    return None if args.no_cache else ResultCache(cfg["cache_dir"])


def _header(trajectories) -> str:
    s = summarise(trajectories)
    return (f"{s['n_trajectories']} trajectories ({s['n_{{HON}}']} {{HON}}, {s['n_{{ATK}}']} {{ATK}}) "
            f"over {s['n_tasks']} tasks")


def cmd_evaluate(cfg: dict, trajectories, args) -> dict:
    cache = _cache(cfg, args)
    results = [cached_evaluate(build({{PROTOCOL}}_spec(cfg, spec["name"])), trajectories, cache)
               for spec in cfg["{{PROTOCOLS}}"]]
    print(_header(trajectories))
    print(results_table(results))
    return {"summary": summarise(trajectories), "results": [r.to_dict() for r in results], "config": cfg}


def cmd_sweep(cfg: dict, trajectories, args) -> dict:
    spec = {{PROTOCOL}}_spec(cfg, args.name)
    values = [float(v) for v in np.linspace(cfg["sweep"]["max_fraction"], 0.0, cfg["sweep"]["points"])]
    summary = frontier_summary(sweep(spec, values, trajectories))
    summary.update({"{{PROTOCOL}}": args.name, "param": SWEEP_PARAM[args.name]})
    print(_header(trajectories))
    print(frontier_table(summary))
    return summary


def cmd_bootstrap(cfg: dict, trajectories, args) -> dict:
    {{PROTOCOLS}} = {spec["name"]: build({{PROTOCOL}}_spec(cfg, spec["name"])) for spec in cfg["{{PROTOCOLS}}"]}
    b = cfg["bootstrap"]
    result = bootstrap({{PROTOCOLS}}, trajectories, n_boot=b["n_boot"], seed=b["seed"], level=b["level"])
    print(_header(trajectories))
    print(bootstrap_table(result))
    return result.to_dict()


def cmd_game(cfg: dict, trajectories, args) -> dict:
    spec = {{PROTOCOL}}_spec(cfg, args.name)
    result = cached_evaluate(build(spec), trajectories, _cache(cfg, args))
    g = game_from_result(result, cfg["game"]["n_tasks"], spec["{{AUD}}_budget"], cfg["game"]["resolution"])
    print(game_summary(g))
    return g


def cmd_scores(cfg: dict, trajectories, args) -> dict:
    rows = score_table(trajectories, cfg["aggregation"]["method"], cfg["aggregation"]["k"])
    for r in rows:
        print(f"{r['id']:>12}  {r['kind']:<12} steps={r['n_steps']:<3} peak={r['peak']:.2f} final={r['final']:.2f}")
    return {"rows": rows}


COMMANDS = {"evaluate": cmd_evaluate, "sweep": cmd_sweep, "bootstrap": cmd_bootstrap, "game": cmd_game,
            "scores": cmd_scores}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args.config, _overrides(args))
        trajectories = load_trajectories(args.data)
        payload = COMMANDS[args.command](cfg, trajectories, args)
    except ValueError as e:   # DataError and ConfigError are ValueErrors
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.json_out:
        to_json(payload, args.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
