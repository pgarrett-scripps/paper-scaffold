"""The built PDF's layout, and its figures against the journal profile.

Two things a journal's production office rejects that no source check sees:

  Overflow   text set past the margin: a table or equation too wide for the
             text block, a long identifier that would not break, a float
             pushed into the foot of the page. Read from the PDF with
             `pdftotext -bbox`: a word off the page or within --edge points
             of its edge, or a line ending more than --tolerance points past
             the text block's right edge (or starting before its left one),
             where the edges are where most lines on pages of that size end
             and start.

  Figures    each raster figure in assets.json, as the PDF places it
             (`pdfimages -list` gives the effective resolution) and as its
             generator recorded it (assets.json `print`: width, height,
             smallest type), against the selected journal profile's
             [figures]: min-dpi, single-column-in, double-column-min-in and
             double-column-max-in, max-height-in, min-type-pt, color-modes.
             A key the profile does not set is not checked; with no profile,
             only overflow is.

Every finding is a warning: a draft PDF is not the typeset article, and a
figure the journal will resize may be fine. --strict makes a warning fail.
`just check-layout` runs it on paper.pdf; `just check-submission` (and so
`just preflight`) on the upload set in submission/ as well. Poppler's
pdftotext and pdfimages must be installed; without them the check says so
and passes.

    uv run paper tool layout_check [--submission] [--strict] [PDF ...]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from paths import ROOT

EDGE_PT = 18.0        # a quarter inch: no journal's margin is narrower
TOLERANCE_PT = 4.0    # past the text block's edge by more than this
RASTER = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
MODES = {"1": "gray", "L": "gray", "LA": "gray", "I": "gray", "I;16": "gray",
         "F": "gray", "P": "rgb", "RGB": "rgb", "RGBA": "rgb", "RGBX": "rgb",
         "CMYK": "cmyk", "YCbCr": "rgb", "LAB": "rgb"}
WORD = re.compile(r'<word xMin="([\d.-]+)" yMin="([\d.-]+)" xMax="([\d.-]+)" '
                  r'yMax="([\d.-]+)">(.*?)</word>')
PAGE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">')


@dataclass
class Finding:
    subject: str
    message: str


def _unescape(text: str) -> str:
    return (text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
            .replace("&#39;", "'").replace("&amp;", "&"))


def pages(pdf: Path) -> list[tuple[float, float, list[tuple]]]:
    """Each page's width, height and words (x0, y0, x1, y1, text)."""
    out = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"], capture_output=True,
                         text=True, check=True).stdout
    result = []
    for chunk in out.split("<page ")[1:]:
        m = PAGE.match("<page " + chunk)
        if not m:
            continue
        words = [(float(a), float(b), float(c), float(d), _unescape(t))
                 for a, b, c, d, t in WORD.findall(chunk)]
        result.append((float(m[1]), float(m[2]), words))
    return result


def lines(words: list[tuple]) -> list[list[tuple]]:
    """Words grouped into lines by their baseline, left to right."""
    rows: dict[int, list[tuple]] = defaultdict(list)
    for w in words:
        rows[round(w[3])].append(w)
    return [sorted(r) for _, r in sorted(rows.items())]


def _quantile(values: list[float], q: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, max(0, round(q * (len(values) - 1))))]


def overflow(pdf: Path, edge: float = EDGE_PT, tolerance: float = TOLERANCE_PT) -> list[Finding]:
    found: list[Finding] = []
    book = pages(pdf)
    # The text block's edges, per page size: where most lines end and start.
    ends, starts = defaultdict(list), defaultdict(list)
    for width, height, words in book:
        for line in lines(words):
            if len(line) >= 4:   # prose lines, not a page number or a label
                ends[(width, height)].append(line[-1][2])
                starts[(width, height)].append(line[0][0])
    right = {k: _quantile(v, 0.95) for k, v in ends.items() if len(v) >= 10}
    left = {k: _quantile(v, 0.05) for k, v in starts.items() if len(v) >= 10}
    for number, (width, height, words) in enumerate(book, 1):
        where = f"{pdf.name} p.{number}"
        off = [w for w in words if w[0] < edge or w[1] < edge
               or w[2] > width - edge or w[3] > height - edge]
        if off:
            sample = " ".join(w[4] for w in off[:6])
            found.append(Finding(where, f"{len(off)} word(s) within {edge:g} pt of "
                                        f"the page edge or past it: {sample!r}"))
        r, l = right.get((width, height)), left.get((width, height))
        for line in lines(words):
            if r is not None and line[-1][2] > r + tolerance and line[-1] not in off:
                text = " ".join(w[4] for w in line)[-60:]
                found.append(Finding(where, f"line ends {line[-1][2] - r:.0f} pt past "
                                            f"the right margin: {text!r}"))
            if l is not None and line[0][0] < l - tolerance and line[0] not in off:
                text = " ".join(w[4] for w in line)[:60]
                found.append(Finding(where, f"line starts {l - line[0][0]:.0f} pt "
                                            f"before the left margin: {text!r}"))
    return found


def placed_ppi(pdfs: list[Path]) -> dict[tuple[int, int], tuple[float, str]]:
    """Each embedded image's pixel size -> its lowest effective ppi and where."""
    out: dict[tuple[int, int], tuple[float, str]] = {}
    for pdf in pdfs:
        listing = subprocess.run(["pdfimages", "-list", str(pdf)], capture_output=True,
                                 text=True, check=True).stdout.splitlines()[2:]
        for row in listing:
            cols = row.split()
            if len(cols) < 14 or cols[2] != "image":
                continue
            size = (int(cols[3]), int(cols[4]))
            ppi = min(float(cols[12]), float(cols[13]))
            if size not in out or ppi < out[size][0]:
                out[size] = (ppi, f"{pdf.name} p.{cols[0]}")
    return out


