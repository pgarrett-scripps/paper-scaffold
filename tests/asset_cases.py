"""assets.json: the manifest, the files it describes, and the prose that
names one directly instead of by id."""
from __future__ import annotations

import hashlib
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

def toolchain_version_cases() -> bool:
    """A scaffold version bump in the ROOT pyproject.toml / uv.lock leaves a
    generator that declared them current; a dependency change, and any change
    to analysis/pyproject.toml, still reads as stale (cascade/paper saw every
    figure and number go stale on a bump)."""
    import hashcache
    sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
    import _provenance
    ok = True

    def expect(name, got, want):
        nonlocal ok
        if got != want:
            print(f"  toolchain-version [{name}]: expected {want}, got {got}")
            ok = False

    py = ('[project]\nname = "paper"\nversion = "3.23.0"\n'
          'dependencies = ["pillow>=10"]\n\n[tool.x]\nversion = "1"\n')
    lock = ('version = 1\n\n[[package]]\nname = "paper"\nversion = "3.23.0"\n'
            'source = { virtual = "." }\n\n[[package]]\nname = "pillow"\n'
            'version = "10.0.0"\nsource = { registry = "https://pypi.org/simple" }\n')
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "analysis").mkdir()
        (root / "pyproject.toml").write_text(py)
        (root / "uv.lock").write_text(lock)
        (root / "analysis" / "pyproject.toml").write_text(py)
        rec = {n: hashcache.recorded_sha(root, n)
               for n in ("pyproject.toml", "uv.lock", "analysis/pyproject.toml")}
        # The generator side records through the same function.
        with_paper = _provenance.PAPER
        _provenance.PAPER = root
        try:
            expect("declared_inputs", _provenance.declared_inputs(["pyproject.toml"]),
                   {"pyproject.toml": rec["pyproject.toml"]})
        finally:
            _provenance.PAPER = with_paper
        legacy = hashcache.sha(root / "pyproject.toml")

        def bump(text):
            return text.replace('version = "3.23.0"', 'version = "3.24.0"')
        (root / "pyproject.toml").write_text(bump(py))
        (root / "uv.lock").write_text(bump(lock))
        (root / "analysis" / "pyproject.toml").write_text(bump(py))
        for n in ("pyproject.toml", "uv.lock"):
            expect(f"{n} bump", hashcache.input_current(root, n, rec[n]), True)
        expect("analysis/pyproject.toml bump", hashcache.input_current(
            root, "analysis/pyproject.toml", rec["analysis/pyproject.toml"]), False)
        # A raw-bytes hash recorded before this still matches only unchanged bytes.
        expect("legacy raw hash after bump",
               hashcache.input_current(root, "pyproject.toml", legacy), False)
        (root / "pyproject.toml").write_text(py)
        expect("legacy raw hash unchanged",
               hashcache.input_current(root, "pyproject.toml", legacy), True)
        # Anything else in the file still counts: a dependency, a tool's
        # version, a locked package's version.
        for n, text in (("pyproject.toml", py.replace("pillow>=10", "pillow>=11")),
                        ("pyproject.toml", py.replace('version = "1"', 'version = "2"')),
                        ("uv.lock", lock.replace('"10.0.0"', '"11.0.0"'))):
            (root / n).write_text(text)
            expect(f"{n} real change", hashcache.input_current(root, n, rec[n]), False)

    # 4.x: the paper's version is constant and the release moves in the
    # paper-scaffold pin. Moving it (pyproject dependency, lock requires-dist,
    # the paper-scaffold block) leaves a record current; a dependency the new
    # toolchain locks differently does not.
    def pinned(tag, commit, pillow="10.0.0"):
        py = ('[project]\nname = "paper"\nversion = "0.0.0"\ndependencies = [\n'
              f'  "paper-scaffold @ git+https://github.com/o/paper-scaffold@v{tag}",\n]\n')
        lock = ('version = 1\n\n[[package]]\nname = "paper"\nversion = "0.0.0"\n'
                'source = { virtual = "." }\ndependencies = [\n'
                '    { name = "paper-scaffold" },\n]\n\n[package.metadata]\n'
                'requires-dist = [{ name = "paper-scaffold", git = '
                f'"https://github.com/o/paper-scaffold?rev=v{tag}" }}]\n\n'
                '[[package]]\nname = "paper-scaffold"\n'
                f'version = "{tag}"\nsource = {{ git = "https://github.com/o/'
                f'paper-scaffold?rev=v{tag}#{commit}" }}\ndependencies = [\n'
                '    { name = "pillow" },\n]\n\n[[package]]\nname = "pillow"\n'
                f'version = "{pillow}"\nsource = {{ registry = "https://pypi.org/simple" }}\n')
        return {"pyproject.toml": py, "uv.lock": lock}
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for n, text in pinned("4.1.0", "a" * 40).items():
            (root / n).write_text(text)
        rec = {n: hashcache.recorded_sha(root, n) for n in ("pyproject.toml", "uv.lock")}
        # A 4.0.0-form record (own version line only) is accepted while unchanged.
        old = {n: "sha256:" + hashlib.sha256(hashcache._without_own_version(
                   n, (root / n).read_text()).encode()).hexdigest() for n in rec}
        for n in rec:
            expect(f"{n} 4.0 form unchanged", hashcache.input_current(root, n, old[n]), True)
        for n, text in pinned("4.1.1", "b" * 40).items():
            (root / n).write_text(text)
        for n in rec:
            expect(f"{n} pin move", hashcache.input_current(root, n, rec[n]), True)
        (root / "uv.lock").write_text(pinned("4.1.1", "b" * 40, pillow="11.0.0")["uv.lock"])
        expect("uv.lock pin move with a dependency change",
               hashcache.input_current(root, "uv.lock", rec["uv.lock"]), False)

    # `paper sync` rewrites analysis/scripts/_toolchain/ with the release in a
    # header: never recorded, and an older record holding one is not stale.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scripts = root / "analysis" / "scripts"
        (scripts / "_toolchain").mkdir(parents=True)
        (scripts / "_toolchain" / "tc_probe.py").write_text("# release 4.1.0\n")
        (scripts / "helper_probe.py").write_text("X = 1\n")
        import importlib.util
        for name, path in (("tc_probe", scripts / "_toolchain" / "tc_probe.py"),
                           ("helper_probe", scripts / "helper_probe.py")):
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sys.modules[name] = module
        with_paper = _provenance.PAPER
        _provenance.PAPER = root.resolve()
        try:
            recorded = _provenance.code_inputs()
        finally:
            _provenance.PAPER = with_paper
            sys.modules.pop("tc_probe")
            sys.modules.pop("helper_probe")
        expect("helper recorded", "analysis/scripts/helper_probe.py" in recorded, True)
        expect("_toolchain not recorded",
               any("_toolchain" in k for k in recorded), False)
        rel = "analysis/scripts/_toolchain/tc_probe.py"
        want = hashcache.recorded_sha(root, rel)
        (root / rel).write_text("# release 4.1.1\n")
        expect("old _toolchain record after sync", hashcache.input_current(root, rel, want), True)
    return ok


