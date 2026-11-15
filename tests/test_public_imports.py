"""No published module under sfe/ imports a module that is left out of the public copy (15 Nov 2026).

The release tests build every public page from a clean copy without the unpublished files, so a published builder that
imports one of them cannot run there. The first test reads the exclusion list from scripts/prepublish_check.py, which is not
published itself, and is skipped where that script is absent; the second runs everywhere."""
import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "prepublish_check.py"
WRITEUP_BUILDER = "build_" + "blog"          # the unpublished write-up builder (spelt in two parts: this file is published)
NAMED = ["sfe/build_keyresults.py", "sfe/build_datasets.py", "sfe/build_followup.py", "sfe/build_onepage.py", "sfe/panel_counts.py",
         "sfe/review_counts.py", "sfe/core_code.py"]


def imported_sfe_modules(path: Path) -> set[str]:
    """Every sfe module a file imports, at any depth (`import sfe.x`, `from sfe.x import y`, `from sfe import x`)."""
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[1] for a in node.names if a.name.startswith("sfe.")}
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "sfe":
                out |= {a.name for a in node.names}
            elif node.module.startswith("sfe."):
                out.add(node.module.split(".")[1])
    return out


@pytest.mark.skipif(not SCRIPT.exists(), reason="scripts/prepublish_check.py is not in the public copy")
def test_no_published_module_imports_an_unpublished_one():
    spec = importlib.util.spec_from_file_location("prepublish_check", SCRIPT)
    ppc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ppc)                 # defines constants and functions only; it runs nothing at import
    bad = []
    for f in sorted((ROOT / "sfe").glob("*.py")):
        rel = f"sfe/{f.name}"
        if ppc.excluded(rel):
            continue
        for mod in sorted(imported_sfe_modules(f)):
            if ppc.excluded(f"sfe/{mod}.py"):
                bad.append(f"{rel} imports sfe.{mod}, which is left out of the public copy")
    assert not bad, "\n".join(bad)


def test_the_public_builders_do_not_name_the_writeup_builder():
    for rel in NAMED:
        p = ROOT / rel
        assert p.exists(), rel
        assert WRITEUP_BUILDER not in p.read_text(), rel
        assert WRITEUP_BUILDER not in imported_sfe_modules(p), rel
