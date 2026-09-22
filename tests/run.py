#!/usr/bin/env python3
"""Assert the prose extractors still handle every construct in tests/fixture.typ.

Why this exists as its own fixture rather than relying on the manuscript: the
placeholder prose in paper.typ is deleted the moment someone starts writing, so
anything that depended on it for coverage would be tested exactly once and never
again. The fixture is never part of the manuscript, so it stays.

Two properties are checked:

  1. The extracted prose matches tests/expected/. A golden-file diff catches a
     regex that quietly starts eating or leaking a construct.
  2. Reflowing the fixture with typstyle changes neither result. This is the
     failure mode that actually happened: several patterns assumed a construct
     sits on one line, which --wrap-text stops being true.

Usage:
    python3 tests/run.py            # check
    python3 tests/run.py --update   # rewrite the golden files (review the diff!)
"""
from __future__ import annotations

import difflib
import importlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIXTURE = HERE / "fixture.typ"
EXPECTED = HERE / "expected"

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "audio"))

import readability  # noqa: E402

# audio/ is optional: a project that wants no narration deletes the directory.
# The extractor tests that do not involve it must still run, so this is a soft
# import rather than a hard one. Everything narration-specific is then skipped,
# and the run says so instead of quietly testing half of what it claims to.
try:
    import extract_prose  # noqa: E402
except ImportError:
    extract_prose = None

# Words that must never appear in extracted prose. Each marks a construct that
# should have been dropped whole rather than partially stripped.
FORBIDDEN = [
    "fixturecaption",  # a figure caption leaked
    "refn",            # the bare-number cross-reference helper leaked
    "#ref",            # Typst's own #ref( call leaked. Matched with the "#" so
                       # ordinary words like "reference" do not trip it.
    "#link",           # a link call leaked
    "sym.",            # a symbol token leaked
    "lovelace1843",    # a citation key leaked
    "typst.app",       # a link URL leaked
    "#s(",             # a generated number was left as a call instead of resolved
    "#n(",             # ditto for the raw-value helper
    "#lit(",           # a vouched literal must resolve to its text, not leak
    "#todo(",          # a note to self must be stripped, not counted or spoken
    "lab notebook",    # nor may the note's TEXT leak into count or narration
    "fixturebibliography",  # a reference list's own title leaked
    "bibliographyx",   # the SI's Alexandria list leaked as a call
]


# Every case module under tests/. Each one exports `run_cases() -> bool`,
# owns its own fixtures, and is runnable on its own while you iterate on it:
#
#     uv run python tests/stats_cases.py
#
# This list is the only place that has to change to add one. It used to be a
# chain of `ok &= <name>_cases()` calls at the end of structural_cases(), where
# thirteen unrelated suites ran as a side effect of one named for prose rules --
# a failure in the Word export was reported under "structural cases", and adding
# a suite meant editing a function that had nothing to do with it.
CASE_MODULES = (
    "prose_cases",            # the prose checker: rules, boundaries, suppression
    "bibliography_cases",     # references.bib, and the SI's own list
    "asset_cases",            # assets.json and the files it describes
    "stats_cases",            # stats.json: resolution, guards, the checker
    "stats_ownership_cases",  # who owns which field of a stats.json entry
    "resolver_cases",         # the manuscript as plain Typst, for pandoc
    "export_cases",           # the pandoc export path
    "adoption_cases",         # migrating files whose analysis is gone
    "new_paper_cases",        # scripts/new-paper.sh
    "hardening",              # concurrency, permissions, malformed state
    "review_cases",           # the review export
    "document_cases",         # manuscript.toml projects
    "code_cases",             # native code through every output
    "slide_cases",            # slide decks
    "journal_cases",          # journal profiles and the graphical abstract
    "upgrade_plan_cases",     # tools/upgrade_plan.py against a throwaway scaffold
    "submission_cases",       # the journal upload set in submission/
)


