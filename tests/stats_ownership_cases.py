"""The ownership split in stats.json -- the script owns each value, the
author owns how it is shown and what the prose assumes about it."""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

def run_cases() -> bool:
    """The ownership split in stats.json: the script owns each entry's VALUE,
    the author owns fmt/unit/desc/expect once the entry exists.

    Each case is a way the split could quietly fail: a seed clobbering an author
    edit, an author guard not judging the fresh value, a stale script argument
    dying silently instead of with a note, a timestamp that means "the script
    ran" rather than "the value changed", or a pinned block lost in the rewrite.
    """
    import io
    import json
    from contextlib import redirect_stdout
    sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
    import _stats
    from _stats import StatError, Stats
    ok = True

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "stats.json"

        def run(st):
            buf = io.StringIO()
            with redirect_stdout(buf):
                st.write(out=p)
            return buf.getvalue()

        # 1. seeds populate a NEW entry in full.
        st = Stats()
        st.add("m.x", 1.5, fmt=".2f", unit="kg", desc="mass",
               sign="+", between=(0, 10))
        run(st)
        doc = json.loads(p.read_text())
        e = doc["values"]["m.x"]
        if e["fmt"] != ".2f" or e["unit"] != "kg" or \
                e["expect"] != {"sign": "+", "min": 0, "max": 10}:
            print(f"  ownership: seeds did not populate a new entry -- {e}")
            ok = False
        if not e.get("origin", {}).get("at"):
            print("  ownership: a new entry got no origin.at")
            ok = False
        if not str(e.get("checksum", "")).startswith("v2:"):
            print(f"  ownership: expected a v2 checksum, got {e.get('checksum')!r}")
            ok = False
        first_at = e["origin"]["at"]

        # 2. author edits survive a re-run, and the stale seeds are called out.
        e["fmt"], e["unit"], e["expect"] = ".1f", "g", {"min": 0}
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", 1.5, fmt=".2f", sign="+")     # stale seeds, same value
        out = run(st)
        e2 = json.loads(p.read_text())["values"]["m.x"]
        if (e2["fmt"], e2["unit"], e2["expect"]) != (".1f", "g", {"min": 0}):
            print(f"  ownership: author edits were clobbered by seeds -- {e2}")
            ok = False
        if "IGNORED" not in out:
            print("  ownership: stale seeds were dropped with no note")
            ok = False
        if e2["origin"]["at"] != first_at:
            print("  ownership: origin.at moved although the value did not")
            ok = False

        # 3. steady state: no seeds, no note; a changed value updates value,
        #    checksum and origin.at while the author fields stay put.
        st = Stats()
        st.add("m.x", 2.5)
        out = run(st)
        e3 = json.loads(p.read_text())["values"]["m.x"]
        if "IGNORED" in out:
            print("  ownership: a seed note fired with no seeds passed")
            ok = False
        if e3["value"] != 2.5 or e3["checksum"] != _stats._checksum(2.5):
            print(f"  ownership: value/checksum not updated -- {e3}")
            ok = False
        if e3["fmt"] != ".1f":
            print("  ownership: author fmt lost on a value change")
            ok = False

        # 4. the FILE's guard judges the fresh value. The author narrowed it to
        #    min 0; the analysis producing a negative must fail the write.
        st = Stats()
        st.add("m.x", -1.0)
        try:
            run(st)
            print("  ownership: the file's guard did not judge the new value")
            ok = False
        except StatError:
            pass
        if json.loads(p.read_text())["values"]["m.x"]["value"] != 2.5:
            print("  ownership: a failed write still modified the file")
            ok = False

        # 5. the file's fmt must apply to the new value, and fail loudly when
        #    the analysis changes type under it.
        doc = json.loads(p.read_text())
        doc["values"]["m.x"]["expect"] = {}
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", "a label now")
        try:
            run(st)
            print("  ownership: a numeric fmt silently accepted a string value")
            ok = False
        except StatError:
            pass

        # 6. blocks the script does not own pass through the rewrite untouched.
        doc = json.loads(p.read_text())
        doc["pinned"] = {"some/file.csv": "sha256:abc"}
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", 2.5)
        run(st)
        if json.loads(p.read_text()).get("pinned") != {"some/file.csv": "sha256:abc"}:
            print("  ownership: the pinned block was lost in a generator rewrite")
            ok = False

        # 6b. DELETING an author-owned field is an edit like any other: a guard
        #     removed from the file must stay removed, not come back from the
        #     seed the contract promises is ignored.
        doc = json.loads(p.read_text())
        del doc["values"]["m.x"]["expect"]
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", -5.0, sign="+")     # stale seed guard; value violates it
        out = run(st)
        e6 = json.loads(p.read_text())["values"]["m.x"]
        if e6.get("expect") != {}:
            print(f"  ownership: a deleted guard was resurrected -- {e6.get('expect')}")
            ok = False
        if "IGNORED" not in out:
            print("  ownership: resurrection-averted seed was dropped with no note")
            ok = False

        # 6c. origin.at must move when the value's REPRESENTATION changes:
        #     35 == 35.0 in Python but not in the file, and the checksum moves.
        #     The stored date is backdated first, because _now() has second
        #     granularity and two writes in one second look identical.
        doc = json.loads(p.read_text())
        doc["values"]["m.x"]["origin"]["at"] = "2000-01-01T00:00:00Z"
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", -5)                 # same number, int now
        run(st)
        e6c = json.loads(p.read_text())["values"]["m.x"]
        if e6c["origin"]["at"] == "2000-01-01T00:00:00Z":
            print("  ownership: origin.at kept its date across an int/float change")
            ok = False
        # and the counterpart: an identical value keeps its date.
        doc = json.loads(p.read_text())
        doc["values"]["m.x"]["origin"]["at"] = "2000-01-01T00:00:00Z"
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", -5)
        run(st)
        if json.loads(p.read_text())["values"]["m.x"]["origin"]["at"] \
                != "2000-01-01T00:00:00Z":
            print("  ownership: origin.at moved although the value did not")
            ok = False

        # 6d. a malformed values block must refuse the merge, not rewrite the
        #     file with every hand and other-script entry silently deleted.
        doc = json.loads(p.read_text())
        doc["values"] = []
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", 1.0)
        try:
            run(st)
            print("  ownership: merged into a malformed values block")
            ok = False
        except StatError:
            pass
        if json.loads(p.read_text())["values"] == []:
            pass        # untouched, as it must be
        else:
            print("  ownership: a refused merge still modified the file")
            ok = False
        # restore a valid file for anything below
        doc["values"] = {}
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", 1.0)
        run(st)

        # 6e. guards read from the file are hand-edited JSON: an unknown key, a
        #     quoted bound and a NaN value must each refuse the write loudly.
        for name, mutate, value in [
            ("unknown expect key",
             lambda e: e.__setitem__("expect", {"between": [0, 1]}), 2.0),
            ("quoted bound",
             lambda e: e.__setitem__("expect", {"min": "0"}), 2.0),
            ("NaN against a guard",
             lambda e: e.__setitem__("expect", {"min": 0}), float("nan")),
        ]:
            doc = json.loads(p.read_text())
            mutate(doc["values"]["m.x"])
            p.write_text(json.dumps(doc))
            st = Stats()
            st.add("m.x", value)
            try:
                run(st)
                print(f"  ownership guard shape [{name}]: accepted silently")
                ok = False
            except StatError:
                pass
        # leave the temp file valid
        doc = json.loads(p.read_text())
        doc["values"]["m.x"]["expect"] = {}
        p.write_text(json.dumps(doc))

        # 6f. hand entries survive a rewrite by default; keep_hand_ids prunes
        #     the retired ones, names them, and never touches another owner.
        doc = json.loads(p.read_text())
        hand = {"value": 1, "fmt": "", "origin": {"by": "hand", "note": "n"}}
        doc["values"]["h.live"] = dict(hand)
        doc["values"]["h.gone"] = dict(hand)
        doc["values"]["o.other"] = {"value": 2, "fmt": "",
                                    "origin": {"by": "analysis/scripts/x.py"}}
        p.write_text(json.dumps(doc))
        st = Stats()
        st.add("m.x", 1.0)
        run(st)
        if not {"h.live", "h.gone"} <= set(json.loads(p.read_text())["values"]):
            print("  ownership: a hand entry was dropped without keep_hand_ids")
            ok = False
        st = Stats()
        st.add("m.x", 1.0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            st.write(out=p, keep_hand_ids={"h.live"})
        vals = json.loads(p.read_text())["values"]
        if "h.gone" in vals or "h.live" not in vals or "o.other" not in vals:
            print(f"  ownership: keep_hand_ids pruned the wrong set -- {sorted(vals)}")
            ok = False
        if "h.gone" not in buf.getvalue():
            print("  ownership: keep_hand_ids pruned a hand entry silently")
            ok = False

    # 7. assets: origin.at means "the output changed", not "the script ran".
    #
    # record() insists the file it declares exists, so this needs a real one --
    # DISCOVERED from the project rather than named. The scaffold's demo figure
    # is deleted by the second week of a real manuscript, and a test hardcoding
    # it then fails for a reason unrelated to what it checks. (Found downstream,
    # in the dnoise manuscript.)
    sample = next(iter(sorted((ROOT / "figures").glob("*.png"))), None)
    if sample is None:
        print("  note: no figures/*.png, so the asset origin.at cases were skipped")
        return ok
    fig_rel = sample.relative_to(ROOT).as_posix()
    import _assets
    saved = _assets.OUT
    try:
        with tempfile.TemporaryDirectory() as d:
            _assets.OUT = Path(d) / "assets.json"
            kw = dict(kind="figure", inputs=[], desc="d")
            with redirect_stdout(io.StringIO()):
                _assets.record("fig.t", fig_rel, **kw)
            doc = json.loads(_assets.OUT.read_text())
            old = "2000-01-01T00:00:00Z"
            doc["values"]["fig.t"]["origin"]["at"] = old
            _assets.OUT.write_text(json.dumps(doc))
            with redirect_stdout(io.StringIO()):
                _assets.record("fig.t", fig_rel, **kw)
            at = json.loads(_assets.OUT.read_text())["values"]["fig.t"]["origin"]["at"]
            if at != old:
                print("  asset origin.at: moved although the output did not change")
                ok = False
            doc = json.loads(_assets.OUT.read_text())
            doc["values"]["fig.t"]["hash"] = "sha256:" + "0" * 64
            _assets.OUT.write_text(json.dumps(doc))
            with redirect_stdout(io.StringIO()):
                _assets.record("fig.t", fig_rel, **kw)
            at = json.loads(_assets.OUT.read_text())["values"]["fig.t"]["origin"]["at"]
            if at == old:
                print("  asset origin.at: kept a stale date across an output change")
                ok = False

            # 8. print geometry: size read back from the file, and a stated
            #    min_pt recorded for a figure no matplotlib canvas drew.
            with redirect_stdout(io.StringIO()):
                _assets.record("fig.t", fig_rel, min_pt=6, **kw)
            geo = json.loads(_assets.OUT.read_text())["values"]["fig.t"].get("print", {})
            if geo.get("min_pt") != 6 or not geo.get("width_in"):
                print(f"  asset print geometry: expected size and min_pt, got {geo}")
                ok = False

            # 9. generators run in parallel must not drop each other's
            #    entries: the read-modify-write is serialized by a lock.
            import threading

            def one(i):
                _assets.record(f"fig.p{i}", fig_rel, **kw)
            with redirect_stdout(io.StringIO()):
                threads = [threading.Thread(target=one, args=(i,))
                           for i in range(8)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
            got = set(json.loads(_assets.OUT.read_text())["values"])
            lost = {f"fig.p{i}" for i in range(8)} - got
            if lost:
                print(f"  asset lock: parallel records lost {sorted(lost)}")
                ok = False
    finally:
        _assets.OUT = saved

    return ok

if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