def synced_header_cases() -> bool:
    """A file `paper sync` wrote (its GENERATED header names the release),
    recorded as an input, stays current when a pin move rewrites only that
    release; an edit to its body still reads stale. cascade/paper declares
    analysis/scripts/_stats.py, and 4.1.1 marked its numbers stale on every
    pin move (4.1.2)."""
    import hashcache
    sys.path.insert(0, str(ROOT / "src"))
    from paper_scaffold.sync import with_header
    sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
    import _provenance
    ok = True

    def expect(name, got, want):
        nonlocal ok
        if got != want:
            print(f"  synced-header [{name}]: expected {want}, got {got}")
            ok = False

    body = '"""helper"""\nX = 1\n'
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scripts = root / "analysis" / "scripts"
        scripts.mkdir(parents=True)
        cases = {"analysis/scripts/_stats.py": body,
                 "stats.typ": "#let s(id) = id\n",
                 "audio/make_cover.py": "#!/usr/bin/env python3\n" + body}
        for rel, text in cases.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(with_header(rel, text, "4.1.2"))
            want = hashcache.recorded_sha(root, rel)
            expect(f"{rel} not raw", want == hashcache.sha(root / rel), False)
            (root / rel).write_text(with_header(rel, text, "4.2.0"))
            expect(f"{rel} pin move", hashcache.input_current(root, rel, want), True)
            expect(f"{rel} same record", hashcache.recorded_sha(root, rel), want)
            (root / rel).write_text(with_header(rel, text + "Y = 2\n", "4.2.0"))
            expect(f"{rel} body change", hashcache.input_current(root, rel, want), False)
        # A record in the 4.1.1 form (raw bytes) is accepted while unchanged.
        rel = "analysis/scripts/_stats.py"
        (root / rel).write_text(with_header(rel, body, "4.1.1"))
        raw = "sha256:" + hashlib.sha256((root / rel).read_bytes()).hexdigest()
        expect("4.1.1 raw record unchanged", hashcache.input_current(root, rel, raw), True)
        # A file with no header, or one that only mentions it later, is hashed whole.
        (root / "plain.py").write_text("X = 1\n# GENERATED by `paper sync` from paper-scaffold 1. Do not edit:\n")
        expect("no header: raw", hashcache.recorded_sha(root, "plain.py"),
               "sha256:" + hashlib.sha256((root / "plain.py").read_bytes()).hexdigest())
        # code_inputs() records a synced module the same way.
        probe = scripts / "synced_probe.py"
        probe.write_text(with_header("analysis/scripts/synced_probe.py", body, "4.1.2"))
        import importlib.util
        spec = importlib.util.spec_from_file_location("synced_probe", probe)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules["synced_probe"] = module
        with_paper = _provenance.PAPER
        _provenance.PAPER = root.resolve()
        try:
            recorded = _provenance.code_inputs()
        finally:
            _provenance.PAPER = with_paper
            sys.modules.pop("synced_probe")
        prel = "analysis/scripts/synced_probe.py"
        probe.write_text(with_header(prel, body, "4.2.0"))
        expect("code_inputs pin move",
               hashcache.input_current(root, prel, recorded.get(prel, "")), True)
    return ok


def run_cases() -> bool:
    ok = True
    for case in (asset_cases, check_assets_cases, toolchain_version_cases,
                 synced_header_cases):
        ok &= case()
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
