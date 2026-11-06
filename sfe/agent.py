"""One episode: render the task under a framing into a fresh sandbox, run K agent turns, grade after each."""
from __future__ import annotations

import asyncio
import json
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path

from sfe import api
from sfe.config import MODELS, SYSTEM_PROMPTS, TURN1_TEMPLATE, TURN1_TEMPLATE_DUMP, TURN_BUDGET_MSG, TURN_NEXT, Model
from sfe.grade import grade_hidden, run_public_tests
from sfe.judge import classify_turn
from sfe.render import Task, load_task, neutralize, render_hidden_tests, render_task
from sfe.sandbox import TOOLS, Sandbox, dispatch, ensure_bin_dir


@dataclass
class EpisodeSpec:
    model: str
    task: str
    framing: str
    seed: int
    system: str = "default"
    turns: int = 3
    max_tool_calls: int = 15
    dump_repo: bool = False     # True = paste the whole repo into turn 1 (the pilot setting); False = file list only

    @property
    def id(self) -> str:
        return f"{self.model}__{self.task}__{self.framing}__s{self.seed}__{self.system}"


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k) != after.get(k))


async def run_turn(model: Model, messages: list[dict], sb: Sandbox, max_tool_calls: int, log) -> dict:
    """Drive tool calls until the model answers without one (or the budget runs out)."""
    n_calls, calls_log, cost, errors = 0, [], 0.0, []
    tokens_in = tokens_out = cached_in = 0
    providers: dict[str, int] = {}
    byok = False
    finish_reasons: list[str] = []
    budget_notice_sent = False
    final_text = ""
    while True:
        tool_choice = "auto"
        if n_calls >= max_tool_calls:
            if not budget_notice_sent:
                messages.append({"role": "user", "content": TURN_BUDGET_MSG})
                budget_notice_sent = True
            tool_choice = "none"
        r = await api.chat(model, messages, tools=TOOLS, tool_choice=tool_choice, log=log)
        cost += r.cost_usd
        if r.usage:
            tokens_in += r.usage.get("prompt_tokens") or 0
            tokens_out += r.usage.get("completion_tokens") or 0
            cached_in += ((r.usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
            byok = byok or bool(r.usage.get("is_byok"))
        if r.provider:
            providers[r.provider] = providers.get(r.provider, 0) + 1
        finish_reasons.append(str(r.finish_reason))
        if r.error:
            errors.append(r.error)
            log(f"turn aborted: {r.error[:200]}")
            break
        messages.append(r.as_message())
        if not r.tool_calls:
            final_text = r.text
            break
        for tc in r.tool_calls:
            t0 = time.time()
            result = dispatch(sb, tc["name"], tc["arguments"])
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            n_calls += 1
            try:
                args = json.loads(tc["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc["arguments"][:200]}
            calls_log.append({"name": tc["name"], "args": {k: (v if len(str(v)) < 300 else str(v)[:300] + "...")
                                                         for k, v in (args.items() if isinstance(args, dict) else [])},
                              "result_head": result[:300], "secs": round(time.time() - t0, 2)})
        if r.text and r.tool_calls:
            final_text = r.text   # interim commentary; overwritten by the real final message
    return {"final_text": final_text, "n_tool_calls": n_calls, "calls": calls_log, "cost_usd": cost,
            "tokens_in": tokens_in, "tokens_out": tokens_out, "cached_in": cached_in, "providers": providers,
            "is_byok": byok, "errors": errors, "hit_budget": budget_notice_sent,
            "finish_reasons": finish_reasons,
            "empty_reply": (n_calls == 0 and not final_text.strip()),
            # Anthropic's safety classifier refuses at input with finish_reason content_filter and no usage
            "platform_refusal": any(fr in ("content_filter", "refusal") for fr in finish_reasons)}


async def run_episode(spec: EpisodeSpec, run_dir: Path, log=print) -> dict:
    model = MODELS[spec.model]
    task: Task = load_task(spec.task)
    from sfe.sandbox import neutral_sandbox_dir
    ep_dir = neutral_sandbox_dir()     # random name outside the project tree: no eval name or framing label in any path
    hidden_dir = run_dir / "hidden" / f"{spec.task}__{spec.framing}"
    if not (hidden_dir / ".rendered").exists():
        render_hidden_tests(task, spec.framing, hidden_dir)
        (hidden_dir / ".rendered").write_text("ok")
    if ep_dir.exists():
        import shutil
        shutil.rmtree(ep_dir)
    render_task(task, spec.framing, ep_dir)
    sb = Sandbox(ep_dir, bin_dir=ensure_bin_dir(run_dir))
    from sfe.sandbox import MAX_OUTPUT_CHARS
    record: dict = {"spec": asdict(spec), "id": spec.id, "model_id": model.model_id, "started": time.time(),
                    "max_output_chars": MAX_OUTPUT_CHARS,
                    "turns": [], "cost_usd": 0.0, "error": None}
    baseline = grade_hidden(sb, hidden_dir, task.rubric)
    record["baseline"] = {"n_pass": baseline["n_pass"], "n_total": baseline["n_total"]}
    blurb = task.framings[spec.framing]["TASK_BLURB"]
    if spec.dump_repo:
        first = TURN1_TEMPLATE_DUMP.format(blurb=blurb, repo_dump=sb.repo_dump())
    else:
        first = TURN1_TEMPLATE.format(blurb=blurb, repo_dump="\n".join(f"  {rel}" for rel, _ in sb.iter_files()))
    messages = [{"role": "system", "content": SYSTEM_PROMPTS[spec.system]},
                {"role": "user", "content": first}]
    try:
        before = sb.snapshot()
        for t in range(1, spec.turns + 1):
            if t > 1:
                messages.append({"role": "user", "content": TURN_NEXT})
            tr = await run_turn(model, messages, sb, spec.max_tool_calls, log)
            after = sb.snapshot()
            tr["turn"] = t
            tr["files_changed"] = changed_files(before, after)
            before = after
            tr["grade"] = grade_hidden(sb, hidden_dir, task.rubric)
            tr["public_tests"] = run_public_tests(sb, task.public_test_cmd)
            tr["final_text_neutral"] = neutralize(tr["final_text"], task, spec.framing)
            if tr.get("platform_refusal") and tr["empty_reply"]:
                tr["judge"] = {"category": "full_refusal", "disclosed_limitation": False, "hedging": False,
                               "reason": "platform content filter (finish_reason content_filter), empty reply", "judge_cost": 0.0}
            else:
                tr["judge"] = await classify_turn(tr["final_text_neutral"], len(tr["files_changed"]), tr["n_tool_calls"],
                                                  tr["hit_budget"])
            record["cost_usd"] += tr["cost_usd"] + (tr["judge"].get("judge_cost") or 0)
            record["turns"].append(tr)
            log(f"{spec.id} turn {t}: rubric {tr['grade']['n_pass']}/{tr['grade']['n_total']} "
                f"calls={tr['n_tool_calls']} changed={len(tr['files_changed'])} judge={tr['judge']['category']} "
                f"${tr['cost_usd']:.2f}")
            if tr["errors"]:
                record["error"] = tr["errors"][-1]
                break
    except Exception:  # noqa: BLE001 - keep the record even on harness bugs
        record["error"] = traceback.format_exc()[-2000:]
        log(f"{spec.id} CRASHED: {record['error'][-400:]}")
    record["final_frac"] = record["turns"][-1]["grade"]["frac"] if record["turns"] else None
    record["final_snapshot"] = sb.snapshot()
    record["sandbox_dir"] = str(ep_dir)
    record["messages"] = messages
    record["finished"] = time.time()
    record["complete"] = record["error"] is None and len(record["turns"]) == spec.turns
    out = run_dir / "episodes" / f"{spec.id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1, default=str))
    return record
