"""Both reference lists: references.bib itself, and the SI's own list."""
from __future__ import annotations

import io
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

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

    # A resolving DOI is not proof that the fields beside it describe that
    # work. These cases stay pure and offline so the ordinary test suite catches
    # a metadata check that is weakened or accidentally removed.
    entry = {
        "_key": "curie2020",
        "_type": "article",
        "doi": "10.1/example",
        "title": "{An} Example: Results & Methods",
        "author": "Curie, M. and Einstein, Albert",
        "year": "2020",
        "journal": "Journal of Examples",
        "volume": "12",
        "issue": "3",
        "pages": "10--20",
    }
    metadata = {
        "title": ["<i>An</i> example: results &amp; methods"],
        "author": [
            {"family": "Curie", "given": "Marie"},
            {"family": "Einstein", "given": "A."},
        ],
        "published-print": {"date-parts": [[2020]]},
        "published-online": {"date-parts": [[2019]]},
        "container-title": ["Journal of Examples: Annual Proceedings"],
        "volume": "12",
        "issue": "3",
        "page": "10-20",
    }
    if ba._metadata_issues(entry, "ok", metadata):
        print("  bib-audit metadata: formatting-only differences were reported")
        ok = False

    tex_entry = dict(entry,
                     author=("Dan{\\v{c}}{\\'i}k, V. and "
                             "Weilnb{\\\"o}ck, Lisa and others"))
    tex_metadata = dict(metadata, author=[
        {"family": "Dančík", "given": "Vlado"},
        {"family": "Weilnböck", "given": "Lisa"},
        {"family": "Someone", "given": "Else"},
    ])
    if ba._metadata_issues(tex_entry, "ok", tex_metadata):
        print("  bib-audit metadata: TeX accents or 'and others' were reported")
        ok = False

    short_title = dict(metadata, title=["An Example"])
    issues = ba._metadata_issues(entry, "ok", short_title)
    if [(item.field, item.fatal) for item in issues] != [("title", False)]:
        print("  bib-audit metadata: an incomplete registered title was not "
              "reported as a non-fatal review item")
        ok = False

    wrong = dict(entry, title="A Different Paper",
                 author="Curie, Pierre and Einstein, Albert", year="2021")
    issues = ba._metadata_issues(wrong, "ok", metadata)
    fatal = {item.field for item in issues if item.fatal}
    if fatal != {"title", "author", "year"}:
        print("  bib-audit metadata: wrong core fields produced "
              f"{sorted(fatal)}, expected author/title/year")
        ok = False

    wrong_details = dict(entry, journal="Other Journal", volume="99",
                         issue="", number="8", pages="200--220")
    issues = ba._metadata_issues(wrong_details, "ok", metadata)
    warnings = {item.field for item in issues if not item.fatal}
    if warnings != {"venue", "volume", "issue", "pages"}:
        print("  bib-audit metadata: wrong detail fields produced "
              f"{sorted(warnings)}, expected issue/pages/venue/volume")
        ok = False

    datacite = {
        "titles": [{"title": "A Dataset"}],
        "creators": [{"familyName": "Curie", "givenName": "Marie"}],
        "publicationYear": 2020,
        "container": {"title": "Example Repository"},
    }
    data_entry = dict(entry, title="A Dataset", author="Curie, Marie",
                      journal="Example Repository")
    if ba._metadata_issues(data_entry, "datacite", datacite):
        print("  bib-audit metadata: matching DataCite fields were reported")
        ok = False

    # Exercise the command-level contract too: a mismatched title must make
    # preflight fail, not merely print an advisory that can scroll past.
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        rc = ba.audit(entries=[wrong],
                      fetch=lambda doi, timeout: ("ok", metadata), pause=False)
    if rc != 1:
        print("  bib-audit metadata: a core mismatch did not fail the audit")
        ok = False
    return ok

# A minimal manuscript whose SI sets its own reference list, as the scaffold
# writes one: the routing show rule in paper.typ, the list at the foot of
# si-body.typ, and one prefixed citation.
SI_PAPER = ('''#import "@preview/alexandria:0.2.0": alexandria
#show: alexandria(prefix: "si-", read: p => read(p))
// >>> BODY START
Main text @a2020.
// <<< BODY END
#bibliography("references.bib", title: [References], style: paper-bib-style)
#include "si-body.typ"
''')

SI_BODY = ('''#import "@preview/alexandria:0.2.0": bibliographyx
SI prose @si-b2020.
#set heading(numbering: none)
#bibliographyx(
  "references.bib",
  prefix: "si-",
  title: [References],
  style: paper-bib-style,
) <si-references>
''')


