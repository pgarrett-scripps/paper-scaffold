#!/usr/bin/env python3
"""Guard for a copy-edit pass: prove that only wording changed.

STYLE.md permits dropping a number from the main text; it never permits editing
one. It also forbids adding, deleting, or renumbering a figure, table, heading,
or citation. Those are mechanical properties, so they get checked mechanically
rather than eyeballed.

    just edit-baseline          # before the editing pass
    just edit-check             # after it

Snapshots live in .edit-guard/ at the manuscript root: local state like
.build-stamp, gitignored, disposable. A tag argument keeps several passes
apart (`just edit-baseline round2`); omitted, it is "default".

Upstreamed from the koth manuscript, which wrote it for exactly this and ran
it in anger first.

What it compares, across the manuscript (main text and SI together, because
content legitimately moves between them):

  numbers      Every numeric token. Must be a SUBSET after editing: a number may
               disappear (rule 7 permits thinning), but one that appears nowhere
               it appeared before is either invented or altered, and both are
               fatal.
  labels       <fig:...>, <tbl:...>, <sec:...>, <eq:...> definitions. Exact set.
  refs         Every @citekey and #ref(<...>) target. Exact set.
  figures      Count of #figure( blocks. Exact.
  headings     The heading text, in order, per file. Exact.

The numeric tokenizer deliberately does NOT use a greedy [\\d,]* : that swallows
a sentence comma into the token, so "12.6, and" becomes "12.6," and every such
token reads as changed. It also strips a trailing period, since a citation moved
to the end of a sentence picks one up.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# The manuscript root, one level up: this file lives in tools/.
ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / ".edit-guard"

FILES = ["paper.typ", "si-body.typ"]

# A number: digits, optionally with internal separators, but never trailing
# punctuation. Handles 12.6, 1,177, 79.4, 0.01, 2026-07-31, 8-11.
NUM = re.compile(r"(?<![A-Za-z0-9_.])[+-]?\d[\d.,:/-]*\d|(?<![A-Za-z0-9_.])\d")
LABEL = re.compile(r"\)\s*<((?:fig|tbl|eq|sec):[A-Za-z0-9_-]+)>|"
                   r"^(?:=+|#heading)[^\n]*?<((?:sec):[A-Za-z0-9_-]+)>", re.M)
REF = re.compile(r"@([A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*)|"
                 r"#refn?\(\s*<([^>]+)>")
HEADING = re.compile(r"(?m)^(=+)\s+([^\n<]+?)(?:\s*<[^>]+>)?\s*$")


def _nums(text: str) -> list[str]:
    return sorted(m.group(0).rstrip(".,:").lstrip("+") for m in NUM.finditer(text))


def profile(path: Path) -> dict:
    src = path.read_text()
    return {
        "numbers": _nums(src),
        "labels": sorted({g for m in LABEL.finditer(src) for g in m.groups() if g}),
        "refs": sorted({g for m in REF.finditer(src) for g in m.groups() if g}),
        "figures": src.count("#figure("),
        "headings": [f"{m.group(1)} {m.group(2).strip()}" for m in HEADING.finditer(src)],
    }


def snapshot(tag: str) -> int:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    data = {f: profile(ROOT / f) for f in FILES}
    (SNAP_DIR / f"{tag}.json").write_text(json.dumps(data, indent=1))
    n = sum(len(d["numbers"]) for d in data.values())
    print(f"snapshot '{tag}': {n:,} numeric tokens, "
          f"{sum(len(d['refs']) for d in data.values())} refs, "
          f"{sum(d['figures'] for d in data.values())} figures across {len(FILES)} files")
    return 0


def check(tag: str) -> int:
    """Compare against the snapshot, judging inventions across the MANUSCRIPT.

    Per-file would be wrong. Content legitimately moves between the main text and
    the SI -- that is most of what a "this belongs in the SI" edit is -- and a
    per-file test reads one move as a number dropped from paper.typ and a
    different number invented in si-body.typ. So the fatal tests (invented
    numbers, lost or gained references, float count) run on the union of both
    files, and per-file movement is reported as a note. A number that appears
    nowhere it appeared before still fails, which is the property that matters.
    """
    from collections import Counter
    want = json.loads((SNAP_DIR / f"{tag}.json").read_text())
    now = {f: profile(ROOT / f) for f in FILES}
    ok = True

    def union(src, key):
        out = Counter()
        for f in FILES:
            out += Counter(src[f][key])
        return out

    # --- manuscript-wide, fatal ---
    ca, cb = union(want, "numbers"), union(now, "numbers")
    invented = sorted((cb - ca).elements())
    if invented:
        print(f"  FATAL -- {len(invented)} numeric token(s) appear nowhere in the "
              f"original: {invented[:12]}")
        ok = False
    dropped = sorted((ca - cb).elements())
    if dropped:
        print(f"  note -- {len(dropped)} numeric token(s) dropped from the "
              f"manuscript (allowed; confirm each is in a table): {dropped[:12]}")

    for key in ("labels", "refs"):
        a, b = union(want, key), union(now, key)
        lost, gained = sorted((a - b).elements()), sorted((b - a).elements())
        if lost or gained:
            print(f"  FATAL -- {key} changed. lost={lost[:8]} gained={gained[:8]}")
            ok = False
    fa = sum(want[f]["figures"] for f in FILES)
    fb = sum(now[f]["figures"] for f in FILES)
    if fa != fb:
        print(f"  FATAL -- #figure count {fa} -> {fb}")
        ok = False

    # --- per-file, informational: where things moved ---
    for f in FILES:
        a, b = want[f], now[f]
        moved = len(set(a["numbers"]) ^ set(b["numbers"]))
        if a["headings"] != b["headings"]:
            lost = [x for x in a["headings"] if x not in b["headings"]]
            gained = [x for x in b["headings"] if x not in a["headings"]]
            print(f"  FATAL -- {f}: headings changed. lost={lost[:6]} gained={gained[:6]}")
            ok = False
        elif moved:
            print(f"  note -- {f}: {moved} numeric token(s) moved in or out")

    print("  prose-edit guard: PASS (no number invented, no reference or float lost)"
          if ok else "  prose-edit guard: FAIL")
    return 0 if ok else 1


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("snapshot", "check"):
        sys.exit(__doc__)
    tag = sys.argv[2] if len(sys.argv) > 2 else "default"
    if sys.argv[1] == "check" and not (SNAP_DIR / f"{tag}.json").is_file():
        print(f"no snapshot '{tag}' -- record one BEFORE the editing pass: "
              f"just edit-baseline" + (f" {tag}" if tag != "default" else ""))
        return 1
    return snapshot(tag) if sys.argv[1] == "snapshot" else check(tag)


if __name__ == "__main__":
    raise SystemExit(main())
