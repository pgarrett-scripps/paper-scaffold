"""Where the numbers come from: evidence.toml, versions, inputs, pending.

tools/evidence.py (the manifest and the run log), tools/check_evidence.py
(the gate, stamp and impact), the origin.source rule for hand entries in
check_stats, `checked_against` and the generator run log in check_assets,
and the pending placeholders in stats.typ / assets.typ. Every case builds its
own tree in a temporary directory; nothing reads the manuscript's own files
except stats.typ and assets.typ, which are copied.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_assets  # noqa: E402
import check_evidence as ce  # noqa: E402
import check_stats  # noqa: E402
import evidence  # noqa: E402


def levels(found, level="error"):
    return [f for f in found if f.level == level]


class Evidence(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / ".git").mkdir()          # git_top() stops here

    def put(self, rel: str, text: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def manifest(self, body: str):
        self.put("evidence.toml", body)
        return evidence.load(self.root)

    def stats(self, values: dict, **extra):
        self.put("stats.json", json.dumps({"values": values, **extra}))

    def assets(self, values: dict, **extra):
        self.put("assets.json", json.dumps({"values": values, **extra}))

    # ---- the manifest ------------------------------------------------------

    def test_paths_must_be_repo_relative(self):
        self.put("runs/a/x.csv", "1")
        for bad in ('"/home/me/runs/a"', '"~/runs/a"', '"../../elsewhere"'):
            with self.subTest(bad=bad), self.assertRaises(evidence.EvidenceError):
                self.manifest(f"[sets.a]\npath = {bad}\n")
        # `..` inside the repository is fine (a manuscript in paper/).
        (self.root / "paper").mkdir()
        self.put("paper/evidence.toml", '[sets.a]\npath = "../runs/a"\n')
        self.assertIn("a", evidence.load(self.root / "paper").sets)

    def test_unknown_keys_and_bad_values_are_errors(self):
        for body in ('[sets.a]\npath = "r"\nversion = "1"\n',
                     '[sets.a]\npath = "r"\nstatus = "done"\n',
                     '[sets.a]\npath = "r"\nfrozen_at = "last week"\n',
                     '[checks]\nuntracked_inputs = "loud"\n',
                     '[sets.a]\nsoftware = { tool = "1" }\n'):
            with self.subTest(body=body), self.assertRaises(evidence.EvidenceError):
                self.manifest(body)

    def test_symlinked_data_dir_is_inside_lexically(self):
        with tempfile.TemporaryDirectory() as drive:
            Path(drive, "x.csv").write_text("1")
            os.symlink(drive, self.root / "data")
            m = self.manifest('[sets.d]\npath = "data"\n')
            self.assertEqual(m.containing(self.root, "data/x.csv"), ["d"])
            self.assertEqual(evidence.resolve(self.root, "d", m), self.root / "data")

    def test_resolve_fails_loudly(self):
        m = self.manifest('[sets.a]\npath = "runs/a"\n')
        with self.assertRaisesRegex(evidence.EvidenceError, "does not exist"):
            evidence.resolve(self.root, "a", m)
        with self.assertRaisesRegex(evidence.EvidenceError, "no such set"):
            evidence.resolve(self.root, "b", m)

    # ---- versions ----------------------------------------------------------

    def test_stale_and_mixed_versions(self):
        self.put("runs/new/x", "1")
        self.put("runs/old/x", "1")
        m = self.manifest('[sets.new]\npath = "runs/new"\nsoftware = { tool = "0.10.0" }\n'
                          '[sets.old]\npath = "runs/old"\nsoftware = { tool = "0.7.0" }\n')
        docs = {"stats": {"values": {
                    "stale": {"value": 1, "evidence": {"new": {"tool": "0.7.0"}}},
                    "mixed": {"value": 1, "evidence": {"new": {"tool": "0.10.0"},
                                                       "old": {"tool": "0.7.0"}}},
                    "fine": {"value": 1, "evidence": {"new": {"tool": "0.10.0"}}}}},
                "assets": {"values": {}}}
        errors = {f.id for f in levels(ce._entries(m, docs))}
        self.assertEqual(errors, {"stale", "mixed"})
        m.allow_mixed = ("mix*",)
        found = ce._entries(m, docs)
        self.assertEqual({f.id for f in levels(found)}, {"stale"})
        self.assertIn("mixed", {f.id for f in levels(found, "note")})

    def test_attribution_by_pattern_input_and_name(self):
        self.put("runs/a/x.csv", "1")
        self.put("runs/b/x.csv", "1")
        m = self.manifest('[sets.a]\npath = "runs/a"\nsoftware = { t = "1" }\n'
                          'stats = ["bench.*"]\n'
                          '[sets.b]\npath = "runs/b"\nsoftware = { t = "2" }\n')
        self.assertEqual(evidence.attribution(m, self.root, "bench.q", "stats"),
                         {"a": {"t": "1"}})
        got = evidence.attribution(m, self.root, "x", "assets", ["runs/b/x.csv"], ["a"])
        self.assertEqual(evidence.mixed(got), {"t": ["1", "2"]})

    def test_impact_lists_sets_entries_and_uses(self):
        self.put("runs/a/x", "1")
        self.manifest('[sets.a]\npath = "runs/a"\nsoftware = { tool = "0.7.0" }\n')
        self.stats({"q": {"value": 1, "fmt": "", "evidence": {"a": {"tool": "0.7.0"}}}})
        self.assets({})
        self.put("paper.typ", 'Recall was #s("q").\n')
        with patch("manuscript_sources.ROOT", self.root):
            lines, rc = ce.impact(self.root, "tool@0.7.0")
        text = "\n".join(lines)
        self.assertEqual(rc, 0)
        self.assertIn("set     a", text)
        self.assertIn("q", text)
        lines, _ = ce.impact(self.root, "tool@0.8.0")
        self.assertTrue(lines[0].startswith("tool@0.8.0: 0 evidence set(s), 0"))

    # ---- sets: pending, verify, stale inputs, frozen, held-out --------------

    def test_set_checks(self):
        self.put("runs/a/r.csv", "1")
        self.put("runs/a/verification.json", json.dumps({"status": "failed"}))
        self.put("config/search.toml", "fdr = 0.01")
        m = self.manifest(
            '[sets.a]\npath = "runs/a"\nsoftware = { t = "1" }\n'
            'verify = "runs/a/verification.json"\ninputs = ["config/search.toml"]\n'
            'status = "held-out"\nfrozen_at = 2026-09-02\nfirst_scored_at = 2026-09-01\n'
            '[sets.p]\npath = "runs/p"\nstatus = "pending"\n')
        msgs = " | ".join(f.msg for f in levels(ce._sets(self.root, m, False)))
        self.assertIn("not verified", msgs)
        self.assertIn("after it was first scored", msgs)
        self.assertIn("declared pending", msgs)
        # The stale-setting trap: stamp, change the config, and the gate fails.
        self.put("runs/a/verification.json", json.dumps({"status": "verified"}))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ce.stamp(self.root, ["a"])[1], 0)
        self.assertFalse([f for f in levels(ce._sets(self.root, m, False))
                          if f.id == "set a" and "scored" not in f.msg])
        self.put("config/search.toml", "fdr = 0.05")
        self.put("runs/a/extra.csv", "2")
        msgs = " | ".join(f.msg for f in levels(ce._sets(self.root, m, False)))
        self.assertIn("config/search.toml changed after", msgs)
        self.assertIn("its files changed since", msgs)

    def test_missing_path_is_an_error_only_when_strict(self):
        m = self.manifest('[sets.a]\npath = "runs/a"\nsoftware = { t = "1" }\n')
        self.assertFalse(levels(ce._sets(self.root, m, False)))
        self.assertTrue(levels(ce._sets(self.root, m, True)))

    def test_pending_blocks_fail_the_gate(self):
        self.stats({}, pending={"bench.*": "rerun at 0.10"})
        self.assets({}, pending={"fig.x": "rerun"})
        found = ce.check(self.root)
        self.assertEqual({f.id for f in levels(found)}, {"bench.*", "fig.x"})

    def test_version_literal_in_prose(self):
        self.put("runs/a/x", "1")
        m = self.manifest('[sets.a]\npath = "runs/a"\nsoftware = { searchtool = "0.10.0" }\n')
        self.put("paper.typ", "We used searchtool 0.7.0 throughout.\n"
                              "Searchtool v0.10.0 is current.\n")
        with patch("manuscript_sources.ROOT", self.root):
            found = ce._literals(self.root, m)
        self.assertEqual([f.id for f in found], ["paper.typ:1"])

    # ---- inputs ------------------------------------------------------------

    def test_untracked_and_host_inputs_warn(self):
        if not shutil.which("git"):
            self.skipTest("git not installed")
        shutil.rmtree(self.root / ".git")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.put(".gitignore", "data/big/\n")
        self.put("data/tracked.csv", "1")
        self.put("data/loose.csv", "1")
        self.put("data/big/x.bin", "1")
        subprocess.run(["git", "add", ".gitignore", "data/tracked.csv"], cwd=self.root, check=True)
        self.stats({}, sources={"analysis/scripts/gen_stats.py": {
            "data/tracked.csv": "h", "data/loose.csv": "h", "data/big/x.bin": "h",
            "/home/me/raw.csv": "h"}})
        self.assets({})
        found = ce.check(self.root)
        warn = " | ".join(f.msg for f in levels(found, "warn"))
        self.assertIn("2 declared input(s) not tracked by git (1 gitignored)", warn)
        self.assertIn("host paths", warn)
        self.assertFalse(levels(found))
        self.put("evidence.toml", '[checks]\nuntracked_inputs = "error"\n')
        self.assertEqual(len(levels(ce.check(self.root))), 1)
        # Inputs inside a declared evidence set are the manifest's business.
        self.put("evidence.toml", '[checks]\nuntracked_inputs = "error"\n'
                                  '[sets.d]\npath = "data"\n')
        self.assertFalse(levels(ce.check(self.root)))

    # ---- hand entries name a source ----------------------------------------

    def test_hand_entry_source(self):
        with patch.object(check_stats, "ROOT", self.root):
            hs = check_stats._hand_source
            self.assertEqual(hs("x", {"note": "n"})[0].level, "error")
            self.put(".paper/grandfathered.json", json.dumps({"hand-source": ["x"]}))
            self.assertEqual(hs("x", {"note": "n"})[0].level, "warn")
            self.assertEqual(hs("y", {"note": "n"})[0].level, "error")
            self.assertFalse(hs("x", {"source": "https://example.org/t1"}))
            self.assertFalse(hs("x", {"source": "doi:10.1000/182"}))
            self.assertFalse(hs("x", {"source": "3f9a2c1"}))
            self.assertEqual(hs("x", {"source": "/mnt/data/t.csv"})[0].level, "error")
            self.assertEqual(hs("x", {"source": "evidence:none"})[0].level, "error")
            self.assertEqual(hs("x", {"source": "notes/t.csv"})[0].level, "warn")
            self.put("notes/t.csv", "1")
            self.assertFalse(hs("x", {"source": "notes/t.csv#row-3"}))

    def test_sync_grandfathers_on_the_move_to_5(self):
        from paper_scaffold import sync
        self.stats({"a": {"value": 1, "origin": {"by": "hand", "note": "n"}},
                    "b": {"value": 1, "origin": {"by": "hand", "note": "n",
                                                  "source": "doi:10.1/x"}}})
        self.assertEqual(sync.grandfather(self.root, "5.0.0"), [])
        self.assertEqual(sync.grandfather(self.root, "4.3.0"), ["a"])
        self.assertEqual(evidence.grandfathered(self.root, "hand-source"), {"a"})

    # ---- assets: checked_against, generators that did not run --------------

    def test_checked_against_warns_on_change(self):
        import adopt_assets
        self.put("uv.lock", "v1")
        self.put("si/versions.typ", "#table()")
        self.assets({"tbl.v": {"path": "si/versions.typ", "kind": "table",
                               "origin": {"by": "adopted"},
                               "checked_against": {"uv.lock": None}}})
        rec = lambda: json.loads((self.root / "assets.json").read_text())["values"]["tbl.v"]
        with patch.object(check_assets, "ROOT", self.root):
            self.assertEqual(levels(check_assets._checked_against("tbl.v", rec()), "warn")[0].id, "tbl.v")
            self.assertEqual(adopt_assets.checked(self.root, "tbl.v")[1], 0)
            self.assertFalse(check_assets._checked_against("tbl.v", rec()))
            self.put("uv.lock", "v2")
            self.assertIn("has changed", check_assets._checked_against("tbl.v", rec())[0].msg)

    def test_run_log_names_generators_that_did_not_run(self):
        values = {"fig.a": {"origin": {"by": "analysis/scripts/gen_a_figure.py"}},
                  "fig.b": {"origin": {"by": "analysis/scripts/old_plot.py"}}}
        with patch.object(check_assets, "ROOT", self.root):
            self.assertFalse(check_assets._generators(values))   # no log: silent
            self.put("analysis/justfile", "assets:\n  uv run scripts/gen_a_figure.py\n")
            self.assertEqual([f.id for f in check_assets._generators(values)],
                             ["analysis/scripts/old_plot.py"])
            token = evidence.run_start(self.root)
            with patch.dict(os.environ, {"PAPER_ASSETS_RUN": token}):
                evidence.run_note(self.root, "analysis/scripts/gen_a_figure.py")
            self.assertIsNone(evidence.last_run(self.root))      # still open
            evidence.run_end(self.root, token)
            found = check_assets._generators(values)
            self.assertEqual([(f.level, f.id) for f in found],
                             [("warn", "analysis/scripts/old_plot.py")])

    # ---- pending placeholders compile --------------------------------------

    def test_pending_ids_compile_to_a_placeholder(self):
        if not shutil.which("typst"):
            self.skipTest("typst not installed")
        for name in ("stats.typ", "assets.typ"):
            shutil.copy(ROOT / name, self.root / name)
        self.put("stats-rendered.json", json.dumps({
            "values": {"a.b": {"display": "1.5", "value": 1.5}},
            "pending": {"bench.*": "waiting for the rerun"}}))
        self.assets({}, pending={"fig.x": "rerun"})
        self.put("t.typ", '#import "stats.typ": s\n#import "assets.typ": fig\n'
                          'Value #s("a.b") and #s("bench.q").\n'
                          '#figure(fig("fig.x"), caption: [x])\n')
        proc = subprocess.run(["typst", "compile", "--root", str(self.root),
                               str(self.root / "t.typ")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # An undeclared, non-pending id still fails the compile.
        self.put("t.typ", '#import "stats.typ": s\n#s("bench2.q")\n')
        proc = subprocess.run(["typst", "compile", "--root", str(self.root),
                               str(self.root / "t.typ")], capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)


def run_cases() -> bool:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Evidence)
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
