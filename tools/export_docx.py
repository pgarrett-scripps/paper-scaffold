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

from resolve_typst import FLOAT_PREFIX, SI_HEADING  # noqa: E402
from typst_prose import CITE  # noqa: E402
from bibliography import entries
from manuscript_sources import BIBLIOGRAPHY, call_span, mask
from word_xml import order_properties

SRC = ROOT / "paper.resolved.typ"
OUT = ROOT / "paper.docx"
MAIN_ONLY = False


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


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
PAGE_BREAK = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
TEXT_WIDTH_IN = 6.5
# A table this short is kept on one page; a longer one breaks between rows.
KEEP_TABLE_ROWS = 20
# Front-matter keys pandoc copies into docProps/custom.xml. Both hold
# absolute paths on the machine that built the file (spectrl-paper).
LOCAL_META = ("bibliography", "csl")


def text_width(reference: Path | None) -> float:
    """The body text width in inches: the reference document's page less
    its margins, or US Letter with 1 in margins when it sets none."""
    if reference is None or not reference.is_file():
        return TEXT_WIDTH_IN
    with zipfile.ZipFile(reference) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    size, margin = root.find(f".//{W}sectPr/{W}pgSz"), root.find(f".//{W}sectPr/{W}pgMar")
    if size is None or margin is None:
        return TEXT_WIDTH_IN
    twips = (int(size.get(W + "w")) - int(margin.get(W + "left", 0))
             - int(margin.get(W + "right", 0)))
    return twips / 1440 if twips > 0 else TEXT_WIDTH_IN


def adapt_tree(tree: dict, width_in: float = TEXT_WIDTH_IN) -> dict:
    """Pandoc-tree fixes for Word, in place; returns the tree.

    Each is a divergence between pandoc's Word output and the PDF that
    downstream papers patched locally before it came here:

      - `#pagebreak()` reads as a page-break Div around a horizontal rule,
        which Word drew as a line across the page. It becomes a real break.
      - `image(..., width: 70%)` kept the percentage, which the docx writer
        measures against a fixed 420 pt, not the text width, so every such
        figure came out narrower than in the PDF. It becomes inches.
      - The manuscript title is the head's `= Title`, which Word styled as
        the first Heading 1. It takes the Title style.
      - The .bib and .csl paths are dropped from the metadata, which pandoc
        writes into the file's custom properties as absolute local paths.
    """
    def image_width(attr) -> None:
        for pair in attr[2]:
            if pair[0] == "width" and pair[1].endswith("%"):
                try:
                    share = float(pair[1][:-1]) / 100
                except ValueError:
                    continue
                pair[1] = f"{width_in * share:.2f}in"

    def walk(value):
        if isinstance(value, list):
            for i, child in enumerate(value):
                if (isinstance(child, dict) and child.get("t") == "Div"
                        and "page-break" in child["c"][0][1]):
                    value[i] = {"t": "RawBlock", "c": ["openxml", PAGE_BREAK]}
                else:
                    walk(child)
        elif isinstance(value, dict):
            if value.get("t") == "Image":
                image_width(value["c"][0])
            for child in value.values():
                walk(child)

    walk(tree["blocks"])
    for i, block in enumerate(tree["blocks"]):
        if block.get("t") != "Header":
            continue
        if block["c"][0] == 1:
            tree["blocks"][i] = {"t": "Div", "c": [
                [block["c"][1][0], [], [["custom-style", "Title"]]],
                [{"t": "Para", "c": block["c"][2]}]]}
        break
    for key in LOCAL_META:
        tree.get("meta", {}).pop(key, None)
    return tree


