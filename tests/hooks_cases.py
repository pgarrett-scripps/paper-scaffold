"""project.toml: the extension hooks a paper declares instead of editing the
scaffold (docs/hooks.md).

Every case writes its own project.toml into a temporary directory; nothing
here reads the manuscript's, which belongs to the paper.
"""
from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
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


class Sources(Tmp):
    """[sources] typst: extra hand-written files for fmt and prose-check."""

    def test_defaults_skip_missing_and_declared_files_follow(self):
        for name in ("paper.typ", "reviewer_response.typ"):
            (self.root / name).write_text("Text.\n")
        self.write('[sources]\ntypst = ["reviewer_response.typ", "paper.typ"]\n')
        self.assertEqual(ph.typst_sources(self.root, ("paper.typ", "cover-letter.typ")),
                         ["paper.typ", "reviewer_response.typ"])
        rc, out = self.main("typst-sources", "paper.typ", "cover-letter.typ")
        self.assertEqual((rc, out), (0, "paper.typ\nreviewer_response.typ\n"))

    def test_no_declaration_is_the_justfile_list(self):
        (self.root / "paper.typ").write_text("Text.\n")
        self.assertEqual(self.main("typst-sources", "paper.typ", "si-body.typ"),
                         (0, "paper.typ\n"))

    def test_a_declared_file_that_is_missing_is_an_error(self):
        self.write('[sources]\ntypst = ["reviewer_respnse.typ"]\n')
        with self.assertRaisesRegex(ValueError, "reviewer_respnse.typ"):
            ph.typst_sources(self.root)
        self.assertEqual(self.main("typst-sources")[0], 2)

    def test_paths_must_be_project_relative_typst(self):
        for bad in ('"/abs/x.typ"', '"../x.typ"', '"notes.md"', '""', "3"):
            with self.subTest(bad=bad):
                self.write(f"[sources]\ntypst = [{bad}]\n")
                with self.assertRaises(ValueError):
                    ph.load(self.root)

    def test_prose_check_reads_the_declared_files(self):
        import prose_check
        (self.root / "reviewer_response.typ").write_text(
            'We thank the reviewer. #todo("answer point 3")\n')
        self.write('[sources]\ntypst = ["reviewer_response.typ"]\n')
        extra, findings = prose_check.project_sources(self.root)
        self.assertEqual((list(extra), findings), (["reviewer_response.typ"], []))
        todos = prose_check.check_todos(extra)
        self.assertEqual([(f.rule, f.where) for f in todos],
                         [("unresolved-todo", "reviewer_response.typ")])
        self.write('[sources]\ntypst = ["gone.typ"]\n')
        extra, findings = prose_check.project_sources(self.root)
        self.assertEqual((extra, [f.rule for f in findings]), ({}, ["project-config"]))


LUA = '''function Str(el)
  if el.text == "Main" then return pandoc.Str("MAINFILTERED") end
end
'''
# Logs its phase and whether any keepNext exists yet: none before pagination
# (which keeps the bold run-in label with what follows), some after. The after
# step then puts a <w:jc> FIRST in that paragraph's properties, out of schema
# order, for the export to put back.
STEP = '''import sys, zipfile
from pathlib import Path
phase, docx = sys.argv[0].rsplit("_", 1)[1][:-3], Path(sys.argv[1])
with zipfile.ZipFile(docx) as z:
    parts = {n: z.read(n) for n in z.namelist()}
xml = parts["word/document.xml"].decode()
with open("steps.log", "a") as log:
    log.write(f"{phase} {'<w:keepNext' in xml}\\n")
if phase == "after":
    import word_xml  # tools/ is on the path
    start = xml.rindex("<w:pPr>", 0, xml.index("<w:keepNext")) + len("<w:pPr>")
    xml = xml[:start] + '<w:jc w:val="center"/>' + xml[start:]
    parts["word/document.xml"] = xml.encode()
    with zipfile.ZipFile(docx, "w") as z:
        for n, data in parts.items():
            z.writestr(n, data)
'''


