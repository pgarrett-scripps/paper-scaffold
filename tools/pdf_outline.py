"""Make a compiled PDF open with its bookmarks panel showing.

Typst writes a full outline (/Outlines) from the headings but never sets
/PageMode, so viewers open the file with the sidebar closed, unlike a
journal's PDF. This adds `/PageMode /UseOutlines` to the catalog as a PDF
incremental update: the original bytes are kept as they are and a
replacement catalog, a one-entry xref section and a trailer pointing back
at the old one are appended. Nothing else in the file is re-saved.

Call it on the staged PDF, before any hash of the output is recorded, so
freshness checks see the stamped file. A PDF with no outline, one that
already sets a page mode, or one whose structure this does not recognise
(an xref stream rather than a classic trailer) is left untouched.

Usage: python3 pdf_outline.py FILE.pdf [...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_TRAILER = re.compile(rb"trailer\s*(<<.*?>>)\s*startxref\s*(\d+)\s*%%EOF\s*$", re.S)
_ROOT = re.compile(rb"/Root\s+(\d+)\s+(\d+)\s+R")
_SIZE = re.compile(rb"/Size\s+(\d+)")


def _object(data: bytes, num: int, gen: int) -> bytes | None:
    """The body of the LAST definition of object `num gen` (a later
    incremental update supersedes an earlier one)."""
    found = None
    for m in re.finditer(rb"(?:^|[\r\n])%d\s+%d\s+obj\b" % (num, gen), data):
        found = m
    if not found:
        return None
    end = data.find(b"endobj", found.end())
    return data[found.end():end].strip() if end >= 0 else None


def open_with_outline(path: Path) -> bool:
    """Stamp /PageMode /UseOutlines into `path`. True when the file changed."""
    if not path.is_file():
        return False
    data = path.read_bytes()
    trailer = _TRAILER.search(data[-4096:])
    if not trailer:
        return False
    tdict, prev = trailer.group(1), int(trailer.group(2))
    root, size = _ROOT.search(tdict), _SIZE.search(tdict)
    if not (root and size) or b"/Prev" in tdict:
        return False
    num, gen = int(root.group(1)), int(root.group(2))
    catalog = _object(data, num, gen)
    if (not catalog or not catalog.startswith(b"<<") or b"/Outlines" not in catalog
            or b"/PageMode" in catalog):
        return False
    new_catalog = b"<<\n  /PageMode /UseOutlines" + catalog[2:]
    body = b"\n%d %d obj\n%s\nendobj\n" % (num, gen, new_catalog)
    offset = len(data) + 1  # the object line starts after the leading newline
    xref_at = len(data) + len(body)
    new_trailer = b"<<\n  /Prev %d" % prev + tdict[2:]
    tail = (b"xref\n%d 1\n%010d %05d n \ntrailer\n%s\nstartxref\n%d\n%%%%EOF\n"
            % (num, offset, gen, new_trailer, xref_at))
    tmp = path.with_name(path.name + ".outline-tmp")
    tmp.write_bytes(data + body + tail)
    tmp.replace(path)
    return True


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(f"{arg}: {'stamped' if open_with_outline(Path(arg)) else 'unchanged'}")
