"""The single paper's Word reference document, generated from [word.style].

pandoc takes every paragraph and character style of paper.docx from a
reference document. The Word export never compiles the Typst preamble, so
the paper's look reaches Word only through this file. It used to be a
tracked binary, word/paper-reference.docx, that each paper edited in Word
and every upgrade then had to diff by eye. Now it is generated: pandoc's
default, the scaffold's stock adjustments (single-spaced figures and
references, code in DejaVu Sans Mono, black title and headings), then the
settings in project.toml's [word.style]. docs/word-export.md lists them.

The result is cached under .build-state/word-reference/, keyed by a hash of
the settings, this tool, the code styling in export_docx.py and the pandoc
version, so an export regenerates it only when one of those changes. The
staleness record already covers both: project.toml is a build input, and
this file is one of the build tools.

    uv run paper tool paper_word_reference            # generate; print path
    uv run paper tool paper_word_reference --translate word/paper-reference.docx
        # the [word.style] that reproduces an old hand-edited template, or
        # what no setting can express
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from word_xml import order_properties, W

from paths import ROOT, TOOLS  # the manuscript; the toolchain's tools (tools/paths.py)

# The stock values; a [word.style] key left out keeps these (or pandoc's).
STOCK = {"title_color": "000000", "heading_color": "000000"}
HEADINGS = tuple(f"Heading{i}" for i in range(1, 10))
LETTER = ("12240", "15840")   # US Letter in twips, when margins need a page


def tag(name: str) -> str:
    return "{" + W + "}" + name


def child(parent, name: str):
    element = parent.find(tag(name))
    if element is None:
        element = ET.SubElement(parent, tag(name))
    return element


def parse(data: bytes):
    """Parse a part, keeping its namespace prefixes for the rewrite."""
    for _, (prefix, uri) in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
        ET.register_namespace(prefix, uri)
    return ET.fromstring(data)


def set_color(props, value: str) -> None:
    color = child(props, "color")
    color.attrib.clear()
    color.set(tag("val"), value)


def set_font(fonts, family: str) -> None:
    """Concrete faces in place of the theme's, for Latin and complex script."""
    for face in ("ascii", "hAnsi", "cs"):
        fonts.set(tag(face), family)
    for theme in ("asciiTheme", "hAnsiTheme", "cstheme"):
        fonts.attrib.pop(tag(theme), None)


def apply_style(styles, document, style: dict) -> bool:
    """Write the settings into styles.xml and document.xml's section.
    Returns whether document.xml changed."""
    settings = {**STOCK, **style}
    by_id = {s.get(tag("styleId")): s for s in styles.findall(tag("style"))}
    defaults = child(styles, "docDefaults")
    run_default = child(child(defaults, "rPrDefault"), "rPr")
    para_default = child(child(defaults, "pPrDefault"), "pPr")

    if "font" in settings:
        set_font(child(run_default, "rFonts"), settings["font"])
        # Title and headings name the theme's heading face; one family for
        # the whole manuscript is what a journal asks for. Code styles name a
        # concrete face and keep it.
        for element in styles.iter(tag("rFonts")):
            if any(element.get(tag(t)) for t in ("asciiTheme", "hAnsiTheme", "cstheme")):
                set_font(element, settings["font"])
    if "font_size" in settings:
        half = str(round(settings["font_size"] * 2))
        child(run_default, "sz").set(tag("val"), half)
        child(run_default, "szCs").set(tag("val"), half)
    if "line_spacing" in settings:
        spacing = child(para_default, "spacing")
        spacing.set(tag("line"), str(round(settings["line_spacing"] * 240)))
        spacing.set(tag("lineRule"), "auto")
        # Table cells and tight lists (Compact) stay single, like figures
        # and references: double-spaced table rows only lengthen the file.
        if "Compact" in by_id:
            spacing = child(child(by_id["Compact"], "pPr"), "spacing")
            spacing.set(tag("line"), "240")
            spacing.set(tag("lineRule"), "auto")
    title = by_id.get("Title")
    if title is not None:
        if "title_size" in settings:
            half = str(round(settings["title_size"] * 2))
            props = child(title, "rPr")
            child(props, "sz").set(tag("val"), half)
            child(props, "szCs").set(tag("val"), half)
        if "title_align" in settings:
            child(child(title, "pPr"), "jc").set(tag("val"), settings["title_align"])
    for name in ("Title", "Subtitle"):
        if name in by_id:
            set_color(child(by_id[name], "rPr"), settings["title_color"])
    for name in HEADINGS + tuple(h + "Char" for h in HEADINGS):
        if name in by_id:
            set_color(child(by_id[name], "rPr"), settings["heading_color"])
    if "margins" not in settings:
        return False
    from project_hooks import length_twips
    twips = str(length_twips(settings["margins"]))
    for section in document.iter(tag("sectPr")):
        size = section.find(tag("pgSz"))
        if size is None:
            size = child(section, "pgSz")
            size.set(tag("w"), LETTER[0])
            size.set(tag("h"), LETTER[1])
        margin = child(section, "pgMar")
        for side in ("top", "right", "bottom", "left"):
            margin.set(tag(side), twips)
        for side, default in (("header", "720"), ("footer", "720"), ("gutter", "0")):
            margin.set(tag(side), margin.get(tag(side), default))
    return True


