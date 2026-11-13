"""Episodes through OpenAI's Responses API: reasoning items (encrypted) are carried across every call, as in Codex,
and a reasoning SUMMARY is recorded for every model call. Same tasks, prompts, tools, budget and grading as sfe.agent.

    python -m sfe.agent_native --run native_sol61 --model sol61 --tasks organism_data prompt_augment diff_monitor --seeds 0 1 2 3
Billed to the OpenAI account (OPENAI_API_KEY in .env), flex tier.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import time
from pathlib import Path

from sfe.config import RUNS_DIR, SYSTEM_PROMPTS, TURN1_TEMPLATE, TURN_BUDGET_MSG, TURN_NEXT
from sfe.grade import grade_hidden, run_public_tests
from sfe.judge import classify_turn
from sfe.render import load_task, neutralize, render_hidden_tests, render_task
from sfe.responses_api import MODEL_IDS, PRICES, _call, tools_for_responses
from sfe.sandbox import TOOLS, Sandbox, dispatch, ensure_bin_dir


async def call(model_key, instructions, items, tool_choice, effort):
    body = {"model": MODEL_IDS[model_key], "instructions": instructions, "input": items, "tools": tools_for_responses(TOOLS),
            "tool_choice": tool_choice, "reasoning": {"effort": effort, "summary": "detailed"},
            "include": ["reasoning.encrypted_content"], "store": False, "service_tier": "flex", "max_output_tokens": 24000}
    return await asyncio.to_thread(_call, body)


def cost_of(model_key, u):
    pin, pout = PRICES[MODEL_IDS[model_key]]
    cached = (u.get("input_tokens_details") or {}).get("cached_tokens", 0)
    return ((u.get("input_tokens", 0) - cached) * pin + cached * pin * 0.1 + u.get("output_tokens", 0) * pout) / 1e6


async def run_episode(model_key, task_id, framing, seed, run_dir, turns=3, max_calls=15, effort="medium", log=print):
    task = load_task(task_id)
    eid = f"{model_key}__{task_id}__{framing}__s{seed}__native"
    from sfe.sandbox import neutral_sandbox_dir
    ep_dir = neutral_sandbox_dir()
    hidden = run_dir / "hidden" / f"{task_id}__{framing}"
    if not (hidden / ".rendered").exists():
        render_hidden_tests(task, framing, hidden); (hidden / ".rendered").write_text("ok")
    if ep_dir.exists():
        shutil.rmtree(ep_dir)
    render_task(task, framing, ep_dir)
    sb = Sandbox(ep_dir, bin_dir=ensure_bin_dir(run_dir))
    instructions = SYSTEM_PROMPTS["default"]
    listing = "\n".join(f"  {rel}" for rel, _ in sb.iter_files())
    items = [{"role": "user", "content": TURN1_TEMPLATE.format(blurb=task.framings[framing]["TASK_BLURB"], repo_dump=listing)}]
    rec = {"spec": {"model": model_key, "task": task_id, "framing": framing, "seed": seed, "system": "default",
                    "turns": turns, "max_tool_calls": max_calls, "backend": "responses"},
           "id": eid, "turns": [], "cost_usd": 0.0, "error": None}
    for t in range(1, turns + 1):
        if t > 1:
            items.append({"role": "user", "content": TURN_NEXT})
        n_calls, calls_log, summaries, final_text, budget_sent, cost = 0, [], [], "", False, 0.0
        before = sb.snapshot()
        while True:
            tc = "auto"
            if n_calls >= max_calls:
                if not budget_sent:
                    items.append({"role": "user", "content": TURN_BUDGET_MSG}); budget_sent = True
                tc = "none"
            r = await call(model_key, instructions, items, tc, effort)
            if r.get("error"):
                rec["error"] = r["error"]; log(f"{eid} API error {r['error'][:200]}"); break
            cost += cost_of(model_key, r.get("usage", {}))
            out = r.get("output", [])
            fcalls = []
            for o in out:
                if o.get("type") == "reasoning":
                    s = "\n".join(x.get("text", "") for x in o.get("summary", []))
                    if s.strip():
                        summaries.append({"after_calls": n_calls, "text": s})
                elif o.get("type") == "message":
                    final_text = "\n".join(c.get("text", "") for c in o.get("content", []) if c.get("type") == "output_text")
                elif o.get("type") == "function_call":
                    fcalls.append(o)
            items += out
            if not fcalls:
                break
            for fc in fcalls:
                res = dispatch(sb, fc["name"], fc.get("arguments", ""))
                items.append({"type": "function_call_output", "call_id": fc["call_id"], "output": res})
                n_calls += 1
                try:
                    args = json.loads(fc.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                calls_log.append({"name": fc["name"], "args": {k: str(v)[:300] for k, v in (args.items() if isinstance(args, dict) else [])},
                                  "result_head": res[:300]})
        after = sb.snapshot()
        tr = {"turn": t, "final_text": final_text, "n_tool_calls": n_calls, "calls": calls_log, "summaries": summaries,
              "cost_usd": cost, "hit_budget": budget_sent, "files_changed": sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)),
              "errors": [rec["error"]] if rec["error"] else []}
        tr["grade"] = grade_hidden(sb, hidden, task.rubric)
        tr["public_tests"] = run_public_tests(sb, task.public_test_cmd)
        tr["final_text_neutral"] = neutralize(final_text, task, framing)
        tr["judge"] = await classify_turn(tr["final_text_neutral"], len(tr["files_changed"]), n_calls, budget_sent)
        rec["turns"].append(tr); rec["cost_usd"] += cost
        log(f"{eid} turn {t}: {tr['grade']['n_pass']}/{tr['grade']['n_total']} calls={n_calls} summaries={len(summaries)} ${cost:.2f}")
        if rec["error"]:
            break
    rec["complete"] = rec["error"] is None and len(rec["turns"]) == turns
    rec["final_snapshot"] = sb.snapshot()
    rec["native_items_count"] = len(items)
    out = run_dir / "episodes" / f"{eid}.json"; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1, default=str))
    return rec


async def main_async(a):
    run_dir = RUNS_DIR / a.run; (run_dir / "episodes").mkdir(parents=True, exist_ok=True)
    logf = open(run_dir / "run.log", "a")
    def log(m):
        line = f"{time.strftime('%H:%M:%S')} {m}"; print(line, flush=True); logf.write(line + "\n"); logf.flush()
    sem = asyncio.Semaphore(a.concurrency)
    done = {p.stem for p in (run_dir / "episodes").glob("*.json") if json.loads(p.read_text()).get("complete")}
    state = {"spent": 0.0}
    async def one(task, fr, seed):
        if f"{a.model}__{task}__{fr}__s{seed}__native" in done:
            return
        async with sem:
            if state["spent"] > a.cap_usd:
                log("SPEND CAP reached"); return
            r = await run_episode(a.model, task, fr, seed, run_dir, effort=a.effort, log=log)
            state["spent"] += r["cost_usd"]
            log(f"done {r['id']} final={r['turns'][-1]['grade']['frac'] if r['turns'] else None} cost=${r['cost_usd']:.2f} total=${state['spent']:.2f}")
    await asyncio.gather(*(one(t, fr, s) for s in a.seeds for t in a.tasks for fr in ("safety", "capabilities")))
    log(f"finished; total ${state['spent']:.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True); ap.add_argument("--model", required=True)
    ap.add_argument("--tasks", nargs="+", required=True); ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--effort", default="medium"); ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--cap-usd", type=float, default=20)
    asyncio.run(main_async(ap.parse_args()))
