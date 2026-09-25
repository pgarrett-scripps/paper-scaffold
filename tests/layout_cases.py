"""tools/layout_check.py: text past the margins in a built PDF, and figures
against the journal profile's [figures] limits (docs/journals.md).

Each case compiles its own small Typst document into a temporary directory;
skipped where typst or poppler is missing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

import journal
import layout_check as lc

TOOLS = all(shutil.which(b) for b in ("typst", "pdftotext", "pdfimages"))

PROFILE = '''schema_version = 1
label = "Test Article"
journal = "Journal of Tests"
type = "Article"
source = "https://example.org/authors"
guidelines-dated = "2026-01-01"
checked = "2026-01-02"
[figures]
min-dpi = 300
single-column-in = 3.33
double-column-min-in = 4.167
double-column-max-in = 7.0
max-height-in = 9
min-type-pt = 4.5
color-modes = ["rgb", "cmyk"]
'''

PROSE = ("#set page(paper: \"us-letter\", margin: 1in)\n#set par(justify: true)\n"
         "#lorem(400)\n\n")


@unittest.skipUnless(TOOLS, "typst or poppler not installed")
class Layout(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def compile(self, body: str) -> Path:
        (self.root / "paper.typ").write_text(PROSE + body + "\n\n#lorem(300)\n")
        subprocess.run(["typst", "compile", "--root", str(self.root),
                        str(self.root / "paper.typ")], check=True, capture_output=True)
        return self.root / "paper.pdf"

    def test_a_clean_page_has_no_findings(self):
        self.assertEqual(lc.overflow(self.compile("")), [])

    def test_a_table_past_the_right_margin_is_found(self):
        pdf = self.compile("#table(columns: (2.5in, 2.5in, 2.3in), "
                           "[one], [two], [three and more words here])")
        found = lc.overflow(pdf)
        self.assertEqual(len(found), 1, found)
        self.assertIn("past the right margin", found[0].message)
        self.assertIn("p.1", found[0].subject)

    def test_text_off_the_page_is_found(self):
        pdf = self.compile("#place(dx: 7.1in, [edgeword])")
        found = lc.overflow(pdf)
        self.assertTrue(any("page edge" in f.message for f in found), found)

    def test_figures_are_read_against_the_profile(self):
        from PIL import Image
        (self.root / "journals").mkdir()
        (self.root / "journals/t.toml").write_text(PROFILE)
        (self.root / "journal.toml").write_text('schema_version = 1\nprofile = "t"\n')
        (self.root / "figures").mkdir()
        Image.new("RGB", (600, 300), "white").save(self.root / "figures/low.png")
        Image.new("L", (3000, 1500), "white").save(self.root / "figures/gray.png")
        (self.root / "assets.json").write_text(json.dumps({"values": {
            "fig.low": {"path": "figures/low.png", "kind": "figure",
                        "print": {"width_in": 5.0, "height_in": 2.5, "min_pt": 8}},
            "fig.gray": {"path": "figures/gray.png", "kind": "figure",
                         "print": {"width_in": 3.0, "height_in": 1.5, "min_pt": 3}},
            "tbl.t": {"path": "si/t.typ", "kind": "table"}}}))
        pdf = self.compile('#image("figures/low.png", width: 5in)\n\n'
                           '#image("figures/gray.png", width: 3in)')
        profile = journal.load_profile(self.root, "t")
        found = {(f.subject, f.message.split(";")[0]) for f in
                 lc.figures(self.root, [pdf], profile.figures)}
        # 600 px over 5 in: 120 ppi as placed.
        self.assertIn(("fig.low", "prints at 120 ppi in paper.pdf p.1"), found)
        self.assertIn(("fig.gray", "smallest type is 3 pt at its recorded size"), found)
        self.assertIn(("fig.gray", "gray.png is gray (L)"), found)
        self.assertEqual(len(found), 3, found)
        # A width between the single and double column ranges.
        values = json.loads((self.root / "assets.json").read_text())
        values["values"]["fig.low"]["print"]["width_in"] = 3.8
        (self.root / "assets.json").write_text(json.dumps(values))
        messages = [f.message for f in lc.figures(self.root, [pdf], profile.figures)]
        self.assertTrue(any(m.startswith("prints 3.8 in wide") for m in messages), messages)

    def test_the_command_warns_and_strict_fails(self):
        self.compile("#table(columns: (2.5in, 2.5in, 2.3in), "
                     "[one], [two], [three and more words here])")
        from unittest.mock import patch
        import contextlib
        import io
        out = io.StringIO()
        with patch.object(lc, "ROOT", self.root), contextlib.redirect_stdout(out):
            self.assertEqual(lc.main([]), 0)
            self.assertEqual(lc.main(["--strict"]), 1)
        self.assertIn("warn: paper.pdf p.1", out.getvalue())


class Profile(unittest.TestCase):
    def test_figure_keys_are_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "journals").mkdir()
            (root / "journals/ok.toml").write_text(PROFILE)
            self.assertEqual(journal.load_profile(root, "ok").figures["min-type-pt"], 4.5)
            for bad in ('single-column-in = "3in"', 'color-modes = ["hsv"]',
                        'double-column-min-in = 8', 'max-height-in = 0'):
                key = bad.split(" =")[0]
                text = "\n".join(ln for ln in PROFILE.splitlines()
                                 if not ln.startswith(key + " ")) + "\n" + bad + "\n"
                if key == "double-column-min-in":
                    text = PROFILE.replace("double-column-min-in = 4.167", bad)
                with self.subTest(bad=bad):
                    (root / "journals/bad.toml").write_text(text)
                    with self.assertRaises(journal.JournalError):
                        journal.load_profile(root, "bad")


def run_cases() -> bool:
    suite = unittest.TestSuite()
    for case in (Layout, Profile):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