class Word(Tmp):
    """[word]: Lua filters and Python steps in the Word export."""

    def setUp(self):
        super().setUp()
        (self.root / "hooks").mkdir()
        (self.root / "hooks/mark.lua").write_text(LUA)
        for phase in ("before", "after"):
            (self.root / f"hooks/step_{phase}.py").write_text(STEP)
        (self.root / "hooks/widths.json").write_text("{}")
        self.full = ('[word]\nlua_filters = ["hooks/mark.lua"]\n'
                     'before_pagination = ["hooks/step_before.py"]\n'
                     'after_pagination = ["hooks/step_after.py"]\n'
                     'inputs = ["hooks/widths.json"]\n')

    def export(self) -> int:
        import export_docx
        from unittest.mock import patch
        source = self.root / "paper.resolved.typ"
        source.write_text("= Main\n\n*Run-in label.*\n\nMore prose.\n")
        out = io.StringIO()
        with patch.multiple(export_docx, ROOT=self.root, SRC=source,
                            OUT=self.root / "paper.docx"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            return export_docx.main()

    def test_filters_and_steps_run_in_their_places(self):
        import zipfile
        self.write(self.full)
        self.assertEqual(self.export(), 0)
        self.assertEqual((self.root / "steps.log").read_text(),
                         "before False\nafter True\n")
        with zipfile.ZipFile(self.root / "paper.docx") as z:
            xml = z.read("word/document.xml").decode()
        self.assertIn("MAINFILTERED", xml)
        # Property order restored: the <w:jc> the step put first is back
        # after <w:keepNext>, where the schema wants it.
        start = xml.rindex("<w:pPr>", 0, xml.index("<w:keepNext"))
        ppr = xml[start:xml.index("</w:pPr>", start)]
        self.assertIn("<w:jc ", ppr)
        self.assertLess(ppr.index("<w:keepNext"), ppr.index("<w:jc "))

    def test_no_word_table_is_the_plain_export(self):
        self.assertEqual(self.export(), 0)
        self.assertFalse((self.root / "steps.log").exists())

    def test_a_failing_step_fails_the_export(self):
        (self.root / "hooks/step_before.py").write_text("raise SystemExit(4)\n")
        self.write(self.full)
        self.assertEqual(self.export(), 1)

    def test_word_files_are_build_inputs(self):
        from build_state import snapshot
        self.assertEqual(ph.build_inputs(self.root), [])
        self.write(self.full)
        self.assertEqual(ph.build_inputs(self.root),
                         ["project.toml", "hooks/mark.lua", "hooks/step_before.py",
                          "hooks/step_after.py", "hooks/widths.json"])
        before = snapshot(self.root)
        for name in ph.build_inputs(self.root):
            self.assertIsNotNone(before.get(name), name)
        (self.root / "hooks/widths.json").write_text('{"table": 2}')
        self.assertNotEqual(before, snapshot(self.root))
        (self.root / "hooks/widths.json").unlink()
        with self.assertRaisesRegex(ValueError, "widths.json"):
            ph.build_inputs(self.root)

    def test_word_paths_are_checked(self):
        for bad in ('lua_filters = ["hooks/mark.py"]', 'after_pagination = ["x.lua"]',
                    'before_pagination = ["/abs/x.py"]', 'unknown = []'):
            with self.subTest(bad=bad):
                self.write(f"[word]\n{bad}\n")
                with self.assertRaises(ValueError):
                    ph.load(self.root)


class WordStyle(Tmp):
    """[word.style] and [word] reference: the Word export's styles."""

    def test_settings_are_validated(self):
        self.write('[word.style]\nfont = "Times New Roman"\nfont_size = 12\n'
                   'line_spacing = 2.0\nmargins = "1in"\ntitle_size = 20\n'
                   'title_align = "left"\ntitle_color = "000000"\n'
                   'heading_color = "0f4761"\n')
        style = ph.load(self.root).word.style
        self.assertEqual(style["heading_color"], "0F4761")
        self.assertEqual(style["margins"], "1in")
        for bad in ('fontsize = 12', 'font_size = "12"', 'font_size = 12.3',
                    'font_size = true', 'line_spacing = 5', 'margins = "1 inch"',
                    'margins = "10in"', 'title_align = "right"',
                    'heading_color = "blue"', 'font = ""'):
            with self.subTest(bad=bad):
                self.write(f"[word.style]\n{bad}\n")
                with self.assertRaises(ValueError):
                    ph.load(self.root)

    def test_reference_and_style_are_exclusive(self):
        self.write('[word]\nreference = "word/custom.docx"\n[word.style]\nfont_size = 11\n')
        with self.assertRaisesRegex(ValueError, "exclusive"):
            ph.load(self.root)
        self.write('[word]\nreference = "word/custom.dotx"\n')
        with self.assertRaises(ValueError):
            ph.load(self.root)

    def test_reference_is_a_build_input(self):
        self.write('[word]\nreference = "word/custom.docx"\n')
        with self.assertRaisesRegex(ValueError, "custom.docx"):
            ph.build_inputs(self.root)
        (self.root / "word").mkdir()
        (self.root / "word/custom.docx").write_bytes(b"x")
        self.assertEqual(ph.build_inputs(self.root), ["project.toml", "word/custom.docx"])

    def test_a_settings_change_makes_the_word_file_stale(self):
        from build_state import snapshot
        self.write('[word.style]\nfont_size = 12\n')
        before = snapshot(self.root)
        self.write('[word.style]\nfont_size = 11\n')
        self.assertNotEqual(before, snapshot(self.root))

    def test_a_left_over_template_is_an_error(self):
        (self.root / "word").mkdir()
        (self.root / "word/paper-reference.docx").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "no longer read"):
            ph.build_inputs(self.root)
        self.write('[word]\nreference = "word/paper-reference.docx"\n')
        self.assertEqual(ph.build_inputs(self.root),
                         ["project.toml", "word/paper-reference.docx"])

    def test_the_export_uses_the_settings(self):
        import zipfile
        import export_docx
        from unittest.mock import patch
        self.write('[word.style]\ntitle_align = "left"\nheading_color = "123456"\n')
        source = self.root / "paper.resolved.typ"
        source.write_text("= Main\n\nProse.\n")
        out = io.StringIO()
        with patch.multiple(export_docx, ROOT=self.root, SRC=source,
                            OUT=self.root / "paper.docx"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.assertEqual(export_docx.main(), 0)
        with zipfile.ZipFile(self.root / "paper.docx") as z:
            styles = z.read("word/styles.xml").decode()
        heading = styles[styles.index('w:styleId="Heading1"'):]
        self.assertIn('<w:color w:val="123456"', heading[:heading.index("</w:style>")])


class Bibliography(Tmp):
    """[bibliography] single: the SI cites the main list's keys on purpose."""

    ALEXANDRIA = '#show: alexandria(prefix: "si-", read: p => read(p))\n= Intro\n'
    SI_LIST = '= SI\nAs shown @smith2020.\n#bibliographyx("references.bib", prefix: "si-")\n'

    def setUp(self):
        super().setUp()
        (self.root / "references.bib").write_text(
            "@article{smith2020, title={T}, author={Smith, A}, year={2020}}\n")

    def findings(self):
        import prose_check
        return [f.rule for f in prose_check.check_si_bibliography(self.root)]

    def test_default_keeps_the_si_routing_check(self):
        (self.root / "paper.typ").write_text(self.ALEXANDRIA)
        (self.root / "si-body.typ").write_text(self.SI_LIST)
        self.assertEqual(self.findings(), ["misrouted-citation"])

    def test_single_list_accepts_bare_keys_in_the_si(self):
        (self.root / "paper.typ").write_text("= Intro\n#bibliography(\"references.bib\")\n")
        (self.root / "si-body.typ").write_text("= SI\nAs shown @smith2020.\n")
        self.write("[bibliography]\nsingle = true\n")
        self.assertEqual(self.findings(), [])
        self.assertIn("one reference list", "\n".join(ph.describe(ph.load(self.root))))

    def test_single_list_with_a_left_over_si_list_is_an_error(self):
        (self.root / "paper.typ").write_text(self.ALEXANDRIA)
        (self.root / "si-body.typ").write_text(self.SI_LIST)
        self.write("[bibliography]\nsingle = true\n")
        self.assertEqual(self.findings(), ["si-bibliography-mode"])

    def test_single_must_be_a_boolean(self):
        for bad in ('single = "yes"', "one = true"):
            with self.subTest(bad=bad):
                self.write(f"[bibliography]\n{bad}\n")
                with self.assertRaises(ValueError):
                    ph.load(self.root)


class Wiring(unittest.TestCase):
    """The justfile calls the hooks at each gate; a refactor that drops one
    would leave a project's stage silently unrun."""

    def test_each_gate_runs_its_stages(self):
        text = (ROOT / "justfile").read_text()
        for gate in ph.GATES:
            self.assertIn(f"tools/project_hooks.py stages {gate}", text, gate)
        self.assertIn("tools/project_hooks.py bib-audit-args", text)
        # fmt and fmt-check both format the declared sources.
        self.assertEqual(text.count("project_hooks.py typst-sources {{typst_sources}}"), 2)

    def test_upgrade_plan_never_offers_the_projects_hook_files(self):
        import upgrade_plan
        for path in ("project.toml", "project.just", "hooks/fix_tables.py",
                     "hooks/word/filter.lua"):
            self.assertTrue(upgrade_plan.project_owned(path), path)


@unittest.skipUnless(shutil.which("just"), "just is not installed")
class ProjectJust(Tmp):
    """project.just adds recipes; it can never replace one."""

    def just(self, *argv: str) -> subprocess.CompletedProcess:
        shutil.copyfile(ROOT / "justfile", self.root / "justfile")
        return subprocess.run(["just", "--justfile", str(self.root / "justfile"),
                               "--working-directory", str(self.root), *argv],
                              capture_output=True, text=True)

    def test_absent_file_imports_nothing(self):
        self.assertEqual(self.just("--summary").returncode, 0)

    def test_project_recipes_are_listed_and_run(self):
        (self.root / "project.just").write_text(
            "# Package the source data for the journal\n"
            "source-data:\n  @echo packaged > packaged.txt\n")
        listed = self.just("--list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("source-data", listed.stdout)
        self.assertIn("Package the source data", listed.stdout)
        self.assertEqual(self.just("source-data").returncode, 0)
        self.assertEqual((self.root / "packaged.txt").read_text(), "packaged\n")

    def test_a_scaffold_recipe_cannot_be_overridden(self):
        (self.root / "project.just").write_text("verify:\n  @true\n")
        done = self.just("--summary")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("verify", done.stderr)


def run_cases() -> bool:
    suite = unittest.TestSuite()
    for case in (Stages, Sources, Word, WordStyle, Bibliography, Wiring, ProjectJust):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