def generate(target: Path, style: dict) -> Path:
    """Write the reference document for `style` to `target`."""
    import pypandoc
    from export_docx import style_code
    target.parent.mkdir(parents=True, exist_ok=True)
    pypandoc.convert_text("Template seed.", "docx", format="markdown", outputfile=str(target))
    style_code(target)
    with zipfile.ZipFile(target) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    styles = parse(files["word/styles.xml"])
    document = parse(files["word/document.xml"])
    for element in styles.findall(tag("style")):
        if element.get(tag("styleId")) in ("Figure", "CaptionedFigure", "Bibliography"):
            spacing = child(child(element, "pPr"), "spacing")
            spacing.set(tag("line"), "240")
            spacing.set(tag("lineRule"), "auto")
    page_changed = apply_style(styles, document, style)
    # Concrete choices must win over theme attributes in Word and Writer alike.
    for element in styles.iter():
        if element.tag == tag("color") and element.get(tag("val")) not in (None, "auto"):
            for attr in list(element.attrib):
                if "theme" in attr.lower():
                    del element.attrib[attr]
        if element.tag == tag("rFonts"):
            for face in ("ascii", "hAnsi", "eastAsia", "cs"):
                if element.get(tag(face)):
                    element.attrib.pop(tag("cstheme" if face == "cs" else face + "Theme"), None)
    order_properties(styles)
    files["word/styles.xml"] = ET.tostring(styles, encoding="utf-8", xml_declaration=True)
    if page_changed:
        order_properties(document)
        files["word/document.xml"] = ET.tostring(document, encoding="utf-8",
                                                 xml_declaration=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return target


def cache_key(style: dict) -> str:
    import pypandoc
    h = hashlib.sha256(json.dumps(style, sort_keys=True).encode())
    for name in ("paper_word_reference.py", "export_docx.py", "word_xml.py"):
        h.update((TOOLS / name).read_bytes())
    h.update(str(pypandoc.get_pandoc_version()).encode())
    return h.hexdigest()[:16]


def cache_dir(root: Path) -> Path:
    """The project's .build-state/word-reference. A build converts a captured
    copy of the manuscript that lives under .build-state/, so the cache is the
    nearest enclosing .build-state, and a capture never writes into itself."""
    enclosing = next((p for p in root.resolve().parents if p.name == ".build-state"), None)
    return (enclosing or root / ".build-state") / "word-reference"


def reference_for(root: Path, style: dict) -> Path:
    """The generated reference document for `style`, from the cache."""
    target = cache_dir(root) / f"{cache_key(style)}.docx"
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".docx", dir=target.parent)
    os.close(fd)
    try:
        generate(Path(tmp), style)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target


# --------------------------------------------------------------- translation

def _flat(element, prefix: str = "") -> dict:
    out = {}
    for c in element:
        name = prefix + "/" + c.tag.split("}")[-1]
        for k, v in c.attrib.items():
            out[name + "@" + k.split("}")[-1]] = v
        if not c.attrib and len(c) == 0:
            out[name] = ""
        out.update(_flat(c, name))
    return out


