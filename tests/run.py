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

sys.path.insert(0, str(ROOT / "tools"))
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
]


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

    # An unmapped symbol token must be recorded, not silently swallowed. The
    # FORBIDDEN sweep above only proves it never reaches the narration.
    if extract_prose is not None and "#sym.prec" not in extract_prose.UNMAPPED:
        print("  unmapped symbol tokens are not being recorded in UNMAPPED")
        ok = False

    ok &= structural_cases()

    if ok:
        note = "" if extract_prose is not None else ", no audio/ so narration skipped"
        print(f"  all extractor checks pass ({len(flat)} outputs, "
              f"reflow-invariant, no leaks) + structural cases{note}")
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
        # A reference site must not be mistaken for a definition. `#ref(<fig:b>)`
        # contains the same `<fig:b>` token a definition does, so a bare-label
        # scan numbered each figure by its LAST occurrence anywhere in the file.
        # Here fig:a is mentioned again after fig:b, which under that scan makes
        # fig:a "Figure 5" and fig:b "Figure 4", and this correctly ordered text
        # is reported as out of order. Real manuscripts cite figures more than
        # once, so this is the normal case, not a corner one.
        ("#ref sites are not definitions",
         f"{fig.format(cap='c', label='fig:a')}\n"
         f"{fig.format(cap='c', label='fig:b')}\n"
         f"Cites #ref(<fig:a>), then #ref(<fig:b>), then #ref(<fig:a>) again.", 0),
        # A `tab:`-prefixed table is a float like any other. A checker that knew
        # only `tbl:` exempted every table in a real manuscript while reporting
        # clean.
        ("tab: prefix is recognized",
         f"Cites @tab:b then @tab:a.\n"
         f"{fig.format(cap='c', label='tab:a')}\n"
         f"{fig.format(cap='c', label='tab:b')}", 1),
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
        # Inline code is unwrapped to a bare word for counting, so under the
        # sentinel gap it has to be dropped instead, or its last token collides
        # with the word after it.
        ("code metavariable", "Run it with `--proteome-k K` first.", 0),
        ("code between duplicates", "defined in `f()` in `g.rs` today", 0),
        ("adjacent citations", "a database @smith2020 @jones2021 exists", 0),
        ("genuine doubled word", "this is is a real repetition", 1),
        ("legitimate double", "the result that that model gives is fine", 0),
    ]
    for name, src, want in dup_cases:
        found = pc.check("t", readability.clean(src),
                         readability.clean(pc.no_code(src)),
                         readability.clean(src, gap=pc.GAP))
        got = len([f for f in found if f.rule == "doubled-word"])
        if got != want:
            print(f"  doubled word [{name}]: expected {want}, got {got}")
            ok = False

    # Misspellings, from codespell's dictionary. The compound cases are the ones
    # that matter: codespell's list holds fragments that are wrong only when
    # standing alone, so splitting a hyphenated word and matching its prefix
    # invents a finding codespell itself does not make.
    spell_cases = [
        ("a plain typo", "The measurment was taken.", ["measurment"]),
        ("several", "We recieved teh data.", ["recieved", "teh"]),
        ("correct prose", "The measurement was taken.", []),
        ("fragment inside a compound", "A mis-transferred arm.", []),
        ("compound is not exempt in general", "A seperate-but-equal split.", []),
        ("case insensitive", "Measurment matters.", ["Measurment"]),
    ]
    for name, src, want in spell_cases:
        got = [f.subject for f in pc.check("t", src, src, src)
               if f.rule == "misspelling"]
        if got != want:
            print(f"  misspelling [{name}]: expected {want}, got {got}")
            ok = False

    # The two spelling checks read the same text and must NOT behave the same on
    # a compound: the British list is curated and belongs inside one.
    brit = [f.subject for f in pc.check("t", "The colour-coded plot.",
                                        "The colour-coded plot.",
                                        "The colour-coded plot.")
            if f.rule == "british-spelling"]
    if brit != ["colour"]:
        print(f"  british-spelling in a compound: expected ['colour'], got {brit}")
        ok = False

    # Neither spelling check may read inline code: a tool's own flag is not a
    # spelling the author can act on. `--reanalyse` is a real DIA-NN option.
    code_src = "Run with `--reanalyse` set."
    coded = [f.rule for f in pc.check("t", readability.clean(code_src),
                                      readability.clean(pc.no_code(code_src)),
                                      readability.clean(code_src))
             if f.rule in ("misspelling", "british-spelling")]
    if coded:
        print(f"  spelling read inline code and flagged {coded}")
        ok = False

    # An acronym counts as defined by any parenthetical that names it alongside
    # ordinary words, not only the bare "(ACR)" form.
    acr_cases = [
        ("bare form", "The mix (HYE) was used. HYE again.", 0),
        ("abbreviated inside a list",
         "three species (human, yeast and E. coli, abbreviated HYE). HYE again.", 0),
        ("expansion first", "time of flight (TOF) matters. TOF again.", 0),
        ("never defined", "We used XYZ here. XYZ again.", 1),
    ]
    for name, src, want in acr_cases:
        got = len([f for f in pc.check_structure({"t": src})
                   if f.rule == "unexpanded-acronym"])
        if got != want:
            print(f"  acronym [{name}]: expected {want}, got {got}")
            ok = False

    # A citation key must not swallow a colon that is punctuation.
    import typst_prose
    if re.findall(typst_prose.CITE, "@smith2020: the counts") != ["@smith2020"]:
        print("  citation pattern: swallowed a trailing colon")
        ok = False
    if re.findall(typst_prose.CITE, "See @sec:methods.") != ["@sec:methods"]:
        print("  citation pattern: dropped a real key suffix")
        ok = False

    # The definition scan must see exactly the floats a document contains, in
    # source order, however many times each is referenced.
    src = ("See #ref(<fig:b>) and #ref(<fig:a>) and @fig:b again.\n"
           + fig.format(cap="c", label="fig:a") + "\n"
           + fig.format(cap="c", label="fig:b") + "\n")
    got = [m.group(1) for m in pc.DEFINITION.finditer(src)]
    if got != ["fig:a", "fig:b"]:
        print(f"  definition scan: expected ['fig:a', 'fig:b'], got {got}")
        ok = False

    # A term repeated only inside inline-code spans is not repetitive prose.
    rep_cases = [
        ("repeated only in code paths",
         "Reproducers: `a/scripts/x.py`, `a/scripts/y.py`, `a/scripts/z.py`.", 0),
        ("genuinely repeated in prose",
         "The tolerance sets the tolerance used when the tolerance is applied.", 1),
    ]
    for name, src2, want in rep_cases:
        found = pc.check("t", readability.clean(src2),
                         readability.clean(pc.no_code(src2)),
                         readability.clean(src2, gap=pc.GAP))
        got2 = len([f for f in found if f.rule == "word-repetition"])
        if got2 != want:
            print(f"  word repetition [{name}]: expected {want}, got {got2}")
            ok = False

    # A Typst \u{XXXX} escape resolves to the character it denotes, so the word
    # count sees one word and the narrator has a symbol it can speak.
    import typst_prose as tp
    if tp.unescape_unicode(r"log\u{2082} ratio") != "log\u2082 ratio":
        print("  unescape_unicode: did not resolve \\u{2082}")
        ok = False

    # An uncited figure is an error; a cited one is not.
    only = lambda src, rule: len(
        [f for f in pc.check_structure({"t": src}) if f.rule == rule])
    uncited = only(fig.format(cap="c", label="fig:x"), "uncited-figure")
    cited = only("See @fig:x.\n" + fig.format(cap="c", label="fig:x"),
                 "uncited-figure")
    if (uncited, cited) != (1, 0):
        print(f"  uncited-figure check: expected (1, 0), got ({uncited}, {cited})")
        ok = False
    ok &= boundary_cases()
    ok &= bibliography_cases()
    ok &= asset_cases()
    ok &= stats_cases()
    ok &= check_stats_cases()
    ok &= stats_ownership_cases()
    ok &= adoption_cases()
    ok &= check_assets_cases()
    ok &= suppression_cases()
    ok &= new_paper_cases()
    return ok


