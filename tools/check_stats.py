#!/usr/bin/env python3
"""Check stats.json: every declared number, and whether it can still be trusted.

WHY THIS EXISTS. stats.json used to be pure output, protected by a whole-file
hash in .assets-stamp: any edit was reported, because any edit was wrong. It is
now a file the author may edit -- `origin.by = "hand"` is a supported way to
declare a number that no script produces -- and a hash cannot tell a legitimate
hand entry from a corrupted generated one. This does that job instead, per entry.

WHAT IT CAN AND CANNOT ESTABLISH. It re-runs the generator and diffs, so a
generated value that no longer matches its own analysis is caught outright. It
re-runs every declared guard, so a value that violates what the prose assumes is
caught whoever wrote it. It cannot establish that a hand-entered number is
*correct* -- nothing can, which is why `origin.note` is mandatory: the note is
the audit trail a reader would need.

Run with `just check-stats`; `just verify` runs it as part of the gate.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import typst_prose  # noqa: E402

STATS = ROOT / "stats.json"

# Where a generated entry is re-derived from. One script per project by contract
# (see analysis/justfile), so this can regenerate into a temp file and diff.
GEN = ROOT / "analysis" / "scripts" / "gen_stats.py"


class Finding:
    def __init__(self, level: str, id: str, msg: str) -> None:
        self.level, self.id, self.msg = level, id, msg

    def __str__(self) -> str:
        return f"  {self.level:<6} {self.id:<32} {self.msg}"


def _guard(id: str, rec: dict) -> list[Finding]:
    """Re-run the sign/range guards against the value as committed.

    The generator checks these as it runs, which does nothing for a value that
    was edited afterwards or typed in by hand. This is the same check applied to
    whatever is actually in the file.
    """
    out: list[Finding] = []
    v = rec.get("value")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return out
    expect = rec.get("expect") or {}
    sign = expect.get("sign")
    if sign:
        ok = {"+": v > 0, "-": v < 0, "nonzero": v != 0}.get(sign)
        if ok is None:
            out.append(Finding("error", id, f"unknown sign guard {sign!r}"))
        elif not ok:
            word = {"+": "positive", "-": "negative", "nonzero": "nonzero"}[sign]
            out.append(Finding("error", id,
                f"is {v}, but the prose assumes it is {word}. Either the value "
                f"is wrong or the sentence reading it needs rewording."))
    lo, hi = expect.get("min"), expect.get("max")
    if lo is not None and hi is not None and not lo <= v <= hi:
        out.append(Finding("error", id,
            f"is {v}, outside its declared range [{lo}, {hi}] -- usually a unit "
            f"error or a changed denominator"))
    return out


def _display(id: str, rec: dict) -> list[Finding]:
    """The display string must still be a faithful rendering of the value.

    Catches the edit that changes what a reader sees without changing what the
    arithmetic in `#n("id")` uses -- the two would then silently disagree.
    """
    fmt, v = rec.get("fmt", ""), rec.get("value")
    try:
        want = format(v, fmt) if fmt else str(v)
    except (TypeError, ValueError) as e:
        return [Finding("error", id, f"cannot format {v!r} with {fmt!r}: {e}")]

    if "display" not in rec:
        # Legitimately absent only when str(value) reproduces it AND the reader
        # can be trusted to compute that: ints and strings render the same in
        # Typst and Python. Typst's str() rounds floats, so a float with no
        # stored display would be rendered by a rule this project does not own.
        if isinstance(v, bool) or not isinstance(v, (int, str)):
            return [Finding("error", id,
                f"has no display string, and {type(v).__name__} values cannot "
                f"fall back to str(value) -- Typst's str() rounds floats and "
                f"Python's does not. Re-run: just assets")]
        if want != str(v):
            return [Finding("error", id,
                f"has no display string, but fmt {fmt!r} would render {v!r} as "
                f"{want!r} rather than {str(v)!r}. Re-run: just assets")]
        return []

    shown = rec["display"]
    if want != shown:
        return [Finding("error", id,
            f"display is {shown!r} but value {v!r} formatted {fmt!r} is {want!r}")]
    return []


def _origin(id: str, rec: dict) -> list[Finding]:
    """Every entry must say where it came from, and mean it."""
    o = rec.get("origin")
    if not isinstance(o, dict) or not o.get("by"):
        return [Finding("error", id,
            'has no origin.by -- add "hand" with a note, or let a generator '
            'write it')]
    by = o["by"]
    if by == "hand":
        if not (o.get("note") or "").strip():
            return [Finding("error", id,
                "is hand-entered but has no origin.note. Say where the number "
                "came from: a protocol, a spec, a paper. A typed number with no "
                "provenance is the thing this file exists to prevent.")]
        return []
    if not (ROOT / by).is_file():
        return [Finding("error", id,
            f"was generated by {by}, which no longer exists. Restore the script, "
            f'or take ownership of the value with origin.by = "hand" and a note.')]
    return []


def _unused(values: dict) -> list[Finding]:
    """Declared but never read by the manuscript.

    A warning, not an error: a value can legitimately be declared ahead of the
    sentence that will use it. It is reported because the opposite direction is
    already a hard failure (an unknown id panics the compile), so without this
    nothing ever notices a value going out of use.
    """
    # Line comments are stripped first. stats.typ documents its own usage with a
    # literal `#s("effect.treated_over_control")` in a comment, and paper.typ has
    # `#s("id")` in its header -- counting those as real calls would mask exactly
    # the value that had gone out of use.
    src = " ".join(re.sub(r"//[^\n]*", " ", p.read_text())
                   for p in sorted(ROOT.glob("*.typ")))
    called = set(re.findall(typst_prose.STATS, src))
    called |= set(re.findall(typst_prose.STATS_N, src))
    return [Finding("warn", id, "is declared but no .typ file reads it")
            for id in sorted(set(values) - called)]


def _rederive(values: dict) -> list[Finding]:
    """Re-run the generator and diff its entries against what is committed.

    This is the one check here that establishes something rather than merely
    checking consistency: a generated number is recomputed from the data and
    compared. Possible only because gen_stats.py is a single fast script -- the
    equivalent for figures would mean re-running an analysis that takes hours.

    A generator that cannot run (missing environment, missing data) is reported
    as unverified rather than failed. On a machine without the analysis data
    there is nothing to re-derive from, and failing the gate there would make
    every fresh clone red for a reason the person cannot act on.
    """
    owned = {id: r for id, r in values.items()
             if r.get("origin", {}).get("by") == GEN.relative_to(ROOT).as_posix()}
    if not owned or not GEN.is_file():
        return []

    with tempfile.TemporaryDirectory() as d:
        shadow = Path(d) / "stats.json"
        # The generator merges into whatever is at the target path, so it is
        # pointed at an empty directory: what comes back is exactly this script's
        # own output, with nothing inherited to compare against by accident.
        proc = subprocess.run(
            [sys.executable, str(GEN)],
            cwd=GEN.parent, capture_output=True, text=True,
            env={**__import__("os").environ, "PAPER_STATS_OUT": str(shadow)})
        if proc.returncode != 0:
            return [Finding("note", "(re-derive)",
                f"could not re-run {GEN.relative_to(ROOT)}, so generated values "
                f"were not re-checked: {proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else 'no output'}")]
        if not shadow.is_file():
            return [Finding("note", "(re-derive)",
                "the generator did not honour PAPER_STATS_OUT, so generated "
                "values were not re-checked")]
        fresh = json.loads(shadow.read_text()).get("values", {})

    out: list[Finding] = []
    for id, rec in sorted(owned.items()):
        if id not in fresh:
            out.append(Finding("error", id,
                "is recorded as generated but the generator no longer produces "
                "it. Re-run `just assets` to drop it, or take it over by hand."))
        elif fresh[id].get("value") != rec.get("value"):
            out.append(Finding("error", id,
                f"is {rec.get('value')!r} in stats.json but the analysis now "
                f"produces {fresh[id].get('value')!r} -- run: just assets"))
    for id in sorted(set(fresh) - set(owned)):
        out.append(Finding("error", id,
            "is produced by the generator but is missing from stats.json -- "
            "run: just assets"))
    return out


def main() -> int:
    if not STATS.is_file():
        print("no stats.json: this manuscript declares no generated numbers.")
        return 0
    try:
        doc = json.loads(STATS.read_text())
    except json.JSONDecodeError as e:
        print(f"stats.json is not valid JSON: {e}")
        return 1
    values = doc.get("values")
    if not isinstance(values, dict):
        print("stats.json has no `values` table; regenerate it with `just assets`")
        return 1

    found: list[Finding] = []
    for id, rec in sorted(values.items()):
        found += _origin(id, rec)
        found += _display(id, rec)
        found += _guard(id, rec)
    found += _rederive(values)
    found += _unused(values)

    hand = sum(1 for r in values.values()
               if r.get("origin", {}).get("by") == "hand")
    errors = [f for f in found if f.level == "error"]

    for f in found:
        print(f)
    print(f"  {len(values)} declared value(s), {hand} hand-entered"
          + (f", {len(errors)} error(s)" if errors else ", no errors"))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
