"""Build the public data bundle: runs/<run>/episodes/*.json for every run listed in docs/RUNS.md, with absolute paths
from the original machine replaced by "<repo>", as episodes.tar.gz.

    python scripts/pack_data.py --out dist/episodes.tar.gz
"""
from __future__ import annotations

import argparse
import io
import re
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ABS = re.compile(r"/(?:Users|home)/[^/\s\"']+/Code/safety-framing-eval")
VENV = re.compile(r"/(?:Users|home)/[^/\s\"']+/\.venvs/[^/\s\"']+")
HOME = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]*")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?:gmail|anthropic|openai)\.com")


def runs_listed() -> list[str]:
    text = (ROOT / "docs" / "RUNS.md").read_text()
    return re.findall(r"^\| `([a-z0-9_]+)` \|", text, re.M)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(ROOT / "dist" / "episodes.tar.gz"))
    a = ap.parse_args(); out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    runs = runs_listed(); n = 0
    with tarfile.open(out, "w:gz", compresslevel=9) as tar:
        for run in runs:
            for f in sorted((ROOT / "runs" / run / "episodes").glob("*.json")):
                data = ABS.sub("<repo>", f.read_text())
                data = VENV.sub("<venv>", data)
                data = HOME.sub("<home>", data)          # any remaining /Users/<name> or /home/<name>, incl. truncated ones
                data = EMAIL.sub("<email>", data)        # agents that ran `git log` saw the project's commit authors
                b = data.encode()
                info = tarfile.TarInfo(f"runs/{run}/episodes/{f.name}"); info.size = len(b)
                tar.addfile(info, io.BytesIO(b)); n += 1
    print(f"{n} episodes from {len(runs)} runs -> {out} ({out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