def figures(root: Path, pdfs: list[Path], limits: dict) -> list[Finding]:
    manifest = root / "assets.json"
    if not limits or not manifest.is_file():
        return []
    try:
        values = json.loads(manifest.read_text()).get("values", {})
    except (OSError, ValueError):
        return []
    found: list[Finding] = []
    ppi = placed_ppi(pdfs) if "min-dpi" in limits and pdfs else {}
    single = limits.get("single-column-in")
    low, high = limits.get("double-column-min-in"), limits.get("double-column-max-in")
    for id, rec in sorted(values.items()):
        if not isinstance(rec, dict) or rec.get("kind") != "figure":
            continue
        path = root / str(rec.get("path", ""))
        geometry = rec.get("print") if isinstance(rec.get("print"), dict) else {}
        width, height = geometry.get("width_in"), geometry.get("height_in")
        if isinstance(width, (int, float)) and (single or high):
            fits = ((single is not None and width <= single + 0.005)
                    or (low is not None and low - 0.005 <= width <= high + 0.005))
            if not fits:
                allowed = " or ".join(x for x in (
                    f"up to {single:g} in (single column)" if single else "",
                    f"{low:g}-{high:g} in (double column)" if high else "") if x)
                found.append(Finding(id, f"prints {width:g} in wide; the journal takes "
                                         f"{allowed}"))
        if isinstance(height, (int, float)) and "max-height-in" in limits \
                and height > limits["max-height-in"] + 0.005:
            found.append(Finding(id, f"prints {height:g} in tall; the journal's "
                                     f"maximum is {limits['max-height-in']:g} in"))
        small = geometry.get("min_pt")
        if isinstance(small, (int, float)) and "min-type-pt" in limits \
                and small < limits["min-type-pt"]:
            found.append(Finding(id, f"smallest type is {small:g} pt at its recorded "
                                     f"size; the journal's floor is "
                                     f"{limits['min-type-pt']:g} pt"))
        if path.suffix.lower() not in RASTER or not path.is_file():
            continue
        try:
            from PIL import Image
            with Image.open(path) as im:
                size, mode = im.size, im.mode
        except Exception:
            continue
        if "color-modes" in limits:
            kind = MODES.get(mode, mode.lower())
            if kind not in limits["color-modes"]:
                found.append(Finding(id, f"{path.name} is {kind} ({mode}); the journal "
                                         f"takes {', '.join(limits['color-modes'])}"))
        if size in ppi and ppi[size][0] < limits["min-dpi"] - 0.5:
            found.append(Finding(id, f"prints at {ppi[size][0]:.0f} ppi in {ppi[size][1]}; "
                                     f"the journal's floor is {limits['min-dpi']} dpi"))
    return found


def default_pdfs(root: Path, submission: bool) -> list[Path]:
    pdfs = [root / "paper.pdf"]
    if submission:
        pdfs += sorted(p for p in (root / "submission").glob("*.pdf")
                       if p.name != "cover-letter.pdf")
    return [p for p in pdfs if p.is_file()]


def run(root: Path, pdfs: list[Path], *, edge=EDGE_PT, tolerance=TOLERANCE_PT) -> tuple[list[Finding], list[str]]:
    """Findings, and notes on what could not be checked."""
    notes: list[str] = []
    missing = [b for b in ("pdftotext", "pdfimages") if shutil.which(b) is None]
    if missing:
        return [], [f"{', '.join(missing)} not installed (poppler-utils): layout not checked"]
    if not pdfs:
        return [], ["no PDF to check: run just paper"]
    found: list[Finding] = []
    for pdf in pdfs:
        found += overflow(pdf, edge, tolerance)
    limits: dict = {}
    try:
        from journal import current
        profile, _ = current(root)
        limits = profile.figures if profile else {}
    except ValueError as exc:
        notes.append(f"journal profile unreadable, figures not checked: {exc}")
    if not limits:
        notes.append("no journal profile [figures] limits: figures not checked")
    found += figures(root, pdfs, limits)
    return found, notes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", nargs="*", type=Path, help="default paper.pdf")
    parser.add_argument("--submission", action="store_true",
                        help="also the PDFs in submission/")
    parser.add_argument("--strict", action="store_true", help="a warning fails")
    parser.add_argument("--edge", type=float, default=EDGE_PT)
    parser.add_argument("--tolerance", type=float, default=TOLERANCE_PT)
    args = parser.parse_args(argv)
    pdfs = [p if p.is_absolute() else ROOT / p for p in args.pdf] \
        or default_pdfs(ROOT, args.submission)
    found, notes = run(ROOT, pdfs, edge=args.edge, tolerance=args.tolerance)
    for n in notes:
        print(f"note: {n}")
    for f in found:
        print(f"warn: {f.subject}: {f.message}")
    checked = ", ".join(p.name for p in pdfs)
    if not found:
        print(f"layout: no overflow or figure findings ({checked})" if pdfs else "layout: nothing checked")
        return 0
    print(f"layout: {len(found)} warning(s) in {checked}"
          + ("" if args.strict else " (warnings; --strict to fail)"))
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
