"""First-message probe: what does a model say BEFORE it has read any code, under many small edits of the description?

GPT-6 Astra and GPT-6.1 Sol state their limit in their first words to the user (20 of 20 safety-described episodes on the
attack-like repositories, against 1 of 19 product-described ones), after a single `list_files` call. So the opening
paragraph of the user's message is the whole stimulus, and the first message is a cheap readout of how a description is
taken. This script runs a real checkout and the real tools, lets the model act until it first writes something to the user
(at most MAX_STEPS model calls), saves that, and labels it with the same judge and definition as sfe/real_disclosure.py.

It is a proxy. Whether the final diff changes the core code still needs full episodes (python -m sfe.real --framings ...).

    python -m sfe.first_words run --models astra sol61s --tasks rsl_rl synthetic-data-kit --samples 6
    python -m sfe.first_words label          # judge every saved probe
    python -m sfe.first_words table          # print and save results/real/first_words_table.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import time
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from sfe import api  # noqa: E402
from sfe.config import MODELS, RESULTS_DIR  # noqa: E402
from sfe.real import SYSTEM_PROMPT, RealSandbox, ensure_venv, first_message, load_real_task, make_checkout  # noqa: E402
from sfe.real_disclosure import PROMPT, blocks, render, verify_quotes  # noqa: E402
from sfe.sandbox import TOOLS, dispatch  # noqa: E402

# SFE_FIRST_WORDS_DIR keeps another study's first replies apart from the 640 of the description-edit study.
OUT = Path(os.environ.get("SFE_FIRST_WORDS_DIR") or RESULTS_DIR / "real" / "first_words")
MAX_STEPS = int(os.environ.get("SFE_FIRST_WORDS_MAX_STEPS") or 5)   # model calls allowed before the first words


async def probe(model_key: str, task_id: str, framing: str, k: int) -> dict:
    dest = OUT / f"{model_key}__{task_id}__{framing}__k{k}.json"
    if dest.exists():
        return json.loads(dest.read_text())
    model, task = MODELS[model_key], load_real_task(task_id)
    loop = asyncio.get_running_loop()
    venv = ensure_venv(task)
    ws, repo, _ = await loop.run_in_executor(None, make_checkout, task, framing)
    sb = RealSandbox(repo, ws, venv, task.get("pythonpath", "."))
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": first_message(task["framings"][framing]["context"])}]
    rec = {"model": model_key, "task": task_id, "framing": framing, "k": k, "first_text": "", "calls_before": [], "cost_usd": 0.0,
           "error": None, "blocked": False, "started": time.time()}
    try:
        for step in range(MAX_STEPS):
            r = await api.chat(model, messages, tools=TOOLS, tool_choice="auto")
            rec["cost_usd"] += r.cost_usd
            if r.error:
                rec["error"] = r.error
                break
            if r.finish_reason in ("content_filter", "refusal") and not r.tool_calls and not (r.text or "").strip():
                rec["blocked"] = True                     # the provider's filter returned nothing
                break
            messages.append(r.as_message())
            if (r.text or "").strip():
                rec["first_text"] = r.text.strip()
                rec["first_text_with_tool_calls"] = bool(r.tool_calls)
                rec["next_calls"] = [{"name": tc["name"], "arguments": tc["arguments"][:300]} for tc in r.tool_calls]
                break
            if not r.tool_calls:
                break
            for tc in r.tool_calls:
                result = await loop.run_in_executor(None, dispatch, sb, tc["name"], tc["arguments"])
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                rec["calls_before"].append({"name": tc["name"], "arguments": tc["arguments"][:300]})
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    rec["messages"] = messages
    OUT.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rec, indent=1, default=str))
    print(f"{dest.stem}: ${rec['cost_usd']:.2f} {rec['error'] or ''}{'BLOCKED ' if rec['blocked'] else ''}{rec['first_text'][:150]!r}", flush=True)
    return rec


async def run(a) -> None:
    sem = asyncio.Semaphore(a.concurrency)
    jobs = []
    for t in a.tasks:
        names = a.framings or [f for f in load_real_task(t)["framings"] if not f.endswith("_reworded")]
        for f in names:
            for m in a.models:
                for k in range(a.samples):
                    jobs.append((m, t, f, k))

    async def one(j):
        async with sem:
            try:
                return await probe(*j)
            except Exception as e:  # noqa: BLE001 - one failed probe must not stop the rest
                print(f"FAILED {j}: {type(e).__name__}: {str(e)[:200]}", flush=True)

    recs = [r for r in await asyncio.gather(*(one(j) for j in jobs)) if r]
    print(f"{len(recs)} probes; total ${sum(r['cost_usd'] for r in recs):.2f}; errors {sum(bool(r['error']) for r in recs)}; "
          f"blocked {sum(r['blocked'] for r in recs)}; no words within {MAX_STEPS} steps {sum(not r['first_text'] and not r['error'] and not r['blocked'] for r in recs)}")


async def label(a) -> None:
    sem = asyncio.Semaphore(a.concurrency)
    files = sorted(OUT.glob("*.json"))

    async def one(f: Path):
        rec = json.loads(f.read_text())
        if rec.get("label") is not None and not a.force:
            return
        bl = blocks(rec["messages"])
        record, _ = render(bl)
        if not rec["first_text"]:
            rec["label"] = {"restriction_stated": False, "nothing_said": True}
        else:
            lab = None
            for _ in range(3):
                async with sem:
                    resp = await api.chat(MODELS[a.judge], [{"role": "user", "content": PROMPT.format(record=record)}],
                                          response_format={"type": "json_object"}, max_tokens=4000)
                lab = api.parse_json_reply(resp.text)
                if isinstance(lab, list):
                    lab = lab[0] if lab and isinstance(lab[0], dict) else None
                if isinstance(lab, dict) and "restriction_stated" in lab:
                    break
                lab = None
            if lab is None:
                print("FAILED to label", f.stem, flush=True)
                return
            rec["label"] = {**verify_quotes(bl, lab), "judge": a.judge}
        f.write_text(json.dumps(rec, indent=1, default=str))

    await asyncio.gather(*(one(f) for f in files))
    print(f"labelled {sum(json.loads(f.read_text()).get('label') is not None for f in files)} of {len(files)} probes")


def table(a) -> None:
    rows: dict = {}
    for f in sorted(OUT.glob("*.json")):
        r = json.loads(f.read_text())
        key = (r["task"], r["framing"], r["model"])
        c = rows.setdefault(key, {"n": 0, "limit": 0, "refusal": 0, "reason": 0, "blocked": 0, "silent": 0, "errors": 0, "examples": [], "what": []})
        if r["error"]:
            c["errors"] += 1
            continue
        c["n"] += 1
        lab = r.get("label") or {}
        c["blocked"] += bool(r["blocked"])
        c["silent"] += bool(not r["first_text"] and not r["blocked"])
        c["limit"] += bool(lab.get("restriction_stated"))
        c["refusal"] += bool(lab.get("refusal_wording"))
        c["reason"] += bool(lab.get("reason_given"))
        if lab.get("restriction_stated") and len(c["what"]) < 3:
            c["what"].append(lab.get("what", ""))
        if r["first_text"] and len(c["examples"]) < 2:
            c["examples"].append(r["first_text"][:260])
    out = {}
    for task in sorted({k[0] for k in rows}):
        edits = load_real_task(task)["framings"]
        print(f"\n=== {task}: first words that state a limit on what the model will work on (of probes run) ===")
        models = sorted({k[2] for k in rows if k[0] == task})
        print(f"{'description':<24}" + "".join(f"{m:>22}" for m in models) + "   what changed")
        for fr in edits:
            if not any((task, fr, m) in rows for m in models):
                continue
            cells = []
            for m in models:
                c = rows.get((task, fr, m))
                if not c:
                    cells.append(f"{'-':>22}")
                    continue
                extra = (f" refuse {c['refusal']}" if c["refusal"] else "") + (f" why {c['reason']}" if c["reason"] else "") + (f" blk {c['blocked']}" if c["blocked"] else "")
                cells.append(f"{(str(c['limit']) + '/' + str(c['n']) + extra):>22}")
                out[f"{task}|{fr}|{m}"] = {k: v for k, v in c.items()}
            print(f"{fr:<24}" + "".join(cells) + "   " + edits[fr].get("edit", {"safety": "ORIGINAL safety description", "capabilities": "ORIGINAL product description"}.get(fr, "")))
    (OUT.parent / f"{OUT.name}_table.json").write_text(json.dumps(out, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--models", nargs="+", default=["astra", "sol61s"])
    r.add_argument("--tasks", nargs="+", default=["rsl_rl", "synthetic-data-kit"])
    r.add_argument("--framings", nargs="*", default=None, help="default: every description of the task except the Claude rewordings")
    r.add_argument("--samples", type=int, default=6)
    r.add_argument("--concurrency", type=int, default=8)
    lb = sub.add_parser("label")
    lb.add_argument("--judge", default="argon")
    lb.add_argument("--force", action="store_true")
    lb.add_argument("--concurrency", type=int, default=10)
    sub.add_parser("table")
    a = ap.parse_args()
    if a.cmd == "run":
        asyncio.run(run(a))
    elif a.cmd == "label":
        asyncio.run(label(a))
    else:
        table(a)


if __name__ == "__main__":
    main()
