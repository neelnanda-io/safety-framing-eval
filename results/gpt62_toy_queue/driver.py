"""Run the original six toy tasks for GPT-6.2 Sol and GPT-6.2 Astra strictly one episode at a time on the laptop.

Part A of docs/GPT62_PREREG.md: six tasks x safety and capabilities x seeds 0-5 = 72 episodes per model, default system
prompt, 3 turns of 15 tool calls, into runs/w5_sol62 and runs/w5_astra62 (the settings of main3_astra / w2_sol61 /
w3_terra61). Adapted from the driver that re-ran the sixteen spoiled episodes on 16 Nov.

Order: seed by seed; within a seed, task by task; within a task, one model then the other; the two descriptions of a pair
run back to back, in an order drawn from a fixed random seed. So the twins of every pair run minutes apart, and after
each seed both models have a complete block.

One harness process per episode (python -m sfe.run, concurrency 1, one spec); the next starts only after the previous
process has exited. Before each: no other local episode process (waits up to 30 minutes, then stops), at least 3 GiB free
disk, spend under the caps. Around each: a listing of /private/tmp; afterwards, entries that are NEW since the listing
and are named in this episode's own tool calls are MOVED (not deleted) into tmp_leftovers/ so the next episode cannot read
a stale script. Nothing that existed before is touched. An episode that ends incomplete is moved to failed/ next to this
script and run once more.

Usage: python3 driver.py   (writes driver.log and driver_state.json next to this file; safe to start again: completed
episodes are skipped)
"""
import datetime
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path("<repository>")
RUNS = REPO / "runs"
TMP = Path("/private/tmp")
TASKS = ["clf_eval", "diff_monitor", "organism_data", "probe_train", "prompt_augment", "redteam_loop"]
MODELS = ["sol62", "astra62"]
SEEDS = range(6)
MODEL_CAP = {"sol62": 45.0, "astra62": 130.0}     # also passed to the harness as each run's own cap
TOTAL_CAP = 165.0
LOG = open(HERE / "driver.log", "a")


def now():
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    line = f"{now()} {msg}"
    print(line, flush=True)
    LOG.write(line + "\n")
    LOG.flush()


def episodes():
    rng = random.Random(20261117)
    out = []
    for seed in SEEDS:
        for task in TASKS:
            for model in MODELS:
                framings = ["safety", "capabilities"]
                rng.shuffle(framings)
                for framing in framings:
                    out.append({"run": f"w5_{model}", "model": model, "task": task, "framing": framing, "seed": seed,
                                "id": f"{model}__{task}__{framing}__s{seed}__default"})
    return out


def tmp_listing():
    out = {}
    for e in os.scandir(TMP):
        try:
            st = e.stat(follow_symlinks=False)
            out[e.name] = (st.st_mtime, st.st_size, e.is_dir(follow_symlinks=False))
        except FileNotFoundError:
            pass
    return out


TMPNAME = re.compile(r"(?:/private)?/tmp/([^\s'\"`;|&<>(){}\\,:=/]+)")
# a LOCAL python process running episodes; an ssh command that only carries such text to the rented machine does not count
EPISODE_PROC = re.compile(r"^\s*\d+\s+\S*[Pp]ython[\d.]*\s+(?:-\S+\s+)*-m\s+sfe\.(run|real)(\s|$)")


def names_in_commands(rec):
    names = set()
    for m in rec.get("messages") or []:
        for tc in m.get("tool_calls") or []:
            names |= set(TMPNAME.findall((tc.get("function") or {}).get("arguments") or ""))
    return names


def other_episode_process():
    r = subprocess.run(["ps", "axo", "pid=,command="], capture_output=True, text=True)
    return [ln.strip() for ln in r.stdout.splitlines() if EPISODE_PROC.search(ln)]


def free_gib():
    st = os.statvfs("/System/Volumes/Data")
    return st.f_bavail * st.f_frsize / 2**30


def spent(model=None):
    tot = 0.0
    for m in ([model] if model else MODELS):
        for p in (RUNS / f"w5_{m}" / "episodes").glob("*.json"):
            tot += json.loads(p.read_text()).get("cost_usd", 0) or 0
        for p in (HERE / "failed").glob(f"{m}__*.json"):
            tot += json.loads(p.read_text()).get("cost_usd", 0) or 0
    return tot


def launch(ep):
    cmd = [sys.executable, "-m", "sfe.run", "--run", ep["run"], "--models", ep["model"], "--tasks", ep["task"],
           "--framings", ep["framing"], "--seeds", str(ep["seed"]), "--system", "default", "--turns", "3",
           "--max-tool-calls", "15", "--concurrency", "1", "--cap-usd", str(MODEL_CAP[ep["model"]])]
    shown = " ".join(["python3"] + cmd[1:])
    log(f"START {ep['id']}: {shown}")
    env = {k: v for k, v in os.environ.items() if k not in ("SFE_RUNS_DIR", "SFE_MAX_OUTPUT_CHARS")}
    with open(HERE / "harness_stdout.log", "a") as so:
        r = subprocess.run(cmd, cwd=REPO, env=env, stdout=so, stderr=subprocess.STDOUT)
    log(f"EXIT {ep['id']} code {r.returncode}")
    return shown


