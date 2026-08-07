#!/usr/bin/env python3
"""Adopt committed figures and tables that no generator can rebuild.

WHY THIS EXISTS. The manifest contract assumes every file under figures/ and
si/ is written by a script that calls record(). A manuscript migrating onto
this scaffold usually cannot satisfy that: the figures exist, the paper cites
them, and the analysis that made them is gone, unrunnable, or lives in a
repository nobody can find. Without this tool those files are permanent
`unclaimed` errors, and the honest options are to lie (fake a generator) or to
give up on the manifest entirely.

Adoption is the third option: the file is declared with `origin.by =
"adopted"` and a note saying where it came from. That buys the checks that
still apply -- the hash (so a silent change to the file is caught), the
reference check (so the manuscript must actually use it) -- and states plainly
what is missing: NOTHING CAN REGENERATE THIS FILE. The note is the audit
trail, exactly as it is for a hand-entered number in stats.json.

There is no stats equivalent of this tool because none is needed: a value
whose analysis is gone is entered by hand with `origin.by = "hand"` and a
note, which stats.json has supported since 3.3.0.

USAGE.
    just adopt note="imported from github.com/x/y at 3f2a1c0"

Every file under figures/ and si/ that no assets.json entry claims is adopted
with that note. Re-running it refreshes the hash of an adopted file that
changed -- accepting the change deliberately, like `just pin` -- and reports
what it did. Reference the adopted ids from the prose like any other:
`#fig("fig.name")`, `#tbl("tbl.name")`.

THE WAY BACK. If the analysis is ever restored, a generator that calls
record() with an adopted id TAKES IT OVER: adoption is explicitly the
provenance a script may replace, because a rebuildable file is strictly better
than an adopted one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import hashcache  # noqa: E402

ASSETS = ROOT / "assets.json"
OUTPUT_DIRS = ("figures", "si")

ABOUT = ("Figures and tables the manuscript includes, referenced as "
         "#fig(\"<id>\") / #tbl(\"<id>\"). Written by the scripts in "
         "analysis/scripts/; see analysis/scripts/_assets.py.")


def _id_for(rel: str) -> str:
    """figures/flow_chart.png -> fig.flow-chart; si/cohort_table.typ -> tbl.cohort-table"""
    p = Path(rel)
    prefix = "fig" if p.parts[0] == "figures" else "tbl"
    stem = p.stem.replace("_", "-").replace(" ", "-").lower()
    return f"{prefix}.{stem}"


def adopt(root: Path, note: str) -> tuple[list[str], int]:
    """Adopt every unclaimed file; refresh changed adopted hashes. Pure-ish for tests."""
    if not note.strip():
        return (["a note is required: where did these files come from? "
                 '(just adopt note="imported from ... at commit ...")'], 1)

    doc = {"_about": ABOUT, "values": {}}
    if (root / "assets.json").is_file():
        try:
            doc = json.loads((root / "assets.json").read_text())
            doc.setdefault("values", {})
        except json.JSONDecodeError as e:
            return ([f"assets.json is not valid JSON ({e}); fix it first"], 1)
    values = doc["values"]
    if not isinstance(values, dict):
        return (["assets.json has a `values` block that is not an object; "
                 "fix it first"], 1)

    claimed = {r.get("path") for r in values.values()}
    lines: list[str] = []

    for d in OUTPUT_DIRS:
        folder = root / d
        if not folder.is_dir():
            continue
        for f in sorted(folder.rglob("*")):
            if not f.is_file() or f.name.startswith(".") or f.suffix == ".pyc":
                continue
            rel = f.relative_to(root).as_posix()
            if rel in claimed:
                continue
            id = _id_for(rel)
            if id in values:
                lines.append(f"  SKIPPED   {rel}: id {id} is already declared "
                             f"for {values[id].get('path')}; rename the file "
                             f"or edit the entry by hand")
                continue
            values[id] = {
                "path": rel,
                "kind": "figure" if rel.startswith("figures/") else "table",
                "desc": "",
                "hash": hashcache.sha(f),
                "origin": {"by": "adopted", "note": note.strip()},
                "inputs": {},
            }
            lines.append(f"  adopted   {rel} as {id}")

    # Refresh adopted entries whose file changed: re-running this tool IS the
    # deliberate acceptance, the same contract as `just pin`.
    for id, rec in sorted(values.items()):
        if rec.get("origin", {}).get("by") != "adopted":
            continue
        p = root / rec.get("path", "")
        if p.is_file() and hashcache.sha(p) != rec.get("hash"):
            rec["hash"] = hashcache.sha(p)
            lines.append(f"  refreshed {rec['path']}: hash re-recorded, "
                         f"accepting the change")

    (root / "assets.json").write_text(json.dumps(
        {**doc, "_about": doc.get("_about", ABOUT),
         "values": dict(sorted(values.items()))}, indent=2) + "\n")
    adopted = sum(1 for r in values.values()
                  if r.get("origin", {}).get("by") == "adopted")
    lines.append(f"  {len(values)} declared asset(s), {adopted} adopted -- "
                 f"nothing can regenerate an adopted file; the note is its "
                 f"provenance")
    return (lines, 0)


def main() -> int:
    note = ""
    for a in sys.argv[1:]:
        if a.startswith("--note="):
            note = a[len("--note="):]
    lines, rc = adopt(ROOT, note)
    for line in lines:
        print(line)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
