"""Table styling in the Word export, from [word.style] and [word.tables].

pandoc writes every table auto-fit, in the reference document's "Table"
style, at the body's type size. Word and LibreOffice then pick different
column widths, and dense SI tables wrap identifiers mid-word. Four papers
each wrote a Word hook to fix the same things (koth-paper, spectrl-paper,
uno-paper, koth-lfq-paper); this module is what they had in common:

    table_font_size      type size in every table cell, in points
    table_header_bold    header rows in bold
    table_header_shading header-row fill, six hex digits
    table_borders        "booktabs" (rules above, below the header, below
                         the table), "grid" (every cell) or "none"
    table_layout         "fixed": full text width, fixed column widths
                         (pandoc's proportions, or [word.tables] widths);
                         "auto": leave pandoc's auto-fit
    table_cell_margin    left and right padding in each cell ("0.04in")
    table_compact        single-spaced cell paragraphs, no space around
                         them, kept whole across a page break
    table_valign         "top", "center" or "bottom" in every cell
    table_unnest         a figure holding several tables: pandoc writes a
                         one-row layout table with one nested table per
                         cell; true restores them as consecutive tables

    [word.tables."tbl:x"]  one table, by its label:
        widths       relative column widths (fixed layout), e.g. [3, 1, 1]
        font_size    this table's type size
        header_rows  how many leading rows repeat on each page and take
                     the header styling (pandoc already repeats the rows
                     of a Typst table.header)

Runs inside export_docx.postprocess(), after paginate(), and only when one
of these keys is set, so a paper without them converts to the same bytes as
before. docs/word-export.md.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from word_xml import W, order_properties

TABLE_KEYS = ("table_font_size", "table_header_bold", "table_header_shading",
              "table_borders", "table_layout", "table_cell_margin",
              "table_compact", "table_valign", "table_unnest")
CAPTION_STYLES = ("TableCaption", "ImageCaption", "Caption", "CaptionedFigure")


def tag(name: str) -> str:
    return "{" + W + "}" + name


def child(parent: ET.Element, name: str) -> ET.Element:
    found = parent.find(tag(name))
    if found is None:
        found = ET.SubElement(parent, tag(name))
    return found


def replace(parent: ET.Element, name: str) -> ET.Element:
    old = parent.find(tag(name))
    if old is not None:
        parent.remove(old)
    return ET.SubElement(parent, tag(name))


def wanted(style: dict, tables: dict) -> bool:
    return bool(tables) or any(k in style for k in TABLE_KEYS)


def label_of(p: ET.Element | None) -> str | None:
    """The tbl:/tab: bookmark a caption paragraph carries (paginate() moves
    the float's label anchor into its caption)."""
    if p is None or p.tag != tag("p"):
        return None
    for mark in p.iter(tag("bookmarkStart")):
        name = mark.get(tag("name"), "")
        if name.startswith(("tbl:", "tab:")):
            return name
    return None


def is_caption(p: ET.Element | None) -> bool:
    if p is None or p.tag != tag("p"):
        return False
    s = p.find(f"{tag('pPr')}/{tag('pStyle')}")
    return s is not None and s.get(tag("val")) in CAPTION_STYLES


def span(cell: ET.Element) -> int:
    s = cell.find(f"{tag('tcPr')}/{tag('gridSpan')}")
    return int(s.get(tag("val"), "1")) if s is not None else 1


def layout_cells(table: ET.Element) -> list[ET.Element] | None:
    """The cells of pandoc's layout table around several tables, or None."""
    rows = table.findall(tag("tr"))
    if len(rows) != 1:
        return None
    cells = rows[0].findall(tag("tc"))
    if not cells or not all(len(c.findall(tag("tbl"))) == 1 for c in cells):
        return None
    # Never drop a real cell paragraph that sits beside a nested table.
    if any("".join(p.itertext()).strip() for c in cells for p in c.findall(tag("p"))):
        return None
    return cells


def labelled(body: ET.Element, unnest: bool) -> list[tuple[ET.Element, str | None]]:
    """Every table in the body with the label of its float, un-nesting
    layout tables first when asked."""
    out: list[tuple[ET.Element, str | None]] = []
    blocks = list(body)
    for i, block in enumerate(blocks):
        if block.tag != tag("tbl"):
            continue
        before = blocks[i - 1] if i else None
        after = blocks[i + 1] if i + 1 < len(blocks) else None
        label = label_of(before) if is_caption(before) else None
        if label is None and is_caption(after):
            label = label_of(after)
        cells = layout_cells(block) if unnest else None
        if cells is None:
            out.append((block, label))
            continue
        at = list(body).index(block)
        body.remove(block)
        if label and is_caption(after) and label_of(after) == label:
            # The caption leads, as for any other table.
            body.remove(after)
            body.insert(at, after)
            at += 1
        for k, cell in enumerate(cells):
            inner = cell.find(tag("tbl"))
            body.insert(at, inner)
            at += 1
            out.append((inner, label))
            if k < len(cells) - 1:
                body.insert(at, ET.Element(tag("p")))
                at += 1
    # Tables nested in cells that stayed nested still get the cell styling.
    seen = {id(t) for t, _ in out}
    for t in body.iter(tag("tbl")):
        if id(t) not in seen:
            out.append((t, None))
    return out


def borders(tbl_pr: ET.Element, kind: str) -> None:
    edges = replace(tbl_pr, "tblBorders")
    rule = {"val": "single", "sz": "8", "space": "0", "color": "000000"}
    thin = {**rule, "sz": "4"}
    nil = {"val": "nil"}
    spec = {
        "booktabs": {"top": rule, "left": nil, "bottom": rule, "right": nil,
                     "insideH": nil, "insideV": nil},
        "grid": {e: thin for e in ("top", "left", "bottom", "right", "insideH", "insideV")},
        "none": {e: nil for e in ("top", "left", "bottom", "right", "insideH", "insideV")},
    }[kind]
    for edge, attrs in spec.items():
        el = ET.SubElement(edges, tag(edge))
        for k, v in attrs.items():
            el.set(tag(k), v)


def cell_margin(tbl_pr: ET.Element, twips: int) -> None:
    mar = replace(tbl_pr, "tblCellMar")
    for side in ("left", "right"):
        el = ET.SubElement(mar, tag(side))
        el.set(tag("w"), str(twips))
        el.set(tag("type"), "dxa")


def column_widths(table: ET.Element, ncols: int, weights, total: int,
                  label: str | None) -> list[int]:
    if weights and len(weights) != ncols:
        raise ValueError(f"[word.tables] {label}: {len(weights)} widths for a "
                         f"{ncols}-column table")
    if not weights:
        grid = [int(g.get(tag("w"), "0") or 0)
                for g in table.findall(f"{tag('tblGrid')}/{tag('gridCol')}")]
        weights = grid if len(grid) == ncols and sum(grid) > 0 else [1] * ncols
    scale = total / sum(weights)
    widths = [int(w * scale) for w in weights]
    widths[-1] += total - sum(widths)
    return widths


def style_table(table: ET.Element, style: dict, own: dict, width_twips: int,
                twips, label: str | None = None) -> None:
    rows = table.findall(tag("tr"))
    if not rows:
        return
    ncols = max(sum(span(c) for c in r.findall(tag("tc"))) for r in rows)
    tbl_pr = table.find(tag("tblPr"))
    if tbl_pr is None:
        tbl_pr = ET.Element(tag("tblPr"))
        table.insert(0, tbl_pr)
    widths = None
    if style.get("table_layout") == "fixed" or "widths" in own:
        widths = column_widths(table, ncols, own.get("widths"), width_twips, label)
        w = child(tbl_pr, "tblW")
        w.attrib.clear()
        w.set(tag("w"), str(width_twips))
        w.set(tag("type"), "dxa")
        child(tbl_pr, "tblLayout").set(tag("type"), "fixed")
        grid = table.find(tag("tblGrid"))
        if grid is None:
            grid = ET.Element(tag("tblGrid"))
            table.insert(list(table).index(tbl_pr) + 1, grid)
        for g in list(grid):
            grid.remove(g)
        for width in widths:
            ET.SubElement(grid, tag("gridCol")).set(tag("w"), str(width))
    if "table_borders" in style:
        borders(tbl_pr, style["table_borders"])
    if "table_cell_margin" in style:
        cell_margin(tbl_pr, twips(style["table_cell_margin"]))

    header_rows = own.get("header_rows")
    if header_rows is None:
        header_rows = 0
        for r in rows:
            if r.find(f"{tag('trPr')}/{tag('tblHeader')}") is None:
                break
            header_rows += 1
    size = own.get("font_size", style.get("table_font_size"))
    for index, row in enumerate(rows):
        head = index < header_rows
        if own.get("header_rows") is not None:
            tr_pr = child(row, "trPr")
            flag = tr_pr.find(tag("tblHeader"))
            if head and flag is None:
                ET.SubElement(tr_pr, tag("tblHeader"))
            elif not head and flag is not None:
                tr_pr.remove(flag)
        column = 0
        for cell in row.findall(tag("tc")):
            n = span(cell)
            tc_pr = cell.find(tag("tcPr"))
            if tc_pr is None:
                tc_pr = ET.Element(tag("tcPr"))
                cell.insert(0, tc_pr)
            if widths is not None:
                w = child(tc_pr, "tcW")
                w.attrib.clear()
                w.set(tag("w"), str(sum(widths[column:column + n])))
                w.set(tag("type"), "dxa")
            column += n
            if "table_valign" in style:
                child(tc_pr, "vAlign").set(tag("val"), style["table_valign"])
            if head and "table_header_shading" in style:
                shd = child(tc_pr, "shd")
                shd.attrib.clear()
                shd.set(tag("val"), "clear")
                shd.set(tag("color"), "auto")
                shd.set(tag("fill"), style["table_header_shading"])
            if (head and index == header_rows - 1
                    and style.get("table_borders") == "booktabs"):
                edges = child(tc_pr, "tcBorders")
                bottom = child(edges, "bottom")
                for k, v in (("val", "single"), ("sz", "4"), ("space", "0"),
                             ("color", "000000")):
                    bottom.set(tag(k), v)
            for p in cell.findall(tag("p")):
                if style.get("table_compact"):
                    p_pr = p.find(tag("pPr"))
                    if p_pr is None:
                        p_pr = ET.Element(tag("pPr"))
                        p.insert(0, p_pr)
                    spacing = child(p_pr, "spacing")
                    for k, v in (("before", "0"), ("after", "0"), ("line", "240"),
                                 ("lineRule", "auto")):
                        spacing.set(tag(k), v)
                    child(p_pr, "keepLines")
                for run in p.iter(tag("r")):
                    if size is None and not (head and style.get("table_header_bold")):
                        continue
                    r_pr = run.find(tag("rPr"))
                    if r_pr is None:
                        r_pr = ET.Element(tag("rPr"))
                        run.insert(0, r_pr)
                    if head and style.get("table_header_bold"):
                        child(r_pr, "b")
                    if size is not None:
                        half = str(round(size * 2))
                        child(r_pr, "sz").set(tag("val"), half)
                        child(r_pr, "szCs").set(tag("val"), half)


def apply(root: ET.Element, style: dict, tables: dict, width_twips: int) -> set[str]:
    """Style every table in document.xml's tree in place. `tables` maps a
    label (tbl:x) to its own widths, font_size and header_rows. Returns the
    labels of `tables` that matched no table in the document."""
    if not wanted(style, tables):
        return set()
    from project_hooks import length_twips
    body = root.find(tag("body"))
    if body is None:
        return set(tables)
    seen = set()
    for table, label in labelled(body, bool(style.get("table_unnest"))):
        seen.add(label)
        style_table(table, style, tables.get(label, {}) if label else {},
                    width_twips, length_twips, label)
    order_properties(root)
    return set(tables) - seen
