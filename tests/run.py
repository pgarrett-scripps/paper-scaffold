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

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "audio"))

import readability  # noqa: E402
import extract_prose  # noqa: E402

# Words that must never appear in extracted prose. Each marks a construct that
# should have been dropped whole rather than partially stripped.
FORBIDDEN = [
    "fixturecaption",  # a figure caption leaked
    "refn",            # a cross-reference call leaked
    "#link",           # a link call leaked
    "sym.",            # a symbol token leaked
    "lovelace1843",    # a citation key leaked
    "typst.app",       # a link URL leaked
]


def extract(src: str) -> dict[str, str]:
    body = readability.slice_body(src)
    return {
        "readability": readability.clean(body),
        "narration": extract_prose.clean(extract_prose.extract_body(src)),
    }


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
        print("error: typstyle not found (cargo install typstyle)", file=sys.stderr)
        return 2

    src = FIXTURE.read_text()
    flat = extract(src)
    wrapped = extract(reflowed(src))

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

    ok &= structural_cases()

    if ok:
        print(f"  all extractor checks pass ({len(flat)} outputs, "
              f"reflow-invariant, no leaks) + structural cases")
    return 0 if ok else 1


def structural_cases() -> bool:
    """Table-driven cases for prose_check's source-level checks.

    These are pure functions over a string, so they get real cases rather than a
    golden file. The caption case is the one worth keeping: a figure that
    cross-references a later figure from inside its own caption must not count as
    the text having reached that figure.
    """
    import prose_check as pc

    fig = '#figure(image("x.png"), caption: [{cap}]) <{label}>'
    cases = [
        ("in order", f"Cites @fig:a then @fig:b.\n"
                     f"{fig.format(cap='c', label='fig:a')}\n"
                     f"{fig.format(cap='c', label='fig:b')}", 0),
        ("out of order", f"Cites @fig:b then @fig:a.\n"
                         f"{fig.format(cap='c', label='fig:a')}\n"
                         f"{fig.format(cap='c', label='fig:b')}", 1),
        ("caption ref does not count",
         f"{fig.format(cap='see @fig:b', label='fig:a')}\n"
         f"{fig.format(cap='c', label='fig:b')}\n"
         f"Cites @fig:a then @fig:b.", 0),
    ]
    ok = True
    for name, src, want in cases:
        got = len(pc.check_reference_order({"t": src}))
        if got != want:
            print(f"  reference order [{name}]: expected {want} finding(s), got {got}")
            ok = False

    # A construct removed from between two identical words must not fabricate a
    # repetition, and a real repetition must still be caught.
    import readability
    dup_cases = [
        ("math between duplicates", 'the human and $N_h$ and yeast counts', 0),
        ("citation between duplicates", "reported and @smith2020 and confirmed", 0),
        ("genuine doubled word", "this is is a real repetition", 1),
    ]
    for name, src, want in dup_cases:
        errs, _ = pc.check("t", readability.clean(src),
                           readability.clean(pc.no_code(src)),
                           readability.clean(src, gap=pc.GAP))
        got = len([e for e in errs if "doubled word" in e])
        if got != want:
            print(f"  doubled word [{name}]: expected {want}, got {got}")
            ok = False

    # A citation key must not swallow a colon that is punctuation.
    import typst_prose
    if re.findall(typst_prose.CITE, "@smith2020: the counts") != ["@smith2020"]:
        print("  citation pattern: swallowed a trailing colon")
        ok = False
    if re.findall(typst_prose.CITE, "See @sec:methods.") != ["@sec:methods"]:
        print("  citation pattern: dropped a real key suffix")
        ok = False

    # An uncited figure is an error; a cited one is not.
    uncited = len(pc.check_structure({"t": fig.format(cap="c", label="fig:x")})[0])
    cited = len(pc.check_structure(
        {"t": "See @fig:x.\n" + fig.format(cap="c", label="fig:x")})[0])
    if (uncited, cited) != (1, 0):
        print(f"  uncited-figure check: expected (1, 0), got ({uncited}, {cited})")
        ok = False
    return ok


if __name__ == "__main__":
    raise SystemExit(main())
