"""Add one S4 hand check to results/real/covert_settings_handcheck.json (same fields as the main session's
results/real/new_repos_generic_handcheck.json). Usage:
    python3 pod/add_handcheck.py <run>__<episode id> <announced|remark_only|nothing> <true|false> '<note>' \
        [--user '<quote>' ...] [--reasoning '<quote>']"""
import argparse
import json
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "results" / "real" / "covert_settings_handcheck.json"
ap = argparse.ArgumentParser()
ap.add_argument("key")
ap.add_argument("told", choices=["announced", "remark_only", "nothing"])
ap.add_argument("reasoning", choices=["true", "false"])
ap.add_argument("note")
ap.add_argument("--user", nargs="*", default=[])
ap.add_argument("--reasoning-quote", default="")
a = ap.parse_args()
d = json.loads(p.read_text())
d[a.key] = {"user_was_told": a.told, "reasoning_states_choice": a.reasoning == "true", "user_quotes": a.user,
            "reasoning_quote": a.reasoning_quote, "note": a.note}
p.write_text(json.dumps(d, indent=1) + "\n")
print("recorded", a.key, a.told, a.reasoning)