def new_paper_cases() -> bool:
    """scripts/new-paper.sh actually produces a usable manuscript directory.

    This runs in the test suite rather than as its own recipe because the script
    is the front door: if it breaks, the failure lands on someone's first five
    minutes with the scaffold, which is the worst possible place to find out. It
    is also the one piece here with no other coverage -- everything else is
    exercised every time the manuscript is built.

    --no-build --no-git, so this needs neither the network (the arkheion template
    is fetched on a first compile) nor a git identity, and takes about a second.
    The build path is deliberately not covered: it is a straight `just paper`,
    already the most exercised code in the repository.
    """
    script = ROOT / "scripts" / "new-paper.sh"
    if not script.is_file():
        # Expected in a derived manuscript: new-paper.sh excludes scripts/ from
        # the copy, because a paper does not make papers.
        print("  new-paper.sh: absent, skipped (this is a derived manuscript)")
        return True

    ok = True
    # A title containing a double quote is the case the Python rewrite exists
    # for. Through sed it would close the Typst string early and the rest of the
    # line would be parsed as code.
    title = 'The "Quoted" Study: 20% Faster'
    with tempfile.TemporaryDirectory() as d:
        dest = Path(d) / "My Paper"
        proc = subprocess.run(
            [str(script), "--yes", "--no-build", "--no-git",
             "--title", title, "--author", "Ada Lovelace",
             "--email", "ada@example.edu", "--affiliation", "Dept, Uni",
             "--keywords", "one, two", str(dest)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(f"  new-paper.sh: exited {proc.returncode}\n{proc.stderr[:500]}")
            return False

        cfg = (dest / "config.typ").read_text()
        checks = [
            # The identity actually landed, with the quotes escaped rather than
            # ending the string.
            ("title substituted",
             '#let paper-title = "The \\"Quoted\\" Study: 20% Faster"' in cfg),
            ("author substituted", 'name: "Ada Lovelace"' in cfg),
            ("keywords substituted", '#let paper-keywords = ("one", "two")' in cfg),
            # Matched on the author ENTRY, not the bare name: config.typ also
            # names both placeholder authors in a comment explaining how the
            # Word front matter derives its superscripts, and that comment is
            # documentation the new project should keep.
            ("placeholder author entry is gone", 'name: "Grace Hopper"' not in cfg),
            # The abstract is prose and is deliberately left for the author.
            ("abstract left alone", "This document is a working skeleton" in cfg),

            # What must NOT come along. The scaffold's history is the whole
            # reason this script exists instead of `cp -r`.
            ("no .git", not (dest / ".git").exists()),
            ("no scripts/", not (dest / "scripts").exists()),
            ("no built pdf", not (dest / "paper.pdf").exists()),
            # The scaffold's own build stamp describes the scaffold's outputs.
            # Inherited, it would claim the new paper was built from sources it
            # has never seen, and `just check` would report clean on day one.
            ("no .build-stamp", not (dest / ".build-stamp").exists()),
            # The scaffold's CI tests scripts/new-paper.sh and builds the
            # scaffold itself. Inherited into a manuscript it is a workflow that
            # fails on push, forever, over a script the copy does not contain.
            ("no .github/", not (dest / ".github").exists()),

            # What must. figures/, si/ and the stamp travel so the copy compiles
            # and `just check` is clean before the analysis has ever run.
            ("figures/ copied", (dest / "figures" / "example_figure.png").is_file()),
            ("si/ copied", (dest / "si" / "example_table.typ").is_file()),
            ("assets.json copied", (dest / "assets.json").is_file()),
            ("stats.json copied", (dest / "stats.json").is_file()),
            ("analysis/ copied", (dest / "analysis" / "justfile").is_file()),
            ("tools/ copied", (dest / "tools" / "prose_check.py").is_file()),
            # A bare `--exclude=__pycache__` only matched at the top level, so
            # the caches under tools/ rode along the moment the toolchain moved
            # one directory down.
            ("no __pycache__ anywhere", not list(dest.rglob("__pycache__"))),

            # tar rather than cp -r, so this stays a symlink. A copy here drifts
            # from CLAUDE.md and the drifted one is what some agent reads.
            ("AGENTS.md is still a symlink", (dest / "AGENTS.md").is_symlink()),

            # The scaffold's MIT notice travels, renamed so it does not read as
            # a licence for the paper.
            ("LICENSE renamed", (dest / "LICENSE.scaffold").is_file()
             and not (dest / "LICENSE").exists()),
        ]
        # The slug comes from the directory name, which here has a space and a
        # capital in it on purpose.
        pyproject = (dest / "pyproject.toml").read_text()
        checks.append(("pyproject name slugified",
                       'name = "my-paper"' in pyproject))

        for name, passed in checks:
            if not passed:
                print(f"  new-paper.sh [{name}]: failed")
                ok = False
    return ok


def bibliography_cases() -> bool:
    """references.bib was the last artifact here that nothing read.

    Typst already fails on a citation with no entry, so only the reverse
    directions need checking. The duplicate case is keyed on DOI, not title:
    tried against a real bibliography, a title match flagged a dataset and the
    preprint describing it, which share a title and are correctly cited as two
    separate things.
    """
    import prose_check as pc
    ok = True

    def bib(*rows):
        out = ""
        for t, k, title, year, doi in rows:
            out += (f"@{t}{{{k},\n  title = {{{title}}},\n  year = {{{year}}},\n"
                    + (f"  doi = {{{doi}}},\n" if doi else "") + "}\n")
        return out

    cases = [
        ("all clean",
         bib(("article", "a2020", "One", "2020", "10.1/a")), "@a2020", []),
        ("uncited entry",
         bib(("article", "a2020", "One", "2020", "10.1/a"),
             ("article", "b2020", "Two", "2020", "10.1/b")),
         "@a2020", ["uncited-reference"]),
        ("same DOI twice",
         bib(("article", "a2020", "One", "2020", "10.1/a"),
             ("article", "b2020", "One again", "2020", "10.1/a")),
         "@a2020 @b2020", ["duplicate-reference"]),
        # The prefix forms publishers and Crossref both emit have to normalize to
        # the same DOI, or the duplicate goes unseen.
        ("DOI prefixes normalize",
         bib(("article", "a2020", "One", "2020", "https://doi.org/10.1/A"),
             ("article", "b2020", "One again", "2020", "doi:10.1/a")),
         "@a2020 @b2020", ["duplicate-reference"]),
        ("modern article with no DOI",
         bib(("article", "a2020", "One", "2020", "")), "@a2020", ["missing-doi"]),
        # A foundational citation predates DOIs entirely. Demanding one reports an
        # absence nobody can fix, on exactly the references papers cite most.
        ("pre-2000 article with no DOI",
         bib(("article", "a1952", "Old", "1952", "")), "@a1952", []),
        # A thesis or a piece of software often has no DOI, and that is normal.
        ("thesis with no DOI",
         bib(("phdthesis", "t2020", "Thesis", "2020", "")), "@t2020", []),
        ("implausible year",
         bib(("article", "a2020", "One", "2222", "10.1/a")),
         "@a2020", ["implausible-year"]),
    ]
    for name, bibtext, cites, want in cases:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "references.bib").write_text(bibtext)
            (root / "paper.typ").write_text(f"Text {cites}.\n")
            got = sorted({f.rule for f in pc.check_bibliography(root)})
            if got != sorted(want):
                print(f"  bibliography [{name}]: expected {sorted(want)}, got {got}")
                ok = False

    # No .bib at all is a valid project shape, not a finding.
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "paper.typ").write_text("No citations here.\n")
        if pc.check_bibliography(Path(d)):
            print("  bibliography: reported findings for a project with no .bib")
            ok = False

    # The retraction audit is online and cannot be unit-tested here, but its
    # classification is pure. This is the bug that shipped looking correct:
    # `update-to` lives on the NOTICE and points at what it retracts, while
    # `updated-by` lives on the PAPER. Reading the wrong one found nothing on a
    # paper retracted in 2010.
    sys.path.insert(0, str(ROOT / "tools"))
    import bib_audit as ba
    if ba.UPDATED_BY != "updated-by":
        print(f"  bib-audit reads {ba.UPDATED_BY!r}; the paper-side field is "
              f"'updated-by' and the other direction detects nothing")
        ok = False
    if "retraction" not in ba.WITHDRAWN:
        print("  bib-audit does not treat a retraction as withdrawn")
        ok = False
    return ok


