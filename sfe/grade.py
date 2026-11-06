"""Hidden-rubric grading: one pytest function per rubric item, run against the sandbox after each turn."""
from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from sfe.sandbox import HIDDEN_PREFIX, Sandbox


def run_pytest_junit(sandbox_root: Path, target: str, env: dict, timeout: int = 240) -> tuple[dict[str, str], str]:
    """Run pytest on `target` (relative to sandbox) and return {test_name: outcome}, raw output."""
    junit = sandbox_root / f".tmp/junit_{uuid.uuid4().hex}.xml"
    junit.parent.mkdir(exist_ok=True)
    cmd = [sys.executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider", "--junitxml", str(junit),
           "-o", "junit_family=xunit2", "--continue-on-collection-errors"]
    try:
        r = subprocess.run(cmd, cwd=sandbox_root, env=env, capture_output=True, text=True, timeout=timeout,
                           errors="replace")
        raw = (r.stdout + "\n" + r.stderr)[-6000:]
    except subprocess.TimeoutExpired:
        return {}, f"TIMEOUT after {timeout}s"
    results: dict[str, str] = {}
    if junit.exists():
        try:
            root = ET.parse(junit).getroot()
            for tc in root.iter("testcase"):
                name = tc.get("name", "")
                outcome = "passed"
                for child in tc:
                    if child.tag in ("failure", "error"):
                        outcome = "failed"
                    elif child.tag == "skipped":
                        outcome = "skipped"
                results[name] = outcome
        except ET.ParseError:
            pass
        junit.unlink(missing_ok=True)
    return results, raw


def grade_hidden(sb: Sandbox, hidden_src: Path, rubric: list[dict]) -> dict:
    """Copy the rendered hidden tests into the sandbox under a hidden name, run them, remove them."""
    hidden_dir = sb.root / f"{HIDDEN_PREFIX}{uuid.uuid4().hex[:8]}"
    shutil.copytree(hidden_src, hidden_dir)
    try:
        results, raw = run_pytest_junit(sb.root, hidden_dir.name, sb._env())
    finally:
        shutil.rmtree(hidden_dir, ignore_errors=True)
        for pc in sb.root.rglob("__pycache__"):
            shutil.rmtree(pc, ignore_errors=True)
    items = {}
    for r in rubric:
        items[r["id"]] = results.get(r["test"], "missing") == "passed"
    n_pass = sum(items.values())
    return {"n_pass": n_pass, "n_total": len(rubric), "frac": n_pass / max(1, len(rubric)),
            "items": items, "raw_tail": raw[-1500:], "n_collected": len(results)}


def run_public_tests(sb: Sandbox, cmd: str) -> dict:
    out = sb.run_command(cmd, timeout=240)
    return {"passed": out.startswith("exit code 0"), "output_tail": out[-1500:]}
