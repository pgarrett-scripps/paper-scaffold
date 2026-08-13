#!/usr/bin/env python3
"""Convert the Typst-exported HTML of paper.typ into a Word .docx.

Invoked by `just docx`; not usually run by hand. Two problems sit between Typst's
HTML export and a usable Word file, and this script fixes both.

1. Inline math. Typst's HTML export silently DROPS every equation, gutting
   sentences into things like "the threshold's __ must be recalibrated ...
   ranges __ to __". paper.typ works around this in docx mode by
   wrapping each equation in `html.frame()`, which preserves it as an SVG. But
   Typst emits that frame as a BLOCK-level sibling, so a sentence containing inline
   math is shattered into separate <p> fragments:

       <p>The threshold</p> <svg/> <p>must be recalibrated ...</p>

   We stitch those fragments back into one paragraph, then rasterize each math SVG
   to an inline PNG. PNG rather than SVG because pandoc cannot size a raw SVG
   without `rsvg-convert` (absent here) and older Word versions will not render it.

2. Everything else already survives the round trip: headings become real Word
   heading styles, tables stay tables, and figures embed as images.

Usage: typst2docx.py <input.html> <output.docx>
"""

from __future__ import annotations

import base64
import io
import re
import sys
from pathlib import Path

import cairosvg
import pypandoc
from PIL import Image

# Rasterization factor for math. 4x keeps symbols crisp on a high-DPI screen and
# when printed; the <img> is then sized back down to the glyph's natural size.
SCALE = 4

# What pandoc's default reference document sets as the Word body size
# (docDefaults, measured from the produced file). Typst frames carry their own
# em -- an 11pt manuscript emits 11pt-per-em frames -- so without rescaling,
# every equation lands ~9% smaller than the Word text around it. Each frame's
# em is read from its own style attribute, so a project that changes its text
# size stays correctly scaled.
WORD_BODY_PT = 12.0


def _em_pt(svg: str) -> float:
    """pt per em for this frame, from its width in pt vs its width in em."""
    pt = _pt(svg, "width")
    em = re.search(r'width:\s*([0-9.]+)em', svg)
    if pt and em and float(em.group(1)):
        return pt / float(em.group(1))
    return WORD_BODY_PT                      # no ratio available: no rescale

# Only stitch a frame back into the surrounding paragraph if it is glyph-sized.
# Inline math runs ~7-15pt tall; a display equation is taller and deserves to stay
# its own block. Raise this if a tall inline construct (a fraction, a stacked
# subscript) is being wrongly promoted to its own paragraph.
MAX_INLINE_PT = 30.0

FRAME_RE = re.compile(r'<svg class="typst-frame".*?</svg>', re.S)
# </p>  <frame>  <p>   ->   one paragraph, frame inline
MERGE_RE = re.compile(r'</p>\s*(<svg class="typst-frame".*?</svg>)\s*<p>', re.S)


def _pt(svg: str, attr: str) -> float:
    m = re.search(rf'\b{attr}="([0-9.]+)pt"', svg)
    return float(m.group(1)) if m else 0.0


# Typst sizes a math frame to its LINE BOX and then relies on `overflow: visible`
# to paint the parts that stick out (subscripts, descenders, italic overhang).
# Browsers honour that; cairosvg does not -- it rasterizes to a canvas of exactly
# width x height and silently shears off anything outside, which cropped every
# subscripted equation to a uniform 44px band. So grow the canvas before
# rendering, then crop back to the ink. PAD is a multiple of the frame height and
# only has to be big enough to contain the overhang; the crop removes the slack.
PAD = 1.0


def _pad_frame(svg: str) -> str:
    """Enlarge an SVG's canvas symmetrically so nothing is clipped when raster-
    ized. Keeps the user-unit scale identical, so the glyph renders unchanged."""
    w, h = _pt(svg, "width"), _pt(svg, "height")
    vb = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"', svg)
    if not (w and h and vb):
        return svg
    x0, y0, vw, vh = (float(g) for g in vb.groups())
    pad = PAD * h
    head_end = svg.index(">") + 1
    head, body = svg[:head_end], svg[head_end:]
    head = re.sub(r'\bwidth="[0-9.]+pt"', f'width="{w + 2 * pad}pt"', head)
    head = re.sub(r'\bheight="[0-9.]+pt"', f'height="{h + 2 * pad}pt"', head)
    head = re.sub(
        r'viewBox="[^"]+"',
        f'viewBox="{x0 - pad} {y0 - pad} {vw + 2 * pad} {vh + 2 * pad}"',
        head,
    )
    return head + body


def _render(svg: str) -> tuple[bytes, float]:
    """Rasterize one math frame and return (png bytes, ink width in pt)."""
    png = cairosvg.svg2png(bytestring=_pad_frame(svg).encode(), scale=SCALE)
    im = Image.open(io.BytesIO(png))
    box = im.getbbox()  # bounding box of the non-transparent pixels
    if box:
        im = im.crop(box)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue(), im.width / SCALE


def merge_inline_frames(html: str) -> tuple[str, int]:
    """Rejoin paragraphs that Typst split around an inline math frame."""

    def repl(m: re.Match) -> str:
        svg = m.group(1)
        if _pt(svg, "height") > MAX_INLINE_PT:
            return m.group(0)  # tall enough to be display math; leave it alone
        return f" {svg} "

    return MERGE_RE.subn(repl, html)


def rasterize_frames(html: str) -> tuple[str, int]:
    """Replace each math SVG with an inline PNG <img> at its natural size."""

    def repl(m: re.Match) -> str:
        svg = m.group(0)
        png, ink_pt = _render(svg)
        b64 = base64.b64encode(png).decode()
        # pt -> CSS px so Word lays the glyph out at the size Typst intended,
        # rescaled from the manuscript's em to Word's, so an 11pt paper's math
        # is not 9% small beside 12pt Word text. Measured off the cropped image
        # rather than the declared width, since the declared box understates
        # glyphs that overhang it.
        w = ink_pt * (WORD_BODY_PT / _em_pt(svg)) * 96 / 72
        size = f' width="{w:.1f}"' if w else ""
        return f'<img src="data:image/png;base64,{b64}"{size} alt="equation" />'

    return FRAME_RE.subn(repl, html)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    src, out = Path(sys.argv[1]), Path(sys.argv[2])

    html = src.read_text(encoding="utf-8")
    html, merged = merge_inline_frames(html)
    html, drawn = rasterize_frames(html)
    print(f"math: {drawn} equations rasterized, {merged} paragraphs rejoined")

    staged = src.with_suffix(".staged.html")
    staged.write_text(html, encoding="utf-8")
    try:
        pypandoc.convert_file(
            str(staged), "docx", outputfile=str(out),
            extra_args=["--standalone", "--toc", "--toc-depth=3",
                        "--shift-heading-level-by=-1"],
        )
    finally:
        staged.unlink(missing_ok=True)

    print(f"wrote {out.name} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