def extract(src: str) -> dict[str, str]:
    """Both extractions of the fixture, resolved against the TEST-OWNED stats.

    The fixture's `#s()` ids used to resolve against the manuscript's
    stats.json -- coupling the permanent fixture to the analysis it exists to
    outlive, and breaking `just test` the day a real gen_stats.py stopped
    declaring the scaffold's demo ids. tests/fixture-stats.json is owned by
    tests/ and pins those ids for the life of the project. The fallback keeps a
    manuscript whose fixture was adapted to its own ids (and has no
    fixture-stats file yet) working as before.
    """
    import typst_prose
    fixture_stats = HERE / "fixture-stats.json"
    saved = typst_prose.STATS_JSON
    if fixture_stats.is_file():
        typst_prose.STATS_JSON = fixture_stats
    try:
        body = readability.slice_body(src)
        out = {"readability": readability.clean(body)}
        if extract_prose is not None:
            out["narration"] = extract_prose.clean(extract_prose.extract_body(src))
    finally:
        typst_prose.STATS_JSON = saved
    return out


def reflowed(src: str) -> str:
    """The fixture as `just fmt` would leave it."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "fixture.typ"
        p.write_text(src)
        subprocess.run(
            ["typstyle", "--inplace", "--line-width", "80", "--wrap-text", str(p)],
            check=True, capture_output=True,
        )
        return p.read_text()


def report(name: str, want: str, got: str) -> bool:
    if want == got:
        return True
    print(f"  {name}: DIFFERS")
    for line in list(difflib.unified_diff(
        want.split(), got.split(), "expected", "actual", lineterm="", n=3
    ))[:40]:
        print(f"    {line}")
    return False


def main() -> int:
    if not shutil.which("typstyle"):
        print("note: typstyle absent; reflow checks skipped, ordinary tests still run")

    src = FIXTURE.read_text()
    flat = extract(src)
    wrapped = extract(reflowed(src)) if shutil.which("typstyle") else flat

    if "--update" in sys.argv:
        EXPECTED.mkdir(exist_ok=True)
        for name, text in flat.items():
            (EXPECTED / f"{name}.txt").write_text(text + "\n")
        print(f"wrote {len(flat)} golden files to {EXPECTED.relative_to(ROOT)}")
        print("review the diff before committing")
        return 0

    ok = True

    # 1. golden-file comparison
    for name, got in flat.items():
        f = EXPECTED / f"{name}.txt"
        if not f.exists():
            print(f"  {name}: no golden file; run `just test-update`")
            ok = False
            continue
        ok &= report(name, f.read_text().rstrip("\n"), got)

    # 2. reflow invariance -- the property that broke in practice
    for name in flat:
        if flat[name] != wrapped[name]:
            print(f"  {name}: CHANGED BY REFLOW")
            for line in list(difflib.unified_diff(
                flat[name].split(), wrapped[name].split(),
                "before-reflow", "after-reflow", lineterm="", n=3
            ))[:40]:
                print(f"    {line}")
            ok = False

    # 3. nothing that should have been dropped leaked through
    for name, got in flat.items():
        for bad in FORBIDDEN:
            if bad in got:
                hit = re.search(rf".{{0,50}}{re.escape(bad)}.{{0,50}}", got)
                print(f"  {name}: LEAKED {bad!r} -- ...{hit.group(0)}...")
                ok = False

    # An unmapped symbol token must be recorded, not silently swallowed. The
    # FORBIDDEN sweep above only proves it never reaches the narration.
    if extract_prose is not None and "#sym.prec" not in extract_prose.UNMAPPED:
        print("  unmapped symbol tokens are not being recorded in UNMAPPED")
        ok = False

    # Named, so a failure says which suite it came from. Every module prints
    # its own detail; this only attributes it.
    for name in CASE_MODULES:
        if not importlib.import_module(name).run_cases():
            print(f"  {name}: FAILED")
            ok = False

    if ok:
        note = "" if extract_prose is not None else ", no audio/ so narration skipped"
        invariant = "reflow-invariant" if shutil.which("typstyle") else "reflow skipped"
        print(f"  all extractor checks pass ({len(flat)} outputs, "
              f"{invariant}, no leaks) + {len(CASE_MODULES)} case modules{note}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
