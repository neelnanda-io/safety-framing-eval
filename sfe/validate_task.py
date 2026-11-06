"""Validate a paired task before it is used.

For each framing: the baseline (template) must pass its public tests and FAIL every hidden rubric test
(otherwise an item is free); the reference solution must pass the public tests and EVERY hidden test
(otherwise an item is unachievable). The two framings must render to the same file structure with the
same line counts, which is what "identical apart from names/comments/docs" means operationally.

    python -m sfe.validate_task clf_eval            # one task
    python -m sfe.validate_task all                 # every task
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from sfe.grade import grade_hidden, run_public_tests
from sfe.render import list_tasks, load_task, render_hidden_tests, render_solution, render_task, render_text
from sfe.sandbox import Sandbox, ensure_bin_dir


def validate(task_id: str, keep: bool = False) -> bool:
    task = load_task(task_id)
    tmp = Path(tempfile.mkdtemp(prefix=f"sfe_validate_{task_id}_"))
    bin_dir = ensure_bin_dir(tmp)
    ok = True
    shapes = {}
    print(f"== {task_id}: {len(task.rubric)} rubric items, boundary={task.meta.get('boundary')}")
    for framing in ("safety", "capabilities", "neutral"):
        hidden = render_hidden_tests(task, framing, tmp / f"hidden_{framing}")
        base = render_task(task, framing, tmp / f"base_{framing}")
        shapes[framing] = {str(p.relative_to(base)): (len(p.read_bytes().splitlines()))
                           for p in base.rglob("*") if p.is_file()}
        sb = Sandbox(base, bin_dir)
        pub = run_public_tests(sb, task.public_test_cmd)
        g = grade_hidden(sb, hidden, task.rubric)
        free = [k for k, v in g["items"].items() if v]
        print(f"  [{framing}] baseline: public tests {'PASS' if pub['passed'] else 'FAIL'}; "
              f"hidden {g['n_pass']}/{g['n_total']} pass (want 0); collected {g['n_collected']}")
        if not pub["passed"]:
            ok = False; print("    public tests output:", pub["output_tail"][-800:])
        if free:
            ok = False; print(f"    FREE rubric items on baseline: {free}")
        if g["n_collected"] < g["n_total"]:
            ok = False; print(f"    hidden suite collected {g['n_collected']} < {g['n_total']} tests; raw:",
                              g["raw_tail"][-800:])
        sol = render_solution(task, framing, tmp / f"sol_{framing}")
        sbs = Sandbox(sol, bin_dir)
        pub_s = run_public_tests(sbs, task.public_test_cmd)
        gs = grade_hidden(sbs, hidden, task.rubric)
        unach = [k for k, v in gs["items"].items() if not v]
        print(f"  [{framing}] solution: public tests {'PASS' if pub_s['passed'] else 'FAIL'}; "
              f"hidden {gs['n_pass']}/{gs['n_total']} pass (want all)")
        if not pub_s["passed"]:
            ok = False; print("    public tests output:", pub_s["output_tail"][-800:])
        if unach:
            ok = False; print(f"    UNACHIEVABLE rubric items with solution: {unach}"); print(gs["raw_tail"][-1200:])
    # structural identity between the two framings: same paths (modulo tokens) and same line counts
    s_map, c_map, n_map = task.framings["safety"], task.framings["capabilities"], task.framings["neutral"]
    tmpl = task.path / "template"
    for p in tmpl.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(tmpl))
        rs, rc, rn = render_text(rel, s_map), render_text(rel, c_map), render_text(rel, n_map)
        counts = (shapes["safety"].get(rs), shapes["capabilities"].get(rc), shapes["neutral"].get(rn))
        if len(set(counts)) != 1:
            ok = False; print(f"  line-count mismatch for {rel}: safety/capabilities/neutral = {counts}")
    # the blurbs should be about the same length
    ls, lc, ln = (len(m["TASK_BLURB"].split()) for m in (s_map, c_map, n_map))
    if abs(ls - lc) > max(8, 0.2 * max(ls, lc)):
        ok = False; print(f"  blurb length mismatch: safety {ls} words vs capabilities {lc} words")
    if abs(ln - (ls + lc) / 2) > max(10, 0.25 * max(ls, lc)):
        ok = False; print(f"  neutral blurb length {ln} words is far from safety {ls} / capabilities {lc}")
    print(f"  blurb words: safety {ls}, capabilities {lc}, neutral {ln}")
    print(f"== {task_id}: {'OK' if ok else 'FAILED'}")
    if keep:
        print(f"  renders kept in {tmp}")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    keep = "--keep" in sys.argv
    ids = list_tasks() if (not args or args == ["all"]) else args
    results = {t: validate(t, keep) for t in ids}
    bad = [t for t, v in results.items() if not v]
    print("\nSUMMARY:", ", ".join(f"{t}={'OK' if v else 'FAIL'}" for t, v in results.items()))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
