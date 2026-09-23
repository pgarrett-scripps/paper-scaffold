"""stats.json: resolution, guards, and the checker that reads them."""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

def stats_cases() -> bool:
    """The generated-number mechanism: resolution, guards, and the check that
    catches a number typed by hand.

    Deliberately NOT in fixture.typ. The fixture's golden files would then depend
    on whatever values a project's gen_stats.py happens to declare, so every
    project would see a spurious diff on its first edit. These use a temporary
    stats file instead and stay true whatever the project computes.
    """
    import json
    import prose_check as pc
    import typst_prose as tp
    ok = True

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "stats.json"
        p.write_text(json.dumps({"values": {
            "a.pct":   {"value": 84.23, "fmt": ".1f"},
            "a.count": {"value": 1204, "fmt": ","},
            "a.small": {"value": 3, "fmt": ""},
            "a.label": {"value": "Treated", "fmt": ""},
        }}))

        # 1. resolution: substitutes the display string, survives a reflow inside
        #    the call, and is a no-op on prose that uses none.
        res = [
            ("plain", 'fell by #s("a.pct")%', "fell by 84.2%"),
            ("reflowed", 'fell by #s(\n  "a.pct",\n)%', "fell by 84.2%"),
            ("untouched", "no calls here", "no calls here"),
        ]
        for name, src, want in res:
            got = tp.resolve_stats(src, p)
            if got != want:
                print(f"  stats resolve [{name}]: expected {want!r}, got {got!r}")
                ok = False

        # 2. an unknown id fails loudly rather than deleting a number silently.
        try:
            tp.resolve_stats('#s("a.nope")', p)
            print("  stats resolve: an unknown id did not raise")
            ok = False
        except SystemExit:
            pass

        # 3. derivable-number: fires on a typed value, silent on a derived one,
        #    and ignores values too short to match without noise.
        cases = [
            ("typed distinctive", "recovery reached 84.2% overall.", 1),
            ("typed with separator", "we enrolled 1,204 participants.", 1),
            ("derived", 'recovery reached #s("a.pct")% overall.', 0),
            ("too common to flag", "there were 3 conditions.", 0),
            ("inside a larger number", "the id was 184.25 exactly.", 0),
            ("inline code is not a result", "pass `--threshold 84.2` to it.", 0),
            # lit() must NOT silence this rule: a value the analysis computes
            # belongs in #s(), and vouching for it as prose is the bypass the
            # two checks exist to be on opposite sides of.
            ("lit does not bypass derivable",
             'recovery reached #lit("84.2")% overall.', 1),
        ]
        for name, src, want in cases:
            got = len(pc.check_derivable_numbers({"t": src}, p))
            if got != want:
                print(f"  derivable-number [{name}]: expected {want}, got {got}")
                ok = False

        # 4. no stats.json at all: the mechanism is optional, so this is silent.
        if pc.check_derivable_numbers({"t": "84.2"}, Path(d) / "absent.json"):
            print("  derivable-number: reported findings with no stats.json")
            ok = False

        # 4b. unaccounted-number: the other half. A distinctive numeral that
        #     matches NOTHING declared is the least traceable number in the
        #     paper; a match is derivable-number's case, a year or a short
        #     count is noise, and no stats.json means nowhere to trace to.
        unaccounted = [
            ("matches nothing", "recovery reached 84.7% overall.", 1),
            ("undeclared thousands", "we screened 9,999 records.", 1),
            ("matches a declared display", "recovery reached 84.2% overall.", 0),
            ("matches a declared raw value", "the mean was 84.23 exactly.", 0),
            ("a year", "unchanged since 2019.", 0),
            ("too short to flag", "there were 3 conditions.", 0),
            ("derived is not typed", 'reached #s("a.pct")% overall.', 0),
            ("inline code is not prose", "pass `--cutoff 84.7` to it.", 0),
            # The two false positives the first real manuscript produced: a
            # clause comma is not a thousands separator, and digits inside an
            # identifier are not a result.
            ("clause comma is not part of the number",
             "isolated across frames (median 1, mean 2.67, up to 10).", 1),
            ("digits inside an identifier",
             "deposited at accession PXD070049 for review.", 0),
            ("repeated value reports once", "it was 84.7 then 84.7 again.", 1),
            # #lit() is the inline vouch: the wrapped occurrence is accounted
            # for, a bare occurrence of the same value elsewhere is not.
            ("lit-wrapped is vouched", 'ran at #lit("40.5") degrees.', 0),
            ("lit vouches the spot, not the value",
             'ran at #lit("40.5") degrees, later 40.5 again.', 1),
            ("reflowed lit is vouched too",
             'in total #lit(\n  "12,345",\n) events.', 0),
        ]
        for name, src, want in unaccounted:
            got = len(pc.check_unaccounted_numbers({"t": src}, p))
            if got != want:
                print(f"  unaccounted-number [{name}]: expected {want}, got {got}"
                      + f" -- {[f.subject for f in pc.check_unaccounted_numbers({'t': src}, p)]}")
                ok = False
        if pc.check_unaccounted_numbers({"t": "84.7"}, Path(d) / "absent.json"):
            print("  unaccounted-number: reported findings with no stats.json")
            ok = False
        # A Results section can owe dozens at once; the report shows a capped
        # sample plus a count, because a 189-line wall is read by nobody.
        many = " ".join(f"value {i}.{i} appears." for i in range(1, 15))
        found = pc.check_unaccounted_numbers({"t": many}, p)
        if len(found) != 9 or "more distinctive numerals" not in found[-1].message:
            print(f"  unaccounted-number cap: expected 8 + summary, got {len(found)}")
            ok = False

    # 5. guards. Shape errors (a guard on a label, a misspelt sign) fail at
    #    add(), next to the line that wrote them. VALUE violations fail at
    #    write(), because the guard that judges a value is the one in the file
    #    -- the author's -- and the file is only known then.
    sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
    try:
        from _stats import StatError, Stats
    except ImportError:
        print("  stats guards: analysis/scripts/_stats.py not importable")
        return False

    for name, value, kw in [
        ("guard on a non-number", "Treated", dict(sign="+")),
        ("one-sided guard on a non-number", "Treated", dict(minimum=0)),
        ("nonsense sign", 1.0, dict(sign="up")),
        ("between and minimum", 1.0, dict(between=(0, 2), minimum=0)),
    ]:
        try:
            Stats().add("x.y", value, **kw)
            print(f"  stats guard [{name}]: accepted a seed it should reject")
            ok = False
        except StatError:
            pass

    import io
    from contextlib import redirect_stdout
    for name, value, kw in [
        ("sign flip", 1.09, dict(sign="-")),
        ("out of range", 1.09, dict(between=(0, 1))),
        ("below a one-sided minimum", -1, dict(minimum=0)),
        ("above a one-sided maximum", 0.2, dict(maximum=0.05)),
    ]:
        st = Stats()
        st.add("x.y", value, **kw)
        try:
            with tempfile.TemporaryDirectory() as d, \
                    redirect_stdout(io.StringIO()):
                st.write(out=Path(d) / "s.json")
            print(f"  stats guard [{name}]: accepted a value it should reject")
            ok = False
        except StatError:
            pass

    # A value that satisfies its guard is accepted, and its fmt is recorded.
    #
    # The rendered string is NOT stored -- stats.json holds the value and the
    # format spec, and tools/render_stats.py turns them into what Typst reads. So
    # what this asserts is that the spec survives, and that rendering it through
    # the one shared formatter gives the rounded form.
    # A one-sided seed records only its own bound: a count has a floor and no
    # ceiling, and inventing one would fail the day the data grows.
    st = Stats()
    st.add("x.n", 12, minimum=0)
    if st._values["x.n"]["expect"] != {"min": 0}:
        print(f"  stats guard: minimum seeded {st._values['x.n']['expect']}")
        ok = False

    st = Stats()
    st.add("x.y", 84.23, fmt=".1f", sign="+", between=(0, 100))
    rec = st._values["x.y"]
    if "display" in rec:
        print("  stats guard: a rendered string was stored; it is derived at build time")
        ok = False
    if tp.display_of(rec) != "84.2":
        print(f"  stats guard: fmt not applied -- {tp.display_of(rec)!r}")
        ok = False

    # A format spec that cannot apply to the value must fail at declaration,
    # where the script that chose it is named, rather than at render time.
    try:
        Stats().add("x.bad", "not a number", fmt=".2f")
        print("  stats guard: an impossible fmt was accepted")
        ok = False
    except StatError:
        pass
    try:
        st.add("x.y", 1)
        print("  stats guard: a duplicate id was accepted")
        ok = False
    except StatError:
        pass
    return ok