def asset_cases() -> bool:
    """A generated asset nothing includes, which every staleness check calls
    current because it is -- it is simply not in the paper."""
    import prose_check as pc
    ok = True

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "si").mkdir()
        (root / "figures").mkdir()
        (root / "si" / "used_table.typ").write_text("#table()")
        (root / "si" / "orphan_table.typ").write_text("#table()")
        (root / "si" / "stats.json").write_text("{}")
        (root / "figures" / "used_figure.png").write_bytes(b"x")
        (root / "figures" / "orphan_figure.png").write_bytes(b"x")
        (root / "paper.typ").write_text(
            '#include "si/used_table.typ"\n#image("figures/used_figure.png")\n')

        found = pc.check_orphaned_assets(root)
        got = sorted(f.subject for f in found)
        want = ["orphan_figure.png", "orphan_table.typ"]
        if got != want:
            print(f"  orphaned-asset: expected {want}, got {got}")
            ok = False
        # stats.json is read by id through stats.typ, never by filename, so it
        # must never be reported however the manuscript is written.
        if any(f.subject == "stats.json" for f in found):
            print("  orphaned-asset: reported stats.json, which is read by id")
            ok = False

        # Print resolution: pixels over the width the figure is RENDERED at, not
        # the width it was saved at. A file that passes at 100% can fail at 50%
        # of nothing -- it is the same pixels over a smaller area, so the dpi
        # goes UP. The direction is easy to get backwards, hence both cases.
        import struct
        import zlib

        def png(w: int, h: int) -> bytes:
            body = b"IHDR" + struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00"
            return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + body
                    + struct.pack(">I", zlib.crc32(body)))

        (root / "figures" / "sharp.png").write_bytes(png(3000, 1000))
        (root / "figures" / "soft.png").write_bytes(png(400, 300))
        (root / "figures" / "vector.svg").write_text("<svg/>")
        (root / "figures" / "half.png").write_bytes(png(1000, 500))
        (root / "paper.typ").write_text(
            '#include "si/used_table.typ"\n#image("figures/used_figure.png")\n'
            '#image("figures/sharp.png", width: 100%)\n'
            '#image("figures/soft.png", width: 100%)\n'
            '#image("figures/vector.svg", width: 100%)\n'
            '#image("figures/half.png", width: 30%)\n')
        flagged = sorted(f.subject
                         for f in pc.check_figure_resolution(root))
        # used_figure.png is a 1-byte stub with no readable header, so it is
        # reported as unmeasurable -- which is the honest outcome, not silence.
        want_flagged = ["soft.png", "used_figure.png"]
        if flagged != want_flagged:
            print(f"  figure resolution: expected {want_flagged}, got {flagged}")
            ok = False

    # Table shape. None of this is visible from the source: a generated table
    # grows a column per condition and the first sign is an unreadable proof.
    tbl = lambda cols, rows, cell="[x]": (
        "#table(\n  columns: %d,\n" % cols
        + "".join("  " + ", ".join([cell] * cols) + ",\n" for _ in range(rows))
        + ")\n")
    table_cases = [
        ("normal", tbl(5, 3), 0),
        ("too many columns", tbl(12, 3), 1),
        ("too many rows", tbl(3, 50), 1),
        ("one overlong cell", tbl(3, 2, "[%s]" % ("word " * 20)), 1),
        ("both dimensions", tbl(12, 50), 2),
        # A cell's own brackets must not cut it short, or a long cell containing
        # a link would be measured as a few characters and pass.
        ("markup does not shorten a cell",
         tbl(2, 1, "[#emph[%s]]" % ("word " * 20)), 1),
    ]
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for name, src, want in table_cases:
            (root / "t.typ").write_text(src)
            got = len(pc.check_table_size(root))
            if got != want:
                print(f"  table size [{name}]: expected {want}, got {got}")
                ok = False

    # `columns:` has three spellings and the repeat form is the one that bites:
    # read as a bare tuple it counts one column, and every row count derived
    # from it is then wrong by that factor.
    for spec, want in [("5", 5), ("(left, right, right)", 3),
                       ("(1fr,) * 12", 12), ("(auto, auto) * 3", 6)]:
        got = pc._column_count(spec)
        if got != want:
            print(f"  column count [{spec}]: expected {want}, got {got}")
            ok = False

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "figures").mkdir()

        # No si/ or figures/ at all is a valid project shape, not a finding.
        bare = Path(d) / "bare"
        bare.mkdir()
        (bare / "paper.typ").write_text("= Title\n")
        if pc.check_orphaned_assets(bare):
            print("  orphaned-asset: reported findings for a project with no assets")
            ok = False
    return ok


