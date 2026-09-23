"""project.toml: the extension hooks a paper declares instead of editing the
scaffold (docs/hooks.md).

Every case writes its own project.toml into a temporary directory; nothing
here reads the manuscript's, which belongs to the paper.
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

import project_hooks as ph


class Tmp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, text: str) -> None:
        (self.root / "project.toml").write_text("schema_version = 1\n" + text)

    def main(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = ph.main(list(argv), root=self.root)
        return rc, out.getvalue()


class Stages(Tmp):
    def test_no_project_toml_declares_nothing(self):
        project = ph.load(self.root)
        self.assertFalse(project.declared)
        self.assertEqual(project.stages, {g: () for g in ph.GATES})
        self.assertTrue(project.bib_audit_require_complete)
        for gate in ph.GATES:
            self.assertEqual(self.main("stages", gate), (0, ""))
        self.assertEqual(self.main("bib-audit-args"), (0, "--require-complete\n"))

    def test_every_stage_runs_and_a_failure_fails_the_gate(self):
        self.write('[[stages.verify]]\nname = "first"\nrun = "echo one; exit 3"\n'
                   '[[stages.verify]]\nname = "second"\nrun = "echo two > ran"\n')
        rc, out = self.main("stages", "verify")
        self.assertEqual(rc, 1)
        self.assertIn("=== first (project.toml) ===", out)
        self.assertIn("=== second (project.toml) ===", out)
        self.assertIn("'first' failed (exit 3)", out)
        # Run from the manuscript root, after the failure.
        self.assertEqual((self.root / "ran").read_text(), "two\n")

    def test_passing_stages_pass_and_other_gates_stay_empty(self):
        self.write('[stages]\ncheck = [{name = "ok", run = "test -n \\"$PAPER_ROOT\\""}]\n')
        rc, out = self.main("stages", "check")
        self.assertEqual(rc, 0)
        self.assertIn("=== ok (project.toml) ===", out)
        self.assertEqual(self.main("stages", "verify"), (0, ""))

    def test_mistakes_are_errors_not_silence(self):
        for text in ('[[stages.verfiy]]\nname = "x"\nrun = "true"\n',
                     '[[stages.verify]]\nname = "x"\n',
                     '[[stages.verify]]\nname = "x"\nrun = "true"\nextra = 1\n',
                     '[[stages.verify]]\nname = "x"\nrun = "true"\n'
                     '[[stages.verify]]\nname = "x"\nrun = "true"\n',
                     '[unknown]\n',
                     '[preflight]\nbib_audit_require_complete = "no"\n'):
            with self.subTest(text=text):
                self.write(text)
                with self.assertRaises(ValueError):
                    ph.load(self.root)
                rc, out = self.main("stages", "verify")
                self.assertEqual(rc, 2)
                self.assertIn("=== project.toml ===", out)
        (self.root / "project.toml").write_text("schema_version = 2\n")
        with self.assertRaises(ValueError):
            ph.load(self.root)

    def test_preflight_may_relax_the_bibliography_audit(self):
        self.write("[preflight]\nbib_audit_require_complete = false\n")
        self.assertEqual(self.main("bib-audit-args"), (0, "\n"))
        rc, out = self.main("show")
        self.assertIn("without --require-complete", out)

    def test_show_lists_each_stage(self):
        self.write('[[stages.preflight]]\nname = "figure qc"\nrun = "just check-figure-qc"\n')
        rc, out = self.main("show")
        self.assertEqual(rc, 0)
        self.assertIn("preflight  figure qc: just check-figure-qc", out)


class Wiring(unittest.TestCase):
    """The justfile calls the hooks at each gate; a refactor that drops one
    would leave a project's stage silently unrun."""

    def test_each_gate_runs_its_stages(self):
        text = (ROOT / "justfile").read_text()
        for gate in ph.GATES:
            self.assertIn(f"tools/project_hooks.py stages {gate}", text, gate)
        self.assertIn("tools/project_hooks.py bib-audit-args", text)

    def test_upgrade_plan_never_offers_the_projects_hook_files(self):
        import upgrade_plan
        for path in ("project.toml", "project.just", "hooks/fix_tables.py",
                     "hooks/word/filter.lua"):
            self.assertTrue(upgrade_plan.project_owned(path), path)


def run_cases() -> bool:
    suite = unittest.TestSuite()
    for case in (Stages, Wiring):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
