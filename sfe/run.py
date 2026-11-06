"""Orchestrate episodes: model x task x framing x seed with concurrency, resume and a spend cap.

    python -m sfe.run --run pilot --models astra --tasks all --seeds 0 --turns 3 --concurrency 6 --cap-usd 40
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from sfe.agent import EpisodeSpec, run_episode
from sfe.config import FRAMINGS, MODELS, RUNS_DIR
from sfe.render import list_tasks


def build_specs(a) -> list[EpisodeSpec]:
    tasks = list_tasks() if a.tasks == ["all"] else a.tasks
    specs = []
    for seed in a.seeds:
        for task in tasks:
            for model in a.models:
                for framing in a.framings:
                    for system in a.system:
                        specs.append(EpisodeSpec(model=model, task=task, framing=framing, seed=seed, system=system,
                                                 turns=a.turns, max_tool_calls=a.max_tool_calls, dump_repo=a.dump_repo))
    return specs


async def main_async(a) -> None:
    run_dir = RUNS_DIR / a.run
    (run_dir / "episodes").mkdir(parents=True, exist_ok=True)
    logf = open(run_dir / "run.log", "a")

    def log(msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        logf.write(line + "\n"); logf.flush()

    specs = build_specs(a)
    done = {p.stem for p in (run_dir / "episodes").glob("*.json")
            if json.loads(p.read_text()).get("complete") or a.no_retry_failed}
    todo = [s for s in specs if s.id not in done]
    log(f"run {a.run}: {len(specs)} episodes, {len(done)} already complete, {len(todo)} to run; cap ${a.cap_usd}")
    spent = sum(json.loads(p.read_text()).get("cost_usd", 0) for p in (run_dir / "episodes").glob("*.json"))
    sem = asyncio.Semaphore(a.concurrency)
    state = {"spent": spent, "stopped": False}

    async def one(spec: EpisodeSpec):
        async with sem:
            if state["stopped"]:
                return
            if state["spent"] >= a.cap_usd:
                state["stopped"] = True
                log(f"SPEND CAP reached (${state['spent']:.2f} >= ${a.cap_usd}); not starting {spec.id}")
                return
            rec = await run_episode(spec, run_dir, log=log)
            state["spent"] += rec["cost_usd"]
            log(f"done {spec.id}: final={rec['final_frac']} cost=${rec['cost_usd']:.2f} "
                f"run total=${state['spent']:.2f} complete={rec['complete']}")

    await asyncio.gather(*(one(s) for s in todo))
    log(f"finished; run total ${state['spent']:.2f}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True)
    p.add_argument("--models", nargs="+", default=["astra"], choices=sorted(MODELS))
    p.add_argument("--tasks", nargs="+", default=["all"])
    p.add_argument("--framings", nargs="+", default=list(FRAMINGS))
    p.add_argument("--seeds", nargs="+", type=int, default=[0])
    p.add_argument("--system", nargs="+", default=["default"])
    p.add_argument("--turns", type=int, default=3)
    p.add_argument("--max-tool-calls", type=int, default=15)
    p.add_argument("--dump-repo", action="store_true", help="paste the whole repo into turn 1 instead of a file list")
    p.add_argument("--concurrency", type=int, default=6)
    p.add_argument("--cap-usd", type=float, default=50.0)
    p.add_argument("--no-retry-failed", action="store_true", help="treat crashed/incomplete episodes as done")
    a = p.parse_args()
    asyncio.run(main_async(a))


if __name__ == "__main__":
    main()
