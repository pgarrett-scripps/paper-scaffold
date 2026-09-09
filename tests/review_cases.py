"""Revision contracts, independent of the replaceable manuscript prose."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import build_state
import manuscript_snapshot as snapshot
import resolve_typst
import review


class Reviews(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self, name, text="Original words.", image="red"):
        import pypandoc
        folder = self.root / name
        folder.mkdir()
        (folder / "figure.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">'
            f'<rect width="40" height="40" fill="{image}"/></svg>')
        doc = json.loads(pypandoc.convert_text(
            text + '\n\n![An example](figure.svg)\n\n| Result | Value |\n|---|---|\n| Test | 35 |\n',
            "json", format="markdown"))
        (folder / "document.json").write_text(json.dumps(doc))
        (folder / "manifest.json").write_text(json.dumps({"schema_version": 1,
            "files": {p.name: snapshot.sha(p) for p in folder.iterdir() if p.is_file()}}))
        return folder

    def test_literal_resolution_preserves_typst_text_and_raw_examples(self):
        stats = {"x": {"value": 35, "display": "35 (#special)_"}}
        source = '''#set text(style: "italic")
// #s("missing")
`#s("missing")` /* #s("missing") */
Result: #s("x"). #let doubled = n("x") * 2
The notation s("x") is plain prose here.
'''
        got = snapshot.resolve_source(source, stats, {}, "fixture")
        self.assertIn('#set text(style: "italic")', got)
        self.assertIn('#("35 (#special)_")', got)
        self.assertIn('doubled = (35) * 2', got)
        self.assertEqual(got.count('#s("missing")'), 3)
        self.assertIn('notation s("x")', got)

    def test_toc_graphic_uses_word_resource_paths(self):
        source = '#let toc-graphic = image("/figures/abstract.png", width: 92%)\n'
        with patch.object(resolve_typst, "ROOT", self.root), \
                patch.object(resolve_typst, "NATIVE_NUMBERING", []):
            block = resolve_typst._toc_block(source, {})
        self.assertIn('image("figures/abstract.png"', block)

    def test_nested_asset_arguments_and_kind_validation(self):
        assets = {"f": {"kind": "figure", "path": "figures/plot.png"}}
        got = snapshot.resolve_source('#figure(fig("f", width: (n("w") * 1pt)))',
                                      {"w": {"value": 35}}, assets, "sections/result.typ")
        self.assertIn('image("/figures/plot.png", width: ((35) * 1pt))', got)
        with self.assertRaisesRegex(ValueError, "not a table"):
            snapshot.resolve_source('#tbl("f")', {}, assets, "fixture")

    @unittest.skipUnless(shutil.which("typst"), "Typst not installed")
    def test_native_numbering_includes_unlabeled_figures_and_custom_styles(self):
        body = '''= Results <sec:results>
#figure(rect(), kind: image, caption: [First unlabeled.])
#figure(rect(), kind: image, caption: [Second labeled.]) <fig:second>
See #ref(<fig:second>) and #ref(<sec:results>).
'''
        (self.root / "paper.typ").write_text('#set heading(numbering: "I.")\n' + body)
        numbers = snapshot.query_numbers(self.root)
        resolved = resolve_typst.resolve_crossrefs("", body, numbers)
        self.assertIn("Figure 2: Second", resolved)
        self.assertIn("See Figure 2 and Section I", resolved)
        self.assertIn("= I. Results", resolved)

    @unittest.skipUnless(shutil.which("typst"), "Typst not installed")
    def test_pdf_resolution_preserves_include_scope_and_rendered_bytes(self):
        (self.root / "sections").mkdir()
        (self.root / "stats.typ").write_text('#let s(id) = "35 (#special)_"\n')
        source = '#set page(width: 8cm, height: 4cm)\n#include "sections/body.typ"\n'
        body = '#import "../stats.typ": s\n#set text(style: "italic")\nResult: #s("x").\n'
        (self.root / "paper.typ").write_text(source)
        (self.root / "sections/body.typ").write_text(body)
        command = ["typst", "compile", "--root", str(self.root)]
        subprocess.run([*command, str(self.root / "paper.typ"), str(self.root / "before.png")], check=True)
        (self.root / "sections/body.typ").write_text(snapshot.resolve_source(
            body, {"x": {"value": 35, "display": "35 (#special)_"}}, {}, "sections/body.typ"))
        subprocess.run([*command, str(self.root / "paper.typ"), str(self.root / "after.png")], check=True)
        self.assertEqual((self.root / "before.png").read_bytes(), (self.root / "after.png").read_bytes())

    def test_reflow_is_not_a_change_but_words_and_same_path_images_are(self):
        old = self.fixture("old", "Original words with context.")
        wrapped = self.fixture("wrapped", "Original words\nwith context.")
        _, count = review.report(old, wrapped, "old", "wrapped")
        self.assertEqual(count, 0)
        changed = self.fixture("changed", "Revised words with context.", "blue")
        html, count = review.report(old, changed, "old", "changed")
        self.assertGreater(count, 0)
        self.assertIn('class="removed">Original', html)
        self.assertIn('class="added">Revised', html)
        self.assertEqual(html.count('data:image/svg+xml;base64,'), 2)
        self.assertIn("<table>", html)

    def test_deleted_passages_and_table_cell_changes_remain_visible(self):
        old = self.fixture("old", "Keep this.\n\nDelete this paragraph.")
        new = self.fixture("new", "Keep this.")
        doc = json.loads((new / "document.json").read_text())

        def replace(value):
            if isinstance(value, list):
                for child in value:
                    replace(child)
            elif isinstance(value, dict):
                if value.get("t") == "Str" and value.get("c") == "35":
                    value["c"] = "36"
                else:
                    for child in value.values():
                        replace(child)
        replace(doc)
        (new / "document.json").write_text(json.dumps(doc))
        manifest = json.loads((new / "manifest.json").read_text())
        manifest["files"]["document.json"] = snapshot.sha(new / "document.json")
        (new / "manifest.json").write_text(json.dumps(manifest))
        html, count = review.report(old, new, "old", "new")
        self.assertEqual(count, 2)
        self.assertIn('class="removed">Delete', html)
        self.assertIn('class="removed">35', html)
        self.assertIn('class="added">36', html)

    def test_modified_snapshot_and_unsafe_name_are_rejected(self):
        folder = self.fixture("old")
        (folder / "figure.svg").write_text("changed")
        with self.assertRaisesRegex(ValueError, "snapshot was modified"):
            snapshot.validate(folder)
        for name in ("../escape", "current", "/absolute", "two words"):
            with self.assertRaises(ValueError):
                review.version_path(self.root, name)

    @unittest.skipUnless(shutil.which("typst"), "Typst not installed")
    def test_unchanged_statistic_call_detects_changed_display_value(self):
        config = '''#let paper-title = "Review fixture"
#let paper-running-title = "Review fixture"
#let paper-authors = ()
#let paper-affiliations = ()
#let paper-date = "2026"
#let paper-keywords = ()
#let paper-abstract = [A permanent test manuscript.]
'''
        paper = '''#import "config.typ": *
#import "stats.typ": s
#set heading(numbering: "1.")
// >>> BODY START
= Results
We measured #s("count") samples.
// <<< BODY END
'''
        (self.root / "config.typ").write_text(config)
        (self.root / "paper.typ").write_text(paper)
        (self.root / "stats.typ").write_text(
            '#let s(id) = json("stats-rendered.json").values.at(id).display\n')
        outputs = []
        for value in (35, 36):
            (self.root / "stats.json").write_text(json.dumps({"values": {"count": {"value": value}}}))
            (self.root / "stats-rendered.json").write_text(json.dumps({
                "values": {"count": {"value": value, "display": str(value)}}}))
            sources = {name: snapshot.sha(self.root / name)
                       for name in ("paper.typ", "config.typ", "stats.typ", "stats.json")}
            destination = self.root / f"version-{value}"
            build_state.prepare_snapshot(self.root, destination, sources, list(sources))
            outputs.append(destination)
        self.assertEqual((self.root / "paper.typ").read_text(), paper)
        html, count = review.report(*outputs, "before", "after")
        self.assertEqual(count, 1)
        self.assertIn('class="removed">35', html)
        self.assertIn('class="added">36', html)

    def test_citation_identity_survives_automatic_renumbering(self):
        def cite(key, number):
            return {"t": "Cite", "c": [[{"citationId": key, "citationNoteNum": number,
                                         "citationHash": number}], [{"t": "Str", "c": str(number)}]]}
        self.assertEqual(review.canonical(cite("study", 1), self.root),
                         review.canonical(cite("study", 2), self.root))
        self.assertNotEqual(review.canonical(cite("study", 1), self.root),
                            review.canonical(cite("other", 1), self.root))

    def test_unchanged_images_are_embedded_once_for_context(self):
        old = self.fixture("old")
        new = self.fixture("new")
        html, count = review.report(old, new, "old", "new")
        self.assertEqual(count, 0)
        self.assertEqual(html.count('data:image/svg+xml;base64,'), 1)

    def test_decimal_changes_highlight_the_complete_number(self):
        old, new = review.highlight("<p>Size: 6.7 GB.</p>", "<p>Size: 6.6800 GB.</p>")
        self.assertIn('class="removed">6.7</mark>', old)
        self.assertIn('class="added">6.6800</mark>', new)

    def test_section_navigation_preserves_deleted_section_context(self):
        old = self.fixture("old", "# Introduction\n\nKeep this.\n\n## Old method\n\nDelete this.")
        new = self.fixture("new", "# Introduction\n\nKeep this.")
        html, count = review.report(old, new, "old", "new")
        self.assertEqual(count, 1)
        self.assertIn('href="#change-1">Introduction › Old method', html)
        self.assertIn('class="removed">Delete', html)

    def test_renumbering_is_separated_from_content_edits(self):
        old = self.fixture("old")
        new = self.fixture("new")
        for folder, number in ((old, 1), (new, 2)):
            doc = json.loads((folder / "document.json").read_text())
            doc["blocks"][0] = {"t": "Para", "c": [{"t": "Cite", "c": [[{
                "citationId": "same-study", "citationPrefix": [], "citationSuffix": [],
                "citationMode": {"t": "NormalCitation"}, "citationNoteNum": 0,
                "citationHash": 0}], [{"t": "Str", "c": str(number)}]]}]}
            (folder / "document.json").write_text(json.dumps(doc))
            manifest = json.loads((folder / "manifest.json").read_text())
            manifest["files"]["document.json"] = snapshot.sha(folder / "document.json")
            (folder / "manifest.json").write_text(json.dumps(manifest))
        html, count = review.report(old, new, "old", "new")
        self.assertEqual(count, 1)
        self.assertIn('0 content edits · 1 display / numbering change', html)
        self.assertIn('class="changed" data-display="true"', html)

    def test_listing_versions_never_builds_or_changes_snapshots(self):
        path = review.version_path(self.root, "reviewed")
        path.mkdir(parents=True)
        (path / "manifest.json").write_text('{}')
        output = io.StringIO()
        with patch.object(review, "ROOT", self.root), \
                patch.object(sys, "argv", ["review.py", "versions"]), \
                patch.object(review, "current_snapshot") as build, \
                contextlib.redirect_stdout(output):
            self.assertEqual(review.main(), 0)
            self.assertIn("reviewed", output.getvalue())
            build.assert_not_called()

    def test_existing_baseline_is_never_overwritten(self):
        path = review.version_path(self.root, "reviewed")
        path.mkdir(parents=True)
        with patch.object(review, "current_snapshot") as build:
            with self.assertRaisesRegex(ValueError, "already exists"):
                review.save(self.root, "reviewed")
            build.assert_not_called()

    def test_edit_during_snapshot_preserves_last_good_output(self):
        (self.root / "paper.typ").write_text("Before.")
        (self.root / "paper.pdf").write_text("Last good PDF.")

        def run(args, **kwargs):
            if args[0] == "typst":
                Path(args[-1]).write_text("probe")
                Path(args[args.index("--deps") + 1]).write_text('{"inputs":["paper.typ"]}')

        def capture(root, folder, sources, dependencies):
            folder.mkdir()
            (folder / "paper.pdf").write_text("New PDF.")
            (root / "paper.typ").write_text("Edited during snapshot.")
            return {"id": "fixture"}

        with patch.object(build_state.subprocess, "run", side_effect=run), \
                patch.object(build_state, "prepare_snapshot", side_effect=capture):
            with self.assertRaisesRegex(ValueError, "sources changed"):
                build_state.build("paper", self.root)
        self.assertEqual((self.root / "paper.pdf").read_text(), "Last good PDF.")
        self.assertFalse((self.root / ".build-state/manuscript.json").exists())


def run_cases():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Reviews)
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
