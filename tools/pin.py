#!/usr/bin/env python3
"""Record hashes for the author-pinned files declared in stats.json.

WHY THIS EXISTS. The provenance the pipeline records automatically stops at what
a generator imported or declared. Plenty of files matter to a manuscript without
any script reading them: a raw instrument export, a protocol PDF, a config that
shaped the analysis upstream. Nothing can discover those programmatically -- so
they are declared by hand instead, and this records what they currently are.

HOW TO USE IT. Add the path to the `pinned` block of stats.json with a null
hash, then run `just pin`:

    "pinned": {
      "analysis/data/raw_export_2026-06.csv": null
    }

This fills in the sha256. From then on `just check-stats` (and so `just verify`)
reports when the file changes, and the fix it names is deliberate: look at the
numbers that depend on it, then run `just pin` again to accept the new state.

The block is the author's. Generators carry it through untouched when they
rewrite stats.json, and nothing here adds or removes paths -- declaring what is
worth watching is the author's call, made in the file.

Run with `just pin`.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATS = ROOT / "stats.json"

HOW = ('add  "pinned": {"path/relative/to/root": null}  to stats.json, then '
       'run this again')


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def pin(doc: dict, root: Path) -> tuple[list[str], int]:
    """Fill or refresh every hash in doc["pinned"]. Returns (report lines, rc)."""
    lines: list[str] = []
    rc = 0
    pinned = doc.get("pinned") or {}
    if not isinstance(pinned, dict):
        # The block is hand-authored; a list of paths is the natural wrong
        # first guess, and .items() on it would kill the one command that
        # could explain the right shape.
        return ([f'  pinned is not an object ({type(pinned).__name__}). '
                 f'The shape is {{"path/relative/to/root": null}}.'], 1)
    for src, old in sorted(pinned.items()):
        p = root / src
        if not p.is_file():
            # An error, unlike in check_stats: you are the one pinning, on the
            # machine that is supposed to have the file. A pin recorded from a
            # guess would defeat the point.
            lines.append(f"  MISSING   {src} -- cannot pin a file that is not here")
            rc = 1
            continue
        new = _sha(p)
        if not old:
            lines.append(f"  pinned    {src}")
        elif old != new:
            lines.append(f"  updated   {src} -- the old hash is replaced; the "
                         f"numbers that depend on it are your job to re-check")
        else:
            lines.append(f"  unchanged {src}")
        doc["pinned"][src] = new
    return lines, rc


def main() -> int:
    if not STATS.is_file():
        print(f"no stats.json to pin into. {HOW}")
        return 1
    try:
        doc = json.loads(STATS.read_text())
    except json.JSONDecodeError as e:
        print(f"stats.json is not valid JSON: {e}")
        return 1
    if not doc.get("pinned"):
        print(f"nothing is pinned. {HOW}")
        return 0

    lines, rc = pin(doc, ROOT)
    for line in lines:
        print(line)
    STATS.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n")
    print(f"  {len(doc['pinned'])} pin(s) recorded in stats.json -- "
          f"`just check-stats` now watches them")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