def effective(data: bytes) -> dict[str, dict]:
    """What Word renders from a template: each style's properties with its
    basedOn chain applied (so an explicit colour equal to the inherited one
    is no difference), the document defaults, the page section, and a hash
    of every other part. docProps (the creation time) is ignored."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    styles = ET.fromstring(parts.pop("word/styles.xml"))
    document = ET.fromstring(parts.pop("word/document.xml"))
    raw, parent = {}, {}
    for s in styles.findall(tag("style")):
        sid = s.get(tag("styleId"))
        props = {}
        for kind in ("pPr", "rPr"):
            element = s.find(tag(kind))
            if element is not None:
                props.update(_flat(element, "/" + kind))
        raw[sid] = props
        based = s.find(tag("basedOn"))
        parent[sid] = based.get(tag("val")) if based is not None else None

    def resolve(sid, seen=()):
        if sid not in raw or sid in seen:
            return {}
        return {**resolve(parent[sid], seen + (sid,)), **raw[sid]}

    out = {sid: resolve(sid) for sid in raw}
    defaults = styles.find(tag("docDefaults"))
    out["(defaults)"] = _flat(defaults) if defaults is not None else {}
    section = document.find(".//" + tag("sectPr"))
    out["(page)"] = _flat(section) if section is not None else {}
    out["(parts)"] = {n: hashlib.sha256(b).hexdigest()[:12] for n, b in parts.items()
                      if not n.startswith("docProps/")}
    return out


def differences(a: dict, b: dict) -> list[str]:
    """`style key: a -> b` for every rendered property that differs."""
    lines = []
    for name in sorted(set(a) | set(b)):
        x, y = a.get(name, {}), b.get(name, {})
        for key in sorted(set(x) | set(y)):
            if x.get(key) != y.get(key):
                lines.append(f"{name} {key}: {x.get(key)} -> {y.get(key)}")
    return lines


def guess(data: bytes) -> dict:
    """The [word.style] values a template's styles suggest."""
    eff = effective(data)
    d, page, title = eff["(defaults)"], eff["(page)"], eff.get("Title", {})
    style: dict = {}
    if d.get("/rPrDefault/rPr/rFonts@ascii"):
        style["font"] = d["/rPrDefault/rPr/rFonts@ascii"]
    if d.get("/rPrDefault/rPr/sz@val"):
        style["font_size"] = int(d["/rPrDefault/rPr/sz@val"]) / 2
    if d.get("/pPrDefault/pPr/spacing@line"):
        style["line_spacing"] = round(int(d["/pPrDefault/pPr/spacing@line"]) / 240, 2)
    sides = {page.get(f"/pgMar@{s}") for s in ("top", "right", "bottom", "left")}
    if len(sides) == 1 and None not in sides:
        style["margins"] = f"{int(sides.pop()) / 1440:g}in"
    if title.get("/rPr/sz@val"):
        style["title_size"] = int(title["/rPr/sz@val"]) / 2
    if title.get("/pPr/jc@val") in ("left", "center"):
        style["title_align"] = title["/pPr/jc@val"]
    for key, sid in (("title_color", "Title"), ("heading_color", "Heading1")):
        color = eff.get(sid, {}).get("/rPr/color@val")
        if color and color != "auto":
            style[key] = color.upper()
    return style


def translate(data: bytes, baseline: bytes | None = None) -> tuple[dict, list[str]]:
    """The smallest [word.style] reproducing a template, and what it leaves.

    Values equal to the stock reference's are dropped; the rest are applied
    to a fresh reference, which is compared with the template as Word
    renders it. No leftovers means the settings reproduce the template.

    `baseline` is the scaffold template the paper started from. Given it,
    only the paper's own edits count: a value the old template already had
    (pandoc's blue headings, say) is the stock's to change, not the paper's.
    """
    with tempfile.TemporaryDirectory() as tmp:
        stock = guess(generate(Path(tmp) / "stock.docx", {}).read_bytes())
        before = guess(baseline) if baseline is not None else {}
        style = {k: v for k, v in guess(data).items()
                 if stock.get(k) != v and (baseline is None or before.get(k) != v)}
        made = effective(generate(Path(tmp) / "made.docx", style).read_bytes())
    left = differences(made, effective(data))
    if baseline is not None:
        edited = {line.rsplit(":", 1)[0] for line in
                  differences(effective(baseline), effective(data))}
        left = [line for line in left if line.rsplit(":", 1)[0] in edited]
    return style, left


def toml_block(style: dict) -> str:
    if not style:
        return "# no [word.style]: the stock reference reproduces it"
    lines = ["[word.style]"]
    for key, value in style.items():
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        lines.append(f"{key} = {json.dumps(value)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--translate", type=Path, metavar="DOCX",
                        help="print the [word.style] that reproduces this template")
    parser.add_argument("--baseline", type=Path, metavar="DOCX",
                        help="with --translate: the scaffold template the paper "
                             "started from, so only the paper's edits count")
    args = parser.parse_args(argv)
    if args.translate:
        style, left = translate(args.translate.read_bytes(),
                                args.baseline.read_bytes() if args.baseline else None)
        print(toml_block(style))
        if left:
            print(f"\n{len(left)} difference(s) no setting expresses. Keep the file "
                  "and declare [word] reference instead, or accept the change:")
            print("\n".join("  " + line for line in left))
            return 1
        return 0
    from project_hooks import load
    try:
        word = load(ROOT).word
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(ROOT / word.reference if word.reference else reference_for(ROOT, word.style))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
