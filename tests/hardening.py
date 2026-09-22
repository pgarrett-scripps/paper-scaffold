"""Regression cases for the contracts that a green example did not exercise."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_state
import check_stats
import export_docx
import manifest_validation
import manuscript_sources
import prose_edit_guard
import resolve_typst
import trace


class Hardening(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_references_never_count_as_definitions(self):
        for ref in ("#ref(<fig:x>)", "#ref( <fig:x>)", "#ref(\n <fig:x>,\n)"):
            with self.subTest(ref=ref):
                body = '#figure(rect(), caption: [Example]) <fig:x>\n' + ref + " and " + ref
                resolved = resolve_typst.resolve_crossrefs("", body)
                self.assertNotIn("Figure 2", resolved)
                self.assertEqual(resolved.count("Figure 1"), 3)
        body = resolve_typst.resolve_notation(
            '#figure(rect(), caption: [Example]) <fig:x>\n#refn(\n <fig:x>,\n)', {}, "fixture")
        self.assertTrue(resolve_typst.resolve_crossrefs("", body).endswith("\n1"))

    @unittest.skipUnless(shutil.which("typst"), "typst not installed")
    def test_native_reference_number_agrees_with_resolver(self):
        body = '#figure(rect(), caption: [Example]) <fig:x>\nSee #ref(\n <fig:x>,\n).'
        src = self.put("reference.typ", body)
        # Typst itself evaluates ref content through a show rule into metadata.
        src.write_text('#show ref: it => context metadata(counter(figure).at(it.element.location()))\n' + body)
        proc = subprocess.run(["typst", "query", str(src), "metadata", "--field", "value"],
                              capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(proc.stdout), [[1]])
        self.assertIn("See Figure 1.", resolve_typst.resolve_crossrefs("", body))

    def test_guard_types_are_not_silently_ignored(self):
        for value, guard in (("oops", {"min": 0}), (True, {"sign": "+"}),
                             (float("inf"), {}), (float("nan"), {}),
                             (1, {"min": float("nan")}), (1, {"sign": ""}),
                             (1, []), (1, {"min": 3, "max": 2})):
            with self.subTest(value=value, guard=guard):
                self.assertTrue(manifest_validation.guard_errors(value, guard))
                self.assertTrue(check_stats._guard("test", {"value": value, "expect": guard}))

    def test_malformed_manifests_are_named_errors(self):
        for doc in ([], {"values": {"x": None}},
                    {"values": {"x": {"value": 1, "origin": {"note": 4}}}},
                    {"values": {}, "sources": []}, {"values": {}, "pinned": []}):
            with self.subTest(doc=doc):
                with self.assertRaises(manifest_validation.ManifestError):
                    manifest_validation.validate(doc, "stats")

    def test_source_index_follows_relative_includes_and_ignores_examples(self):
        self.put("paper.typ", '#include "sections/results.typ"\n// #s("fake")\n`#s("fake")`')
        self.put("sections/results.typ", '#include "detail.typ"\n#s(\n "real",\n)')
        self.put("sections/detail.typ", '#fig("fig.real")')
        self.put("paper.resolved.typ", '#s("stale")')
        uses = manuscript_sources.usages(self.root)
        self.assertEqual({u["id"] for u in uses}, {"real", "fig.real"})
        self.assertEqual(next(u for u in uses if u["id"] == "real")["line"], 2)
        self.put("sections/detail.typ", '#include "results.typ"')
        with self.assertRaisesRegex(ValueError, "cyclic"):
            manuscript_sources.source_files(self.root)

    def test_edit_guard_protects_helper_ids_and_abstract(self):
        paper = self.put("paper.typ", '= Results\n#s("control")\n#figure(fig("fig.control")) <fig:x>\n@fig:x @fig:x')
        config = self.put("config.typ", '#let paper-abstract = [Observed #s("control").]')
        self.put("si-body.typ", "= Details\n")
        with patch.object(prose_edit_guard, "ROOT", self.root), patch.object(
                prose_edit_guard, "SNAP_DIR", self.root / ".edit-guard"), contextlib.redirect_stdout(io.StringIO()):
            prose_edit_guard.snapshot("test")
            self.assertEqual(prose_edit_guard.check("test"), 0)
            original = paper.read_text()
            for replacement in (original.replace('s("control")', 's("treated")'),
                                original.replace('fig("fig.control")', 'fig("fig.treated")'),
                                original.replace('@fig:x @fig:x', '@fig:x')):
                paper.write_text(replacement)
                self.assertEqual(prose_edit_guard.check("test"), 1)
            paper.write_text(original)
            config.write_text('#let paper-abstract = [Observed #s("treated").]')
            self.assertEqual(prose_edit_guard.check("test"), 1)

    def test_edit_guard_allows_dropping_a_numeric_statement(self):
        paper = self.put("paper.typ", '= Results\n#s("x") and 84.2.\n')
        with patch.object(prose_edit_guard, "ROOT", self.root), patch.object(
                prose_edit_guard, "SNAP_DIR", self.root / ".edit-guard"), contextlib.redirect_stdout(io.StringIO()):
            prose_edit_guard.snapshot("test")
            paper.write_text("= Results\nSee the table.\n")
            self.assertEqual(prose_edit_guard.check("test"), 0)

    def test_build_hash_tracks_includes_csl_filter_but_not_pins(self):
        self.put("paper.typ", '#include "sections/results.typ"')
        self.put("sections/results.typ", "Original.")
        self.put("stats.json", json.dumps({"values": {}, "pinned": {"data.csv": "old"}}))
        before = build_state.snapshot(self.root)
        self.put("stats.json", json.dumps({"values": {}, "pinned": {"data.csv": "new"}}))
        self.assertEqual(before, build_state.snapshot(self.root))
        for name in ("sections/results.typ", "csl/example.csl", "tools/refs_div.lua"):
            before = build_state.snapshot(self.root)
            self.put(name, "Changed.")
            self.assertNotEqual(before, build_state.snapshot(self.root))

    def test_mid_build_edit_preserves_last_good_output(self):
        paper = self.put("paper.typ", "Original.")
        self.put("paper.pdf", "last good output")

        def run(args, **kwargs):
            if args[0] == "typst":
                paper.write_text("Edited while compiling.")
                Path(args[-1]).write_text("new output")
                Path(args[args.index("--deps") + 1]).write_text('{"inputs": ["paper.typ"]}')

        with patch.object(build_state.subprocess, "run", side_effect=run):
            with self.assertRaisesRegex(ValueError, "sources changed"):
                build_state.build("paper", self.root)
        self.assertEqual((self.root / "paper.pdf").read_text(), "last good output")
        self.assertFalse(build_state.state_path(self.root, "paper.pdf").exists())

    def test_new_compiler_dependency_is_captured_before_retry(self):
        self.put("paper.typ", "Original.")
        self.put("dynamic.csv", "42")
        calls = []

        def run(args, **kwargs):
            if args[0] == "typst":
                calls.append(args)
                Path(args[-1]).write_text("complete output")
                Path(args[args.index("--deps") + 1]).write_text('{"inputs": ["paper.typ", "dynamic.csv"]}')

        def capture(root, folder, sources, dependencies, **_kw):
            # The dependency retry belongs to the build coordinator. The
            # snapshot renderer has its own real-compiler tests.
            folder.mkdir()
            (folder / "paper.pdf").write_text("complete output")
            (folder / "paper.word.typ").write_text("Original.")
            return {"id": "fixture"}

        with patch.object(build_state.subprocess, "run", side_effect=run), \
                patch.object(build_state, "prepare_snapshot", side_effect=capture), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build_state.build("paper", self.root), 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(build_state.check(self.root)[0]["status"], "current")
        self.put("dynamic.csv", "43")
        self.assertEqual(build_state.check(self.root)[0]["status"], "stale")

    def test_parallel_build_is_rejected(self):
        with build_state.build_lock(self.root):
            with self.assertRaisesRegex(ValueError, "another manuscript build"):
                with build_state.build_lock(self.root):
                    pass

    def test_replaced_output_is_detected(self):
        self.put("paper.typ", "Original.")
        self.put("paper.pdf", "original output")
        state = {"schema_version": 1, "dependencies": [],
                 "sources": build_state.snapshot(self.root),
                 "output_hash": build_state.digest(self.root / "paper.pdf")}
        self.put(".build-state/paper.pdf.json", json.dumps(state))
        self.put("paper.pdf", "replaced output")
        self.assertEqual(build_state.check(self.root)[0]["status"], "replaced")

    def test_deep_noop_and_crash_are_incomplete(self):
        gen = self.put("analysis/scripts/gen_stats.py", 'print("no write")')
        stats = self.put("stats.json", json.dumps({"values": {
            "x": {"value": 1, "origin": {"by": "analysis/scripts/gen_stats.py"}}}}))
        with patch.object(check_stats, "ROOT", self.root), patch.object(check_stats, "STATS", stats), \
                patch.object(check_stats, "GEN", gen), patch("shutil.which", return_value=None):
            for code in ('print("no write")', 'raise RuntimeError("broken")'):
                gen.write_text(code)
                found, status = check_stats._rederive(json.loads(stats.read_text())["values"])
                self.assertTrue(any(f.level == "incomplete" for f in found))
                self.assertNotIn("value(s) re-derived", status)

    def test_deep_real_writer_preserves_authored_guard_and_checks_type(self):
        if not (ROOT / "analysis/scripts/_stats.py").exists():
            self.skipTest("analysis contract removed from this manuscript")
        for name in ("analysis/scripts/_stats.py", "analysis/scripts/_provenance.py",
                     "tools/manifest_validation.py", "tools/atomic_io.py"):
            self.put(name, (ROOT / name).read_text())
        gen = self.put("analysis/scripts/gen_stats.py", 'from _stats import Stats\ns=Stats()\ns.add("x", 1.0)\ns.write()')
        stats = self.put("stats.json", json.dumps({"values": {
            "x": {"value": 1, "expect": {"min": 0}, "origin": {"by": "analysis/scripts/gen_stats.py"}}}}))
        with patch.object(check_stats, "ROOT", self.root), patch.object(check_stats, "STATS", stats), \
                patch.object(check_stats, "GEN", gen), patch("shutil.which", return_value=None):
            found, status = check_stats._rederive(json.loads(stats.read_text())["values"])
            self.assertIn("1 value(s) re-derived", status)
            self.assertTrue(any(f.level == "error" for f in found))
            gen.write_text(gen.read_text().replace('1.0', '-1'))
            found, status = check_stats._rederive(json.loads(stats.read_text())["values"])
            self.assertTrue(any(f.level == "error" for f in found))

    def test_bibliography_reader_accepts_indentation_and_rejects_partial_parse(self):
        bib = self.put("references.bib", '  @article{valid, title={Good}}')
        self.assertEqual(export_docx.check_citations('@valid', [bib]), [])
        self.assertEqual(export_docx.check_citations('`@example` @valid', [bib]), [])
        bib.write_text(bib.read_text() + '\n@article{broken,title={Missing end}')
        with self.assertLogs(level="WARNING"), self.assertRaisesRegex(ValueError, "malformed"):
            export_docx.check_citations('@valid', [bib])

    def test_submission_requires_completed_bibliography_audit(self):
        import bib_audit
        args = {"entries": [{"_key": "x", "doi": "10.1234/example"}],
                "fetch": lambda *args: ("error", "offline"), "pause": False}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bib_audit.audit(**args), 0)
            self.assertEqual(bib_audit.audit(**args, require_complete=True), 2)

    def test_trace_reports_hand_stat_uses_and_guard_failure(self):
        self.put("paper.typ", '#s("x")\n// #s("not-real")')
        doc = {"values": {"x": {"value": 3, "fmt": "", "expect": {"min": 0},
                               "origin": {"by": "hand", "note": "protocol"}}}}
        self.put("stats.json", json.dumps(doc))
        result = trace.inspect("x", self.root)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["uses"][0]["line"], 1)
        self.assertFalse(result["scope"]["rederived"])
        doc["values"]["x"]["value"] = -3
        self.put("stats.json", json.dumps(doc))
        result = trace.inspect("x", self.root)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["findings"][0]["rule"], "stats.guard")

    def test_documented_cli_forwarding_and_json_output(self):
        env = dict(__import__("os").environ)
        proc = subprocess.run(["just", "prose-check", "--list-rules"], cwd=ROOT,
                              env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("unaccounted-number", proc.stdout)
        proc = subprocess.run(["just", "trace", "missing.test.id", "--json"], cwd=ROOT,
                              env=env, capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["schema_version"], 1)

    def test_new_paper_single_keyword_and_local_state_exclusions(self):
        script = ROOT / "scripts/new-paper.sh"
        if not script.exists():
            self.skipTest("new-paper is not shipped into derived manuscripts")
        source = self.root / "source"
        for name in ("scripts/new-paper.sh", "config.typ", "pyproject.toml", "LICENSE", ".gitignore"):
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        shutil.copytree(ROOT / ".claude/skills", source / ".claude/skills")
        (source / ".agents").mkdir()
        shutil.copy2(ROOT / ".agents/skills", source / ".agents/skills",
                     follow_symlinks=False)
        artifacts = ("paper.resolved.typ", ".text-baseline", ".edit-guard/old.json",
                     ".build-state/paper.pdf.json", "audio/paper.m4b")
        for name in artifacts:
            self.put("source/" + name, "old local state")
        destination = self.root / "new"
        proc = subprocess.run([str(source / "scripts/new-paper.sh"), "--yes", "--no-build",
                               "--no-git", "--keywords", "only-one", str(destination)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('paper-keywords = ("only-one",)', (destination / "config.typ").read_text())
        self.assertTrue(all(not (destination / name).exists() for name in artifacts))
        shared = destination / ".agents/skills"
        self.assertTrue(shared.is_symlink())
        self.assertEqual(shared.readlink().as_posix(), "../.claude/skills")
        expected = {"copy-edit", "fix-verify", "declare-number", "new-figure"}
        self.assertEqual({p.name for p in shared.iterdir()}, expected)
        for name in expected:
            skill = shared / name / "SKILL.md"
            canonical = destination / ".claude/skills" / name / "SKILL.md"
            self.assertEqual(skill.resolve(), canonical.resolve())
            original = ROOT / ".claude/skills" / name / "SKILL.md"
            self.assertEqual(skill.read_bytes(), original.read_bytes())

    def test_trace_nonfinite_input_still_has_structured_error(self):
        self.put("stats.json", '{"values": {"x": {"value": NaN}}}')
        with self.assertRaisesRegex(ValueError, "NaN"):
            trace.inspect("x", self.root)

    def test_edit_guard_preserves_negative_single_digit(self):
        self.assertEqual(prose_edit_guard._nums("-3 and +2"), ["-3", "2"])


def run_cases() -> bool:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Hardening)
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
