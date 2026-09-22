"""assets.json: the manifest, the files it describes, and the prose that
names one directly instead of by id."""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

def asset_cases() -> bool:
    """A generated asset nothing includes, which every staleness check calls
    current because it is -- it is simply not in the paper."""
    import prose_check as pc
    ok = True

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "si").mkdir()
        (root / "figures").mkdir()
        (root / "si" / "used_table.typ").write_text("#table()")
        (root / "si" / "orphan_table.typ").write_text("#table()")
        (root / "si" / "stats.json").write_text("{}")
        (root / "figures" / "used_figure.png").write_bytes(b"x")
        (root / "figures" / "orphan_figure.png").write_bytes(b"x")
        (root / "paper.typ").write_text(
            '#include "si/used_table.typ"\n#image("figures/used_figure.png")\n')

        found = pc.check_orphaned_assets(root)
        got = sorted(f.subject for f in found)
        want = ["orphan_figure.png", "orphan_table.typ"]
        if got != want:
            print(f"  orphaned-asset: expected {want}, got {got}")
            ok = False
        # stats.json is read by id through stats.typ, never by filename, so it
        # must never be reported however the manuscript is written.
        if any(f.subject == "stats.json" for f in found):
            print("  orphaned-asset: reported stats.json, which is read by id")
            ok = False

        # Print resolution: pixels over the width the figure is RENDERED at, not
        # the width it was saved at. A file that passes at 100% can fail at 50%
        # of nothing -- it is the same pixels over a smaller area, so the dpi
        # goes UP. The direction is easy to get backwards, hence both cases.
        import struct
        import zlib

        def png(w: int, h: int) -> bytes:
            body = b"IHDR" + struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00"
            return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + body
                    + struct.pack(">I", zlib.crc32(body)))

        (root / "figures" / "sharp.png").write_bytes(png(3000, 1000))
        (root / "figures" / "soft.png").write_bytes(png(400, 300))
        (root / "figures" / "vector.svg").write_text("<svg/>")
        (root / "figures" / "half.png").write_bytes(png(1000, 500))
        (root / "paper.typ").write_text(
            '#include "si/used_table.typ"\n#image("figures/used_figure.png")\n'
            '#image("figures/sharp.png", width: 100%)\n'
            '#image("figures/soft.png", width: 100%)\n'
            '#image("figures/vector.svg", width: 100%)\n'
            '#image("figures/half.png", width: 30%)\n')
        flagged = sorted(f.subject
                         for f in pc.check_figure_resolution(root))
        # used_figure.png is a 1-byte stub with no readable header, so it is
        # reported as unmeasurable -- which is the honest outcome, not silence.
        want_flagged = ["soft.png", "used_figure.png"]
        if flagged != want_flagged:
            print(f"  figure resolution: expected {want_flagged}, got {flagged}")
            ok = False

    # Table shape. None of this is visible from the source: a generated table
    # grows a column per condition and the first sign is an unreadable proof.
    tbl = lambda cols, rows, cell="[x]": (
        "#table(\n  columns: %d,\n" % cols
        + "".join("  " + ", ".join([cell] * cols) + ",\n" for _ in range(rows))
        + ")\n")
    table_cases = [
        ("normal", tbl(5, 3), 0),
        ("too many columns", tbl(12, 3), 1),
        ("too many rows", tbl(3, 50), 1),
        ("one overlong cell", tbl(3, 2, "[%s]" % ("word " * 20)), 1),
        ("both dimensions", tbl(12, 50), 2),
        # A cell's own brackets must not cut it short, or a long cell containing
        # a link would be measured as a few characters and pass.
        ("markup does not shorten a cell",
         tbl(2, 1, "[#emph[%s]]" % ("word " * 20)), 1),
    ]
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for name, src, want in table_cases:
            (root / "t.typ").write_text(src)
            got = len(pc.check_table_size(root))
            if got != want:
                print(f"  table size [{name}]: expected {want}, got {got}")
                ok = False

    # `columns:` has three spellings and the repeat form is the one that bites:
    # read as a bare tuple it counts one column, and every row count derived
    # from it is then wrong by that factor.
    for spec, want in [("5", 5), ("(left, right, right)", 3),
                       ("(1fr,) * 12", 12), ("(auto, auto) * 3", 6)]:
        got = pc._column_count(spec)
        if got != want:
            print(f"  column count [{spec}]: expected {want}, got {got}")
            ok = False

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "figures").mkdir()

        # No si/ or figures/ at all is a valid project shape, not a finding.
        bare = Path(d) / "bare"
        bare.mkdir()
        (bare / "paper.typ").write_text("= Title\n")
        if pc.check_orphaned_assets(bare):
            print("  orphaned-asset: reported findings for a project with no assets")
            ok = False
    return ok