def si_bibliography_cases() -> bool:
    """The SI's own reference list, which every text-level tool has to see.

    Typst allows one native #bibliography per document, so an SI that ships
    to the journal as its own file gets its list from Alexandria and routes
    citations to it by prefix. Nothing about the rendered page says which
    list a citation went to, which is why the prefix is checked here rather
    than left to review.
    """
    import prose_check as pc
    import resolve_typst as rt
    from manuscript_sources import si_bibliography, without_si_bibliography
    ok = True
    sources = {"paper.typ": SI_PAPER, "si-body.typ": SI_BODY}

    si = si_bibliography(sources=sources)
    if si["prefix"] != "si-" or si["list_prefix"] != "si-":
        print(f"  si_bibliography: read the prefixes as {si['prefix']!r} / "
              f"{si['list_prefix']!r}")
        ok = False
    if si["paths"] != ["references.bib"]:
        print(f"  si_bibliography: read the bib paths as {si['paths']!r}")
        ok = False
    # The block spans the `#set` line and the trailing label as well as the
    # call: a `#set heading(numbering: none)` left behind with no list under
    # it silently unnumbers whatever follows.
    block = SI_BODY[slice(*si["block"])]
    if not block.startswith("#set heading") or not block.endswith("<si-references>"):
        print(f"  si_bibliography: the block is not the whole arrangement: "
              f"{block!r}")
        ok = False

    # Removed for the review text; the prefix goes with it, because it is
    # Alexandria's routing tag and no key in the .bib carries it.
    stripped = without_si_bibliography(SI_BODY, SI_PAPER)
    if "#bibliographyx(" in stripped or "<si-references>" in stripped:
        print(f"  without_si_bibliography: the list survived: {stripped!r}")
        ok = False
    if "@b2020" not in stripped or "@si-b2020" in stripped:
        print(f"  without_si_bibliography: the citation kept its routing "
              f"prefix: {stripped!r}")
        ok = False

    # Rewritten for the Word projection: a plain call pandoc can read, with
    # the style resolved from config.typ, since the #let does not travel.
    config = '#let paper-bib-style = "american-chemical-society"'
    out = rt.resolve_si_bibliography(SI_BODY, SI_PAPER, config)
    if "#bibliographyx(" in out or "#bibliography(" not in out:
        print(f"  resolve_si_bibliography: the call was not made plain: {out!r}")
        ok = False
    if 'style: "american-chemical-society"' not in out or "prefix:" in out:
        print(f"  resolve_si_bibliography: style/prefix arguments are wrong: "
              f"{out!r}")
        ok = False

    # Prefixes that disagree do not compile, but Typst reports it from inside
    # the Alexandria package, pointing at neither line.
    try:
        rt.resolve_si_bibliography(SI_BODY.replace('prefix: "si-"',
                                                   'prefix: "sup-"'),
                                   SI_PAPER, config)
        print("  resolve_si_bibliography: mismatched prefixes were accepted")
        ok = False
    except rt.ResolveError:
        pass

    bib = ("@article{a2020,\n  title = {One},\n  year = {2020},\n"
           "  doi = {10.1/a},\n}\n@article{b2020,\n  title = {Two},\n"
           "  year = {2020},\n  doi = {10.1/b},\n}\n")
    cases = [
        ("routed correctly", SI_BODY, []),
        # The failure this exists for: a bare @key in the SI renders a
        # perfectly ordinary superscript and joins the MAIN reference list.
        ("bare key in the SI", SI_BODY.replace("@si-b2020", "@b2020"),
         ["misrouted-citation"]),
        ("prefixes disagree", SI_BODY.replace('prefix: "si-"', 'prefix: "x-"'),
         ["si-bibliography-prefix"]),
    ]
    for name, si_body, want in cases:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "references.bib").write_text(bib)
            (root / "paper.typ").write_text(SI_PAPER)
            (root / "si-body.typ").write_text(si_body)
            got = sorted({f.rule for f in pc.check_si_bibliography(root)})
            if got != sorted(want):
                print(f"  si bibliography [{name}]: expected {sorted(want)}, "
                      f"got {got}")
                ok = False
            # A work cited ONLY in the SI is cited as @si-key and its entry is
            # `key`; without the prefix stripped every one reads as uncited.
            if not want:
                rules = {f.rule for f in pc.check_bibliography(root)}
                if "uncited-reference" in rules:
                    print("  si bibliography: an SI-only citation was reported "
                          "as an uncited entry")
                    ok = False

    # A manuscript with no SI list at all -- every project that predates this
    # -- must look exactly as it did.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "paper.typ").write_text("Main @a2020.\n")
        (root / "si-body.typ").write_text("SI prose.\n")
        if si_bibliography(root) is not None or pc.check_si_bibliography(root):
            print("  si bibliography: a manuscript with one list was treated "
                  "as having two")
            ok = False
    return ok

def run_cases() -> bool:
    ok = True
    for case in (bibliography_cases, si_bibliography_cases,):
        ok &= case()
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