def stats_cases() -> bool:
    """The generated-number mechanism: resolution, guards, and the check that
    catches a number typed by hand.

    Deliberately NOT in fixture.typ. The fixture's golden files would then depend
    on whatever values a project's gen_stats.py happens to declare, so every
    project would see a spurious diff on its first edit. These use a temporary
    stats file instead and stay true whatever the project computes.
    """
    import json
    import prose_check as pc
    import typst_prose as tp
    ok = True

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "stats.json"
        p.write_text(json.dumps({"values": {
            "a.pct":   {"value": 84.23, "fmt": ".1f"},
            "a.count": {"value": 1204, "fmt": ","},
            "a.small": {"value": 3, "fmt": ""},
            "a.label": {"value": "Treated", "fmt": ""},
        }}))

        # 1. resolution: substitutes the display string, survives a reflow inside
        #    the call, and is a no-op on prose that uses none.
        res = [
            ("plain", 'fell by #s("a.pct")%', "fell by 84.2%"),
            ("reflowed", 'fell by #s(\n  "a.pct",\n)%', "fell by 84.2%"),
            ("untouched", "no calls here", "no calls here"),
        ]
        for name, src, want in res:
            got = tp.resolve_stats(src, p)
            if got != want:
                print(f"  stats resolve [{name}]: expected {want!r}, got {got!r}")
                ok = False

        # 2. an unknown id fails loudly rather than deleting a number silently.
        try:
            tp.resolve_stats('#s("a.nope")', p)
            print("  stats resolve: an unknown id did not raise")
            ok = False
        except SystemExit:
            pass

        # 3. derivable-number: fires on a typed value, silent on a derived one,
        #    and ignores values too short to match without noise.
        cases = [
            ("typed distinctive", "recovery reached 84.2% overall.", 1),
            ("typed with separator", "we enrolled 1,204 participants.", 1),
            ("derived", 'recovery reached #s("a.pct")% overall.', 0),
            ("too common to flag", "there were 3 conditions.", 0),
            ("inside a larger number", "the id was 184.25 exactly.", 0),
            ("inline code is not a result", "pass `--threshold 84.2` to it.", 0),
            # lit() must NOT silence this rule: a value the analysis computes
            # belongs in #s(), and vouching for it as prose is the bypass the
            # two checks exist to be on opposite sides of.
            ("lit does not bypass derivable",
             'recovery reached #lit("84.2")% overall.', 1),
        ]
        for name, src, want in cases:
            got = len(pc.check_derivable_numbers({"t": src}, p))
            if got != want:
                print(f"  derivable-number [{name}]: expected {want}, got {got}")
                ok = False

        # 4. no stats.json at all: the mechanism is optional, so this is silent.
        if pc.check_derivable_numbers({"t": "84.2"}, Path(d) / "absent.json"):
            print("  derivable-number: reported findings with no stats.json")
            ok = False

        # 4b. unaccounted-number: the other half. A distinctive numeral that
        #     matches NOTHING declared is the least traceable number in the
        #     paper; a match is derivable-number's case, a year or a short
        #     count is noise, and no stats.json means nowhere to trace to.
        unaccounted = [
            ("matches nothing", "recovery reached 84.7% overall.", 1),
            ("undeclared thousands", "we screened 9,999 records.", 1),
            ("matches a declared display", "recovery reached 84.2% overall.", 0),
            ("matches a declared raw value", "the mean was 84.23 exactly.", 0),
            ("a year", "unchanged since 2019.", 0),
            ("too short to flag", "there were 3 conditions.", 0),
            ("derived is not typed", 'reached #s("a.pct")% overall.', 0),
            ("inline code is not prose", "pass `--cutoff 84.7` to it.", 0),
            # The two false positives the first real manuscript produced: a
            # clause comma is not a thousands separator, and digits inside an
            # identifier are not a result.
            ("clause comma is not part of the number",
             "isolated across frames (median 1, mean 2.67, up to 10).", 1),
            ("digits inside an identifier",
             "deposited at accession PXD070049 for review.", 0),
            ("repeated value reports once", "it was 84.7 then 84.7 again.", 1),
            # #lit() is the inline vouch: the wrapped occurrence is accounted
            # for, a bare occurrence of the same value elsewhere is not.
            ("lit-wrapped is vouched", 'ran at #lit("40.5") degrees.', 0),
            ("lit vouches the spot, not the value",
             'ran at #lit("40.5") degrees, later 40.5 again.', 1),
            ("reflowed lit is vouched too",
             'in total #lit(\n  "12,345",\n) events.', 0),
        ]
        for name, src, want in unaccounted:
            got = len(pc.check_unaccounted_numbers({"t": src}, p))
            if got != want:
                print(f"  unaccounted-number [{name}]: expected {want}, got {got}"
                      + f" -- {[f.subject for f in pc.check_unaccounted_numbers({'t': src}, p)]}")
                ok = False
        if pc.check_unaccounted_numbers({"t": "84.7"}, Path(d) / "absent.json"):
            print("  unaccounted-number: reported findings with no stats.json")
            ok = False
        # A Results section can owe dozens at once; the report shows a capped
        # sample plus a count, because a 189-line wall is read by nobody.
        many = " ".join(f"value {i}.{i} appears." for i in range(1, 15))
        found = pc.check_unaccounted_numbers({"t": many}, p)
        if len(found) != 9 or "more distinctive numerals" not in found[-1].message:
            print(f"  unaccounted-number cap: expected 8 + summary, got {len(found)}")
            ok = False

    # 5. guards. Shape errors (a guard on a label, a misspelt sign) fail at
    #    add(), next to the line that wrote them. VALUE violations fail at
    #    write(), because the guard that judges a value is the one in the file
    #    -- the author's -- and the file is only known then.
    sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
    try:
        from _stats import StatError, Stats
    except ImportError:
        print("  stats guards: analysis/scripts/_stats.py not importable")
        return False

    for name, value, kw in [
        ("guard on a non-number", "Treated", dict(sign="+")),
        ("nonsense sign", 1.0, dict(sign="up")),
    ]:
        try:
            Stats().add("x.y", value, **kw)
            print(f"  stats guard [{name}]: accepted a seed it should reject")
            ok = False
        except StatError:
            pass

    import io
    from contextlib import redirect_stdout
    for name, value, kw in [
        ("sign flip", 1.09, dict(sign="-")),
        ("out of range", 1.09, dict(between=(0, 1))),
    ]:
        st = Stats()
        st.add("x.y", value, **kw)
        try:
            with tempfile.TemporaryDirectory() as d, \
                    redirect_stdout(io.StringIO()):
                st.write(out=Path(d) / "s.json")
            print(f"  stats guard [{name}]: accepted a value it should reject")
            ok = False
        except StatError:
            pass

    # A value that satisfies its guard is accepted, and its fmt is recorded.
    #
    # The rendered string is NOT stored -- stats.json holds the value and the
    # format spec, and tools/render_stats.py turns them into what Typst reads. So
    # what this asserts is that the spec survives, and that rendering it through
    # the one shared formatter gives the rounded form.
    st = Stats()
    st.add("x.y", 84.23, fmt=".1f", sign="+", between=(0, 100))
    rec = st._values["x.y"]
    if "display" in rec:
        print("  stats guard: a rendered string was stored; it is derived at build time")
        ok = False
    if tp.display_of(rec) != "84.2":
        print(f"  stats guard: fmt not applied -- {tp.display_of(rec)!r}")
        ok = False

    # A format spec that cannot apply to the value must fail at declaration,
    # where the script that chose it is named, rather than at render time.
    try:
        Stats().add("x.bad", "not a number", fmt=".2f")
        print("  stats guard: an impossible fmt was accepted")
        ok = False
    except StatError:
        pass
    try:
        st.add("x.y", 1)
        print("  stats guard: a duplicate id was accepted")
        ok = False
    except StatError:
        pass
    return ok


