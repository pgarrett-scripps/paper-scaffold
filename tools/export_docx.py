#!/usr/bin/env python3
"""paper.resolved.typ -> paper.docx, through pandoc's real Typst reader.

WHY THIS PATH EXISTS. The HTML route (tools/typst2docx.py, `just docx-html`)
rasterizes every equation into a PNG, because Typst's HTML export drops math
outright and images were the only way back. Pandoc reads Typst natively --
a real evaluator -- and writes NATIVE, editable Word equations. The resolver
has already replaced every project helper with plain Typst, so what this
script feeds pandoc is exactly what a person would read in the source.

Two adaptations pandoc needs, both made here rather than in the resolver,
because they are pandoc's quirks and not properties of the manuscript:

  - `#bibliography(...)` is real Typst (the resolved file compiles standalone,
    references and all), but pandoc's reader parses the call without wiring it
    into citeproc. The call is swapped for a `= <title>` heading and the .bib
    paths and CSL style are handed to pandoc as flags; citeproc then sets the
    reference list under that heading.
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

import re
import sys
import zipfile
import io
import xml.etree.ElementTree as ET
from pathlib import Path

# The manuscript root, one level up: this file lives in tools/.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from resolve_typst import FLOAT_PREFIX, _call_span  # noqa: E402
from typst_prose import CITE  # noqa: E402
from bibliography import entries
from manuscript_sources import mask

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
    rendered = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(path, "w") as archive:
        for info, data in entries:
            archive.writestr(info, rendered if info.filename == "word/styles.xml" else data)


def split_bibliography(src: str) -> tuple[str, list[str], str | None]:
    """Swap the #bibliography call for its heading; return (src, paths, style).

    The heading is followed by a `#block[]<refs>` anchor: citeproc sets the
    reference list inside a Div with id "refs", and WITHOUT one it appends
    the list at the very end of the document -- which, now that the resolver
    keeps the call in the PDF's position, would strand the references after
    the entire SI. Pandoc's Typst reader turns the anchor into a Span, and
    tools/refs_div.lua promotes it to the Div citeproc looks for.

    Pure and separate from the pandoc run so the tests can hold it still.
    A resolved file without a bibliography passes through unchanged.
    """
    call = _call_span(src, "#bibliography(")
    if call is None:
        return src, [], None
    paths = [p.lstrip("/") for p in re.findall(r'"([^"]+\.(?:bib|yml|yaml|json))"', call)]
    style = re.search(r'style:\s*"([^"]+)"', call)
    title = re.search(r"title:\s*\[([^\]]*)\]", call)
    heading = (f"= {title.group(1) if title else 'Bibliography'}"
               "\n\n#block[]<refs>")
    return (src.replace(call, heading), paths,
            style.group(1) if style else None)


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


def main() -> int:
    if not SRC.is_file():
        print("error: paper.resolved.typ is missing -- run: just resolve",
              file=sys.stderr)
        return 1
    src, bib, style = split_bibliography(SRC.read_text())

    args = ["--fail-if-warnings", "--resource-path", str(ROOT)]
    if bib:
        try:
            missing = check_citations(src, [ROOT / b for b in bib])
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if missing:
            print("error: cited but not in the bibliography: "
                  + ", ".join(f"@{k}" for k in missing)
                  + " -- citeproc would ship each as bold prose and exit 0.",
                  file=sys.stderr)
            return 1
        # The Lua filter must precede --citeproc: pandoc applies filters in
        # command-line order, and the refs anchor has to be a Div before
        # citeproc goes looking for one.
        args += ["--lua-filter", str(ROOT / "tools" / "refs_div.lua")]
        args += ["--citeproc"]
        args += [f"--bibliography={ROOT / b}" for b in bib]
        csl = next((p for p in (ROOT / f"{style}.csl",
                                ROOT / "csl" / f"{style}.csl")
                    if style and p.is_file()), None)
        if csl:
            args += ["--csl", str(csl)]
        elif style:
            print(f'note: no {style}.csl in the manuscript root; citations '
                  f"use pandoc's default style (Chicago author-date). Drop "
                  f"the CSL file there to match the PDF.")

    import pypandoc
    pypandoc.convert_text(src, "docx", format="typst",
                          outputfile=str(OUT), extra_args=args)
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
