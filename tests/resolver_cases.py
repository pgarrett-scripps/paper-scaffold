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

        ok = _si_contents_cases(rt) and ok
        ok = _data_file_cases(rt, typst_prose) and ok
    finally:
        typst_prose.STATS_JSON = saved
        tbl_tmp.cleanup()
    return ok


def _si_contents_cases(rt) -> bool:
    """`#si-contents`: the Word sentence matches what the PDF prints.

    The PDF builds the sentence in a `context` block (assets.typ's si-contents),
    the Word export rebuilds it from the numbering pass (koth-paper, whose
    hand-written paragraph had drifted from the SI's headings). Two
    implementations of one sentence drift too, so the assets.typ helper is
    compiled here and the two texts compared.
    """
    import shutil
    import subprocess
    ok = True
    si = ("= Methods <sec:m>\n"
          '#figure(rect(), caption: [a]) <fig:a>\n'
          "== Detail\n"
          "#figure(table([x]), caption: [t]) <tbl:t>\n"
          "= Data\n"
          '#figure(rect(), caption: [b]) <fig:b>\n')
    main = ("= Intro\n#si-contents\n"
            '#figure(rect(), caption: [m]) <fig:m>\n')
    want = "Sections S1 Methods, S2 Data. Figures S1–S2 and Table S1 (PDF)."
    got = rt.resolve_crossrefs("", main + rt._SI_MARK + "\n" + si)
    if want not in got or "#si-contents" in got:
        print(f"  resolver [si-contents]: expected {want!r} in {got!r}")
        ok = False
    for summary, sentence in (
            ({"sections": [("S1", "Methods")], "fig": 1, "tbl": 0},
             "Section S1 Methods. Figure S1 (PDF)."),
            ({"sections": [], "fig": 0, "tbl": 3}, "Tables S1–S3 (PDF)."),
            ({"sections": [("S1", "A"), ("S2", "B")], "fig": 0, "tbl": 0},
             "Sections S1 A, S2 B (PDF).")):
        if rt.si_contents_sentence(summary) != sentence:
            print(f"  resolver [si-contents]: {summary} gave "
                  f"{rt.si_contents_sentence(summary)!r}, not {sentence!r}")
            ok = False
    try:
        rt.resolve_crossrefs("", main)
        print("  resolver [si-contents]: listed an SI the export does not hold")
        ok = False
    except rt.ResolveError:
        pass

    if not (shutil.which("typst") and shutil.which("pdftotext")):
        print("  resolver [si-contents]: typst or pdftotext missing; "
              "PDF parity not checked")
        return ok
    assets = (ROOT / "assets.typ").read_text(encoding="utf-8")
    block = re.search(r"^(#let si-contents = context \{\n.*?^\}\n)", assets, re.S | re.M)
    if block is None:
        print("  resolver [si-contents]: assets.typ lost the helper")
        return False
    setup = ("#pagebreak()\n#context [#metadata(here().page()) <si-start>]\n"
             "#counter(figure.where(kind: image)).update(0)\n"
             "#counter(figure.where(kind: table)).update(0)\n"
             "#counter(heading).update(0)\n"
             '#set heading(numbering: (..n) => "S" + n.pos().map(str).join("."))\n')
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "si.typ"
        src.write_text(block.group(1) + main + setup + si, encoding="utf-8")
        proc = subprocess.run(["typst", "compile", str(src)],
                              capture_output=True, text=True)
        text = subprocess.run(["pdftotext", str(src.with_suffix(".pdf")), "-"],
                              capture_output=True, text=True).stdout
    if proc.returncode or want not in " ".join(text.split()):
        print(f"  resolver [si-contents]: the PDF printed {' '.join(text.split())[:160]!r}"
              f"{proc.stderr[:200]}, the Word export {want!r}")
        ok = False
    return ok


def _data_file_cases(rt, typst_prose) -> bool:
    """`dfile("id")`: every text copy says what the PDF prints (uno-paper).

    The registry is Typst's reading of config.typ, so the parity check
    compiles assets.typ against a throwaway config.typ and compares
    pdftotext's reading with the resolver's substitution.
    """
    import shutil
    import subprocess
    ok = True
    saved = typst_prose.DATA_FILES
    try:
        typst_prose.DATA_FILES = {"files": ["tbl.a", "tbl.b"],
                                  "name": "Supplementary Data File",
                                  "short": "File"}
        for name, src, want, forbid in (
                ("markup dfile", 'see #dfile("tbl.b").',
                 "see Supplementary Data File 2.", "dfile"),
                ("short, number and count", '#dfile-short("tbl.a"), '
                 '#dfile-number("tbl.b") of #dfile-count()',
                 "File 1, 2 of 2", "dfile"),
                ("code-mode call stays valid Typst",
                 '#figure(dfile("tbl.a"))', "#figure([Supplementary Data File 1])",
                 None),
                ("a project helper ending in dfile is not ours",
                 '#mydfile("x")', '#mydfile("x")', None)):
            got = rt.resolve_notation(src, {}, "t")
            if want not in got or (forbid and forbid in got.replace("mydfile", "")):
                print(f"  resolver [{name}]: expected {want!r} in {got!r}")
                ok = False
        try:
            rt.resolve_notation('#dfile("tbl.nope")', {}, "t")
            print("  resolver [dfile]: an id outside paper-data-files was accepted")
            ok = False
        except SystemExit:
            pass
    finally:
        typst_prose.DATA_FILES = saved

    if not (shutil.which("typst") and shutil.which("pdftotext")):
        print("  resolver [dfile]: typst or pdftotext missing; PDF parity not checked")
        return ok
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        shutil.copyfile(ROOT / "assets.typ", d / "assets.typ")
        (d / "assets.json").write_text(json.dumps({"values": {
            "tbl.a": {"kind": "table", "path": "si/a.typ"},
            "tbl.b": {"kind": "table", "path": "si/b.typ"}}}))
        (d / "config.typ").write_text(
            '#let paper-data-files = ("tbl.a", "tbl.b")\n'
            '#let paper-data-file-short = "Data"\n')
        prose = ('#dfile("tbl.b") and #dfile-short("tbl.a") '
                 'of #dfile-count() (#dfile-number("tbl.b")).')
        (d / "doc.typ").write_text(
            '#import "assets.typ": dfile, dfile-short, dfile-count, dfile-number\n'
            + prose + "\n")
        proc = subprocess.run(["typst", "compile", "--root", tmp, str(d / "doc.typ")],
                              capture_output=True, text=True)
        pdf = " ".join(subprocess.run(["pdftotext", str(d / "doc.pdf"), "-"],
                                      capture_output=True, text=True).stdout.split())
        try:
            typst_prose.DATA_FILES = typst_prose.data_file_registry(d)
            text = typst_prose.resolve_data_files(prose)
        except SystemExit as e:
            text = f"raised {e}"
        finally:
            typst_prose.DATA_FILES = saved
    if proc.returncode or pdf != text:
        print(f"  resolver [dfile]: the PDF printed {pdf!r}{proc.stderr[:200]}, "
              f"the text copies {text!r}")
        ok = False
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