def check_stats_cases() -> bool:
    """tools/check_stats.py: the guard on the one generated file you may edit.

    stats.json came out of the .assets-stamp hash when hand-entered values became
    a supported thing to write -- and that hash is gone entirely now -- so these
    checks are all that stands between a typed number and the prose. Each case below is a way that file has to be able
    to go wrong.

    The re-derive check is NOT exercised here: it shells out to
    analysis/scripts/gen_stats.py against the real analysis environment, which is
    a different thing to test and a slow one. `just check-stats` covers it on
    every run of the gate.
    """
    import json
    import check_stats as cs
    ok = True

    def entry(**kw):
        e = {"value": 1.0, "fmt": ".2f", "unit": "",
             "desc": "d", "expect": {}, "source": "",
             "origin": {"by": "hand", "note": "protocol"}}
        e.update(kw)
        return e

    # <name>, entry overrides, expected error count from the per-entry checks
    cases = [
        ("valid hand entry",        {}, 0),
        ("hand entry with no note", {"origin": {"by": "hand"}}, 1),
        ("hand entry, blank note",  {"origin": {"by": "hand", "note": "  "}}, 1),
        ("no origin at all",        {"origin": None}, 1),
        ("origin with no by",       {"origin": {"note": "x"}}, 1),
        ("generator that is gone",
         {"origin": {"by": "analysis/scripts/nope.py"}}, 1),
        ("generator that exists",
         {"origin": {"by": "analysis/scripts/gen_stats.py"}}, 0),
        # A guard that no longer holds. This is the case the whole mechanism
        # exists for: the prose says "increase", the value went negative.
        ("sign guard violated",
         {"value": -1.0, "expect": {"sign": "+"}}, 1),
        ("sign guard satisfied",   {"expect": {"sign": "+"}}, 0),
        ("range guard violated",
         {"value": 8400.0, "expect": {"min": 0, "max": 100}}, 1),
        # expect is author-edited, so a one-sided band is a legitimate thing to
        # find in the file -- it must be enforced, not silently skipped, which
        # is what a `min and max` condition used to do.
        ("one-sided min violated", {"value": -1.0, "expect": {"min": 0}}, 1),
        ("one-sided min satisfied", {"expect": {"min": 0}}, 0),
        ("one-sided max violated", {"value": 500.0, "expect": {"max": 100}}, 1),
        # NaN compares False against every bound, so the per-bound rewrite
        # would wave it through a band the old chained comparison rejected.
        ("NaN inside a band",
         {"value": float("nan"), "expect": {"min": 0, "max": 100}}, 1),
        # expect is hand-edited JSON. A key this does not understand is a guard
        # that never fires, and a quoted bound is one that cannot compare --
        # each must be an error, not a silence or a TypeError.
        ("unknown expect key",
         {"value": -3.0, "expect": {"between": [0, 1]}}, 1),
        ("quoted bound", {"value": 5.0, "expect": {"min": "0"}}, 1),
        ("expect is not an object", {"expect": [0, 1]}, 1),
        # A label carries no guard and must not be treated as a broken number.
        ("non-numeric with no guard",
         {"value": "Treated", "fmt": "", "expect": {}}, 0),
    ]
    for name, over, want in cases:
        rec = entry(**over)
        if over.get("origin", "keep") is None:
            rec["origin"] = None
        found = cs._origin("x.y", rec) + cs._guard("x.y", rec)
        got = sum(1 for f in found if f.level == "error")
        if got != want:
            print(f"  check-stats [{name}]: expected {want} error(s), got {got}"
                  + (f" -- {[f.msg for f in found]}" if got else ""))
            ok = False

    # The checksum is what makes re-derivation affordable to skip. It has to
    # catch a hand-edited generated value using only what is in the file, since
    # the default path must not re-run the analysis. v2 covers the value ALONE:
    # fmt is the author's to edit now, so changing it must not read as tampering.
    # v1, from before that split, covered fmt too and is still verified so an
    # existing manuscript upgrades without a wall of errors.
    import hashlib
    import _stats
    v1 = "v1:" + hashlib.sha256(json.dumps(
        [35, ","], sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    good = {"value": 35, "fmt": ",", "checksum": _stats._checksum(35),
            "origin": {"by": "analysis/scripts/gen_stats.py"}}
    checks = [
        ("intact", good, 0, 0),
        ("value edited", {**good, "value": 999}, 1, 0),
        ("fmt edited, which the author owns", {**good, "fmt": ".2f"}, 0, 0),
        ("v1 intact", {**good, "checksum": v1}, 0, 0),
        # A v1 digest covers value AND fmt, and cannot tell the documented fmt
        # edit from a value edit -- so a mismatch is a WARNING with the
        # ambiguity stated, not an error that fails the gate over the exact
        # edit the contract invites. `just assets` re-records as v2.
        ("v1 mismatch is a warning", {**good, "checksum": v1, "value": 999}, 0, 1),
        ("v1 fmt edit is the same warning", {**good, "checksum": v1, "fmt": ".2f"}, 0, 1),
        ("unknown checksum version", {**good, "checksum": "v9:beef"}, 1, 0),
        # Written before checksums existed: reported by nothing, so an upgrade
        # is not a wall of errors. `just assets` adds one.
        ("no checksum recorded", {k: v for k, v in good.items() if k != "checksum"}, 0, 0),
        # A hand entry has no generator to have written a checksum, so there is
        # nothing to compare against. Its guarantee is the guard and the note.
        ("hand entry is skipped",
         {**good, "value": 999, "origin": {"by": "hand", "note": "x"}}, 0, 0),
    ]
    for name, rec, want_err, want_warn in checks:
        found = cs._checksum({"x.y": rec})
        got_err = len([f for f in found if f.level == "error"])
        got_warn = len([f for f in found if f.level == "warn"])
        if (got_err, got_warn) != (want_err, want_warn):
            print(f"  check-stats checksum [{name}]: expected "
                  f"{want_err}e/{want_warn}w, got {got_err}e/{got_warn}w")
            ok = False

    # The fmt half of "fail where the mistake was made": a broken fmt edited
    # into stats.json used to pass verify and kill the next build inside
    # render_stats instead. check-stats now renders every entry itself.
    display_cases = [
        ("fmt applies", {"value": 84.23, "fmt": ".1f"}, 0),
        ("numeric fmt on a label", {"value": "Treated", "fmt": ".2f"}, 1),
        ("nonsense fmt", {"value": 84.23, "fmt": ".2q"}, 1),
        ("no fmt is fine for anything", {"value": "Treated", "fmt": ""}, 0),
    ]
    for name, rec, want in display_cases:
        got = len([f for f in cs._display({"x.y": rec}) if f.level == "error"])
        if got != want:
            print(f"  check-stats display [{name}]: expected {want}, got {got}")
            ok = False

    # The hash cache behind _sources/_pinned/check_assets: correct on first
    # sight, correct again after the file changes. The cache may only ever
    # change WHEN the hash is computed, never WHAT it is.
    import hashlib as _hl
    import hashcache
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "data.bin"
        f.write_bytes(b"one")
        want = "sha256:" + _hl.sha256(b"one").hexdigest()
        if hashcache.sha(f) != want or hashcache.sha(f) != want:
            print("  hashcache: wrong digest on first or cached read")
            ok = False
        f.write_bytes(b"two-longer")
        want2 = "sha256:" + _hl.sha256(b"two-longer").hexdigest()
        if hashcache.sha(f) != want2:
            print("  hashcache: served a stale digest after the file changed")
            ok = False

    # The deep check's summary must say what actually ran. On an
    # all-hand-entered manuscript _rederive has nothing to do, and the old
    # label printed "(re-derived)" anyway -- a silent no-op wearing a
    # verification label. (Found downstream, in koth-paper.)
    hand_only = {"x.y": {"value": 1, "origin": {"by": "hand", "note": "n"}}}
    f, status = cs._rederive(hand_only)
    if f != [] or "nothing generator-owned" not in status:
        print(f"  check-stats rederive: expected an honest empty status, got "
              f"{status!r}")
        ok = False

    # Pinned files: declared by the author, hashed by `just pin`, watched from
    # then on. A pin with no hash is an error (the declaration says the file
    # matters and nothing is watching it yet); an absent file is a note, since a
    # fresh clone usually lacks the data.
    bib = ROOT / "references.bib"
    right = "sha256:" + hashlib.sha256(bib.read_bytes()).hexdigest()
    pin_cases = [
        ("unpinned", {"references.bib": None}, 1),
        ("pinned and intact", {"references.bib": right}, 0),
        ("pinned and changed", {"references.bib": "sha256:" + "0" * 64}, 1),
        ("pinned but absent", {"no/such/file.csv": "sha256:" + "0" * 64}, 0),
        ("no pinned block at all", None, 0),
        # Hand-authored block, so a wrong shape (a list of paths is the natural
        # first guess) must be an error finding, not an AttributeError that
        # kills the whole gate.
        ("pinned is a list", ["references.bib"], 1),
    ]
    for name, pinned, want in pin_cases:
        doc = {"values": {}} if pinned is None else {"values": {}, "pinned": pinned}
        got = len([f for f in cs._pinned(doc) if f.level == "error"])
        if got != want:
            print(f"  check-stats pinned [{name}]: expected {want}, got {got}")
            ok = False

    # And the tool that records them: fills a null, refuses a missing file.
    import pin as pin_tool
    doc = {"pinned": {"references.bib": None}}
    _, rc = pin_tool.pin(doc, ROOT)
    if rc != 0 or doc["pinned"]["references.bib"] != right:
        print("  pin: did not record the hash of a present file")
        ok = False
    _, rc = pin_tool.pin({"pinned": {"no/such/file.csv": None}}, ROOT)
    if rc == 0:
        print("  pin: exited 0 while failing to pin a missing file")
        ok = False
    try:
        _, rc = pin_tool.pin({"pinned": ["references.bib"]}, ROOT)
        if rc == 0:
            print("  pin: accepted a list-shaped pinned block")
            ok = False
    except AttributeError:
        print("  pin: crashed on a list-shaped pinned block instead of reporting it")
        ok = False

    # Unused ids are reported against the real manuscript sources, so this only
    # asserts the shape: an id nothing could possibly call must be reported.
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "stats.json"
        p.write_text(json.dumps({"values": {"a.b": entry()}}))
        found = cs._unused({"zzz.never.called.by.anything": entry()})
        if not any(f.level == "warn" for f in found):
            print("  check-stats: an unread id was not reported")
            ok = False

    return ok


def stats_ownership_cases() -> bool:
    """The ownership split in stats.json: the script owns each entry's VALUE,
    the author owns fmt/unit/desc/expect once the entry exists.

    Each case is a way the split could quietly fail: a seed clobbering an author
    edit, an author guard not judging the fresh value, a stale script argument
    dying silently instead of with a note, a timestamp that means "the script
    ran" rather than "the value changed", or a pinned block lost in the rewrite.
    """
    import io
    import json
    from contextlib import redirect_stdout
    sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
    import _stats
    from _stats import StatError, Stats
    ok = True

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "stats.json"

        def run(st):
            buf = io.StringIO()
            with redirect_stdout(buf):
                st.write(out=p)
            return buf.getvalue()

        # 1. seeds populate a NEW entry in full.
        st = Stats()
        st.add("m.x", 1.5, fmt=".2f", unit="kg", desc="mass",
               sign="+", between=(0, 10))
        run(st)
        doc = json.loads(p.read_text())
        e = doc["values"]["m.x"]
        if e["fmt"] != ".2f" or e["unit"] != "kg" or \
                e["expect"] != {"sign": "+", "min": 0, "max": 10}:
            print(f"  ownership: seeds did not populate a new entry -- {e}")
            ok = False
        if not e.get("origin", {}).get("at"):
            print("  ownership: a new entry got no origin.at")
            ok = False
        if not str(e.get("checksum", "")).startswith("v2:"):
            print(f"  ownership: expected a v2 checksum, got {e.get('checksum')!r}")
            ok = False
        first_at = e["origin"]["at"]

        # 2. author edits survive a re-run, and the stale seeds are called out.
        e["fmt"], e["unit"], e["expect"] = ".1f", "g", {"min": 0}
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", 1.5, fmt=".2f", sign="+")     # stale seeds, same value
        out = run(st)
        e2 = json.loads(p.read_text())["values"]["m.x"]
        if (e2["fmt"], e2["unit"], e2["expect"]) != (".1f", "g", {"min": 0}):
            print(f"  ownership: author edits were clobbered by seeds -- {e2}")
            ok = False
        if "IGNORED" not in out:
            print("  ownership: stale seeds were dropped with no note")
            ok = False
        if e2["origin"]["at"] != first_at:
            print("  ownership: origin.at moved although the value did not")
            ok = False

        # 3. steady state: no seeds, no note; a changed value updates value,
        #    checksum and origin.at while the author fields stay put.
        st = Stats()
        st.add("m.x", 2.5)
        out = run(st)
        e3 = json.loads(p.read_text())["values"]["m.x"]
        if "IGNORED" in out:
            print("  ownership: a seed note fired with no seeds passed")
            ok = False
        if e3["value"] != 2.5 or e3["checksum"] != _stats._checksum(2.5):
            print(f"  ownership: value/checksum not updated -- {e3}")
            ok = False
        if e3["fmt"] != ".1f":
            print("  ownership: author fmt lost on a value change")
            ok = False

        # 4. the FILE's guard judges the fresh value. The author narrowed it to
        #    min 0; the analysis producing a negative must fail the write.
        st = Stats()
        st.add("m.x", -1.0)
        try:
            run(st)
            print("  ownership: the file's guard did not judge the new value")
            ok = False
        except StatError:
            pass
        if json.loads(p.read_text())["values"]["m.x"]["value"] != 2.5:
            print("  ownership: a failed write still modified the file")
            ok = False

        # 5. the file's fmt must apply to the new value, and fail loudly when
        #    the analysis changes type under it.
        doc = json.loads(p.read_text())
        doc["values"]["m.x"]["expect"] = {}
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", "a label now")
        try:
            run(st)
            print("  ownership: a numeric fmt silently accepted a string value")
            ok = False
        except StatError:
            pass

        # 6. blocks the script does not own pass through the rewrite untouched.
        doc = json.loads(p.read_text())
        doc["pinned"] = {"some/file.csv": "sha256:abc"}
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", 2.5)
        run(st)
        if json.loads(p.read_text()).get("pinned") != {"some/file.csv": "sha256:abc"}:
            print("  ownership: the pinned block was lost in a generator rewrite")
            ok = False

        # 6b. DELETING an author-owned field is an edit like any other: a guard
        #     removed from the file must stay removed, not come back from the
        #     seed the contract promises is ignored.
        doc = json.loads(p.read_text())
        del doc["values"]["m.x"]["expect"]
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", -5.0, sign="+")     # stale seed guard; value violates it
        out = run(st)
        e6 = json.loads(p.read_text())["values"]["m.x"]
        if e6.get("expect") != {}:
            print(f"  ownership: a deleted guard was resurrected -- {e6.get('expect')}")
            ok = False
        if "IGNORED" not in out:
            print("  ownership: resurrection-averted seed was dropped with no note")
            ok = False

        # 6c. origin.at must move when the value's REPRESENTATION changes:
        #     35 == 35.0 in Python but not in the file, and the checksum moves.
        #     The stored date is backdated first, because _now() has second
        #     granularity and two writes in one second look identical.
        doc = json.loads(p.read_text())
        doc["values"]["m.x"]["origin"]["at"] = "2000-01-01T00:00:00Z"
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", -5)                 # same number, int now
        run(st)
        e6c = json.loads(p.read_text())["values"]["m.x"]
        if e6c["origin"]["at"] == "2000-01-01T00:00:00Z":
            print("  ownership: origin.at kept its date across an int/float change")
            ok = False
        # and the counterpart: an identical value keeps its date.
        doc = json.loads(p.read_text())
        doc["values"]["m.x"]["origin"]["at"] = "2000-01-01T00:00:00Z"
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", -5)
        run(st)
        if json.loads(p.read_text())["values"]["m.x"]["origin"]["at"] \
                != "2000-01-01T00:00:00Z":
            print("  ownership: origin.at moved although the value did not")
            ok = False

        # 6d. a malformed values block must refuse the merge, not rewrite the
        #     file with every hand and other-script entry silently deleted.
        doc = json.loads(p.read_text())
        doc["values"] = []
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", 1.0)
        try:
            run(st)
            print("  ownership: merged into a malformed values block")
            ok = False
        except StatError:
            pass
        if json.loads(p.read_text())["values"] == []:
            pass        # untouched, as it must be
        else:
            print("  ownership: a refused merge still modified the file")
            ok = False
        # restore a valid file for anything below
        doc["values"] = {}
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", 1.0)
        run(st)

        # 6e. guards read from the file are hand-edited JSON: an unknown key, a
        #     quoted bound and a NaN value must each refuse the write loudly.
        for name, mutate, value in [
            ("unknown expect key",
             lambda e: e.__setitem__("expect", {"between": [0, 1]}), 2.0),
            ("quoted bound",
             lambda e: e.__setitem__("expect", {"min": "0"}), 2.0),
            ("NaN against a guard",
             lambda e: e.__setitem__("expect", {"min": 0}), float("nan")),
        ]:
            doc = json.loads(p.read_text())
            mutate(doc["values"]["m.x"])
            p.write_text(json.dumps(doc))
            st = Stats()
            st.add("m.x", value)
            try:
                run(st)
                print(f"  ownership guard shape [{name}]: accepted silently")
                ok = False
            except StatError:
                pass
        # leave the temp file valid
        doc = json.loads(p.read_text())
        doc["values"]["m.x"]["expect"] = {}
        p.write_text(json.dumps(doc))

    # 7. assets: origin.at means "the output changed", not "the script ran".
    #
    # record() insists the file it declares exists, so this needs a real one --
    # DISCOVERED from the project rather than named. The scaffold's demo figure
    # is deleted by the second week of a real manuscript, and a test hardcoding
    # it then fails for a reason unrelated to what it checks. (Found downstream,
    # in the dnoise manuscript.)
    sample = next(iter(sorted((ROOT / "figures").glob("*.png"))), None)
    if sample is None:
        print("  note: no figures/*.png, so the asset origin.at cases were skipped")
        return ok
    fig_rel = sample.relative_to(ROOT).as_posix()
    import _assets
    saved = _assets.OUT
    try:
        with tempfile.TemporaryDirectory() as d:
            _assets.OUT = Path(d) / "assets.json"
            kw = dict(kind="figure", inputs=[], desc="d")
            with redirect_stdout(io.StringIO()):
                _assets.record("fig.t", fig_rel, **kw)
            doc = json.loads(_assets.OUT.read_text())
            old = "2000-01-01T00:00:00Z"
            doc["values"]["fig.t"]["origin"]["at"] = old
            _assets.OUT.write_text(json.dumps(doc))
            with redirect_stdout(io.StringIO()):
                _assets.record("fig.t", fig_rel, **kw)
            at = json.loads(_assets.OUT.read_text())["values"]["fig.t"]["origin"]["at"]
            if at != old:
                print("  asset origin.at: moved although the output did not change")
                ok = False
            doc = json.loads(_assets.OUT.read_text())
            doc["values"]["fig.t"]["hash"] = "sha256:" + "0" * 64
            _assets.OUT.write_text(json.dumps(doc))
            with redirect_stdout(io.StringIO()):
                _assets.record("fig.t", fig_rel, **kw)
            at = json.loads(_assets.OUT.read_text())["values"]["fig.t"]["origin"]["at"]
            if at == old:
                print("  asset origin.at: kept a stale date across an output change")
                ok = False
    finally:
        _assets.OUT = saved

    return ok


def adoption_cases() -> bool:
    """The migration path: files whose analysis is gone, adopted with a note.

    Adoption must buy the checks that still apply (hash, note) without the one
    that cannot (a generator), and a restored generator must be able to take
    the id back.
    """
    import io
    import json
    from contextlib import redirect_stdout
    import adopt_assets as aa
    import check_assets as ca
    ok = True

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "figures").mkdir()
        (root / "si").mkdir()
        (root / "figures" / "legacy_plot.png").write_bytes(b"png-bytes")
        (root / "si" / "old_table.typ").write_text("#table()")

        # No note, no adoption: provenance is the entire point.
        lines, rc = aa.adopt(root, "  ")
        if rc == 0 or (root / "assets.json").is_file():
            print("  adopt: proceeded without a note")
            ok = False

        lines, rc = aa.adopt(root, "imported from repo X at 3f2a1c0")
        doc = json.loads((root / "assets.json").read_text())
        e = doc["values"].get("fig.legacy-plot")
        t = doc["values"].get("tbl.old-table")
        if rc != 0 or not e or not t:
            print(f"  adopt: expected fig.legacy-plot and tbl.old-table -- {list(doc.get('values', {}))}")
            ok = False
        elif (e["origin"]["by"], e["kind"], t["kind"]) != ("adopted", "figure", "table"):
            print(f"  adopt: wrong provenance or kind -- {e}, {t}")
            ok = False

        # check_assets: an adopted entry passes with no generator on disk, and
        # its note is mandatory.
        old_root, ca.ROOT = ca.ROOT, root
        try:
            if [f for f in ca._entry("fig.legacy-plot", e) if f.level == "error"]:
                print("  adopt: a clean adopted entry was reported as an error")
                ok = False
            noteless = {**e, "origin": {"by": "adopted"}}
            if not [f for f in ca._entry("fig.legacy-plot", noteless)
                    if f.level == "error"]:
                print("  adopt: an adopted entry with no note passed")
                ok = False
            # A changed file is an error until re-adoption accepts it.
            (root / "figures" / "legacy_plot.png").write_bytes(b"new-bytes")
            if not [f for f in ca._entry("fig.legacy-plot", e) if f.level == "error"]:
                print("  adopt: a changed adopted file passed the hash check")
                ok = False
        finally:
            ca.ROOT = old_root
        lines, rc = aa.adopt(root, "accepting the regenerated plot")
        e2 = json.loads((root / "assets.json").read_text())["values"]["fig.legacy-plot"]
        if e2["hash"] == e["hash"]:
            print("  adopt: re-running did not refresh a changed hash")
            ok = False

    # A generator may take over an adopted id: rebuildable beats adopted.
    # The figure is discovered, not named -- see the origin.at cases for why.
    sample = next(iter(sorted((ROOT / "figures").glob("*.png"))), None)
    if sample is None:
        print("  note: no figures/*.png, so the adoption takeover case was skipped")
        return ok
    fig_rel = sample.relative_to(ROOT).as_posix()
    import _assets
    saved = _assets.OUT
    try:
        with tempfile.TemporaryDirectory() as d:
            _assets.OUT = Path(d) / "assets.json"
            _assets.OUT.write_text(json.dumps({"values": {
                "fig.t": {"path": fig_rel,
                          "kind": "figure", "hash": "sha256:" + "0" * 64,
                          "origin": {"by": "adopted", "note": "legacy"}}}}))
            buf = io.StringIO()
            with redirect_stdout(buf):
                _assets.record("fig.t", fig_rel,
                               kind="figure", inputs=[], desc="d")
            e = json.loads(_assets.OUT.read_text())["values"]["fig.t"]
            if e["origin"]["by"] == "adopted":
                print("  adopt: a generator could not take over an adopted id")
                ok = False
            if "supersedes" not in buf.getvalue():
                print("  adopt: a takeover happened silently")
                ok = False
    finally:
        _assets.OUT = saved

    return ok


def check_assets_cases() -> bool:
    """tools/check_assets.py, and the prose rule that keeps it honest.

    The manifest is only trustworthy because the compile resolves ids through it.
    Two things have to hold for that: the entries must describe the files that are
    actually there, and the manuscript must not reach around the mechanism by
    naming a generated file directly.
    """
    import json
    import check_assets as ca
    import prose_check as pc
    ok = True

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "figures").mkdir()
        (root / "si").mkdir()
        (root / "analysis" / "scripts").mkdir(parents=True)
        gen = root / "analysis" / "scripts" / "gen_x_figure.py"
        gen.write_text("# generator\n")
        png = root / "figures" / "x.png"
        png.write_bytes(b"pixels")
        data = root / "analysis" / "scripts" / "d.csv"
        data.write_text("a,b\n1,2\n")

        orig_root = ca.ROOT
        ca.ROOT = root
        try:
            def entry(**kw):
                e = {
                    "path": "figures/x.png", "kind": "figure", "desc": "",
                    "hash": ca._sha(png),
                    "origin": {"by": "analysis/scripts/gen_x_figure.py"},
                    "inputs": {"analysis/scripts/d.csv": ca._sha(data)},
                }
                e.update(kw)
                return e

            cases = [
                ("valid entry", {}, 0),
                ("output edited since generation",
                 {"hash": "sha256:" + "0" * 64}, 1),
                ("generator no longer exists",
                 {"origin": {"by": "analysis/scripts/gone.py"}}, 1),
                ("declared input has changed",
                 {"inputs": {"analysis/scripts/d.csv": "sha256:" + "0" * 64}}, 1),
                ("file does not exist",
                 {"path": "figures/absent.png"}, 1),
                ("bad kind", {"kind": "diagram"}, 1),
                # An input that is not present is the ordinary state of a fresh
                # clone (analysis/data/ is untracked). It must NOT be an error, or
                # every clone is red for something the person cannot act on.
                ("input not present is not an error",
                 {"inputs": {"analysis/data/absent.csv": "sha256:" + "0" * 64}}, 0),
            ]
            for name, over, want in cases:
                found = ca._entry("fig.x", entry(**over))
                got = sum(1 for f in found if f.level == "error")
                if got != want:
                    print(f"  check-assets [{name}]: expected {want} error(s), "
                          f"got {got}" + (f" -- {[f.msg for f in found]}" if got else ""))
                    ok = False

            # A file sitting in a generated directory that no entry claims: the
            # deleted-generator leftover nothing else can see.
            (root / "figures" / "stray.png").write_bytes(b"x")
            if not any(f.id.endswith("stray.png")
                       for f in ca._unclaimed({"fig.x": entry()})):
                print("  check-assets: an unclaimed file was not reported")
                ok = False
        finally:
            ca.ROOT = orig_root

    # The bypass rule: naming a declared asset directly goes around the manifest,
    # so assets.json quietly stops describing the manuscript.
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "assets.json"
        p.write_text(json.dumps({"values": {
            "fig.example": {"path": "figures/example_figure.png",
                            "kind": "figure"},
            "tbl.example": {"path": "si/example_table.typ", "kind": "table"},
        }}))
        cases = [
            ("by id", '#figure(fig("fig.example"), caption: [x])', 0),
            ("figure by filename",
             '#figure(image("figures/example_figure.png"), caption: [x])', 1),
            ("table by filename", '#include "si/example_table.typ"', 1),
            # Not every image is a generated asset. A logo or a hand-drawn
            # schematic is named directly and must not be flagged.
            ("undeclared image is fine", '#image("figures/logo.png")', 0),
            ("mentioned in a comment", '// image("figures/example_figure.png")', 0),
        ]
        for name, src, want in cases:
            got = len(pc.check_bypassed_assets({"t": src}, p))
            if got != want:
                print(f"  bypassed-asset [{name}]: expected {want}, got {got}")
                ok = False

    return ok


