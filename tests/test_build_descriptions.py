"""The descriptions page shows every description and README text of the task files word for word."""
import html
import json
import re
from pathlib import Path

from sfe.build_descriptions import ROOT, build

norm = lambda s: re.sub(r"\s+", " ", s).strip()


def test_every_task_file_text_is_on_the_page_word_for_word():
    page = norm(html.unescape(re.sub(r"<[^>]+>", " ", build())))
    files = sorted(list((ROOT / "real_tasks").glob("*/task.json")) + list((ROOT / "real_tasks_new").glob("*/task.json")))
    assert files
    n = 0
    for f in files:
        for key, v in json.loads(f.read_text())["framings"].items():
            for field in ("context", "note"):
                text = norm(v.get(field) or "")
                if text:
                    n += 1
                    assert text in page, (f.parent.name, key, field)
    for f in sorted((ROOT / "tasks").glob("*/framings/*.json")):
        blurb = norm(json.loads(f.read_text()).get("TASK_BLURB", ""))
        if blurb:
            n += 1
            assert blurb in page, (f.parent.parent.name, f.stem)
    assert n > 100


def test_no_private_builder_is_imported():
    src = (ROOT / "sfe" / "build_descriptions.py").read_text()
    named = set(re.findall(r"\bsfe\.(\w+)", src))        # every sfe module it names is in this repository
    assert named and all((ROOT / "sfe" / f"{m}.py").exists() for m in named), named
