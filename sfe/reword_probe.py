"""Try candidate rewordings of a description against a provider's safety filter.

Each candidate is sent as the exact opening request of an episode (system prompt, first user message, tool definitions).
With --readme the request also contains the agent reading the README, whose last section repeats the description, because
the filter sees tool results too. Refused requests cost nothing.

    python -m sfe.reword_probe --file results/real/reword_candidates.json --models fable52 opus --tries 4
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from sfe import api  # noqa: E402
from sfe.config import MODELS, RESULTS_DIR, ROOT  # noqa: E402
from sfe.real import SYSTEM_PROMPT, TURN1, load_real_task, note_block  # noqa: E402
from sfe.sandbox import TOOLS  # noqa: E402

OUT = RESULTS_DIR / "real" / "reword_probe.json"


def readme_at_pin(task: dict) -> str:
    return subprocess.run(["git", "show", f"{task['pin']}:{task.get('readme', 'README.md')}"], cwd=ROOT / task["source"],
                          capture_output=True, text=True).stdout


async def main_async(a) -> None:
    cands = json.loads(Path(a.file).read_text())
    if a.only:
        cands = {k: v for k, v in cands.items() if k in a.only}
    rows = json.loads(OUT.read_text()) if OUT.exists() else []
    sem = asyncio.Semaphore(a.concurrency)
    new = []

    async def one(mkey: str, name: str, c: dict, i: int):
        task = load_real_task(c["task"])
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": TURN1.format(context=c["context"])}]
        if a.readme:
            readme = readme_at_pin(task).rstrip("\n") + note_block(c["note"])
            msgs += [{"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {
                        "name": "read_file", "arguments": json.dumps({"path": task.get("readme", "README.md")})}}]},
                     {"role": "tool", "tool_call_id": "call_1", "content": readme[:8000]}]
        async with sem:
            r = await api.chat(MODELS[mkey], msgs, tools=TOOLS, tool_choice="auto", max_tokens=a.max_tokens)
        refused = r.finish_reason in ("content_filter", "refusal") and not r.tool_calls and not (r.text or "").strip()
        new.append({"model": mkey, "candidate": name, "readme": bool(a.readme), "try": i, "refused": bool(refused),
                    "finish_reason": r.finish_reason, "cost": r.cost_usd, "error": r.error, "text": (r.text or "")[:400],
                    "n_tool_calls": len(r.tool_calls)})

    await asyncio.gather(*(one(m, n, c, i) for m in a.models for n, c in cands.items() for i in range(a.tries)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows + new, indent=1))
    print(f"{len(new)} requests, cost ${sum(r['cost'] for r in new):.2f}" + ("  (with the README read)" if a.readme else ""))
    for m in a.models:
        for n in cands:
            xs = [r for r in new if r["model"] == m and r["candidate"] == n]
            err = sum(bool(r["error"]) for r in xs)
            says = next((r["text"][:110].replace("\n", " ") for r in xs if r["text"].strip()), "")
            print(f"  {m:<8} {n:<26} refused {sum(r['refused'] for r in xs)}/{len(xs) - err}" + (f" ({err} errors)" if err else "")
                  + (f"   says: {says!r}" if says else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--only", nargs="*", default=None, help="candidate names to try (default: all in the file)")
    ap.add_argument("--tries", type=int, default=4)
    ap.add_argument("--readme", action="store_true")
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--concurrency", type=int, default=8)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