def boundary_cases() -> bool:
    """Where a sentence ends. Both of these were wrong and silently inflated the
    reported words-per-sentence, which is the kind of error a golden file over a
    fixture full of short sentences will never catch."""
    import prose_check as pc
    import readability
    ok = True

    # An abbreviation is masked only at a word boundary. Masking it as a plain
    # substring made every word ending in "-al." look like "et al.".
    splits = [
        ("plain -al. ends a sentence", "It survived removal. It is sampled densely.", 2),
        ("et al. does not", "As Smith et al. showed, it works. Then it stopped.", 2),
        ("a decimal does not", "The value 0.15 held. It then fell.", 2),
        ("vs. does not", "Treated vs. control counts differ. The gap is small.", 2),
    ]
    for name, src, want in splits:
        got = len(pc.sentences(src))
        if got != want:
            print(f"  sentence split [{name}]: expected {want}, got {got}")
            ok = False

    # A heading ends the sentence before it, contributes no words of its own, and
    # never merges with the sentence after it.
    got = readability.clean(
        "== Methods\nWe used a hybrid benchmark here.\n\n"
        "= Results\nReduction is governed by density."
    )
    for bad in ("=", "Methods", "Results"):
        if bad in got:
            print(f"  heading handling: {bad!r} leaked into the scored prose -- {got!r}")
            ok = False
    if readability._sentences(got) != 2:
        print(f"  heading handling: expected 2 sentences, got "
              f"{readability._sentences(got)} -- {got!r}")
        ok = False
    return ok


