"""Screen real-repository episodes for things that can spoil them, from the saved tool calls and their results, and
write the list of episodes to leave out of the analysis.

Until 11 Nov 2026 the machines were not offline and every episode on a machine shared /tmp and one user account, so an
agent could (and a few did) download the project's later release, which contains the held-back fixes the checklist is
partly built from, or open files another episode left behind.

An episode is EXCLUDED when any of these holds:
  fetched            a `pip download` / `pip index` / `git clone|fetch|pull|ls-remote` command succeeded
  read_download      it opened a folder under /tmp that holds a copy downloaded by ANOTHER episode
  opened_other_ws    one of its commands names another episode's checkout (e.g. `diff -r <mine> <theirs>`)
Recorded but not excluded (exposure, with no sign that anything was learned from it):
  saw_other_ws       a tool result lists another episode's checkout (a `find /` or `ps` listing)
  reached_network    some other network-looking command did not fail (e.g. a connectivity check that printed "online")
  tmp_shared_names   it used a name directly under /tmp that an overlapping episode on the same machine also used, with
                     one of the two writing it and the other using it in a separate call

    python -m sfe.real_screen            # writes results/real/screen.json and results/real/exclusions.json
"""
from __future__ import annotations

import glob
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from sfe.config import RESULTS_DIR, RUNS_DIR

FETCH_CMD = re.compile(r"\bpip3?\s+(download|index)\b|\buv\s+pip\s+download\b|\bgit\s+(clone|fetch|pull|ls-remote|remote\s+update)\b")
FETCH_OK = re.compile(r"Successfully downloaded|Saved /|Saved \./|Available versions:|Receiving objects|Cloning into '|\brefs/heads/")
NET_CMD = re.compile(r"urllib\.request|urlopen|requests\.(get|post)|httpx\.|\bcurl\b|\bwget\b|https?://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|example\.)")
NET_FAIL = re.compile(r"blocked|not permitted|timed out|Temporary failure|Name or service not known|Connection refused|offline|"
                      r"Network is unreachable|No matching distribution|Could not find a version|ERROR: command|URLError|ConnectionError|Traceback", re.I)
READ_ONLY = re.compile(r"^\s*(grep|rg|sed|cat|head|tail|git (diff|status|show|log))\b")
WS = re.compile(r"/w[0-9a-f]{10}\b")                                   # an episode's checkout folder
TMP = re.compile(r"(?<![\w.])/tmp/(?!w[0-9a-f]{10}\b)([\w.\-]+)")       # a name directly under /tmp
UNPACK = re.compile(r"\.whl|\.tar\.gz|unzip|zipfile|\bpip3?\s+download\b")


def _calls(r: dict):
    """(message index, command text, result text) for every shell command and file-tool call, in order."""
    msgs = r["messages"]
    results = {m.get("tool_call_id"): str(m.get("content")) for m in msgs if m.get("role") == "tool"}
    for i, m in enumerate(msgs):
        for tc in m.get("tool_calls") or []:
            raw = tc["function"].get("arguments") or ""
            try:
                a = json.loads(raw)
            except json.JSONDecodeError:
                a = {"command": raw}
            if not isinstance(a, dict):
                a = {"command": raw}
            yield i, f"{a.get('command') or ''} {a.get('path') or ''}".strip(), results.get(tc["id"], ""), tc["function"]["name"]


def own_workspace(r: dict) -> str | None:
    """The episode's own checkout folder: the one pytest reports as rootdir if any, else the one named most in results."""
    text = " ".join(str(m.get("content")) for m in r["messages"] if m.get("role") == "tool")
    m = re.search(r"rootdir: \S*?(/w[0-9a-f]{10})\b", text)
    if m:
        return m.group(1)
    c = Counter(WS.findall(text))
    return c.most_common(1)[0][0] if c else None


def screen(r: dict) -> dict:
    own = own_workspace(r)
    fetched, reached, download_dirs, opened_other, saw_other = [], [], set(), [], set()
    tmp_written, tmp_used_later = set(), set()
    seen_fetch = False
    for i, cmd, res, tool in _calls(r):
        names = list(dict.fromkeys(TMP.findall(cmd)))
        if tool == "run_command":
            if FETCH_CMD.search(cmd) and not READ_ONLY.search(cmd) and FETCH_OK.search(res[:6000]):
                fetched.append({"m": i, "command": cmd[:260], "result": res[:200]})
                seen_fetch = True
            elif NET_CMD.search(cmd) and not READ_ONLY.search(cmd) and res.startswith("exit code 0") and not NET_FAIL.search(res[:2000]):
                reached.append({"m": i, "command": cmd[:200], "result": res[:120]})
            if seen_fetch and UNPACK.search(cmd):
                download_dirs.update(names)
            others = [w for w in set(WS.findall(cmd)) if own and w != own]
            if others:
                opened_other.append({"m": i, "command": cmd[:260]})
            for n in names:
                writes = re.search(rf"(>>?|tee( -a)?|-o|-d|mkdir( -p)?|cp [^;&|]*|mv [^;&|]*)\s*/tmp/{re.escape(n)}\b", cmd)
                (tmp_written if writes else tmp_used_later).add(n)
        for w in set(WS.findall(res)):
            if own and w != own:
                saw_other.add(w)
    return {"own_workspace": own, "fetched": fetched, "reached_network": reached, "download_dirs": sorted(download_dirs),
            "opened_other_ws": opened_other, "saw_other_ws": len(saw_other),
            "tmp_written": sorted(tmp_written), "tmp_used_in_a_separate_call": sorted(tmp_used_later - tmp_written) + sorted(tmp_used_later & tmp_written)}


