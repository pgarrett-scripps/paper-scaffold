"""Both reference lists: references.bib itself, and the SI's own list."""
from __future__ import annotations

import io
import re
import shutil
import subprocess
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

    # Generational suffixes belong to nobody's surname. BibTeX's three-part
    # "Last, Jr, First", the braced "{Last III}", the unbraced "First Last III",
    # and Crossref's suffix-in-given all describe the registered "Yates, John
    # R". The three-part form once failed a correct author line as initial "I".
    registered_suffix = dict(metadata, author=[
        {"family": "Curie", "given": "Marie"},
        {"family": "Yates", "given": "John R. III"},
    ])
    for form in ("Yates, III, John R.", "{Yates III}, John R.",
                 "John R. Yates III", "Yates, John R."):
        suffixed = dict(entry, author=f"Curie, M. and {form}")
        if ba._metadata_issues(suffixed, "ok", registered_suffix):
            print(f"  bib-audit metadata: suffix form {form!r} broke author "
                  f"matching")
            ok = False
    # ...while an initial that spells a suffix ("V." for Vladimir) is kept,
    # and a different person with the same surname is still caught.
    vlado = dict(entry, author="Curie, M. and Einstein, V.")
    if [i.field for i in ba._metadata_issues(vlado, "ok", metadata)] != ["author"]:
        print("  bib-audit metadata: initial 'V.' was dropped as a suffix")
        ok = False

    short_title = dict(metadata, title=["An Example"])
    issues = ba._metadata_issues(entry, "ok", short_title)
    if [(item.field, item.fatal) for item in issues] != [("title", False)]:
        print("  bib-audit metadata: an incomplete registered title was not "
              "reported as a non-fatal review item")
        ok = False

    # Registry quirks that are not citation errors. A year one apart from the
    # registered print/online pair (2019/2020) is a New Year straddle: shown,
    # never fatal. A generic deposit title says nothing about the work. An
    # article number written "Article 123" is the registered "123". A record
    # whose accents became "?" and whose date is [[null]] still compares.
    quirks = [
        ("adjacent year", dict(entry, year="2021"), metadata,
         [("year", False)]),
        ("generic deposit title", entry,
         dict(metadata, title=["ProteomeXchange dataset"]), [("title", False)]),
        ("article number", dict(entry, pages="Article 123"),
         dict(metadata, page="123"), []),
        ("damaged accents", dict(entry, author="M{\\\"u}ller, M. and Einstein, A."),
         dict(metadata, author=[{"family": "Mu?ller", "given": "M."},
                                {"family": "Einstein", "given": "A."}]), []),
    ]
    if ba._years({"published-print": {"date-parts": [[None]]}}):
        print("  bib-audit metadata: a [[null]] date part became a year")
        ok = False
    for name, local, registered, want in quirks:
        got = [(i.field, i.fatal) for i in
               ba._metadata_issues(local, "ok", registered)]
        if got != want:
            print(f"  bib-audit metadata [{name}]: expected {want}, got {got}")
            ok = False

    # Two years away is not a straddle, so the wrong-work case needs it.
    wrong = dict(entry, title="A Different Paper",
                 author="Curie, Pierre and Einstein, Albert", year="2025")
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

    # Journal abbreviations. Crossref registers the full title, the entry
    # carries the ISO 4 / CASSI form a style wants, and the two must match
    # word for word: a prefix ("Proteome Res."), a contraction ("Natl."),
    # dropped stopwords. The negative cases are real miscitations: an
    # abbreviation of a different journal, and a journal whose name is the
    # first word of another's.
    venues = [
        ("J. Proteome Res.", "Journal of Proteome Research", True),
        ("Mol. Cell. Proteomics", "Molecular & Cellular Proteomics", True),
        ("Proc. Natl. Acad. Sci. U. S. A.", "Proceedings of the National "
         "Academy of Sciences of the United States of America", True),
        ("J. Am. Chem. Soc.", "Journal of the American Chemical Society", True),
        ("Journal of Proteome Research", "J. Proteome Res.", True),
        ("Anal. Chem.", "Analytical Biochemistry", False),
        ("Nature", "Nature Methods", False),
        ("Chem. Res.", "Chemical Reviews", False),
    ]
    for local, registered, want in venues:
        issues = ba._metadata_issues(dict(entry, journal=local), "ok",
                                     dict(metadata, **{"container-title": [registered]}))
        got = "venue" not in {i.field for i in issues}
        if got != want:
            print(f"  bib-audit venue: {local!r} vs registered {registered!r} "
                  f"matched={got}, expected {want}")
            ok = False
    # Crossref's own short-container-title counts as a registered venue.
    abbreviated = dict(metadata, **{"short-container-title": ["J. Ex."]})
    if ba._metadata_issues(dict(entry, journal="J Ex"), "ok", abbreviated):
        print("  bib-audit venue: short-container-title was not consulted")
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
    def run(allowed):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ba.audit(entries=[wrong], allowed=allowed, pause=False,
                          fetch=lambda doi, timeout: ("ok", metadata))
        return rc, out.getvalue()

    rc, _ = run(set())
    if rc != 1:
        print("  bib-audit metadata: a core mismatch did not fail the audit")
        ok = False

    # [allow].doi-metadata in prose-check.toml: the registrar is wrong, not
    # the entry. The key excuses every field; key:field excuses only that one,
    # so a wrong year beside an allowed author still fails. Excused mismatches
    # stay printed, and an allowance that excuses nothing is reported.
    rc, out = run({"curie2020"})
    if rc != 0 or "allowed by [allow].doi-metadata" not in out:
        print("  bib-audit allow: a key allowance did not excuse the entry")
        ok = False
    rc, _ = run({"curie2020:author", "curie2020:title"})
    if rc != 1:
        print("  bib-audit allow: key:field excused fields it did not name")
        ok = False
    rc, _ = run({"curie2020:author", "curie2020:title", "curie2020:year"})
    if rc != 0:
        print("  bib-audit allow: naming every mismatched field did not pass")
        ok = False
    rc, out = run({"curie2020:volume"})
    if "no longer excuse anything" not in out or "curie2020:volume" not in out:
        print("  bib-audit allow: an allowance matching nothing was not reported")
        ok = False

    # An entry with no DOI is identified only by its URL, and a URL is the
    # cheapest citation to invent. The audit resolves it: a dead one fails,
    # a live one prints what the page says about itself for a person to
    # compare, and an unreachable one is a network fact, not a defect. The
    # URL parser is pure so its two API routes stay pinned. (koth manuscript)
    if (ba._url_target("https://github.com/curie/tool.git")
            != ("github", "curie/tool")
            or ba._url_target("https://www.crates.io/crates/tool/")
            != ("crates", "tool")
            or ba._url_target("https://example.org/tool")[0] != "web"):
        print("  bib-audit url: a GitHub or crates.io URL was not routed to "
              "its API")
        ok = False
    url_entry = {"_key": "tool2024", "_type": "misc", "title": "{A} Tool",
                 "author": "Curie, Marie", "url": "https://github.com/curie/tool"}
    page = {"name": "curie/tool", "about": "A tool", "owner": "curie"}
    outcomes = {}
    for state, payload in (("ok", page), ("moved", page),
                           ("missing", "HTTP 404"), ("error", "timed out")):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            outcomes[state] = (ba.audit(
                entries=[url_entry], allowed=set(), pause=False,
                fetch=lambda doi, timeout: ("ok", {}),
                fetch_url=lambda url, timeout: (state, payload)),
                buf.getvalue())
    if outcomes["missing"][0] != 1:
        print("  bib-audit url: a dead URL did not fail the audit")
        ok = False
    if any(outcomes[s][0] != 0 for s in ("ok", "moved", "error")):
        print("  bib-audit url: a live, moved, or unreachable URL failed the "
              "audit")
        ok = False
    if ("A Tool" not in outcomes["ok"][1]
            or "owner curie" not in outcomes["ok"][1]):
        print("  bib-audit url: a live URL did not print the page beside the "
              "bibliography entry")
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