def check_assets_cases() -> bool:
    """tools/check_assets.py, and the prose rule that keeps it honest.

    The manifest is only trustworthy because the compile resolves ids through it.
    Two things have to hold for that: the entries must describe the files that are
    actually there, and the manuscript must not reach around the mechanism by
    naming a generated file directly.
    """
    import json
    import check_assets as ca
    import prose_check as pc
    ok = True

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "figures").mkdir()
        (root / "si").mkdir()
        (root / "analysis" / "scripts").mkdir(parents=True)
        gen = root / "analysis" / "scripts" / "gen_x_figure.py"
        gen.write_text("# generator\n")
        png = root / "figures" / "x.png"
        png.write_bytes(b"pixels")
        data = root / "analysis" / "scripts" / "d.csv"
        data.write_text("a,b\n1,2\n")

        orig_root = ca.ROOT
        ca.ROOT = root
        try:
            def entry(**kw):
                e = {
                    "path": "figures/x.png", "kind": "figure", "desc": "",
                    "hash": ca._sha(png),
                    "origin": {"by": "analysis/scripts/gen_x_figure.py"},
                    "inputs": {"analysis/scripts/d.csv": ca._sha(data)},
                }
                e.update(kw)
                return e

            cases = [
                ("valid entry", {}, 0),
                ("output edited since generation",
                 {"hash": "sha256:" + "0" * 64}, 1),
                ("generator no longer exists",
                 {"origin": {"by": "analysis/scripts/gone.py"}}, 1),
                ("declared input has changed",
                 {"inputs": {"analysis/scripts/d.csv": "sha256:" + "0" * 64}}, 1),
                ("file does not exist",
                 {"path": "figures/absent.png"}, 1),
                ("bad kind", {"kind": "diagram"}, 1),
                # An input that is not present is the ordinary state of a fresh
                # clone (analysis/data/ is untracked). It must NOT be an error, or
                # every clone is red for something the person cannot act on.
                ("input not present is not an error",
                 {"inputs": {"analysis/data/absent.csv": "sha256:" + "0" * 64}}, 0),
            ]
            for name, over, want in cases:
                found = ca._entry("fig.x", entry(**over))
                got = sum(1 for f in found if f.level == "error")
                if got != want:
                    print(f"  check-assets [{name}]: expected {want} error(s), "
                          f"got {got}" + (f" -- {[f.msg for f in found]}" if got else ""))
                    ok = False

            # A file sitting in a generated directory that no entry claims: the
            # deleted-generator leftover nothing else can see.
            (root / "figures" / "stray.png").write_bytes(b"x")
            if not any(f.id.endswith("stray.png")
                       for f in ca._unclaimed({"fig.x": entry()})):
                print("  check-assets: an unclaimed file was not reported")
                ok = False
        finally:
            ca.ROOT = orig_root

    # The bypass rule: naming a declared asset directly goes around the manifest,
    # so assets.json quietly stops describing the manuscript.
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "assets.json"
        p.write_text(json.dumps({"values": {
            "fig.example": {"path": "figures/example_figure.png",
                            "kind": "figure"},
            "tbl.example": {"path": "si/example_table.typ", "kind": "table"},
        }}))
        cases = [
            ("by id", '#figure(fig("fig.example"), caption: [x])', 0),
            ("figure by filename",
             '#figure(image("figures/example_figure.png"), caption: [x])', 1),
            ("table by filename", '#include "si/example_table.typ"', 1),
            # Not every image is a generated asset. A logo or a hand-drawn
            # schematic is named directly and must not be flagged.
            ("undeclared image is fine", '#image("figures/logo.png")', 0),
            ("mentioned in a comment", '// image("figures/example_figure.png")', 0),
        ]
        for name, src, want in cases:
            got = len(pc.check_bypassed_assets({"t": src}, p))
            if got != want:
                print(f"  bypassed-asset [{name}]: expected {want}, got {got}")
                ok = False

    return ok

def run_cases() -> bool:
    ok = True
    for case in (asset_cases, check_assets_cases,):
        ok &= case()
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
