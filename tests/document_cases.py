"""Integration coverage for independent chapter builds and honest scoping."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from document_project import load_project
from document_build import build, status, saved_metrics
from document_check import check
from manuscript_sources import source_files


MANIFEST = '''schema_version = 1
default_document = "thesis"
[parts.one]
source = "chapters/one.typ"
[parts.two]
source = "chapters/two.typ"
[documents.thesis]
entrypoint = "thesis.typ"
output = "build/thesis.pdf"
parts = ["one", "two"]
[documents.one]
entrypoint = "one.typ"
output = "build/one.pdf"
parts = ["one"]
[documents.two]
entrypoint = "two.typ"
output = "build/two.pdf"
parts = ["two"]
'''


class Documents(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("manuscript.toml", MANIFEST)
        self.write("thesis.typ", '#include "chapters/one.typ"\n#include "chapters/two.typ"\n')
        for name, prose in (("one", "Alpha beta gamma."), ("two", "Delta epsilon zeta.")):
            self.write(f"{name}.typ", f'#include "chapters/{name}.typ"\n')
            self.write(f"chapters/{name}.typ", f'''Outside count.
// >>> BODY START
{prose}
// <<< BODY END
Outside count too.
''')
        self.project = load_project(self.root)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def test_validation(self):
        for manifest in (MANIFEST.replace('build/one.pdf', '../escape.pdf'),
                         MANIFEST.replace('parts = ["one"]', 'parts = ["missing"]'),
                         MANIFEST.replace('build/one.pdf', 'build/two.pdf'),
                         MANIFEST.replace('schema_version = 1', 'schema_version = 2')):
            self.write("manuscript.toml", manifest)
            with self.assertRaises(ValueError):
                load_project(self.root)

    def test_scope_and_nested_prose(self):
        self.write("chapters/one.typ", '// >>> BODY START\n#include "nested/body.typ"\n// <<< BODY END\n')
        self.write("chapters/nested/body.typ", 'Visible prose.\n// @fake\n')
        self.assertIn("Visible prose", self.project.prose(self.project.parts["one"]))
        self.assertIn("chapters/nested/body.typ", source_files(self.root))
        self.write("chapters/nested/body.typ", '#include "../one.typ"')
        with self.assertRaisesRegex(ValueError, "cyclic"):
            self.project.prose(self.project.parts["one"])
        self.write("chapters/one.typ", '// >>> BODY START\n#include variable\n// <<< BODY END\n')
        with self.assertRaisesRegex(ValueError, "dynamic"):
            self.project.prose(self.project.parts["one"])

    def test_part_list_must_match_includes(self):
        self.write("one.typ", '#include "chapters/two.typ"')
        with self.assertRaisesRegex(ValueError, "declared parts"):
            self.project.sources(self.project.documents["one"])

    def test_edit_guard_is_scoped_to_document(self):
        import prose_edit_guard as guard
        with (patch.object(guard, "ROOT", self.root),
              patch.object(guard, "SNAP_DIR", self.root / ".edit-guard"),
              patch.object(guard, "DOCUMENT", "one"), redirect_stdout(io.StringIO())):
            guard.snapshot("chapter")
            path = self.root / "chapters/two.typ"
            path.write_text(path.read_text().replace("Delta", "Added 987"))
            self.assertEqual(guard.check("chapter"), 0)
            path = self.root / "chapters/one.typ"
            path.write_text(path.read_text().replace("Alpha", "Added 987"))
            self.assertEqual(guard.check("chapter"), 1)

    def test_prefixed_bibliography_ignores_comment_citations(self):
        self.write("refs.bib", '@article{used, title={First}, year={2020}}\n'
                              '@article{unused, title={Second}, year={2020}}')
        self.write("manuscript.toml", MANIFEST.replace('source = "chapters/one.typ"',
            'source = "chapters/one.typ"\nbibliography = "refs.bib"\ncitation_prefix = "one-"'))
        self.write("chapters/one.typ", '// >>> BODY START\nText @one-used.\n'
                                     '// @one-unused\n// <<< BODY END\n')
        project = load_project(self.root)
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(check(project, project.documents["one"]), 0)
        text = out.getvalue()
        self.assertIn("unused is in the bibliography but never cited", text)
        self.assertNotIn("refs.bib: used is in the bibliography but never cited", text)

    def test_nested_prose_is_checked(self):
        self.write("chapters/one.typ", '// >>> BODY START\n#include "nested.typ"\n// <<< BODY END\n')
        self.write("chapters/nested.typ", "We analyse samples.")
        with redirect_stdout(io.StringIO()) as out:
            result = check(self.project, self.project.documents["one"])
        self.assertEqual(result, 1)
        self.assertIn("analyse", out.getvalue())

    @unittest.skipUnless(shutil.which("typst"), "Typst needed for chapter integration")
    def test_build_counts_and_independent_staleness(self):
        reports = {name: build(self.project, doc) for name, doc in self.project.documents.items()}
        self.assertEqual(reports["one"]["words"], 3)
        self.assertEqual(reports["thesis"]["words"], 6)
        self.assertEqual([p["id"] for p in reports["thesis"]["parts"]], ["one", "two"])
        path = self.root / "chapters/two.typ"
        path.write_text(path.read_text().replace("Delta", "Theta"))
        self.assertEqual(status(self.project, self.project.documents["one"]), "current")
        for name in ("two", "thesis"):
            self.assertEqual(status(self.project, self.project.documents[name]), "stale")
            with self.assertRaisesRegex(ValueError, "stale"):
                saved_metrics(self.project, self.project.documents[name])
        (self.root / "build/one.pdf").write_bytes(b"replaced")
        self.assertEqual(status(self.project, self.project.documents["one"]), "replaced")

    @unittest.skipUnless(shutil.which("typst"), "Typst needed for chapter integration")
    def test_failed_or_concurrent_build_preserves_output(self):
        doc = self.project.documents["one"]
        build(self.project, doc)
        output = self.root / doc.output
        good = output.read_bytes()
        path = self.root / "chapters/one.typ"
        original = path.read_text()
        path.write_text(original.replace("Alpha", "#unknown-function() Alpha"))
        with self.assertRaises(subprocess.CalledProcessError):
            build(self.project, doc)
        self.assertEqual(output.read_bytes(), good)
        path.write_text(original)
        from document_build import metrics as real_metrics

        def edit_during_metrics(*args):
            report = real_metrics(*args)
            path.write_text(original.replace("Alpha", "Changed"))
            return report

        with patch("document_build.metrics", side_effect=edit_during_metrics):
            with self.assertRaisesRegex(ValueError, "sources changed"):
                build(self.project, doc)
        self.assertEqual(output.read_bytes(), good)

    def test_parallel_build_reaps_its_children(self):
        # The compile and the count query run as concurrent children
        # (dissertation). A build that stops early must not leave one running.
        from document_build import running
        with self.assertRaises(RuntimeError):
            with running([sys.executable, "-c", "import time; time.sleep(60)"]) as proc:
                raise RuntimeError("build stopped")
        self.assertIsNotNone(proc.poll())

    @unittest.skipUnless(shutil.which("typst"), "Typst needed for chapter integration")
    def test_edit_during_parallel_scoring_is_caught(self):
        # Readability is scored while typst compiles; an edit made then is a
        # concurrent edit, and the last good output survives it.
        doc = self.project.documents["one"]
        build(self.project, doc)
        output = self.root / doc.output
        good = output.read_bytes()
        path = self.root / "chapters/one.typ"
        original = path.read_text()
        from document_build import readability_scores as real_scores

        def edit_while_scoring(*args):
            scores = real_scores(*args)
            path.write_text(original.replace("Alpha", "Changed"))
            return scores

        with patch("document_build.readability_scores", side_effect=edit_while_scoring):
            with self.assertRaisesRegex(ValueError, "sources changed"):
                build(self.project, doc)
        self.assertEqual(output.read_bytes(), good)

    @unittest.skipUnless(shutil.which("typst"), "Typst needed for chapter integration")
    def test_count_order_and_duplicate_include(self):
        for src in ('#include "chapters/two.typ"\n#include "chapters/one.typ"',
                    '#include "chapters/one.typ"\n#include "chapters/one.typ"\n#include "chapters/two.typ"'):
            self.write("thesis.typ", src)
            with self.assertRaisesRegex(ValueError, "manifest order"):
                build(self.project, self.project.documents["thesis"])

    @unittest.skipUnless(shutil.which("typst"), "Typst needed for chapter integration")
    def test_nested_count_exemptions_and_data_dependencies(self):
        self.write("chapters/one.typ", '''// >>> BODY START
== Heading
#include "nested.typ"
#figure(rect(), caption: [Many excluded caption words.])
$ x + y $
```text
Excluded block code
```
// <<< BODY END
''')
        self.write("chapters/nested.typ", 'Alpha `beta` gamma.\n#let data = read("data.txt")\n')
        self.write("chapters/data.txt", "value one")
        doc = self.project.documents["one"]
        result = build(self.project, doc)
        self.assertEqual(result["words"], 4)
        self.write("chapters/data.txt", "value two")
        self.assertEqual(status(self.project, doc), "stale")
        # Removing a dependency is legitimate, not a concurrent edit.
        self.write("chapters/nested.typ", 'Alpha `beta` gamma.\n')
        build(self.project, doc)
        self.write("chapters/data.txt", "value three")
        self.assertEqual(status(self.project, doc), "current")


    def test_covering_checks_each_part_once(self):
        from document_check import covering
        self.assertEqual([d.id for d in covering(self.project)], ["thesis"])
        self.write("manuscript.toml", MANIFEST.replace('parts = ["one", "two"]',
                                                       'parts = ["one"]'))
        project = load_project(self.root)
        self.assertEqual([d.id for d in covering(project)], ["thesis", "two"])

    def stock(self, tool, *args):
        env = {**__import__("os").environ, "PAPER_ROOT": str(self.root)}
        return subprocess.run([sys.executable, str(ROOT / "tools" / tool), *args],
                              cwd=self.root, env=env, capture_output=True, text=True)

    def test_stock_prose_check_reads_the_parts(self):
        # 4.1.0: `just prose-check` on a manuscript.toml project checks the
        # declared parts; it used to open paper.typ and crash.
        self.write("chapters/two.typ", "// >>> BODY START\n#todo(\"finish\")\n"
                                       "// <<< BODY END\n")
        run = self.stock("prose_check.py")
        self.assertNotIn("FileNotFoundError", run.stderr)
        self.assertIn("chapters/two.typ: #todo('finish')", run.stdout)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_stock_bib_audit_reads_part_bibliographies(self):
        self.write("manuscript.toml", MANIFEST.replace(
            'source = "chapters/one.typ"',
            'source = "chapters/one.typ"\nbibliography = "chapters/one.bib"\n'
            'citation_prefix = "one-"'))
        self.write("chapters/one.bib", "@article{smith20, title={T}, year={2020}}\n")
        import bib_audit
        with patch.object(bib_audit, "ROOT", self.root):
            keys = [e["_key"] for e in bib_audit._entries()]
        self.assertEqual(keys, ["one-smith20"])

    def test_documents_outputs_for_clean(self):
        run = self.stock("documents.py", "outputs")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.split(), ["build/thesis.pdf", "build/thesis.docx",
                                              "build/one.pdf", "build/one.docx",
                                              "build/two.pdf", "build/two.docx"])


def run_cases():
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Documents))
    return result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