def check_stats_cases() -> bool:
    """tools/check_stats.py: the guard on the one generated file you may edit.

    stats.json came out of the .assets-stamp hash when hand-entered values became
    a supported thing to write -- and that hash is gone entirely now -- so these
    checks are all that stands between a typed number and the prose. Each case below is a way that file has to be able
    to go wrong.

    The re-derive check is NOT exercised here: it shells out to
    analysis/scripts/gen_stats.py against the real analysis environment, which is
    a different thing to test and a slow one. `just check-stats` covers it on
    every run of the gate.
    """
    import json
    import check_stats as cs
    ok = True

    def entry(**kw):
        e = {"value": 1.0, "fmt": ".2f", "unit": "",
             "desc": "d", "expect": {}, "source": "",
             "origin": {"by": "hand", "note": "protocol"}}
        e.update(kw)
        return e

    # <name>, entry overrides, expected error count from the per-entry checks
    cases = [
        ("valid hand entry",        {}, 0),
        ("hand entry with no note", {"origin": {"by": "hand"}}, 1),
        ("hand entry, blank note",  {"origin": {"by": "hand", "note": "  "}}, 1),
        ("no origin at all",        {"origin": None}, 1),
        ("origin with no by",       {"origin": {"note": "x"}}, 1),
        ("generator that is gone",
         {"origin": {"by": "analysis/scripts/nope.py"}}, 1),
        ("generator that exists",
         {"origin": {"by": "analysis/scripts/gen_stats.py"}}, 0),
        # A guard that no longer holds. This is the case the whole mechanism
        # exists for: the prose says "increase", the value went negative.
        ("sign guard violated",
         {"value": -1.0, "expect": {"sign": "+"}}, 1),
        ("sign guard satisfied",   {"expect": {"sign": "+"}}, 0),
        ("range guard violated",
         {"value": 8400.0, "expect": {"min": 0, "max": 100}}, 1),
        # expect is author-edited, so a one-sided band is a legitimate thing to
        # find in the file -- it must be enforced, not silently skipped, which
        # is what a `min and max` condition used to do.
        ("one-sided min violated", {"value": -1.0, "expect": {"min": 0}}, 1),
        ("one-sided min satisfied", {"expect": {"min": 0}}, 0),
        ("one-sided max violated", {"value": 500.0, "expect": {"max": 100}}, 1),
        # NaN compares False against every bound, so the per-bound rewrite
        # would wave it through a band the old chained comparison rejected.
        ("NaN inside a band",
         {"value": float("nan"), "expect": {"min": 0, "max": 100}}, 1),
        # expect is hand-edited JSON. A key this does not understand is a guard
        # that never fires, and a quoted bound is one that cannot compare --
        # each must be an error, not a silence or a TypeError.
        ("unknown expect key",
         {"value": -3.0, "expect": {"between": [0, 1]}}, 1),
        ("quoted bound", {"value": 5.0, "expect": {"min": "0"}}, 1),
        ("expect is not an object", {"expect": [0, 1]}, 1),
        # A label carries no guard and must not be treated as a broken number.
        ("non-numeric with no guard",
         {"value": "Treated", "fmt": "", "expect": {}}, 0),
    ]
    for name, over, want in cases:
        rec = entry(**over)
        if over.get("origin", "keep") is None:
            rec["origin"] = None
        found = cs._origin("x.y", rec) + cs._guard("x.y", rec)
        got = sum(1 for f in found if f.level == "error")
        if got != want:
            print(f"  check-stats [{name}]: expected {want} error(s), got {got}"
                  + (f" -- {[f.msg for f in found]}" if got else ""))
            ok = False

    # The checksum is what makes re-derivation affordable to skip. It has to
    # catch a hand-edited generated value using only what is in the file, since
    # the default path must not re-run the analysis. v2 covers the value ALONE:
    # fmt is the author's to edit now, so changing it must not read as tampering.
    # v1, from before that split, covered fmt too and is still verified so an
    # existing manuscript upgrades without a wall of errors.
    import hashlib
    import _stats
    v1 = "v1:" + hashlib.sha256(json.dumps(
        [35, ","], sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    good = {"value": 35, "fmt": ",", "checksum": _stats._checksum(35),
            "origin": {"by": "analysis/scripts/gen_stats.py"}}
    checks = [
        ("intact", good, 0, 0),
        ("value edited", {**good, "value": 999}, 1, 0),
        ("fmt edited, which the author owns", {**good, "fmt": ".2f"}, 0, 0),
        ("v1 intact", {**good, "checksum": v1}, 0, 0),
        # A v1 digest covers value AND fmt, and cannot tell the documented fmt
        # edit from a value edit -- so a mismatch is a WARNING with the
        # ambiguity stated, not an error that fails the gate over the exact
        # edit the contract invites. `just assets` re-records as v2.
        ("v1 mismatch is a warning", {**good, "checksum": v1, "value": 999}, 0, 1),
        ("v1 fmt edit is the same warning", {**good, "checksum": v1, "fmt": ".2f"}, 0, 1),
        ("unknown checksum version", {**good, "checksum": "v9:beef"}, 1, 0),
        # Written before checksums existed: reported by nothing, so an upgrade
        # is not a wall of errors. `just assets` adds one.
        ("no checksum recorded", {k: v for k, v in good.items() if k != "checksum"}, 0, 0),
        # A hand entry has no generator to have written a checksum, so there is
        # nothing to compare against. Its guarantee is the guard and the note.
        ("hand entry is skipped",
         {**good, "value": 999, "origin": {"by": "hand", "note": "x"}}, 0, 0),
    ]
    for name, rec, want_err, want_warn in checks:
        found = cs._checksum({"x.y": rec})
        got_err = len([f for f in found if f.level == "error"])
        got_warn = len([f for f in found if f.level == "warn"])
        if (got_err, got_warn) != (want_err, want_warn):
            print(f"  check-stats checksum [{name}]: expected "
                  f"{want_err}e/{want_warn}w, got {got_err}e/{got_warn}w")
            ok = False

    # The fmt half of "fail where the mistake was made": a broken fmt edited
    # into stats.json used to pass verify and kill the next build inside
    # render_stats instead. check-stats now renders every entry itself.
    display_cases = [
        ("fmt applies", {"value": 84.23, "fmt": ".1f"}, 0),
        ("numeric fmt on a label", {"value": "Treated", "fmt": ".2f"}, 1),
        ("nonsense fmt", {"value": 84.23, "fmt": ".2q"}, 1),
        ("no fmt is fine for anything", {"value": "Treated", "fmt": ""}, 0),
    ]
    for name, rec, want in display_cases:
        got = len([f for f in cs._display({"x.y": rec}) if f.level == "error"])
        if got != want:
            print(f"  check-stats display [{name}]: expected {want}, got {got}")
            ok = False

    # The hash cache behind _sources/_pinned/check_assets: correct on first
    # sight, correct again after the file changes. The cache may only ever
    # change WHEN the hash is computed, never WHAT it is.
    import hashlib as _hl
    import hashcache
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "data.bin"
        f.write_bytes(b"one")
        want = "sha256:" + _hl.sha256(b"one").hexdigest()
        if hashcache.sha(f) != want or hashcache.sha(f) != want:
            print("  hashcache: wrong digest on first or cached read")
            ok = False
        f.write_bytes(b"two-longer")
        want2 = "sha256:" + _hl.sha256(b"two-longer").hexdigest()
        if hashcache.sha(f) != want2:
            print("  hashcache: served a stale digest after the file changed")
            ok = False
        # The racy-clean window: a same-size rewrite that keeps the mtime (a
        # coarse-timestamp filesystem, two writes in one tick). Fresh files
        # must be re-hashed; old ones may be served from the cache.
        import os as _os
        st0 = f.stat()
        f.write_bytes(b"TWO-LONGER")
        _os.utime(f, ns=(st0.st_atime_ns, st0.st_mtime_ns))
        want3 = "sha256:" + _hl.sha256(b"TWO-LONGER").hexdigest()
        if hashcache.sha(f) != want3:
            print("  hashcache: a same-size, same-mtime rewrite served the "
                  "stale digest of a fresh file")
            ok = False
        if str(f.resolve()) in hashcache._load():
            print("  hashcache: a digest was cached inside the racy window")
            ok = False
        old = st0.st_mtime_ns - 10 * hashcache.RACY_NS
        _os.utime(f, ns=(old, old))
        hashcache.sha(f)
        if hashcache._load().get(str(f.resolve()), [None])[-1] != want3:
            print("  hashcache: an old file's digest was not cached")
            ok = False

    # The deep check's summary must say what actually ran. On an
    # all-hand-entered manuscript _rederive has nothing to do, and the old
    # label printed "(re-derived)" anyway -- a silent no-op wearing a
    # verification label. (Found downstream, in koth-paper.)
    hand_only = {"x.y": {"value": 1, "origin": {"by": "hand", "note": "n"}}}
    f, status = cs._rederive(hand_only)
    if f != [] or "nothing generator-owned" not in status:
        print(f"  check-stats rederive: expected an honest empty status, got "
              f"{status!r}")
        ok = False

    # Pinned files: declared by the author, hashed by `just pin`, watched from
    # then on. A pin with no hash is an error (the declaration says the file
    # matters and nothing is watching it yet); an absent file is a note, since a
    # fresh clone usually lacks the data.
    bib = ROOT / "references.bib"
    right = "sha256:" + hashlib.sha256(bib.read_bytes()).hexdigest()
    pin_cases = [
        ("unpinned", {"references.bib": None}, 1),
        ("pinned and intact", {"references.bib": right}, 0),
        ("pinned and changed", {"references.bib": "sha256:" + "0" * 64}, 1),
        ("pinned but absent", {"no/such/file.csv": "sha256:" + "0" * 64}, 0),
        ("no pinned block at all", None, 0),
        # Hand-authored block, so a wrong shape (a list of paths is the natural
        # first guess) must be an error finding, not an AttributeError that
        # kills the whole gate.
        ("pinned is a list", ["references.bib"], 1),
    ]
    for name, pinned, want in pin_cases:
        doc = {"values": {}} if pinned is None else {"values": {}, "pinned": pinned}
        got = len([f for f in cs._pinned(doc) if f.level == "error"])
        if got != want:
            print(f"  check-stats pinned [{name}]: expected {want}, got {got}")
            ok = False

    # And the tool that records them: fills a null, refuses a missing file.
    import pin as pin_tool
    doc = {"pinned": {"references.bib": None}}
    _, rc = pin_tool.pin(doc, ROOT)
    if rc != 0 or doc["pinned"]["references.bib"] != right:
        print("  pin: did not record the hash of a present file")
        ok = False
    _, rc = pin_tool.pin({"pinned": {"no/such/file.csv": None}}, ROOT)
    if rc == 0:
        print("  pin: exited 0 while failing to pin a missing file")
        ok = False
    try:
        _, rc = pin_tool.pin({"pinned": ["references.bib"]}, ROOT)
        if rc == 0:
            print("  pin: accepted a list-shaped pinned block")
            ok = False
    except AttributeError:
        print("  pin: crashed on a list-shaped pinned block instead of reporting it")
        ok = False

    # Unused ids are reported against the real manuscript sources, so this only
    # asserts the shape: an id nothing could possibly call must be reported.
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "stats.json"
        p.write_text(json.dumps({"values": {"a.b": entry()}}))
        found = cs._unused({"zzz.never.called.by.anything": entry()})
        if not any(f.level == "warn" for f in found):
            print("  check-stats: an unread id was not reported")
            ok = False

    return ok

def run_cases() -> bool:
    ok = True
    for case in (stats_cases, check_stats_cases,):
        ok &= case()
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