# The template's bibliographyx, as si-body.typ defines it: Alexandria's, but
# printing nothing -- heading included -- for an SI that cites nothing.
SI_BIBX = '''#import "@preview/alexandria:0.2.0": (
  get-bibliography, load-bibliography, render-bibliography,
)
#let bibliographyx(
  path,
  prefix: auto,
  title: auto,
  full: false,
  style: "ieee",
) = {
  load-bibliography(path, prefix: prefix, full: full, style: style)
  context {
    let bib = get-bibliography(prefix)
    if bib.references.len() > 0 { render-bibliography(bib, title: title) }
  }
}
'''


def empty_si_list_cases() -> bool:
    """An SI that cites nothing through the prefix has no reference list.

    koth-paper and uno-lfq-paper backed out of the SI's own list because
    Alexandria printed a bare "References" heading at the end of an SI that
    cited nothing. The template now prints nothing then, and the Word
    projection has to agree, or the SI docx ends on the same empty heading.
    """
    import resolve_typst as rt
    from manuscript_sources import si_citations
    ok = True
    config = '#let paper-bib-style = "american-chemical-society"'

    got = si_citations('A @si-a, #cite(<si-b>), @sec:si-x, @a. // @si-c\n'
                       '`@si-d` #link("mailto:x@si-e.org")', "si-")
    if got != ["si-a", "si-b"]:
        print(f"  si_citations: read {got}, expected ['si-a', 'si-b']")
        ok = False

    uncited = SI_BODY.replace("SI prose @si-b2020.", "SI prose, cross-ref @sec:si-x.")
    out = rt.resolve_si_bibliography(uncited, SI_PAPER, config)
    if "#bibliography" in out or "<si-references>" in out or "#set heading" in out:
        print(f"  resolve_si_bibliography: an SI citing nothing kept its list: {out!r}")
        ok = False
    if "cross-ref @sec:si-x." not in out:
        print(f"  resolve_si_bibliography: dropping the list lost prose: {out!r}")
        ok = False
    # `full: true` prints every entry whatever is cited, in both outputs.
    full = uncited.replace('prefix: "si-",', 'prefix: "si-",\n  full: true,')
    if "#bibliography(" not in rt.resolve_si_bibliography(full, SI_PAPER, config):
        print("  resolve_si_bibliography: a full: true list was dropped")
        ok = False

    if shutil.which("typst"):
        bib = ("@article{a2020, title={Alpha}, author={A, B}, year={2020}}\n"
               "@article{b2020, title={Beta}, author={C, D}, year={2020}}\n")
        for name, cite, want in (("cites nothing", "", False),
                                 ("cites one", " @si-b2020", True)):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "references.bib").write_text(bib)
                (root / "doc.typ").write_text(
                    '#import "@preview/alexandria:0.2.0": alexandria\n'
                    '#show: alexandria(prefix: "si-", read: p => read(p))\n'
                    + SI_BIBX + f"SI prose{cite}.\n"
                    '#bibliographyx("references.bib", prefix: "si-", '
                    'title: [SIREFS], style: "american-chemical-society") <si-references>\n'
                    '#context [#metadata(query(heading).len()) <n>]\n')
                proc = subprocess.run(
                    ["typst", "query", "--root", d, str(root / "doc.typ"), "<n>",
                     "--field", "value", "--one"], capture_output=True, text=True)
                if proc.returncode != 0:
                    print(f"  si list [{name}]: did not compile: {proc.stderr.strip()}")
                    ok = False
                elif (proc.stdout.strip() == "1") != want:
                    print(f"  si list [{name}]: {proc.stdout.strip()} heading(s), "
                          f"expected {1 if want else 0}")
                    ok = False
    return ok


def run_cases() -> bool:
    ok = True
    for case in (bibliography_cases, si_bibliography_cases, empty_si_list_cases,):
        ok &= case()
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
