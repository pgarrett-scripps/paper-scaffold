"""The migration path: files whose analysis is gone, adopted with a note."""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
# _assets lives with the generators that call it. Inserted here rather
# than relied on: it used to arrive as a side effect of stats_cases()
# having run first, which held only while both lived in one file.
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))

def run_cases() -> bool:
    """The migration path: files whose analysis is gone, adopted with a note.

    Adoption must buy the checks that still apply (hash, note) without the one
    that cannot (a generator), and a restored generator must be able to take
    the id back.
    """
    import io
    import json
    from contextlib import redirect_stdout
    import adopt_assets as aa
    import check_assets as ca
    ok = True

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "figures").mkdir()
        (root / "si").mkdir()
        (root / "figures" / "legacy_plot.png").write_bytes(b"png-bytes")
        (root / "si" / "old_table.typ").write_text("#table()")

        # No note, no adoption: provenance is the entire point.
        lines, rc = aa.adopt(root, "  ")
        if rc == 0 or (root / "assets.json").is_file():
            print("  adopt: proceeded without a note")
            ok = False

        lines, rc = aa.adopt(root, "imported from repo X at 3f2a1c0")
        doc = json.loads((root / "assets.json").read_text())
        e = doc["values"].get("fig.legacy-plot")
        t = doc["values"].get("tbl.old-table")
        if rc != 0 or not e or not t:
            print(f"  adopt: expected fig.legacy-plot and tbl.old-table -- {list(doc.get('values', {}))}")
            ok = False
        elif (e["origin"]["by"], e["kind"], t["kind"]) != ("adopted", "figure", "table"):
            print(f"  adopt: wrong provenance or kind -- {e}, {t}")
            ok = False

        # check_assets: an adopted entry passes with no generator on disk, and
        # its note is mandatory.
        old_root, ca.ROOT = ca.ROOT, root
        try:
            if [f for f in ca._entry("fig.legacy-plot", e) if f.level == "error"]:
                print("  adopt: a clean adopted entry was reported as an error")
                ok = False
            noteless = {**e, "origin": {"by": "adopted"}}
            if not [f for f in ca._entry("fig.legacy-plot", noteless)
                    if f.level == "error"]:
                print("  adopt: an adopted entry with no note passed")
                ok = False
            # A changed file is an error until re-adoption accepts it.
            (root / "figures" / "legacy_plot.png").write_bytes(b"new-bytes")
            if not [f for f in ca._entry("fig.legacy-plot", e) if f.level == "error"]:
                print("  adopt: a changed adopted file passed the hash check")
                ok = False
        finally:
            ca.ROOT = old_root
        lines, rc = aa.adopt(root, "accepting the regenerated plot")
        e2 = json.loads((root / "assets.json").read_text())["values"]["fig.legacy-plot"]
        if e2["hash"] == e["hash"]:
            print("  adopt: re-running did not refresh a changed hash")
            ok = False

    # A generator may take over an adopted id: rebuildable beats adopted.
    # The figure is discovered, not named -- see the origin.at cases for why.
    sample = next(iter(sorted((ROOT / "figures").glob("*.png"))), None)
    if sample is None:
        print("  note: no figures/*.png, so the adoption takeover case was skipped")
        return ok
    fig_rel = sample.relative_to(ROOT).as_posix()
    import _assets
    saved = _assets.OUT
    try:
        with tempfile.TemporaryDirectory() as d:
            _assets.OUT = Path(d) / "assets.json"
            _assets.OUT.write_text(json.dumps({"values": {
                "fig.t": {"path": fig_rel,
                          "kind": "figure", "hash": "sha256:" + "0" * 64,
                          "origin": {"by": "adopted", "note": "legacy"}}}}))
            buf = io.StringIO()
            with redirect_stdout(buf):
                _assets.record("fig.t", fig_rel,
                               kind="figure", inputs=[], desc="d")
            e = json.loads(_assets.OUT.read_text())["values"]["fig.t"]
            if e["origin"]["by"] == "adopted":
                print("  adopt: a generator could not take over an adopted id")
                ok = False
            if "supersedes" not in buf.getvalue():
                print("  adopt: a takeover happened silently")
                ok = False
    finally:
        _assets.OUT = saved

    return ok

if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
