"""Command line entry point.

    python -m {{PKG}}.cli synth  [--store DIR] [--seed N]          write a synthetic activation store
    python -m {{PKG}}.cli train  [--config F] [--set k=v ...]       train an SAE, save <run_dir>/final
    python -m {{PKG}}.cli study  [--config F] [--ckpt DIR]          analyse a checkpoint, write report.json
    python -m {{PKG}}.cli run    [--config F] [--set k=v ...]       synth (if needed) + train + study
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .activations import list_hooks
from .config import PipelineConfig, load_config
from .pipeline import run_study, train_sae
from .report import format_markdown, format_summary
from .synth import SynthSpec, generate, write_synthetic


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m {{PKG}}.cli", description="{{PROJECT_TITLE}}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--config", default=None, help="JSON config file (see configs/default.json)")
        sp.add_argument("--set", action="append", default=[], metavar="SECTION.KEY=VALUE",
                        help="override one config value; may be repeated")
        sp.add_argument("--store", default=None, help="activation store root (overrides paths.store_root)")
        sp.add_argument("--run-dir", default=None, help="run directory (overrides paths.run_dir)")
        return sp

    s = common(sub.add_parser("synth", help="write a synthetic activation store"))
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--n-seqs", type=int, default=120)
    common(sub.add_parser("train", help="train an SAE"))
    st = common(sub.add_parser("study", help="analyse a trained checkpoint"))
    st.add_argument("--ckpt", default=None, help="checkpoint dir (default <run_dir>/final)")
    st.add_argument("--markdown", action="store_true", help="also write report.md")
    r = common(sub.add_parser("run", help="synth (if the store is missing) + train + study"))
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--n-seqs", type=int, default=120)
    return parser


def build_config(args) -> PipelineConfig:
    overrides = list(args.set or [])
    if args.store:
        overrides.append(f"paths.store_root={json.dumps(args.store)}")
    if args.run_dir:
        overrides.append(f"paths.run_dir={json.dumps(args.run_dir)}")
    return load_config(args.config, overrides)


def cmd_synth(cfg: PipelineConfig, args) -> int:
    data = generate(SynthSpec(d_model=cfg.sae.d_model, n_seqs=args.n_seqs, seed=args.seed))
    store = write_synthetic(cfg.paths.store_root, cfg.paths.hook, data)
    print(f"wrote {store.n_tokens} tokens / {store.n_seqs} transcripts to {store.dir}")
    return 0


def cmd_train(cfg: PipelineConfig, args) -> int:
    final, metrics = train_sae(cfg)
    print(f"checkpoint: {final}")
    for name, value in metrics.items():
        print(f"  {name:<18} {value}")
    return 0


def cmd_study(cfg: PipelineConfig, args) -> int:
    ckpt = Path(args.ckpt) if getattr(args, "ckpt", None) else Path(cfg.paths.run_dir) / "final"
    out = Path(cfg.paths.run_dir) / "report.json"
    report = run_study(cfg, ckpt, out_path=out)
    if getattr(args, "markdown", False):
        out.with_suffix(".md").write_text(format_markdown(report), encoding="utf-8")
    print(format_summary(report))
    print(f"report: {out}")
    return 0


def cmd_run(cfg: PipelineConfig, args) -> int:
    if cfg.paths.hook not in list_hooks(cfg.paths.store_root):
        cmd_synth(cfg, args)
    cmd_train(cfg, args)
    return cmd_study(cfg, args)


COMMANDS = {"synth": cmd_synth, "train": cmd_train, "study": cmd_study, "run": cmd_run}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = build_config(args)
        return COMMANDS[args.command](cfg, args)
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
