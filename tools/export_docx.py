#!/usr/bin/env python3
"""paper.resolved.typ -> paper.docx, through pandoc's real Typst reader.

WHY THIS PATH EXISTS. The route it replaced went through Typst's HTML export,
which drops math outright, so every equation came back as a rasterized PNG;
it was removed once this one earned trust. Pandoc reads Typst natively --
a real evaluator -- and writes NATIVE, editable Word equations. The resolver
has already replaced every project helper with plain Typst, so what this
script feeds pandoc is exactly what a person would read in the source.

Two adaptations pandoc needs, both made here rather than in the resolver,
because they are pandoc's quirks and not properties of the manuscript:

  - `#bibliography(...)` is real Typst, but pandoc's reader parses the call
    without wiring it into citeproc. Each call is swapped for a `= <title>`
    heading and the .bib paths and CSL style are handed to pandoc as flags;
    citeproc then sets the reference list under that heading. A manuscript
    whose Supporting Information carries its own list has two calls, and
    citeproc sets one list per run, so each stretch is converted separately
    and the Pandoc trees joined. (That projection no longer compiles as a
    standalone Typst document, which a one-list one does: Typst refuses the
    second call. Nothing in this pipeline compiles it.)
  - The CSL style: Typst bundles styles by name ("american-chemical-society");
    pandoc wants a .csl FILE. If <style>.csl or csl/<style>.csl exists in the
    manuscript root it is used; otherwise pandoc's default (Chicago
    author-date) applies, with a printed note -- visibly different citations,
    not silently different numbers.

Every citation key is checked against the .bib file(s) BEFORE conversion.
Citeproc renders a missing key as bold text plus a warning and still exits 0,
which is exactly the kind of shipped-anyway failure this pipeline exists to
refuse.

Usage: uv run python tools/export_docx.py     (via `just docx`)
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
import io
import xml.etree.ElementTree as ET
from pathlib import Path

# The manuscript root, one level up: this file lives in tools/.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from typing import NamedTuple  # noqa: E402

from resolve_typst import FLOAT_PREFIX  # noqa: E402
from typst_prose import CITE  # noqa: E402
from bibliography import entries
from manuscript_sources import BIBLIOGRAPHY, call_span, mask
from word_xml import order_properties

SRC = ROOT / "paper.resolved.typ"
OUT = ROOT / "paper.docx"


def style_code(path: Path) -> None:
    """Style native Pandoc code without changing its text or token colors.

    Only styles.xml changes. Code stays selectable/editable, with source line
    breaks and indentation intact. Long paragraphs may split across pages.
    Pandoc's default highlighting supplies the language-specific token styles.
    """
    with zipfile.ZipFile(path) as archive:
        entries = [(info, archive.read(info)) for info in archive.infolist()]
    xml = next(data for info, data in entries if info.filename == "word/styles.xml")
    for _, (prefix, uri) in ET.iterparse(io.BytesIO(xml), events=("start-ns",)):
        ET.register_namespace(prefix, uri)
    root = ET.fromstring(xml)
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

    def child(parent, name, **attrs):
        element = parent.find(w + name)
        if element is None:
            element = ET.SubElement(parent, w + name)
        element.attrib.update({w + key: str(value) for key, value in attrs.items()})
        return element

    for style in root.findall(w + "style"):
        name = style.get(w + "styleId")
        if name not in ("SourceCode", "VerbatimChar"):
            continue
        run = child(style, "rPr")
        child(run, "rFonts", ascii="DejaVu Sans Mono", hAnsi="DejaVu Sans Mono")
        child(run, "sz", val=18)
        child(run, "szCs", val=18)
        if name == "SourceCode":
            paragraph = child(style, "pPr")
            child(paragraph, "wordWrap", val=1)
            child(paragraph, "keepNext", val=0)
            child(paragraph, "keepLines", val=0)
            border = child(paragraph, "pBdr")
            for edge in ("top", "left", "bottom", "right"):
                child(border, edge, val="single", sz=4, space=6, color="F4F6F8")
            child(paragraph, "shd", val="clear", fill="F4F6F8")
            child(paragraph, "ind", left=160, right=160)
            child(paragraph, "spacing", before=160, after=160, line=260, lineRule="auto")
    order_properties(root)
    rendered = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(path, "w") as archive:
        for info, data in entries:
            archive.writestr(info, rendered if info.filename == "word/styles.xml" else data)


class Segment(NamedTuple):
    """One stretch of the manuscript and the reference list that closes it."""
    text: str
    paths: list[str]
    style: str | None


def bibliography_segments(src: str) -> list[Segment]:
    """Split the projection at each #bibliography call, one segment apiece.

    Each call is swapped for its heading plus a `#block[]<refs>` anchor:
    citeproc sets the reference list inside a Div with id "refs", and WITHOUT
    one it appends the list at the very end of the document -- which, now
    that the resolver keeps the call in the PDF's position, would strand the
    references after the entire SI. Pandoc's Typst reader turns the anchor
    into a Span, and tools/refs_div.lua promotes it to the Div citeproc
    looks for.

    WHY SEGMENTS. A manuscript whose Supporting Information ships as its own
    file needs its own reference list, and one citeproc run produces exactly
    one: every citation in the document lands in a single list. So each list
    gets its own run over its own stretch of text, and the resulting Pandoc
    trees are joined. The PDF reaches the same place by a different route --
    Typst allows one native #bibliography, so the SI's is set by Alexandria
    and tools/resolve_typst.py rewrites it into the second plain call read
    here.

    Pure and separate from the pandoc run so the tests can hold it still. A
    projection with no bibliography is one segment with no paths, which is
    the same single conversion this did before segments existed.
    """
    out: list[Segment] = []
    at = 0
    while (span := call_span(src, BIBLIOGRAPHY, start=at)) is not None:
        start, end = span
        call = src[start:end]
        paths = [p.lstrip("/") for p in
                 re.findall(r'"([^"]+\.(?:bib|yml|yaml|json))"', call)]
        style = re.search(r'style:\s*"([^"]+)"', call)
        title = re.search(r"title:\s*\[([^\]]*)\]", call)
        heading = (f"= {title.group(1) if title else 'Bibliography'}"
                   "\n\n#block[]<refs>")
        out.append(Segment(src[at:start] + heading, paths,
                           style.group(1) if style else None))
        at = end
    tail = src[at:]
    if tail.strip() or not out:
        out.append(Segment(tail, [], None))
    return out


def check_citations(src: str, bib_paths: list[Path]) -> list[str]:
    """Every @key cited but not defined by the bibliography files.

    Float and section prefixes are cross-references, already resolved to
    literal text by the resolver; anything else surviving as `@key` is a
    citation and must have an entry, or citeproc ships it as bold prose.
    typst_prose.CITE decides what a key looks like -- one authority, so a
    trailing period is prose here exactly as it is everywhere else. One
    guard on top of it: an `@` that is escaped (`\\@scripps` in the author
    email) or mid-word (`"mailto:pgarrett@scripps.edu"`) is not citation
    syntax to Typst and must not be one here -- both live in the back
    matter, and each briefly failed this check as "@scripps not in the
    bibliography".
    """
    cited = {m.group(0)[1:] for m in re.finditer(r"(?<![\w\\:./-])" + CITE, mask(src, strings=True))
             if m.group(0)[1:].split(":", 1)[0] not in FLOAT_PREFIX}
    known: set[str] = set()
    for p in bib_paths:
        known.update(e["_key"] for e in entries(p))
    return sorted(cited - known)


def namespace_refs(value, prefix: str) -> None:
    """Keep citeproc's anchors distinct across two reference lists.

    Each citeproc run numbers from 1 and names its entries `ref-<key>`, so a
    work cited in both the main text and the SI would otherwise land in the
    Word file as two bookmarks with one id, and every link to it would jump
    to whichever Word kept. The same rename as
    tools/document_docx.py:namespace_ids, which does this per chapter;
    the two paths share the constraint, not the code, because that one
    carries the dissertation template with it.

    Renaming the "refs" Div also drops pandoc's own styling of it, so the
    Word Bibliography style is named explicitly in its place.
    """
    if isinstance(value, list):
        for child in value:
            namespace_refs(child, prefix)
    elif isinstance(value, dict):
        kind, c = value.get("t"), value.get("c")
        if kind == "Div" and c[0][0] == "refs":
            c[0][2].append(["custom-style", "Bibliography"])
        if kind in ("Div", "Span", "CodeBlock", "Code", "Link", "Image",
                    "Table", "Figure") and (
                c[0][0] == "refs" or c[0][0].startswith("ref-")):
            c[0][0] = prefix + c[0][0]
        if kind == "Link" and c[2][0].startswith("#ref-"):
            c[2][0] = "#" + prefix + c[2][0][1:]
        for child in value.values():
            namespace_refs(child, prefix)


def document(src: str, root: Path, *, note=print) -> dict:
    """The projection as one Pandoc tree, one citeproc run per reference list.

    Raises ValueError naming every citation with no entry: citeproc renders
    one as bold text plus a warning and still exits 0, which is exactly the
    kind of shipped-anyway failure this pipeline exists to refuse.
    """
    import pypandoc
    segments = bibliography_segments(src)
    merged: dict | None = None
    seen: set[str] = set()
    for i, seg in enumerate(segments):
        args = ["--fail-if-warnings", "--resource-path", str(root)]
        if seg.paths:
            missing = check_citations(seg.text, [root / b for b in seg.paths])
            if missing:
                raise ValueError(
                    "cited but not in the bibliography: "
                    + ", ".join(f"@{k}" for k in missing)
                    + " -- citeproc would ship each as bold prose and exit 0.")
            # The Lua filter must precede --citeproc: pandoc applies filters
            # in command-line order, and the refs anchor has to be a Div
            # before citeproc goes looking for one. Taken from the snapshot
            # when there is one -- it materializes tools/ alongside its
            # sources, so a review of an older version filters the way that
            # version did -- and otherwise from beside this file, which is
            # right wherever the manuscript root has been pointed.
            lua = root / "tools" / "refs_div.lua"
            if not lua.is_file():
                lua = Path(__file__).resolve().parent / "refs_div.lua"
            args += ["--lua-filter", str(lua)]
            args += ["--citeproc"]
            args += [f"--bibliography={root / b}" for b in seg.paths]
            csl = next((p for p in (root / f"{seg.style}.csl",
                                    root / "csl" / f"{seg.style}.csl")
                        if seg.style and p.is_file()), None)
            if csl:
                args += ["--csl", str(csl)]
            elif seg.style and seg.style not in seen:
                seen.add(seg.style)
                note(f'note: no {seg.style}.csl in the manuscript root; '
                     f"citations use pandoc's default style (Chicago "
                     f"author-date). Drop the CSL file there to match the PDF.")
        tree = json.loads(pypandoc.convert_text(seg.text, "json",
                                                format="typst",
                                                extra_args=args))
        # The first list keeps citeproc's own ids, so a manuscript with one
        # bibliography -- every project that predates the SI's own list --
        # converts to exactly the bytes it did before.
        if i:
            namespace_refs(tree["blocks"], f"s{i}-")
        if merged is None:
            merged = tree
        else:
            merged["blocks"] += tree["blocks"]
    return merged


def main() -> int:
    if not SRC.is_file():
        print("error: paper.resolved.typ is missing -- run: just resolve",
              file=sys.stderr)
        return 1
    src = SRC.read_text()
    bib = sorted({b for seg in bibliography_segments(src) for b in seg.paths})
    try:
        tree = document(src, ROOT)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    args = ["--fail-if-warnings", "--resource-path", str(ROOT)]
    reference = ROOT / "word/paper-reference.docx"
    if reference.is_file():
        args += ["--reference-doc", str(reference)]
    import pypandoc
    pypandoc.convert_text(json.dumps(tree), "docx", format="json",
                          outputfile=str(OUT), extra_args=args)
    if not reference.is_file():
        style_code(OUT)

    # Trust, then verify: count what actually landed in the file.
    with zipfile.ZipFile(OUT) as z:
        doc = z.read("word/document.xml").decode("utf-8", errors="replace")
    n_math = doc.count("<m:oMath>")
    n_tbl = doc.count("<w:tbl>")
    n_img = doc.count("<pic:pic ") + doc.count("<pic:pic>")
    mb = OUT.stat().st_size / 1e6
    print(f"wrote {OUT.name} ({mb:.1f} MB) -- {n_math} native equations, "
          f"{n_tbl} tables, {n_img} images"
          + (f", references set from {', '.join(bib)}" if bib else ""))
    return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source", type=Path, default=SRC)
    args = parser.parse_args()
    OUT, ROOT, SRC = args.output, args.root, args.source
    raise SystemExit(main())