def main() -> None:
    out, eps = {}, {}
    for f in sorted(glob.glob(f"{RUNS_DIR}/real_*/episodes/*.json") + glob.glob(f"{RUNS_DIR}/real2_*/episodes/*.json")
                    + glob.glob(f"{RUNS_DIR}/real3_*/episodes/*.json")):
        r = json.loads(Path(f).read_text())
        if r.get("stub") or not r.get("complete"):
            continue
        key = f"{Path(f).parts[-3]}__{r['id']}"
        s = screen(r)
        s.update({k: r["spec"][k] for k in ("model", "task", "framing", "seed")})
        s["platform"] = "rented Linux machine" if "Linux" in str(r.get("platform")) else "laptop"
        s["started"], s["finished"] = r.get("started"), r.get("finished")
        s["own_user"] = bool((r.get("isolation") or {}).get("own_unix_user"))    # ran as its own Unix user: others cannot read its /tmp files
        out[key], eps[key] = s, r

    # Folders holding a downloaded copy, per machine, with the window in which they can have existed.
    downloads = [(s["platform"], d, s["started"], k) for k, s in out.items() for d in s["download_dirs"]]
    for key, s in out.items():
        hits = []
        for plat, d, t0, owner in downloads:
            if owner == key or plat != s["platform"] or s["finished"] is None or t0 is None or s["finished"] < t0:
                continue
            for i, cmd, res, tool in _calls(eps[key]):
                if re.search(rf"/tmp/{re.escape(d)}(/|\s|$|\")", cmd) and not re.search(r"No such file|cannot access", res[:300]):
                    hits.append({"m": i, "folder": f"/tmp/{d}", "downloaded_by": owner, "command": cmd[:220]})
                    break
        s["read_download"] = hits

    # Names under /tmp shared by two episodes that overlapped in time on one machine, one writing and the other using.
    by_name = defaultdict(list)
    for key, s in out.items():
        for n in set(s["tmp_written"]) | set(s["tmp_used_in_a_separate_call"]):
            by_name[(s["platform"], n)].append(key)
    pairs = []
    for (plat, n), keys in by_name.items():
        for a in range(len(keys)):
            for b in range(a + 1, len(keys)):
                x, y = out[keys[a]], out[keys[b]]
                if None in (x["started"], x["finished"], y["started"], y["finished"]) or (x["own_user"] and y["own_user"]):
                    continue
                if x["started"] < y["finished"] and y["started"] < x["finished"]:
                    risky = (n in x["tmp_written"] and n in y["tmp_used_in_a_separate_call"]) or \
                            (n in y["tmp_written"] and n in x["tmp_used_in_a_separate_call"])
                    pairs.append({"name": f"/tmp/{n}", "a": keys[a], "b": keys[b], "one_wrote_other_used_separately": risky})
    exposed = Counter()
    for p in pairs:
        if p["one_wrote_other_used_separately"]:
            exposed[p["a"]] += 1
            exposed[p["b"]] += 1

    excl = {}
    for key, s in out.items():
        s["tmp_shared_names"] = exposed.get(key, 0)
        why = []
        if s["fetched"]:
            why.append("downloaded from the internet: " + s["fetched"][0]["command"][:110])
        if s["read_download"]:
            why.append(f"opened {s['read_download'][0]['folder']}, a copy downloaded by {s['read_download'][0]['downloaded_by']}")
        if s["opened_other_ws"]:
            why.append("a command names another episode's checkout: " + s["opened_other_ws"][0]["command"][:110])
        s["exclude"] = bool(why)
        if why:
            excl[key] = {"model": s["model"], "task": s["task"], "framing": s["framing"], "seed": s["seed"],
                         "platform": s["platform"], "why": why}

    d = RESULTS_DIR / "real"
    (d / "screen.json").write_text(json.dumps(out, indent=1))
    (d / "exclusions.json").write_text(json.dumps(excl, indent=1))
    (d / "screen_tmp_pairs.json").write_text(json.dumps(pairs, indent=1))
    print(f"{len(out)} episodes screened; EXCLUDED: {len(excl)}")
    for k, e in excl.items():
        print(f"  {k} [{e['platform']}]\n      " + "\n      ".join(e["why"]))
    cnt = lambda f: sum(bool(f(s)) for s in out.values())                                               # noqa: E731
    print("downloaded from the internet:", cnt(lambda s: s["fetched"]), dict(Counter(s["model"] for s in out.values() if s["fetched"])))
    print("opened a copy downloaded by another episode:", cnt(lambda s: s["read_download"]))
    print("a command names another episode's checkout:", cnt(lambda s: s["opened_other_ws"]))
    print("not excluded - another checkout appeared in a listing:", cnt(lambda s: s["saw_other_ws"] and not s["exclude"]),
          dict(Counter((s["model"], s["platform"]) for s in out.values() if s["saw_other_ws"] and not s["exclude"])))
    print("not excluded - another network command did not fail:", cnt(lambda s: s["reached_network"] and not s["exclude"]))
    for k, s in out.items():
        if s["reached_network"] and not s["exclude"]:
            print(f"      {k}: {s['reached_network'][0]['command'][:110]!r} -> {s['reached_network'][0]['result'][:60]!r}")
    print(f"pairs of overlapping episodes sharing a /tmp name: {len(pairs)}; with one writing and the other using it in a separate "
          f"call: {sum(p['one_wrote_other_used_separately'] for p in pairs)} (episodes involved: {len(exposed)})")


if __name__ == "__main__":
    main()