def paginate(root: ET.Element) -> ET.Element:
    """Keep Word's page breaks where the PDF would put them, in place.

    Six downstream papers each wrote some of these rules against the same
    failures -- a figure on one page and its caption on the next, a table
    caption stranded above its table, a table row split across pages, a
    heading or bold run-in label left at the foot of a page, an empty page
    after a full-page table. They are general, so they run on every export:

      - A paragraph holding only a page break becomes pageBreakBefore on the
        next paragraph with content; the lone break after a table that
        filled its page otherwise produced a blank page.
      - An empty paragraph holding only bookmarks -- what pandoc makes of a
        `<label>` after a heading or float -- hands its bookmarks to the
        paragraph before it (past a table, to the table's caption) and goes;
        after a full-page table it could spill onto a page of its own.
      - Captions keep their lines together; a table caption and a figure's
        image keep with what follows (the table, the caption).
      - An empty paragraph after a heading, and a short paragraph whose text
        is all bold (a run-in label), keep with what follows.
      - Table rows never split; the first row repeats on each page; a table
        of at most KEEP_TABLE_ROWS rows stays on one page.

    Column widths are the source's business, not this pass's: `columns:
    (2fr, 1fr, 1fr)` reaches Word as proportional widths.
    """
    def props(element: ET.Element, name: str) -> ET.Element:
        found = element.find(W + name)
        if found is None:
            found = ET.Element(W + name)
            element.insert(0, found)
        return found

    def set_flag(element: ET.Element, name: str) -> None:
        flag = element.find(W + name)
        if flag is None:
            ET.SubElement(element, W + name)
        else:
            flag.attrib.pop(W + "val", None)

    def text(p: ET.Element) -> str:
        return "".join(t.text or "" for t in p.iter(W + "t"))

    def style(p: ET.Element) -> str:
        found = p.find(f"{W}pPr/{W}pStyle")
        return "" if found is None else found.get(W + "val", "")

    def content(p: ET.Element) -> bool:
        return (bool(text(p).strip()) or p.find(f".//{W}drawing") is not None
                or p.find(f".//{M}oMath") is not None)

    body = root.find(W + "body")
    pending = False
    previous = None
    for block in list(body):
        if block.tag != W + "p":
            continue
        breaks = [b for b in block.iter(W + "br") if b.get(W + "type") == "page"]
        if breaks and not content(block):
            body.remove(block)
            pending = True
            continue
        anchor = (block.find(W + "bookmarkStart") is not None and not content(block)
                  and all(c.tag in (W + "pPr", W + "bookmarkStart", W + "bookmarkEnd")
                          for c in block))
        if anchor and previous is not None:
            previous.extend(c for c in list(block) if c.tag != W + "pPr")
            body.remove(block)
            continue
        if pending and content(block):
            set_flag(props(block, "pPr"), "pageBreakBefore")
            pending = False
        previous = block

    blocks = list(body)
    for i, p in enumerate(blocks):
        if p.tag != W + "p":
            continue
        name = style(p)
        flags = []
        if name in ("ImageCaption", "TableCaption", "Caption"):
            flags.append("keepLines")
        if name == "TableCaption" or p.find(f".//{W}drawing") is not None:
            flags.append("keepNext")
        if (not content(p) and i and blocks[i - 1].tag == W + "p"
                and style(blocks[i - 1]).startswith("Heading")):
            flags.append("keepNext")
        runs = [r for r in p.iter(W + "r")
                if "".join(t.text or "" for t in r.iter(W + "t")).strip()]
        if (runs and len(text(p)) <= 120 and not name.startswith("Heading")
                and all(r.find(f"{W}rPr/{W}b") is not None for r in runs)):
            flags.append("keepNext")
        for flag in flags:
            set_flag(props(p, "pPr"), flag)

    for table in root.iter(W + "tbl"):
        rows = table.findall(W + "tr")
        for i, row in enumerate(rows):
            row_props = props(row, "trPr")
            set_flag(row_props, "cantSplit")
            if i == 0:
                set_flag(row_props, "tblHeader")
            if len(rows) <= KEEP_TABLE_ROWS and i < len(rows) - 1:
                for p in row.iter(W + "p"):
                    set_flag(props(p, "pPr"), "keepNext")
    order_properties(root)
    return root


