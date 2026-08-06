"""Declare the numbers the manuscript states in prose, with guards.

WHY THIS EXISTS. Tables and figures have always tracked the analysis, because a
script writes them. Numbers written into sentences are typed by hand, and they
drift: a unit error, a stale percentage after a re-run, a value corrected in the
table but not in the paragraph beside it. A staleness checker can only notice
drift after the fact. Sourcing the sentence from the same data as the table makes
the two unable to disagree.

WHAT A GUARD IS FOR. A generated number can still make a sentence read wrong.
"counts fell by #s(...)%" is correct only while the value is negative; the day a
re-run turns it positive, the paper says "fell by -3.1%" and nothing complains.
`sign` and `between` are assertions about what the analysis is allowed to
produce. They fail HERE, when the number changes, naming the sentence's
assumption -- not in review.

WHO OWNS AN ENTRY. Every value records `origin.by`: either the script that wrote
it, or the literal "hand". A script replaces only its own entries when it runs, so
a number you type in by hand is never clobbered by `just assets`. That is the
difference between a file the analysis owns and a file you own that the analysis
contributes to, and it is the reason this is at the manuscript root rather than
under si/.

A hand entry must carry `origin.note` saying where the number came from -- a
protocol, a vendor spec, a reference. `tools/check_stats.py` enforces that, and
re-runs the guards below against whatever is in the file, so a typed number is
guarded exactly as tightly as a derived one.

USAGE. One script per project writes the whole file:

    from _stats import Stats

    st = Stats()
    st.add("recovery.mean", 84.23, fmt=".1f", unit="%",
           desc="Mean recovery across replicates",
           sign="+", between=(0, 100),
           source="scripts/example_data.csv")
    st.write()

The manuscript then reads it as `#s("recovery.mean")`, which resolves at compile
time and fails the build on an unknown key.

IDS. Dotted, flat, and stable: `<group>.<name>`. The dots are part of the key,
not nesting -- one flat table is greppable, listable and diffable, and an ID can
be moved between groups without restructuring the file.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent.parent            # analysis/scripts/ -> analysis/ -> paper/

# At the manuscript root, not under si/, because this is no longer purely
# generated output: `origin.by = "hand"` entries are written by a person and are
# a supported way to use the file. si/ means "written by the analysis, never edit"
# everywhere else, and a file you are invited to edit does not belong there.
OUT = PAPER / "stats.json"

ABOUT = ("Numbers the manuscript states in prose, read as #s(\"<id>\"). Entries "
         "with origin.by pointing at a script are rewritten by that script; "
         "entries with origin.by = \"hand\" are yours and are never overwritten.")


class StatError(Exception):
    """A declared value violated the guard the prose depends on."""


def _caller_script() -> str:
    """Path of the running generator, relative to the manuscript root.

    Recorded as `origin.by` so `write()` knows which entries are its own to
    replace, and so `tools/check_stats.py` can tell a derived number from a typed
    one. Derived from __main__ rather than passed in, because a generator that
    had to name itself would eventually name itself wrongly after a rename.
    """
    main = sys.modules.get("__main__")
    p = getattr(main, "__file__", None)
    if not p:
        raise StatError(
            "cannot tell which script is writing stats.json (no __main__.__file__). "
            "Run the generator as a script, not from an interactive session.")
    return Path(p).resolve().relative_to(PAPER).as_posix()


class Stats:
    """Collects declared values, checks their guards, merges into stats.json."""

    def __init__(self) -> None:
        self._values: dict[str, dict] = {}

    def add(self, id: str, value, *, fmt: str = "", unit: str = "",
            desc: str = "", sign: str | None = None,
            between: tuple[float, float] | None = None,
            source: str = "") -> None:
        """Declare one number.

        `value`   the raw value. A str is allowed for things that are not
                  numbers (a name, a flag); guards are then rejected rather than
                  silently skipped.
        `fmt`     Python format spec for the DISPLAY string: ".1f", ",.0f", "+.2f".
                  Rounding lives here, next to the analysis, rather than being
                  reimplemented in Typst.
        `sign`    "+", "-", or "nonzero". What the prose assumes about direction.
        `between` (lo, hi) inclusive. A plausibility band: catches a unit error
                  or a percentage that lands at 8400.
        `desc`    what the number is, for someone auditing the file later.
        `source`  where it came from, relative to analysis/.
        """
        if id in self._values:
            raise StatError(f"{id!r} declared twice")
        if not id or " " in id:
            raise StatError(f"{id!r} is not a usable id (no spaces, not empty)")

        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not numeric and (sign is not None or between is not None):
            raise StatError(
                f"{id!r} has a guard but its value {value!r} is not numeric. "
                f"Drop the guard, or pass the number rather than a pre-formatted "
                f"string.")

        if numeric:
            self._check(id, float(value), sign, between)

        expect: dict = {}
        if sign is not None:
            expect["sign"] = sign
        if between is not None:
            expect["min"], expect["max"] = between

        self._values[id] = {
            "value": value,
            "display": format(value, fmt) if fmt else str(value),
            # Recorded so check_stats.py can re-derive the display string from the
            # value and catch an edit to one that no longer matches the other.
            "fmt": fmt,
            "unit": unit,
            "desc": desc,
            "expect": expect,
            "source": source,
            "origin": {"by": _caller_script()},
        }

    @staticmethod
    def _check(id: str, v: float, sign: str | None,
               between: tuple[float, float] | None) -> None:
        if sign is not None:
            ok = {"+": v > 0, "-": v < 0, "nonzero": v != 0}
            if sign not in ok:
                raise StatError(
                    f"{id!r}: sign must be '+', '-' or 'nonzero', got {sign!r}")
            if not ok[sign]:
                raise StatError(
                    f"{id!r} is {v}, which violates sign '{sign}'.\n"
                    f"  The prose is written assuming this number is "
                    f"{ {'+': 'positive', '-': 'negative', 'nonzero': 'nonzero'}[sign] }. "
                    f"Either the analysis changed meaning, or the sentence that "
                    f"reads it needs rewording.")
        if between is not None:
            lo, hi = between
            if not lo <= v <= hi:
                raise StatError(
                    f"{id!r} is {v}, outside the expected range [{lo}, {hi}].\n"
                    f"  Usually a unit error or a changed denominator. Widen the "
                    f"band if the new value is genuinely right.")

    def write(self, out: Path | None = None) -> int:
        """Merge these values into stats.json and report what is unguarded.

        MERGES rather than overwrites. Entries whose `origin.by` names this same
        script are replaced (including ones this run no longer declares, which is
        how a deleted `st.add` removes a value). Everything else is kept
        untouched -- `origin.by = "hand"` entries above all, which is what makes
        the file safe to edit.

        The old behaviour was to write the whole file from scratch, so anything
        added by hand survived until the next `just assets` and then vanished.
        """
        # PAPER_STATS_OUT redirects the write, which is how tools/check_stats.py
        # re-derives the generated values into a scratch file and diffs them
        # against what is committed. Pointed at an empty directory there is
        # nothing to merge with, so what comes back is purely this script's own
        # output -- which is exactly what the diff needs.
        p = out or Path(os.environ.get("PAPER_STATS_OUT") or OUT)
        p.parent.mkdir(parents=True, exist_ok=True)
        mine = _caller_script()

        kept: dict[str, dict] = {}
        if p.is_file():
            try:
                existing = json.loads(p.read_text()).get("values", {})
            except json.JSONDecodeError as e:
                raise StatError(
                    f"{p.name} is not valid JSON ({e}), so this script cannot "
                    f"merge into it without losing whatever is there. Fix or "
                    f"delete the file.") from None
            for id, rec in existing.items():
                by = rec.get("origin", {}).get("by")
                if by == mine:
                    continue          # ours; this run rewrites it
                if by is None and id in self._values:
                    # Written before entries recorded an owner. Claimed by the
                    # script that declares it now, which is what makes upgrading
                    # an existing stats.json a no-op rather than a conflict.
                    continue
                kept[id] = rec

        clash = sorted(set(kept) & set(self._values))
        if clash:
            raise StatError(
                f"{', '.join(clash)} already declared in {p.name} by "
                f"{kept[clash[0]].get('origin', {}).get('by', '?')}, and this "
                f"script declares it too. One id, one owner: rename one of them.")

        merged = {**kept, **self._values}
        p.write_text(json.dumps(
            {"_about": ABOUT, "values": dict(sorted(merged.items()))},
            indent=2, sort_keys=False) + "\n")
        hand = sum(1 for v in merged.values()
                   if v.get("origin", {}).get("by") == "hand")

        # An unguarded number is not an error -- plenty of values have no
        # meaningful sign or range. It is reported so the set stays visible
        # rather than quietly becoming the default.
        bare = [k for k, v in self._values.items()
                if not v["expect"] and isinstance(v["value"], (int, float))]
        # Not relative_to(PAPER): under PAPER_STATS_OUT the target is a scratch
        # file outside the manuscript, and relative_to raises on that.
        try:
            shown = p.relative_to(PAPER)
        except ValueError:
            shown = p
        print(f"wrote {shown}  ({len(self._values)} from this "
              f"script, {len(merged)} total"
              f"{f', {hand} hand-entered' if hand else ''})")
        if bare:
            print(f"  {len(bare)} numeric value(s) with no sign/range guard: "
                  f"{', '.join(sorted(bare)[:6])}"
                  f"{' ...' if len(bare) > 6 else ''}")
        return 0
