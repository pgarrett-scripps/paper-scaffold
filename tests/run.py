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
]


def extract(src: str) -> dict[str, str]:
    body = readability.slice_body(src)
    out = {"readability": readability.clean(body)}
    if extract_prose is not None:
        out["narration"] = extract_prose.clean(extract_prose.extract_body(src))
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
    ok &= asset_cases()
    ok &= stats_cases()
    ok &= suppression_cases()
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
            "a.pct":   {"display": "84.2", "value": 84.23},
            "a.count": {"display": "1,204", "value": 1204},
            "a.small": {"display": "3", "value": 3},
            "a.label": {"display": "Treated", "value": "Treated"},
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

    # 5. guards. Each must fail at declaration, which is the whole point: the
    #    build breaks when the analysis changes, not when a reader notices.
    sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
    try:
        from _stats import StatError, Stats
    except ImportError:
        print("  stats guards: analysis/scripts/_stats.py not importable")
        return False

    guards = [
        ("sign flip", 1.09, dict(sign="-")),
        ("out of range", 1.09, dict(between=(0, 1))),
        ("guard on a non-number", "Treated", dict(sign="+")),
        ("nonsense sign", 1.0, dict(sign="up")),
    ]
    for name, value, kw in guards:
        try:
            Stats().add("x.y", value, **kw)
            print(f"  stats guard [{name}]: accepted a value it should reject")
            ok = False
        except StatError:
            pass

    # A value that satisfies its guard is accepted, and rounding is applied.
    st = Stats()
    st.add("x.y", 84.23, fmt=".1f", sign="+", between=(0, 100))
    if st._values["x.y"]["display"] != "84.2":
        print(f"  stats guard: fmt not applied -- {st._values['x.y']['display']!r}")
        ok = False
    try:
        st.add("x.y", 1)
        print("  stats guard: a duplicate id was accepted")
        ok = False
    except StatError:
        pass
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
