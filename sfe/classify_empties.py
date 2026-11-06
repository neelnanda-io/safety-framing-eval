"""Replay every empty-reply turn of the given runs once, to tell platform refusals (finish_reason content_filter)
from transient empties. Input-level refusals cost nothing. Writes results/empties_<runs>.json.

    python -m sfe.classify_empties w2_opus w2_fable
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sfe import api
from sfe.config import MODELS, RESULTS_DIR, RUNS_DIR
from sfe.sandbox import TOOLS


def turn_start_indices(messages: list[dict]) -> list[int]:
    """Index of each user turn-prompt message (turn 1 = index 1; later turns = the TURN_NEXT user messages)."""
    idx = [i for i, m in enumerate(messages) if m["role"] == "user" and not m.get("tool_call_id")]
    return idx


async def main() -> None:
    runs = sys.argv[1:]
    out = []
    for run in runs:
        for f in sorted((RUNS_DIR / run).glob("episodes/*.json")):
            r = json.loads(f.read_text())
            empties = [t["turn"] for t in r["turns"] if t["n_tool_calls"] == 0 and not t["final_text"].strip()]
            if not empties:
                continue
            starts = turn_start_indices(r["messages"])
            for turn in empties:
                if turn - 1 >= len(starts):
                    continue
                msgs = r["messages"][: starts[turn - 1] + 1]
                rep = await api.chat(MODELS[r["spec"]["model"]], msgs, tools=TOOLS)
                rec = {"run": run, "episode": f.stem, "turn": turn, "finish_reason": rep.finish_reason, "error": rep.error,
                       "n_tool_calls": len(rep.tool_calls), "text_head": rep.text[:120], "cost": rep.cost_usd}
                print(rec, flush=True)
                out.append(rec)
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"empties_{'_'.join(runs)}.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