def main():
    eps = episodes()
    (HERE / "failed").mkdir(exist_ok=True)
    state_path = HERE / "driver_state.json"
    state = json.load(open(state_path)) if state_path.exists() else {}
    json.dump([e["id"] for e in eps], open(HERE / "order.json", "w"), indent=1)
    log(f"driver start: {len(eps)} episodes; caps {MODEL_CAP}, total ${TOTAL_CAP}")
    stopped_models = set()
    for n, ep in enumerate(eps, 1):
        out = RUNS / ep["run"] / "episodes" / f"{ep['id']}.json"
        if out.exists() and json.loads(out.read_text()).get("complete"):
            continue
        if ep["model"] in stopped_models:
            continue
        waited = 0
        while True:
            busy = other_episode_process()
            if not busy:
                break
            if waited >= 1800:
                log(f"STOP: another episode process has been running on the laptop for 30 minutes:\n" + "\n".join(busy))
                return
            if waited == 0:
                log(f"waiting: another episode process is running on the laptop: {busy[0][:160]}")
            time.sleep(20)
            waited += 20
        fg = free_gib()
        if fg < 3:
            log(f"STOP: only {fg:.1f} GiB free")
            return
        s_model, s_all = spent(ep["model"]), spent()
        done_m = sum(1 for e in eps[:n - 1] if e["model"] == ep["model"]
                     and (RUNS / e["run"] / "episodes" / f"{e['id']}.json").exists())
        mean_m = s_model / done_m if done_m else 0.0
        log(f"[{n}/{len(eps)}] {ep['model']} spent ${s_model:.2f} over {done_m} (mean ${mean_m:.2f}); all ${s_all:.2f}; "
            f"free {fg:.1f} GiB")
        if s_model + max(mean_m, 0.5) * 2 > MODEL_CAP[ep["model"]]:
            log(f"CAP: no more {ep['model']} episodes (${s_model:.2f} of ${MODEL_CAP[ep['model']]})")
            stopped_models.add(ep["model"])
            continue
        if s_all + 3 > TOTAL_CAP:
            log(f"STOP: total spend ${s_all:.2f} is at the ${TOTAL_CAP} cap")
            return
        for attempt in (1, 2):
            before = tmp_listing()
            t0 = now()
            shown = launch(ep)
            t1 = now()
            after = tmp_listing()
            rec = json.loads(out.read_text()) if out.exists() else None
            named = names_in_commands(rec) if rec else set()
            new = sorted(k for k in after if k not in before)
            changed = sorted(k for k in after if k in before and after[k][:2] != before[k][:2])
            moved, left_new = [], []
            dest = HERE / "tmp_leftovers" / f"{n:03d}_{ep['id']}__attempt{attempt}"
            for k in new:
                if k in named:
                    dest.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(TMP / k), str(dest / k))
                    moved.append(k)
                else:
                    left_new.append(k)
            ok = bool(rec and rec.get("complete"))
            st = state.setdefault(ep["id"], {"run": ep["run"], "attempts": []})
            st["attempts"].append({"attempt": attempt, "command": shown, "launched_utc": t0, "exited_utc": t1,
                                   "file_written": bool(rec), "complete": ok, "error": (rec or {}).get("error"),
                                   "cost_usd": (rec or {}).get("cost_usd"), "final_frac": (rec or {}).get("final_frac"),
                                   "tmp_new_named_and_moved": moved, "tmp_new_not_named_left": left_new,
                                   "tmp_preexisting_changed": changed,
                                   "tmp_preexisting_named_in_commands": sorted(k for k in named if k in before)})
            json.dump(state, open(state_path, "w"), indent=1)
            log(f"END {ep['id']} attempt {attempt}: complete={ok} cost=${(rec or {}).get('cost_usd') or 0:.2f} "
                f"final={(rec or {}).get('final_frac')} /tmp moved={moved} new-unnamed={left_new} "
                f"preexisting-changed={changed} preexisting-named={sorted(k for k in named if k in before)}")
            if ok:
                break
            if attempt == 1:
                if rec:
                    shutil.move(str(out), str(HERE / "failed" / f"{ep['id']}__attempt1.json"))
                log(f"RETRY {ep['id']} once (attempt 1 incomplete: {str((rec or {}).get('error'))[:200]})")
            else:
                log(f"GAVE UP on {ep['id']} after two attempts")
    done = sum(1 for e in eps if (RUNS / e["run"] / "episodes" / f"{e['id']}.json").exists())
    log(f"driver finished: {done} of {len(eps)} episode files present; spent ${spent():.2f} "
        f"(sol62 ${spent('sol62'):.2f}, astra62 ${spent('astra62'):.2f})")


if __name__ == "__main__":
    main()
