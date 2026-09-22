"""tools/resolve_typst.py: the manuscript as plain Typst, for pandoc."""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

def run_cases() -> bool:
    """tools/resolve_typst.py: the manuscript as plain Typst, for pandoc.

    Every case here is a bug this resolver actually had. Three of them only
    appeared on a real manuscript, which is the argument for the fixture: the
    scaffold's placeholder prose contains none of these shapes.
    """
    import resolve_typst as rt
    import typst_prose
    ok = True
    # The table case INLINES the target file, so it must exist on disk. A
    # temp file rather than the scaffold's si/example_table.typ: a derived
    # manuscript may have deleted the example generator, and this suite must
    # not depend on which assets the manuscript's analysis declares. The
    # absolute path wins the resolver's `ROOT / path` join.
    tbl_tmp = tempfile.TemporaryDirectory()
    tbl_file = Path(tbl_tmp.name) / "example_table.typ"
    tbl_file.write_text("#table(columns: 2, [a], [b])\n")
    assets = {"fig.x": {"path": "figures/example_figure.png"},
              "tbl.x": {"path": str(tbl_file)}}
    # Against the TEST-owned stats, like extract(): the fixture must not
    # depend on which ids the manuscript's analysis currently declares. The
    # swap is try/finally-guarded, also like extract(): a case that escapes
    # the loop must not leave the module pointing at the fixture.
    saved = typst_prose.STATS_JSON
    fixture_stats = HERE / "fixture-stats.json"
    if fixture_stats.is_file():
        typst_prose.STATS_JSON = fixture_stats
    try:
        cases = [
            # (name, source, must appear, must NOT appear)
            ("stats resolve", '#s("cohort.total_n")', None, "#s("),
            ("lit unwraps", '#lit("2.2")', "2.2", "#lit("),
            ("figure keeps its arguments", '#fig("fig.x", width: 70%)',
             'image("figures/example_figure.png", width: 70%)', "fig("),
            # The matched `#` must be re-emitted: without it, a markup-mode
            # call resolved to the literal words image("...") in the export.
            ("markup figure keeps its hash", 'See #fig("fig.x") here.',
             '#image("figures/example_figure.png")', None),
            # A markup-mode table needs `#[...]`; bare brackets in markup are
            # literal text, not a content block.
            ("markup table gains a content block", '#tbl("tbl.x")',
             "#[", None),
            # No left boundary matched any identifier ending in fig/tbl, so a
            # manuscript's own #subfig() helper was rejected -- or, on an id
            # collision, silently rewritten.
            ("a subfig helper is not fig", '#subfig("panel-a")',
             '#subfig("panel-a")', "image("),
            # pandoc reads @fig as a CITATION KEY and orphans the label, so a
            # cross-reference silently becomes the words "[fig]:x".
            ("crossref becomes a ref", "see @fig:demo here",
             "#ref(<fig:demo>)", "@fig:"),
            # Labels may be multi-segment, exactly as typst_prose.CITE allows;
            # capturing one segment resolved @fig:panel:a to a nonexistent
            # label plus stray ':a' prose.
            ("multi-segment crossref label", "see @fig:panel:a here",
             "#ref(<fig:panel:a>)", "@fig:"),
            # A bracket after the label is Typst's supplement; pandoc
            # printed "Figure 1[]" (cascade/paper).
            ("empty supplement means the bare number", "see @fig:demo[] here",
             "#ref(<fig:demo>, supplement: none) here", "[]"),
            ("a supplement replaces the word", "see @fig:demo[Panel] here",
             "Panel #ref(<fig:demo>, supplement: none) here", "[Panel]"),
            ("citation is NOT a crossref", "as shown @lovelace1843 here",
             "@lovelace1843", "#ref(<lovelace"),
            # typstyle breaks a long call and leaves a trailing comma; the
            # first draft's pattern had no `,?` and died on a real manuscript.
            # The helper's `#let` is stripped, so the rewrite must write out
            # its definition: plain #ref() rendered "Table Table S1".
            ("reflowed refn keeps its supplement", "#refn(\n  <tbl:x>,\n)",
             "#ref(<tbl:x>, supplement: none)", "refn("),
            # A code-mode refn (inside a larger expression) must not gain an
            # invalid `#`.
            ("code-mode refn stays code", "#figure(refn(<tbl:x>))",
             "(ref(<tbl:x>, supplement: none))", "(#ref"),
            # si-body.typ documents its own usage with a literal #s("id") in a
            # comment, which the resolver then asked stats.json to resolve.
            ("comments are stripped first", '// example: #s("id")\nreal text',
             "real text", "#s("),
            # ...and the #todo refusal runs AFTER the strip: a note mentioned
            # in a comment builds clean under `just paper` and must export.
            ("a commented todo does not refuse", '// old: #todo("was fixed")\nreal text',
             "real text", "#todo"),
            # Directive lines are stripped, as readability.clean strips them:
            # left in place, the "self-contained" output still imported the
            # project helpers and gitignored stats-rendered.json.
            ("directive lines are dropped",
             '#import "stats.typ": s, n\n#let refn(l) = ref(l, supplement: none)\nprose stays',
             "prose stays", "#import"),
            # Raw spans are verbatim in the PDF and must be verbatim in the
            # export: a documented `#s("id")` in backticks was either rejected
            # (undeclared id) or silently replaced by the number.
            ("inline code is verbatim", 'use `#s("id")` here',
             '`#s("id")`', None),
            ("a fence is verbatim", 'before\n```\n#fig("fig.nope")\n```\nafter',
             '#fig("fig.nope")', "image("),
            ("a todo in a fence does not refuse", '```\n#todo("example")\n```',
             '#todo("example")', None),
            # The 80-column reflow splits a long citation cluster across a
            # soft line break. Typst groups citations across it, so the PDF
            # collapsed six keys into one range; pandoc's Typst reader only
            # groups citations on one LINE, and the Word export shipped
            # reading "10-12 13-15" where the PDF read "10-15".
            ("a line-split citation cluster is rejoined",
             "natively @lovelace1843 @hopper1952\n@turing1936, but each",
             "@lovelace1843 @hopper1952 @turing1936, but each",
             "@hopper1952\n"),
            # ...but only a single newline: a blank line is a paragraph break,
            # and two citations either side of one are separate sentences.
            ("citations across a paragraph break stay put",
             "ends here @lovelace1843\n\n@hopper1952 opens the next",
             "@lovelace1843\n\n@hopper1952", None),
        ]
        for name, src, want, forbid in cases:
            try:
                got = rt.resolve_notation(src, assets, "t")
            # SystemExit too: resolve_stats raises it for an unknown id, and
            # `except Exception` let it abort the whole run mid-suite instead
            # of printing this case's diagnostic.
            except (Exception, SystemExit) as e:
                print(f"  resolver [{name}]: raised {type(e).__name__}: {e}")
                ok = False
                continue
            if want and want not in got:
                print(f"  resolver [{name}]: expected {want!r} in {got!r}")
                ok = False
            if forbid and forbid in got:
                print(f"  resolver [{name}]: {forbid!r} survived in {got!r}")
                ok = False

        # A note that cannot ship must not ship through an export either.
        try:
            rt.resolve_notation('#todo("check")', assets, "t")
            print("  resolver: an unresolved #todo was exported anyway")
            ok = False
        except rt.ResolveError:
            pass

        # An id the manifest does not declare must name itself, not vanish.
        try:
            rt.resolve_notation('#fig("fig.nope")', assets, "t")
            print("  resolver: an undeclared asset id was accepted")
            ok = False
        except rt.ResolveError:
            pass
    finally:
        typst_prose.STATS_JSON = saved
        tbl_tmp.cleanup()
    return ok

if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
