"""Regression cases for the contracts that a green example did not exercise."""
from __future__ import annotations
import os

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
import pdf_outline
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

    @unittest.skipUnless(shutil.which("typst"), "typst not installed")
    def test_pdf_opens_with_outline_by_incremental_update(self):
        for body, want in (("= One\nText.\n= Two\nMore.", True), ("No headings.", False)):
            with self.subTest(outline=want):
                src = self.put("doc.typ", body)
                pdf = self.root / "doc.pdf"
                subprocess.run(["typst", "compile", str(src), str(pdf)], check=True)
                before = pdf.read_bytes()
                self.assertEqual(pdf_outline.open_with_outline(pdf), want)
                after = pdf.read_bytes()
                # The original bytes survive untouched; only an update is appended.
                self.assertTrue(after.startswith(before))
                self.assertEqual(b"/PageMode /UseOutlines" in after, want)
                self.assertFalse(pdf_outline.open_with_outline(pdf))  # idempotent
                if want:
                    xref = int(after.rsplit(b"startxref", 1)[1].split()[0])
                    self.assertTrue(after[xref:].startswith(b"xref"))
                    entry = after[xref:].split(b"\n")[2]
                    obj = int(entry.split()[0])
                    self.assertRegex(after[obj:obj + 20], rb"^\d+ 0 obj")

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

    def test_source_index_follows_generated_tables(self):
        # A generated SI table calls #s() for its own numbers; the index must
        # see those calls through tbl(), or check-stats calls them unused and
        # a regenerated table never marks the PDF stale.
        self.put("paper.typ", '#include "si-body.typ"')
        self.put("si-body.typ", '#figure(tbl("tbl.a")) <tbl:a>\n#tbl("tbl.gone") #tbl("fig.b")')
        self.put("si/a.typ", '#table([#s("from-table")])')
        self.put("figures/b.typ", '#s("not-a-table")')
        self.put("assets.json", json.dumps({"values": {
            "tbl.a": {"path": "si/a.typ", "kind": "table"},
            "tbl.gone": {"path": "si/gone.typ", "kind": "table"},
            "fig.b": {"path": "figures/b.typ", "kind": "figure"}}}))
        self.assertIn("si/a.typ", manuscript_sources.source_files(self.root))
        ids = {u["id"] for u in manuscript_sources.usages(self.root)}
        self.assertIn("from-table", ids)
        self.assertNotIn("not-a-table", ids)
        self.put("assets.json", "{not json")
        self.assertNotIn("si/a.typ", manuscript_sources.source_files(self.root))

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

    def test_edit_guard_ignores_import_paths_and_si_prefix_moves(self):
        # Adding the SI's own list adds `#import "@preview/alexandria:0.2.0"`
        # and rewrites SI citations @key -> @si-key; neither is a prose change.
        self.put("paper.typ", '#show: alexandria(prefix: "si-", read: p => read(p))\n'
                              '= Results\nSee @a2020.\n')
        si = self.put("si-body.typ", "= Details\nAs @b2020 found.\n")
        with patch.object(prose_edit_guard, "ROOT", self.root), patch.object(
                prose_edit_guard, "SNAP_DIR", self.root / ".edit-guard"), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            prose_edit_guard.snapshot("test")
            si.write_text('#import "@preview/alexandria:0.2.0": load-bibliography\n'
                          "= Details\nAs @si-b2020 found.\n"
                          '#bibliographyx("references.bib", prefix: "si-")\n')
            self.assertEqual(prose_edit_guard.check("test"), 0, out.getvalue())
            self.assertIn("moved between the main and the SI", out.getvalue())
            # A citation that is not the same work under the prefix still fails.
            si.write_text('#import "@preview/alexandria:0.2.0": load-bibliography\n'
                          "= Details\nAs @si-c2020 found.\n"
                          '#bibliographyx("references.bib", prefix: "si-")\n')
            self.assertEqual(prose_edit_guard.check("test"), 1)
            # A number in the prose, unlike one in an import path, still counts.
            si.write_text("= Details\nAs @b2020 found in 0.2.0.\n")
            self.assertEqual(prose_edit_guard.check("test"), 1)

    def test_edit_guard_ignores_numbers_in_code_directives(self):
        # 3.24.2's SI guard block read as an invented `0` (koth-lfq).
        si = self.put("si-body.typ", "= Details\nAs found.\n")
        with patch.object(prose_edit_guard, "ROOT", self.root), patch.object(
                prose_edit_guard, "SNAP_DIR", self.root / ".edit-guard"), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            prose_edit_guard.snapshot("test")
            si.write_text("#let bibliographyx(\n  path,\n) = {\n  context {\n"
                          "    if b.len() > 0 { render(b) }\n  }\n}\n"
                          "#set text(size: 9pt)\n= Details\nAs found.\n")
            self.assertEqual(prose_edit_guard.check("test"), 0, out.getvalue())
            # A #let bound to content is prose: its numbers still count.
            si.write_text("#let note = [\n  Seen in 12 runs.\n]\n= Details\nAs found.\n")
            self.assertEqual(prose_edit_guard.check("test"), 1)

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
                     "tools/manifest_validation.py", "tools/atomic_io.py",
                     "tools/hashcache.py", "tools/paths.py", "tools/evidence.py"):
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
                               "origin": {"by": "hand", "note": "protocol",
                                          "source": "doi:10.1234/protocol"}}}}
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
        # The whole scaffold as git sees it: new-paper.sh runs `paper sync`
        # from the copy's package source and data (docs/package.md).
        listed = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        for name in filter(None, listed.stdout.split("\0")):
            if not (ROOT / name).exists() and not (ROOT / name).is_symlink():
                continue  # deleted in the working tree
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target, follow_symlinks=False)
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
        self.assertEqual(shared.readlink().as_posix(),
                         os.path.relpath(source / "plugins/paper/skills", destination / ".agents"))
        expected = {"copy-edit", "fix-verify", "declare-number", "new-figure",
                    "cover-letter", "reviewer-response",
                    "claim-audit", "methods-vs-code", "figure-review", "peer-review",
                    "review-all", "prose-review", "readability-review", "intro-review",
                    "literature-check", "story-review", "slide-review"}
        self.assertEqual({p.name for p in shared.iterdir()}, expected)
        for name in expected:
            skill = shared / name / "SKILL.md"
            canonical = source / "plugins/paper/skills" / name / "SKILL.md"
            self.assertEqual(skill.resolve(), canonical.resolve())
            original = ROOT / "plugins/paper/skills" / name / "SKILL.md"
            self.assertEqual(skill.read_bytes(), original.read_bytes())

    def test_trace_nonfinite_input_still_has_structured_error(self):
        self.put("stats.json", '{"values": {"x": {"value": NaN}}}')
        with self.assertRaisesRegex(ValueError, "NaN"):
            trace.inspect("x", self.root)

    def test_edit_guard_preserves_negative_single_digit(self):
        self.assertEqual(prose_edit_guard._nums("-3 and +2"), ["-3", "2"])

    @unittest.skipUnless(shutil.which("just") and shutil.which("typstyle"),
                         "just or typstyle not installed")
    def test_fmt_check_skips_an_absent_optional_source(self):
        # typst_sources lists cover-letter.typ; a project without one must not
        # fail fmt-check on the missing path (exclusionms, koth-lfq deleted the
        # entry locally), while a present file is still checked.
        shutil.copy(ROOT / "justfile", self.root / "justfile")
        # The file list comes from tools/project_hooks.py (project.toml's
        # [sources] typst is appended; none here).
        shutil.copytree(ROOT / "tools", self.root / "tools",
                        ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("config.typ", "paper.typ", "si-body.typ", "code.typ"):
            self.put(name, "Text.\n")
        def run():
            return subprocess.run(["just", "fmt-check"], cwd=self.root,
                                  capture_output=True, text=True, check=False)
        proc = run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.put("paper.typ", "#let   x=1\n")
        self.assertNotEqual(run().returncode, 0)

    @unittest.skipUnless(shutil.which("just"), "just not installed")
    def test_all_skips_narration_without_the_voice_model(self):
        # audio/ is tracked but its voice model is not, so a fresh clone must
        # get the PDF and Word from `just all` rather than die in _audio-check.
        # Runs the condition recipe `all` calls, not `all` itself, so a project
        # that adds steps to `all` keeps this test.
        text = (ROOT / "justfile").read_text()
        self.assertIn("just _narrate-if-voice", text)
        self.put("justfile", "set allow-duplicate-recipes\n" + text +
                 "\naudiobook-all:\n  @echo NARRATED\n")
        self.put("audio/config.py", 'VOICE_NAME = "v"\n')
        def run():
            return subprocess.run(["just", "_narrate-if-voice"], cwd=self.root,
                                  capture_output=True, text=True, check=False)
        proc = run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("no voice model", proc.stdout)
        self.assertNotIn("NARRATED", proc.stdout)
        self.put("audio/models/v.onnx", "")
        proc = run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("NARRATED", proc.stdout)

    @unittest.skipUnless(shutil.which("just") and shutil.which("git"),
                         "just or git not installed")
    def test_version_tree_state_is_scoped_to_the_manuscript(self):
        # A manuscript inside a code repository: a change to the code must not
        # report the paper's tree dirty, and a change to the paper must.
        paper = self.root / "paper"
        paper.mkdir()
        shutil.copy(ROOT / "justfile", paper / "justfile")
        self.put("paper/pyproject.toml", 'version = "0"\n')
        self.put("src/code.py", "x = 1\n")
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        for args in (["init", "-q"], ["add", "."], ["commit", "-qm", "init"]):
            subprocess.run(git + args, cwd=self.root, check=True,
                           capture_output=True)
        self.put("src/code.py", "x = 2\n")
        def tree():
            out = subprocess.run(["just", "version"], cwd=paper, check=True,
                                 capture_output=True, text=True).stdout
            return next(line for line in out.splitlines() if "tree" in line)
        self.assertIn("clean under paper/", tree())
        self.put("paper/pyproject.toml", 'version = "1"\n')
        self.assertIn("1 uncommitted change(s) under paper/", tree())


def run_cases() -> bool:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Hardening)
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
