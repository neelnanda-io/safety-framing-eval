"""Which first requests does a provider's safety filter refuse?

Sends the exact opening request of a real-repository episode (system prompt, first user message, tool definitions) several
times per model, repository and description, and counts refusals (empty reply with finish reason content_filter; for
Google, "blocked the response"). Refused requests cost nothing; accepted ones are capped at a short reply.

    python -m sfe.filter_probe --models fable52 opus carbon argon --tries 3
    python -m sfe.filter_probe --models fable52 --tasks rsl_rl --framings fg_neutral_words fg_hidden_no_monitor
    SFE_REAL_TASKS_DIR=real_tasks_new python -m sfe.filter_probe --models opus --tasks control_arena --framings use_attack_side
(--tasks / --framings added 13 Nov 2026 for the descriptions where the purpose is only implied and for ControlArena;
the defaults are the original six repositories and the safety / product pair.)
"""
from __future__ import annotations

import argparse
import asyncio
import json

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from sfe import api  # noqa: E402
from sfe.config import MODELS, RESULTS_DIR  # noqa: E402
from sfe.real import SYSTEM_PROMPT, TURN1, list_real_tasks, load_real_task  # noqa: E402
from sfe.sandbox import TOOLS  # noqa: E402

OUT = RESULTS_DIR / "real" / "filter_probe.json"


async def main_async(a) -> None:
    old = json.loads(OUT.read_text()) if OUT.exists() else []
    have = {(r["model"], r["task"], r["framing"], r["try"]) for r in old}
    sem = asyncio.Semaphore(a.concurrency)
    rows = list(old)

    async def one(mkey, task, framing, i):
        t = load_real_task(task)
        msgs = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": TURN1.format(context=t["framings"][framing]["context"])}]
        async with sem:
            r = await api.chat(MODELS[mkey], msgs, tools=TOOLS, tool_choice="auto", max_tokens=a.max_tokens)
        refused = r.finish_reason in ("content_filter", "refusal") and not r.tool_calls and not (r.text or "").strip()
        rows.append({"model": mkey, "task": task, "framing": framing, "try": i, "refused": bool(refused),
                     "finish_reason": r.finish_reason, "provider": r.provider, "cost": r.cost_usd, "error": r.error,
                     "n_tool_calls": len(r.tool_calls), "text": (r.text or "")[:300]})

    tasks = a.tasks or list_real_tasks()
    framings = a.framings or ["safety", "capabilities"]
    jobs = [one(m, t, f, i) for m in a.models for t in tasks for f in framings
            if f in load_real_task(t)["framings"] for i in range(a.tries) if (m, t, f, i) not in have]
    await asyncio.gather(*jobs)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1))
    print(f"{len(jobs)} new requests, cost ${sum(r['cost'] for r in rows[len(old):]):.2f}")
    for m in a.models:
        print(f"\n{m}: refused / tried (errors)")
        for f in framings:
            cells = []
            for t in tasks:
                xs = [r for r in rows if r["model"] == m and r["task"] == t and r["framing"] == f]
                if not xs:
                    continue
                err = sum(bool(r["error"]) for r in xs)
                cells.append(f"{t} {sum(r['refused'] for r in xs)}/{len(xs) - err}" + (f" ({err} err)" if err else ""))
            print(f"  {f:<13}" + " | ".join(cells))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=1500)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--tasks", nargs="*", default=None, help="default: every task in the task folder (SFE_REAL_TASKS_DIR)")
    ap.add_argument("--framings", nargs="*", default=None, help="default: safety capabilities")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
