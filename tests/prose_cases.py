"""Table-driven cases for the prose checker: rules, boundaries, suppression.

Pure functions over a string, so they get real cases rather than a golden
file. Everything here is a bug the checker actually had.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

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

def run_cases() -> bool:
    ok = True
    for case in (structural_cases, boundary_cases, suppression_cases,):
        ok &= case()
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
