#!/usr/bin/env python3
"""Check stats.json: every declared number, and whether it can still be trusted.

WHY THIS EXISTS. stats.json used to be pure output, protected by a whole-file
hash in .assets-stamp: any edit was reported, because any edit was wrong. It is
now a file the author may edit -- `origin.by = "hand"` is a supported way to
declare a number that no script produces -- and a hash cannot tell a legitimate
hand entry from a corrupted generated one. This does that job instead, per entry.

COST FIRST. `just verify` must rebuild nothing -- it is the command you run
constantly, and a project whose gen_stats.py takes an hour cannot pay that every
time. So the DEFAULT path here only reads files: guards, provenance, checksums,
and a hash comparison of the code and data behind the numbers. Re-running the
generator and diffing is stronger and is opt-in, behind --deep.

The first version of this re-derived unconditionally. On the scaffold that costs
0.02s and looked free; on a real analysis it turns the gate into the analysis.

WHAT IT CAN AND CANNOT ESTABLISH. With --deep it re-runs the generator and diffs,
so a generated value that no longer matches its own analysis is caught outright.
Without it, the `sources` hashes say whether the code or data moved, and the
per-entry checksum catches a value edited by hand. It re-runs every declared
guard either way, so a value that violates what the prose assumes is caught
whoever wrote it. It cannot establish that a hand-entered number is
*correct* -- nothing can, which is why `origin.note` is mandatory: the note is
the audit trail a reader would need.

Run with `just check-stats`; `just verify` runs it as part of the gate.
`just check-stats-deep` adds the re-derivation, and is what to run before
submitting.
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

import hashcache  # noqa: E402
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
    expect = rec.get("expect") or {}
    # expect is hand-edited JSON, so its SHAPE is checked before its meaning: a
    # key this does not understand ("between" instead of min/max) is a guard
    # that would never fire, which must be an error, not a silence.
    if not isinstance(expect, dict):
        return [Finding("error", id,
            f"has an expect that is not an object ({type(expect).__name__}); "
            f"no guard in it can be enforced")]
    unknown = set(expect) - {"sign", "min", "max"}
    if unknown:
        out.append(Finding("error", id,
            f"expect has unknown key(s) {', '.join(sorted(unknown))} -- only "
            f"sign, min and max are understood, so this guard is not being "
            f"enforced"))
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return out
    if v != v:
        return out + [Finding("error", id,
            "is NaN, which no guard can pass and no sentence can state")]
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
    # Each bound on its own: expect is author-edited, and a one-sided band
    # (`min` with no `max`) is a legitimate thing to write there. A bound that
    # is not a number (a quoted "0") is reported, not compared -- comparing
    # would be a TypeError that kills the whole gate without naming the entry.
    lo, hi = expect.get("min"), expect.get("max")
    for name, bound in (("min", lo), ("max", hi)):
        if bound is not None and (isinstance(bound, bool)
                                  or not isinstance(bound, (int, float))):
            out.append(Finding("error", id,
                f"expect.{name} is {bound!r}, not a number -- quoted in the "
                f"JSON? This bound is not being enforced."))
    lo = lo if isinstance(lo, (int, float)) and not isinstance(lo, bool) else None
    hi = hi if isinstance(hi, (int, float)) and not isinstance(hi, bool) else None
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        band = f"[{lo if lo is not None else '-inf'}, {hi if hi is not None else 'inf'}]"
        out.append(Finding("error", id,
            f"is {v}, outside its declared range {band} -- usually a unit "
            f"error or a changed denominator"))
    return out


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


def _display(values: dict) -> list[Finding]:
    """Every entry's fmt must actually apply to its value.

    fmt is the author's to edit, and an edit that breaks it ('.2f' on a label,
    a typo like '.2ff') used to pass `just verify` and kill the next build
    inside render_stats instead -- a silence here, a failure somewhere else.
    The check is the render itself, through the same function the build uses.
    """
    out: list[Finding] = []
    for id, rec in sorted(values.items()):
        try:
            typst_prose.display_of(rec)
        except (TypeError, ValueError) as e:
            out.append(Finding("error", id,
                f"value {rec.get('value')!r} cannot be rendered with fmt "
                f"{rec.get('fmt', '')!r}: {e}. The build would fail on this; "
                f"fix the fmt in stats.json."))
    return out


def _checksum(values: dict) -> list[Finding]:
    """A generated value edited by hand in stats.json.

    Re-deriving catches this too, and more convincingly -- but re-deriving means
    re-running the analysis, which the default path must not do. The generator
    writes a digest of the value; a hand-edit does not know to update it.

    Two versions. v2 covers the VALUE alone: fmt (with unit, desc and expect) is
    the author's to edit in the file, so changing it must not read as tampering.
    v1, written before that split, also covered fmt -- still verified so an
    existing manuscript upgrades without a wall of errors, and rewritten to v2 by
    the next `just assets`.

    Hand-entered values are skipped: nothing generated their checksum, and there
    is nothing to compare against. Their guarantee is the guard and the note.
    """
    import hashlib
    out: list[Finding] = []
    for id, rec in sorted(values.items()):
        if rec.get("origin", {}).get("by") == "hand":
            continue
        want = rec.get("checksum")
        if not want:
            continue          # written before checksums; `just assets` adds one
        if want.startswith("v1:"):
            payload = json.dumps([rec.get("value"), rec.get("fmt", "")],
                                 sort_keys=True, separators=(",", ":"))
        elif want.startswith("v2:"):
            payload = json.dumps(rec.get("value"),
                                 sort_keys=True, separators=(",", ":"))
        else:
            out.append(Finding("error", id,
                f"has checksum {want!r}, which no version of this scaffold "
                f"wrote -- run `just assets` to re-record it"))
            continue
        version = want[:3]
        have = version + hashlib.sha256(payload.encode()).hexdigest()[:16]
        if have != want:
            if version == "v1:":
                # A v1 digest covers value AND fmt, and cannot tell a fmt edit
                # -- which the contract now invites -- from a value edit, which
                # it exists to catch. Failing the gate here would punish the
                # documented workflow, and on a fresh clone the only clean fix
                # (`just assets`) needs analysis data the clone does not have.
                # So: a warning, with the honest ambiguity stated. The next
                # `just assets` re-records as v2 and the ambiguity is gone.
                out.append(Finding("warn", id,
                    f"has a pre-3.3.0 (v1) checksum that no longer matches. "
                    f"Either the fmt was edited (yours to do) or the value was "
                    f"(not yours) -- a v1 digest cannot tell which. Verify the "
                    f"value, then `just assets` to re-record it as v2."))
            else:
                out.append(Finding("error", id,
                    f"value {rec.get('value')!r} does not match the checksum "
                    f"its generator recorded, so it was edited by hand. Change "
                    f"the analysis and re-run `just assets`, or take the value "
                    f'over with origin.by = "hand" and a note.'))
    return out


def _pinned(doc: dict) -> list[Finding]:
    """Author-pinned files: paths the author declared worth watching, by hand.

    Nothing discovers these programmatically -- that is the point. A generator's
    inputs are recorded by the generator; `pinned` is for everything else the
    manuscript's numbers quietly depend on (a raw export, a protocol document, a
    config), declared in stats.json and hashed by `just pin`.

    A pin with no recorded hash is an error: the declaration says the file
    matters, and until `just pin` runs nothing can say whether it moved. A
    pinned file that is absent is a note, like an absent source -- data usually
    lives outside the repository, and a fresh clone cannot act on it.

    Cached hashing, like _sources: pins exist precisely for the big raw files.
    """
    out: list[Finding] = []
    pinned = doc.get("pinned") or {}
    if not isinstance(pinned, dict):
        # Hand-authored by design, so its shape is a thing that can be wrong.
        # A list of paths is the obvious first guess at the syntax.
        return [Finding("error", "pinned",
            f'is not an object ({type(pinned).__name__}). The shape is '
            f'{{"path/relative/to/root": null}}; then run: just pin')]
    for src, want in sorted(pinned.items()):
        p = ROOT / src
        if not want:
            out.append(Finding("error", src,
                "is listed in `pinned` but has no recorded hash -- run: just pin"))
            continue
        if not p.is_file():
            out.append(Finding("note", src,
                "is pinned but not present, so it could not be verified"))
            continue
        if hashcache.sha(p) != want:
            out.append(Finding("error", src,
                "has changed since it was pinned. Check the numbers that "
                "depend on it, then re-record it: just pin"))
    return out


def _sources(doc: dict) -> list[Finding]:
    """Has the code or data behind the generated numbers moved since they were written?

    The cheap gate. Answers in milliseconds what re-deriving answers in however
    long the analysis takes, and is why re-deriving can be opt-in: if none of
    these hashes moved, there is nothing for a re-run to find.

    A file that is not present is reported as unverifiable rather than stale --
    analysis/data/ is normally untracked, so that is the ordinary state of a
    fresh clone, and failing there would be a red gate nobody can act on.

    Hashing goes through the stat-keyed cache in hashcache.py: a declared input
    can be gigabytes, and the constant gate must not pay a full read of it on
    every run when the file has not been touched.
    """
    out: list[Finding] = []
    for script, inputs in sorted((doc.get("sources") or {}).items()):
        for src, want in sorted((inputs or {}).items()):
            p = ROOT / src
            if not p.is_file():
                out.append(Finding("note", script,
                    f"input {src} is not present, so it could not be verified"))
                continue
            if hashcache.sha(p) != want:
                out.append(Finding("error", script,
                    f"{src} has changed since these numbers were written -- "
                    f"run: just assets  (or `just check-stats-deep` to see "
                    f"which values actually move)"))
    return out


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
    mine = GEN.relative_to(ROOT).as_posix()
    owned = {id: r for id, r in values.items()
             if r.get("origin", {}).get("by") == mine}
    # The status string reaches the summary line, because "(re-derived)" must
    # not be printable when nothing was: on an all-hand-entered manuscript this
    # returned empty and the summary still claimed re-derivation -- a silent
    # no-op wearing a verification label. (Found downstream, in koth-paper.)
    if not owned:
        return [], "nothing generator-owned to re-derive"
    if not GEN.is_file():
        return [], f"{mine} is absent, nothing re-derived"

    with tempfile.TemporaryDirectory() as d:
        shadow = Path(d) / "stats.json"
        # The shadow STARTS AS A COPY of the real stats.json, so the generator
        # merges against the same file it would in `just assets` -- above all,
        # its values are judged by the author-edited guards in the FILE, not by
        # the seeds in add(). An empty shadow used to make every entry "new",
        # which resurrected stale seed guards; the run then died on a guard the
        # author had already widened, and the death was downgraded to a note --
        # re-derivation silently disabled by the exact edit the contract invites.
        shadow.write_text(STATS.read_text())
        # THROUGH uv, not sys.executable. The generator belongs to the analysis,
        # which has its own environment (analysis/pyproject.toml) and its own
        # dependencies -- pandas, typically -- that the manuscript toolchain has
        # no reason to carry. Run with this interpreter it died on
        # ModuleNotFoundError, which was downgraded to "could not re-run ...":
        # the strongest check in the pipeline silently reduced to a note, on a
        # machine where it could have run. `uv run` resolves the project from
        # the script's directory, exactly as analysis/justfile does. Falls back
        # to this interpreter when uv is absent, so a stdlib-only generator
        # still re-derives. (Found downstream, in the dnoise manuscript.)
        import os
        import shutil
        runner = (["uv", "run", "--quiet", "python", str(GEN)]
                  if shutil.which("uv") else [sys.executable, str(GEN)])
        proc = subprocess.run(
            runner,
            cwd=GEN.parent, capture_output=True, text=True,
            env={**os.environ, "PAPER_STATS_OUT": str(shadow)})
        if proc.returncode != 0:
            err = (proc.stderr.strip().splitlines()[-1]
                   if proc.stderr.strip() else "no output")
            if "StatError" in proc.stderr:
                # The fresh value violated a guard in stats.json. That is a
                # finding about the numbers, not an environment problem, and
                # `just assets` would fail the same way.
                return [Finding("error", "(re-derive)",
                    f"the analysis now produces a value that violates a guard "
                    f"in stats.json: {err}")], "re-derivation failed on a guard"
            return [Finding("note", "(re-derive)",
                f"could not re-run {GEN.relative_to(ROOT)}, so generated values "
                f"were not re-checked: {err}")], "could not re-run the generator"
        doc = json.loads(shadow.read_text())
        # Only this generator's entries are compared: the copy carried the hand
        # and other-script entries along, and they are not re-derivable.
        fresh = {id: r for id, r in doc.get("values", {}).items()
                 if r.get("origin", {}).get("by") == mine}

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
    return out, f"{len(owned)} value(s) re-derived"


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
        found += _guard(id, rec)
    found += _display(values)
    found += _checksum(values)
    found += _sources(doc)
    found += _pinned(doc)
    # Opt-in, because it re-runs the analysis. See the module docstring.
    deep = ""
    if "--deep" in sys.argv:
        rederived, status = _rederive(values)
        found += rederived
        deep = f" ({status})"
    found += _unused(values)

    hand = sum(1 for r in values.values()
               if r.get("origin", {}).get("by") == "hand")
    errors = [f for f in found if f.level == "error"]

    from report import findings
    findings([(f.level, f.id, f.msg) for f in found])
    pins = len(doc.get("pinned") or {})
    print(f"  {len(values)} declared value(s), {hand} hand-entered{deep}"
          + (f", {pins} pinned file(s)" if pins else "")
          + (f", {len(errors)} error(s)" if errors else ", no errors"))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
