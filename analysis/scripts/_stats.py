"""Declare the numbers the manuscript states in prose, with guards.

WHY THIS EXISTS. Tables and figures have always tracked the analysis, because a
script writes them. Numbers written into sentences are typed by hand, and they
drift: a unit error, a stale percentage after a re-run, a value corrected in the
table but not in the paragraph beside it. A staleness checker can only notice
drift after the fact. Sourcing the sentence from the same data as the table makes
the two unable to disagree.

WHO OWNS WHICH FIELD. The split follows what each field is:

    value     a fact about the data. The script owns it, and updates it (with
              its checksum and origin) on every run. Nobody else can honestly
              write it.
    fmt, unit, desc
              presentation and documentation -- manuscript concerns. YOURS,
              edited in stats.json. Deciding "two decimals with a sign" is an
              editorial choice, not an analysis result.
    expect    what the PROSE assumes ("fell", "roughly 80-90%"). That assumption
              lives next to the sentence, so it is yours too, in stats.json.

The arguments to `add()` beyond the value are SEEDS: they populate a new entry
so the file is never born empty, and are ignored once the entry exists (with a
note when they differ from the file, so a stale script argument is visible
rather than silently dead).

WHAT A GUARD IS FOR. A generated number can still make a sentence read wrong.
"counts fell by #s(...)%" is correct only while the value is negative; the day a
re-run turns it positive, the paper says "fell by -3.1%" and nothing complains.
`expect` is an assertion about what the analysis is allowed to produce. It fails
HERE, when the number changes, naming the sentence's assumption -- not in
review. The fresh value is checked against the guard AS IT STANDS IN THE FILE,
because that is the one you maintain.

WHO OWNS AN ENTRY. Every value records `origin.by`: either the script that wrote
it, or the literal "hand". A script replaces only its own entries when it runs, so
a number you type in by hand is never clobbered by `just assets`. `origin.at` is
when the value last CHANGED -- a re-run that reproduces the same number does not
touch it, so the date means something.

A hand entry must carry `origin.note` saying where the number came from -- a
protocol, a vendor spec, a reference. `tools/check_stats.py` enforces that, and
re-runs the guards against whatever is in the file, so a typed number is guarded
exactly as tightly as a derived one.

USAGE. One script per project writes the whole file:

    from _stats import Stats

    st = Stats()
    st.add("recovery.mean", 84.23, fmt=".1f", unit="%",
           desc="Mean recovery across replicates",
           sign="+", between=(0, 100))
    st.write()

The manuscript then reads it as `#s("recovery.mean")`, which resolves at compile
time and fails the build on an unknown key.

IDS. Dotted, flat, and stable: `<group>.<name>`. The dots are part of the key,
not nesting -- one flat table is greppable, listable and diffable, and an ID can
be moved between groups without restructuring the file.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from _provenance import PAPER, caller_script, code_inputs, declared_inputs

from manifest_validation import guard_errors, validate, ManifestError
from atomic_io import write_text

# At the manuscript root, not under si/, because this is no longer purely
# generated output: `origin.by = "hand"` entries, and the fmt/unit/desc/expect
# of every entry, are written by a person. si/ means "written by the analysis,
# never edit" everywhere else, and a file you are invited to edit does not
# belong there.
OUT = PAPER / "stats.json"

ABOUT = ("Numbers the manuscript states in prose, read as #s(\"<id>\"). Scripts "
         "own each entry's value; fmt, unit, desc and expect are the author's "
         "to edit here. Entries with origin.by = \"hand\" are entirely yours.")

# Fields the author owns once an entry exists. The script's arguments seed them
# on first write and are ignored afterwards.
AUTHOR_FIELDS = ("fmt", "unit", "desc", "expect")


class StatError(Exception):
    """A declared value violated the guard the prose depends on."""


def _caller_script() -> str:
    """Which generator is writing, recorded as `origin.by`."""
    return caller_script()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _checksum(value) -> str:
    """A short digest of the value, the one field only the generator may write.

    Catches a generated value edited by hand in stats.json. Re-deriving would
    catch it too and more convincingly, but re-deriving means re-running the
    analysis, which is exactly what `just verify` must not do. A hand-edit will
    not know to update this, so it is caught for free on every check.

    v2 covers the VALUE alone. v1 also covered fmt, from when fmt was
    script-owned; editing fmt in the file is supported now, so it must not
    look like tampering. tools/check_stats.py still verifies v1 checksums, so
    an existing manuscript upgrades without a wall of errors.

    Protection against accident, not against a determined edit -- someone who
    updates both is indistinguishable from the generator, and no scheme that
    keeps the record next to the value can do better.
    """
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return "v2:" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def _prune_allowed() -> bool:
    return (os.environ.get("PAPER_STATS_PRUNE", "").lower() in ("1", "true", "yes")
            or "--prune" in sys.argv[1:])


def _record_failures(target: Path, failed: dict[str, str], entries: dict,
                     values: dict) -> None:
    """The guard failures of this run, for `just assets --explain`.

    Written beside the build state, never under PAPER_STATS_OUT's scratch
    target (a --deep re-derivation is not the author's run). Removed when a
    run passes, so a stale list never outlives its failure.
    """
    if os.environ.get("PAPER_STATS_OUT"):
        return
    path = target.parent / ".build-state" / "stats-guard-failures.json"
    if not failed:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, json.dumps({id: {
        "message": msg, "value": values[id],
        "expect": (entries[id] or {}).get("expect", {})}
        for id, msg in sorted(failed.items())}, indent=1, default=str) + "\n")


class Stats:
    """Collects declared values, checks their guards, merges into stats.json."""

    def __init__(self) -> None:
        self._values: dict[str, dict] = {}
        self._passed: dict[str, set] = {}     # which seed fields were explicit

    def add(self, id: str, value, *, fmt: str | None = None,
            unit: str | None = None, desc: str | None = None,
            sign: str | None = None,
            between: tuple[float, float] | None = None,
            minimum: float | None = None,
            maximum: float | None = None) -> None:
        """Declare one number.

        `value`   the raw value. A str is allowed for things that are not
                  numbers (a name, a flag); guards are then rejected rather than
                  silently skipped.

        Everything else SEEDS a new entry and is owned by stats.json once the
        entry exists -- edit the file, not this call, to change them:

        `fmt`     Python format spec for the DISPLAY string: ".1f", ",.0f", "+.2f".
        `sign`    "+", "-", or "nonzero". What the prose assumes about direction.
        `between` (lo, hi) inclusive. A plausibility band: catches a unit error
                  or a percentage that lands at 8400.
        `minimum`, `maximum`
                  one side of that band, inclusive, for a value with no natural
                  ceiling (a count is at least zero) or floor. Either, or both;
                  not together with `between`, which already says both.
        `desc`    what the number is, for someone auditing the file later.

        Guards are enforced in `write()`, against the file's `expect` for an
        existing entry and against these seeds for a new one -- the file's guard
        is the one the author maintains, so it is the one that judges the value.
        """
        if id in self._values:
            raise StatError(f"{id!r} declared twice")
        if not id or " " in id:
            raise StatError(f"{id!r} is not a usable id (no spaces, not empty)")

        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        guarded = (sign is not None or between is not None
                   or minimum is not None or maximum is not None)
        if not numeric and guarded:
            raise StatError(
                f"{id!r} has a guard but its value {value!r} is not numeric. "
                f"Drop the guard, or pass the number rather than a pre-formatted "
                f"string.")
        if sign is not None and sign not in ("+", "-", "nonzero"):
            raise StatError(
                f"{id!r}: sign must be '+', '-' or 'nonzero', got {sign!r}")
        if between is not None and (minimum is not None or maximum is not None):
            raise StatError(
                f"{id!r}: pass between=(lo, hi) or minimum=/maximum=, not both")

        expect: dict = {}
        if sign is not None:
            expect["sign"] = sign
        if between is not None:
            expect["min"], expect["max"] = between
        if minimum is not None:
            expect["min"] = minimum
        if maximum is not None:
            expect["max"] = maximum

        # The seed fmt must at least apply to the value it arrives with. This
        # raises HERE, next to the analysis that chose it, rather than at render
        # time with no idea which script is responsible. The file's fmt is
        # checked again in write(), because the author may have changed either.
        if fmt:
            try:
                format(value, fmt)
            except (TypeError, ValueError) as e:
                raise StatError(
                    f"{id!r}: cannot format {value!r} with fmt {fmt!r}: {e}"
                ) from None

        self._passed[id] = {f for f, v in
                            (("fmt", fmt), ("unit", unit), ("desc", desc))
                            if v is not None}
        if guarded:
            self._passed[id].add("expect")
        self._values[id] = {
            "value": value,
            "fmt": fmt or "",
            "unit": unit or "",
            "desc": desc or "",
            "expect": expect,
        }

    @staticmethod
    def _enforce(id: str, value, expect: dict) -> None:
        """The fresh value against the guard that governs it.

        `expect` may come from the file, where the author can write a one-sided
        bound (`min` without `max`), so each bound is checked independently.
        And because it is hand-edited JSON, its SHAPE is validated too: an
        unknown key ("between" instead of min/max), a quoted bound, a NaN --
        each must fail loudly, because a guard that is silently not enforced is
        worse than no guard at all.
        """
        errors = guard_errors(value, expect)
        if errors:
            raise StatError(f"{id!r}: " + "; ".join(errors))

    def write(self, out: Path | None = None, *, inputs: list[str] = (),
              keep_hand_ids: set[str] | None = None) -> int:
        """Merge these values into stats.json and report what is unguarded.

        MERGES rather than overwrites, twice over. Entries whose `origin.by`
        names another script or "hand" are kept untouched. Entries this script
        owns get their VALUE (and checksum, and origin) replaced, while their
        fmt/unit/desc/expect are preserved as the author left them -- the seeds
        from add() apply only when the entry does not exist yet. An id this run
        no longer declares is removed, which is how a deleted `st.add` retires a
        value.

        Top-level blocks this script does not own (`pinned` above all) are
        carried through unchanged.

        Hand entries are kept too, by default all of them. `keep_hand_ids` is
        the opt-in exception for a manuscript that retires a whole branch of
        its argument: pass the hand ids still in use, and every other hand
        entry is dropped (and named, so the pruning is never silent). Entries
        owned by other scripts are untouched either way.
        """
        # PAPER_STATS_OUT redirects the write, which is how tools/check_stats.py
        # re-derives the generated values into a scratch file and diffs them
        # against what is committed. Pointed at an empty directory there is
        # nothing to merge with, so what comes back is purely this script's own
        # output -- which is exactly what the diff needs.
        # `inputs` are the DATA files this generator read, relative to the
        # manuscript root. Together with the code it imported they become the
        # `sources` block: the CHEAP gate that lets `just check-stats` say "the
        # analysis behind these numbers moved" without re-running the analysis.
        #
        # That gate is the whole point. Re-deriving is a stronger check and it is
        # opt-in (`--deep`), because `just verify` must rebuild nothing: a project
        # whose gen_stats.py takes an hour cannot pay that on every run of the
        # gate, and the first version of this made it do exactly that.
        p = Path(os.environ["PAPER_STATS_OUT"]) if os.environ.get("PAPER_STATS_OUT") else (out or OUT)
        p.parent.mkdir(parents=True, exist_ok=True)
        mine = _caller_script()

        existing_doc: dict = {}
        if p.is_file():
            try:
                existing_doc = json.loads(p.read_text())
            except json.JSONDecodeError as e:
                raise StatError(
                    f"{p.name} is not valid JSON ({e}), so this script cannot "
                    f"merge into it without losing whatever is there. Fix or "
                    f"delete the file.") from None
        try:
            if p.is_file():
                validate(existing_doc, "stats")
        except ManifestError as exc:
            raise StatError(str(exc)) from None
        existing = existing_doc.get("values", {})
        if not isinstance(existing, dict):
            # Refuse, exactly like the invalid-JSON case above: treating a
            # malformed block as empty would rewrite the file with every
            # hand-entered and other-script entry silently deleted.
            raise StatError(
                f"{p.name} has a `values` block that is not an object "
                f"({type(existing).__name__}), so this script cannot merge into "
                f"it without losing whatever is there. Fix the file.")

        kept: dict[str, dict] = {}
        prior: dict[str, dict] = {}
        pruned: list[str] = []
        for id, rec in existing.items():
            by = (rec.get("origin") or {}).get("by")
            if by == mine:
                prior[id] = rec
            elif by is None and id in self._values:
                # Written before entries recorded an owner. Claimed by the
                # script that declares it now, which is what makes upgrading
                # an existing stats.json a no-op rather than a conflict.
                prior[id] = rec
            elif (by == "hand" and keep_hand_ids is not None
                  and id not in keep_hand_ids):
                pruned.append(id)
            else:
                kept[id] = rec

        clash = sorted(set(kept) & set(self._values))
        if clash:
            owner = kept[clash[0]].get("origin", {}).get("by", "?")
            if owner == "hand":
                # The migration handover: the value was declared by hand while
                # the analysis could not run, and now a generator computes it.
                # "Rename one of them" is exactly the wrong advice there -- the
                # ids SHOULD collide; the hand entry is the one that retires.
                # Not automatic, because a hand entry with a note is authored
                # data and a script must not silently overwrite it.
                raise StatError(
                    f"{', '.join(clash)}: declared by hand in {p.name}, and "
                    f"this script now computes it. If the computed value "
                    f"supersedes the hand entry (the usual migration handover), "
                    f"delete the hand entry from {p.name} and re-run; its "
                    f"fmt/unit/desc/expect will seed from this script's add(). "
                    f"If both are meant to exist, rename one id.")
            raise StatError(
                f"{', '.join(clash)} already declared in {p.name} by "
                f"{owner}, and this script declares it too. One id, one owner: "
                f"rename one of them.")

        # What an author-owned field means when the file no longer has it: the
        # author DELETED it, and a deletion is an edit like any other. Falling
        # back to the seed here would resurrect the very argument the contract
        # promises is ignored -- a guard removed from the file would come back
        # from an add() call nobody remembered was still passing it.
        empty = {"fmt": "", "unit": "", "desc": "", "expect": {}}

        # An id this script wrote last time and no longer declares would be
        # removed below. A deleted `st.add` retires a value, but so does a
        # branch of the analysis that did not run, and the prose reading the id
        # then fails at compile. So removal is opt-in: `just stats --prune`.
        retired = sorted(set(prior) - set(self._values))
        if retired and not _prune_allowed():
            raise StatError(
                f"this run no longer declares {len(retired)} id(s) {mine} wrote "
                f"before: {', '.join(retired[:12])}"
                f"{' ...' if len(retired) > 12 else ''}. Nothing was written. "
                f"If they are retired, re-run with --prune (just stats --prune, "
                f"or PAPER_STATS_PRUNE=1); otherwise restore their add() calls.")

        overridden: list[tuple[str, str]] = []
        failed: dict[str, str] = {}
        final: dict[str, dict] = {}
        for id, seed in self._values.items():
            old = prior.get(id)
            if old is None:
                entry = dict(seed)
                at = _now()
            else:
                entry = {"value": seed["value"]}
                for f in AUTHOR_FIELDS:
                    entry[f] = old[f] if f in old else empty[f]
                # A seed the script still passes, that the file has moved away
                # from: dead code in the generator, collected for one note below.
                overridden += [(id, f) for f in self._passed.get(id, ())
                               if seed[f] != entry[f]]
                # `at` is when the value last CHANGED, not when the script last
                # ran -- a re-run that reproduces the number leaves it alone, so
                # the timestamps in the file carry information. The type check
                # matters: 35 == 35.0 in Python but "35" != "35.0" in the file,
                # so a dtype change is a change and the date must say so.
                old_v = old.get("value")
                unchanged = (old_v == seed["value"]
                             and type(old_v) is type(seed["value"]))
                at = ((old.get("origin") or {}).get("at") or _now()) if unchanged \
                    else _now()

            # Enforced against the guard that governs this entry NOW -- the
            # file's for an existing one, the seed's for a new one.
            # Every failing guard is collected, not just the first, so one
            # re-run names them all (`just assets --explain` maps each to the
            # sentences that read it).
            try:
                self._enforce(id, entry["value"], entry.get("expect", {}))
            except StatError as exc:
                failed[id] = str(exc)
                continue
            if entry.get("fmt"):
                try:
                    format(entry["value"], entry["fmt"])
                except (TypeError, ValueError) as e:
                    raise StatError(
                        f"{id!r}: value {entry['value']!r} cannot be formatted "
                        f"with fmt {entry['fmt']!r} (from stats.json): {e}. "
                        f"Fix the fmt there, or the analysis.") from None

            entry["checksum"] = _checksum(entry["value"])
            entry["origin"] = {"by": mine, "at": at}
            final[id] = entry

        _record_failures(p, failed, {id: prior.get(id, self._values[id]) for id in failed},
                         {id: self._values[id]["value"] for id in failed})
        if failed:
            raise StatError("\n".join(failed[id] for id in sorted(failed)))
        if retired:
            print(f"  note: pruned {len(retired)} id(s) this run no longer "
                  f"declares: {', '.join(retired)}")

        merged = {**kept, **final}

        # Recorded once per generator, not per entry: one script writes the whole
        # file by contract, and 1000 values do not need 1000 copies of the same
        # input map.
        sources = existing_doc.get("sources", {}) or {}
        if not isinstance(sources, dict):
            sources = {}
        sources = {k: v for k, v in sources.items() if k != mine}
        if self._values:
            sources[mine] = {**code_inputs(), **declared_inputs(inputs)}
            if not inputs:
                print(f"  note: {mine} declares no data inputs, so a change to "
                      f"the data behind these numbers cannot be detected. "
                      f"Pass write(inputs=[...]) if it reads any.")

        # Everything else in the file -- `pinned`, and whatever a future version
        # adds -- is the author's, and passes through untouched.
        extra = {k: v for k, v in existing_doc.items()
                 if k not in ("_about", "sources", "values")}

        write_text(p, json.dumps(
            {"_about": ABOUT,
             **extra,
             "sources": dict(sorted(sources.items())),
             "values": dict(sorted(merged.items()))},
            indent=2, sort_keys=False) + "\n")
        receipt = os.environ.get("PAPER_STATS_RECEIPT")
        if receipt:
            write_text(Path(receipt), json.dumps({"token": os.environ.get("PAPER_STATS_TOKEN"),
                       "by": mine, "ids": sorted(final), "output": str(p.resolve()),
                       "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}))
        hand = sum(1 for v in merged.values()
                   if (v.get("origin") or {}).get("by") == "hand")

        if pruned:
            print(f"  note: removed {len(pruned)} hand entr"
                  f"{'y' if len(pruned) == 1 else 'ies'} not in keep_hand_ids: "
                  f"{', '.join(sorted(pruned))}")
        if overridden:
            ids = sorted({id for id, _ in overridden})
            fields = sorted({f for _, f in overridden})
            print(f"  note: {', '.join(fields)} passed to add() differ from "
                  f"stats.json for {', '.join(ids[:4])}"
                  f"{f' and {len(ids) - 4} more' if len(ids) > 4 else ''} and "
                  f"were IGNORED -- those fields are owned by stats.json once "
                  f"an entry exists. Edit them there, or drop the arguments.")

        # An unguarded number is not an error -- plenty of values have no
        # meaningful sign or range. It is reported so the set stays visible
        # rather than quietly becoming the default.
        bare = [id for id, v in final.items()
                if not v.get("expect")
                and isinstance(v["value"], (int, float))
                and not isinstance(v["value"], bool)]
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
