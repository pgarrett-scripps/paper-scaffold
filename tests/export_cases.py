"""The pandoc export path: crossref numbering, bibliography, key checks."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

def run_cases() -> bool:
    """The pandoc export path: crossref numbering, bibliography, key checks.

    Pandoc renders a Typst ref as an EMPTY link, so a wrong number here is a
    cross-reference that silently reads wrong in the Word file -- and a
    missing citation key ships as bold prose at exit 0. Both get exact cases.
    """
    import tempfile

    import export_docx as ex
    import resolve_typst as rt
    ok = True

    # The numbering the PDF shows, reimplemented: floats per kind in document
    # order (tbl and tab share the Table counter), headings nest, the SI
    # marker resets everything with an "S" prefix.
    body = (
        "= Intro <sec:i>\n"
        "prose\n"
        '#figure(image("a.png"), caption: [First light.]) <fig:a>\n'
        "== Deep\n<sec:d>\n"  # label wrapped onto its own line, as typstyle may
        "#figure(table()) <tbl:t>\n"
        "#figure(table()) <tab:u>\n"
        "$ x $ <eq:e>\n"
        "\x00SI\x00\n= SI Methods <sec:s>\n"
        '#figure(image("b.png"), caption: [Appendix view.]) <fig:b>\n'
        "see #ref(<fig:a>), #ref(<tbl:t>), #ref(<tab:u>), #ref(<eq:e>), "
        "#ref(<sec:d>), #ref(<sec:s>), #ref(<fig:b>), "
        "figure(ref(<fig:b>, supplement: none)) and "
        "S#ref(<fig:b>, supplement: none) and `#ref(<fig:a>)` verbatim\n")
    try:
        got = rt.resolve_crossrefs("also #ref(<fig:a>) in the abstract\n\n",
                                   body)
    except (Exception, SystemExit) as e:
        print(f"  crossrefs: raised {type(e).__name__}: {e}")
        got = ""
        ok = False
    for want in ("see Figure 1,", " Table 1,", " Table 2,", " Equation 1,",
                 " Section 1.1,", " Section S1,", " Figure S1,",
                 "figure([S1])",        # code mode: a content block, not bare words
                 "and SS1 and",         # supplement: none -> the bare number
                 "`#ref(<fig:a>)` verbatim",   # raw spans stay verbatim
                 "also Figure 1 in the abstract",   # replaced in head too
                 # The count is written into the definitions too: pandoc
                 # numbers nothing, so captions and headings carry the PDF's
                 # numbers as literal text. Main-text headings use arkheion's
                 # "1." pattern (trailing dot); the SI's own function has none.
                 "caption: [Figure 1: First light.]",
                 "caption: [Figure S1: Appendix view.]",
                 "= 1. Intro",
                 "== 1.1. Deep",
                 "= S1 SI Methods"):
        if want not in got:
            print(f"  crossrefs: expected {want!r} in the resolved text")
            ok = False
    if "\x00" in got:
        print("  crossrefs: the SI marker leaked into the output")
        ok = False
    try:
        rt.resolve_crossrefs("", "see #ref(<fig:ghost>)\n")
        print("  crossrefs: a ref to a nonexistent label was accepted")
        ok = False
    except rt.ResolveError:
        pass

    # The bibliography call is carried through with its style identifier
    # resolved from config.typ; commented-out calls are not calls.
    cases = [
        ("style identifier resolves",
         '#bibliography("r.bib", style: paper-bib-style)',
         '#let paper-bib-style = "acs"',
         '#bibliography("r.bib", style: "acs")'),
        ("literal style passes through",
         '#bibliography("r.bib", style: "nature")', "",
         '#bibliography("r.bib", style: "nature")'),
        ("no bibliography is legal", "just prose", "", ""),
        ("a commented call is not a call",
         '// #bibliography("r.bib")', "", ""),
    ]
    for name, paper, config, want in cases:
        try:
            got = rt.bibliography_line(paper, config)
        except (Exception, SystemExit) as e:
            print(f"  bibliography [{name}]: raised {type(e).__name__}: {e}")
            ok = False
            continue
        if got != want:
            print(f"  bibliography [{name}]: expected {want!r}, got {got!r}")
            ok = False
    try:
        rt.bibliography_line('#bibliography("r.bib", style: mystery)', "")
        print("  bibliography: an unresolvable style identifier was accepted")
        ok = False
    except rt.ResolveError:
        pass

    # The exporter swaps the call for its own heading and hands the paths on.
    (seg,) = ex.bibliography_segments(
        'prose\n#bibliography("references.bib", title: [References], '
        'style: "acs")\n')
    if "= References" not in seg.text or "#bibliography" in seg.text:
        print("  bibliography_segments: the call did not become its heading")
        ok = False
    if seg.paths != ["references.bib"] or seg.style != "acs":
        print(f"  bibliography_segments: got paths {seg.paths!r}, "
              f"style {seg.style!r}")
        ok = False
    # Citeproc puts the reference list inside a Div with id "refs" and
    # otherwise appends it at the very END -- after the entire SI. The
    # heading must carry the anchor refs_div.lua promotes into that Div.
    if "#block[]<refs>" not in seg.text:
        print("  bibliography_segments: the <refs> anchor is missing -- the "
              "reference list would land after the SI")
        ok = False

    # The SI's own reference list is a SECOND call, and citeproc sets one
    # list per run: each segment is converted separately and the trees are
    # joined. A segment that kept the other half's prose would print the
    # main text's citations in the SI's list.
    main, si = ex.bibliography_segments(
        'main @a\n#bibliography("references.bib", style: "acs")\n'
        'SI prose @b\n#bibliography("si.bib", title: [References], '
        'style: "acs")\n')
    if "main @a" not in main.text or "SI prose" in main.text:
        print(f"  bibliography_segments: the main segment is wrong: "
              f"{main.text!r}")
        ok = False
    if "SI prose @b" not in si.text or "main @a" in si.text:
        print(f"  bibliography_segments: the SI segment is wrong: "
              f"{si.text!r}")
        ok = False
    if si.paths != ["si.bib"]:
        print(f"  bibliography_segments: the SI list reads the wrong "
              f"bibliography: {si.paths!r}")
        ok = False
    if main.text.count("<refs>") != 1 or si.text.count("<refs>") != 1:
        print("  bibliography_segments: each segment needs exactly one "
              "citeproc anchor")
        ok = False

    # Prose after the last list still travels, in its own segment.
    segments = ex.bibliography_segments(
        'body\n#bibliography("r.bib")\nafterword\n')
    if len(segments) != 2 or "afterword" not in segments[-1].text:
        print(f"  bibliography_segments: back matter after the last list was "
              f"dropped: {[s.text for s in segments]!r}")
        ok = False
    # A projection with no bibliography at all is one plain segment, which
    # is the single conversion this did before segments existed.
    (plain,) = ex.bibliography_segments("just prose\n")
    if plain.text != "just prose\n" or plain.paths:
        print(f"  bibliography_segments: a manuscript with no bibliography "
              f"changed shape: {plain!r}")
        ok = False

    # A cited key with no entry is the failure citeproc ships at exit 0.
    with tempfile.NamedTemporaryFile("w", suffix=".bib") as bib:
        bib.write("@article{real2020,\n  title={x}\n}\n")
        bib.flush()
        p = Path(bib.name)
        missing = ex.check_citations("cite @real2020. and @ghost2020 here",
                                     [p])
        if missing != ["ghost2020"]:
            print(f"  check_citations: expected ['ghost2020'], got {missing!r}")
            ok = False
        # An author email's @, both as Typst escapes it in prose and inside a
        # mailto: string -- neither is citation syntax to Typst, and each
        # briefly failed the export as "@scripps not in the bibliography".
        missing = ex.check_citations(
            'write to #link("mailto:pgarrett@scripps.edu")'
            "[pgarrett\\@scripps.edu] today", [p])
        if missing:
            print(f"  check_citations: an email's @ was read as a citation "
                  f"key: {missing!r}")
            ok = False

    # The back matter travels: sliced from BODY END to the bibliography,
    # never into the SI-appendix machinery (page break, counter surgery).
    fake = ("// >>> BODY START -- t\nbody prose\n// <<< BODY END -- t\n"
            "#heading(numbering: none)[Associated Content]\n\n"
            "Data are available.\n\n"
            '#bibliography("r.bib")\n#pagebreak()\n#counter(heading).update(0)\n')
    back = rt._back_matter(fake, {})
    if "Associated Content" not in back or "Data are available." not in back:
        print(f"  back matter: the sections were dropped: {back!r}")
        ok = False
    if "#bibliography" in back or "#pagebreak" in back or "#counter" in back:
        print(f"  back matter: appendix machinery leaked in: {back!r}")
        ok = False

    # The TOC graphic and its caption, from the front-matter bindings; the
    # caption's bracket walk must survive a nested pair.
    assets = {"fig.x": {"path": "figures/example_figure.png"}}
    fake = ("#let toc-caption = [At a [nested] glance.]\n"
            '#let toc-graphic = fig("fig.x", width: 92%)\n'
            "// >>> BODY START -- t\nbody\n// <<< BODY END -- t\n")
    blk = rt._toc_block(fake, assets)
    if 'image("figures/example_figure.png", width: 92%)' not in blk:
        print(f"  toc block: the graphic did not resolve: {blk!r}")
        ok = False
    if "_At a [nested] glance._" not in blk:
        print(f"  toc block: the caption was truncated or dropped: {blk!r}")
        ok = False
    if rt._toc_block("// >>> BODY START -- t\nb\n// <<< BODY END -- t\n", {}):
        print("  toc block: a manuscript without one produced content")
        ok = False
    # `toc-graphic = none` is the documented way to say "no graphic" while
    # keeping the placement block in paper.typ; it must not leak `#none`.
    if rt._toc_block("#let toc-graphic = none\n#let toc-caption = [c]\n"
                     "// >>> BODY START -- t\nb\n// <<< BODY END -- t\n", {}):
        print("  toc block: toc-graphic = none produced content")
        ok = False

    # The author line carries affiliation superscripts -- the numbers Typst
    # derived, joined for a shared appointment, absent when an author has
    # none to point at. Without them the export showed a bare name list
    # above a numbered affiliation list nothing pointed into.
    line = rt._author_line({"authors": [
        {"name": "A. Uthor", "affils": [1]},
        {"name": "B. Oth", "affils": [1, 2]},
        {"name": "C. Lone", "affils": []}]})
    if line != "A. Uthor#super[1], B. Oth#super[1,2], C. Lone":
        print(f"  author line: got {line!r}")
        ok = False

    # The SI title block is a #heading CALL on purpose: `= ` markup would
    # tick the crossref pass's counter and number the SI's first real
    # section S2. Its author line is the PLAIN names (si-authors), and the
    # probe's records must feed it as cleanly as a test's bare strings.
    si_title = rt._si_title(
        {"title": "T", "authors": [{"name": "A. Uthor", "affils": [1]}]})
    if "_A. Uthor_" not in si_title or "#super" in si_title:
        print(f"  si title: author records leaked markers: {si_title!r}")
        ok = False
    si_title = rt._si_title({"title": "T", "authors": ["A. Uthor"]})
    if "[Supporting Information]" not in si_title or "_A. Uthor_" not in si_title:
        print(f"  si title: missing pieces: {si_title!r}")
        ok = False
    if re.search(r"(?m)^=+ ", si_title):
        print("  si title: a markup heading would steal the SI's S1")
        ok = False
    return ok

if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