def postprocess(path: Path) -> None:
    """Apply paginate() to a written .docx."""
    with zipfile.ZipFile(path) as archive:
        parts = [(info, archive.read(info)) for info in archive.infolist()]
    xml = next(data for info, data in parts if info.filename == "word/document.xml")
    for _, (prefix, uri) in ET.iterparse(io.BytesIO(xml), events=("start-ns",)):
        ET.register_namespace(prefix, uri)
    rendered = ET.tostring(paginate(ET.fromstring(xml)), encoding="utf-8",
                           xml_declaration=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for info, data in parts:
            archive.writestr(info, rendered if info.filename == "word/document.xml" else data)


def reorder(path: Path) -> None:
    """Put every property block back in schema order after a project step.

    Word refuses a file whose properties are out of the order the schema
    fixes ("unreadable content"), and a step that appends a <w:jc> after a
    <w:rPr> is the easiest way to write one. Run only after project steps,
    so a paper without them converts to the same bytes as before.
    """
    with zipfile.ZipFile(path) as archive:
        parts = [(info, archive.read(info)) for info in archive.infolist()]
    out = []
    for info, data in parts:
        if info.filename in ("word/document.xml", "word/styles.xml"):
            for _, (prefix, uri) in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
                ET.register_namespace(prefix, uri)
            root = ET.fromstring(data)
            order_properties(root)
            data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        out.append((info, data))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for info, data in out:
            archive.writestr(info, data)


def main_only(src: str) -> str:
    """The projection up to the Supporting Information, for journals that
    take the SI as a separate upload (koth-paper and d_noise-paper each
    exported this locally)."""
    at = src.find(SI_HEADING)
    if at < 0:
        return src
    head = src[:at].rstrip()
    if head.endswith("#pagebreak()"):
        head = head[:-len("#pagebreak()")].rstrip()
    return head + "\n"


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
        # Typst takes the title as content or as a string; the string form
        # fell back to "Bibliography" (koth-paper patched this).
        title = re.search(r'title:\s*(?:\[([^\]]*)\]|"([^"]*)")', call)
        name = (title.group(1) if title.group(1) is not None else title.group(2)) \
            if title else "Bibliography"
        heading = (f"= {name}"
                   "\n\n#block[]<refs>")
        out.append(Segment(src[at:start] + heading, paths,
                           style.group(1) if style else None))
        at = end
    tail = src[at:]
    if tail.strip() or not out:
        out.append(Segment(tail, [], None))
    return out


def cited_keys(src: str) -> set[str]:
    """Every citation key `src` cites; cross-reference prefixes excluded."""
    return {m.group(0)[1:] for m in re.finditer(r"(?<![\w\\:./-])" + CITE, mask(src, strings=True))
            if m.group(0)[1:].split(":", 1)[0] not in FLOAT_PREFIX}


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
    cited = cited_keys(src)
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
    if MAIN_ONLY:
        src = main_only(src)
    bib = sorted({b for seg in bibliography_segments(src) for b in seg.paths})
    try:
        tree = document(src, ROOT)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # The paper's own Word steps, from project.toml's [word] (docs/hooks.md).
    # ROOT is the captured manuscript during a build, which carries
    # project.toml and every file it names; with no project.toml, none.
    from project_hooks import load as load_project, run_word_steps
    try:
        word = load_project(ROOT).word
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    args = ["--fail-if-warnings", "--resource-path", str(ROOT)]
    reference = ROOT / "word/paper-reference.docx"
    if reference.is_file():
        args += ["--reference-doc", str(reference)]
    for lua in word.lua_filters:
        args += ["--lua-filter", str(ROOT / lua)]
    adapt_tree(tree, text_width(reference))
    import pypandoc
    pypandoc.convert_text(json.dumps(tree), "docx", format="json",
                          outputfile=str(OUT), extra_args=args)
    if not reference.is_file():
        style_code(OUT)
    tools = Path(__file__).resolve().parent
    try:
        run_word_steps(word.before_pagination, OUT, ROOT, tools)
        postprocess(OUT)
        if word.after_pagination:
            run_word_steps(word.after_pagination, OUT, ROOT, tools)
            reorder(OUT)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

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
    parser.add_argument("--main-only", action="store_true",
                        help="stop before the Supporting Information "
                             "(default output paper-main.docx)")
    args = parser.parse_args()
    MAIN_ONLY = args.main_only
    if MAIN_ONLY and args.output == OUT:
        args.output = OUT.with_name("paper-main.docx")
    OUT, ROOT, SRC = args.output, args.root, args.source
    raise SystemExit(main())