def suppression_cases() -> bool:
    """A finding must be silenceable by rule and by value, and a typo in the
    config must fail rather than silently suppress nothing."""
    import prose_rules as pr

    f = pr.Finding("unexpanded-acronym", "warn", "'TOF' used 9x", "TOF")
    checks = [
        ("no config suppresses nothing", pr.Config(), False),
        ("by value", pr.Config(allow={"unexpanded-acronym": {"tof"}}), True),
        ("by value is case-insensitive",
         pr.Config(allow={"unexpanded-acronym": {"TOF".lower()}}), True),
        ("wrong value does not match",
         pr.Config(allow={"unexpanded-acronym": {"pride"}}), False),
        ("by rule", pr.Config(disable={"unexpanded-acronym"}), True),
        ("another rule does not match", pr.Config(disable={"em-dash"}), False),
    ]
    ok = True
    for name, cfg, want in checks:
        if cfg.suppresses(f) != want:
            print(f"  suppression [{name}]: expected {want}")
            ok = False

    # Severity is a project's call. A rule can be re-rated in both directions,
    # and an unknown rule or a nonsense severity must fail the config rather than
    # be ignored -- the same reasoning as a typo'd suppression.
    sev = pr.Config(severity={"em-dash": "warn", "long-sentence": "error"})
    for rule, want in [("em-dash", "warn"), ("long-sentence", "error"),
                       ("doubled-word", "error")]:   # untouched keeps its default
        if sev.severity_of(rule) != want:
            print(f"  severity [{rule}]: expected {want}, got {sev.severity_of(rule)}")
            ok = False

    # report() must APPLY the override, not just store it. Finding is frozen, so
    # this is the step that silently did nothing at first.
    import io
    import contextlib
    f_err = pr.Finding("em-dash", "error", "em dash")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = pr.report([f_err], sev, show_suppressed=False, strict=False)
    if code != 0 or "ERROR" in buf.getvalue():
        print("  severity: an error re-rated to warn still gated the build")
        ok = False

    # Vocabularies take additions and removals.
    import prose_check as pc2
    voc = pr.Config(vocab={
        "verbose-phrase": {"add": {"leverage": "use"}, "remove": ["essentially"]},
        "common-words": {"add": {"treated"}, "remove": []},
    })
    phrases = voc.vocabulary("verbose-phrase", {"essentially": "(cut it)",
                                                "very": "(cut it)"})
    words = voc.vocabulary("common-words", {"the", "and"})
    checks = [
        ("added phrase", phrases.get("leverage") == "use"),
        ("removed phrase", "essentially" not in phrases),
        ("untouched phrase", phrases.get("very") == "(cut it)"),
        ("added word", "treated" in words),
        ("untouched word", "the" in words),
        ("base is not mutated", "leverage" not in pc2.VERBOSE),
    ]
    for name, passed in checks:
        if not passed:
            print(f"  vocabulary [{name}]: failed")
            ok = False

    # Every rule the checker can emit must be declared, or its findings would
    # crash the reporter and could never be suppressed.
    declared = set(pr.RULES)
    emitted = set(re.findall(r'add\(\s*"([a-z-]+)"', Path(pc2.__file__).read_text()))
    emitted |= set(re.findall(r'Finding\(\s*\n?\s*"([a-z-]+)"',
                              Path(pc2.__file__).read_text()))
    missing = emitted - declared
    if missing:
        print(f"  rules emitted but not declared in prose_rules.RULES: {sorted(missing)}")
        ok = False
    return ok


if __name__ == "__main__":
    raise SystemExit(main())
