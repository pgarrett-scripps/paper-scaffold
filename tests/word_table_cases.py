"""Word table styling and page setup from [word.style] and [word.tables]
(tools/word_tables.py, tools/paper_word_reference.py; docs/word-export.md).

Each case writes its own project.toml and paper.resolved.typ into a
temporary directory and runs the real export.
"""
from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

import project_hooks as ph

SOURCE = """= Results

#figure(table(columns: 3,
  table.header(table.cell(colspan: 3)[Grouped heading], [Condition], [Observed], [Expected]),
  [Control], [1.02], [1.00],
  [Treated], [2.10], [2.00]), caption: [Grouped.]) <tbl:grouped>

#figure(grid(columns: 2,
  table(columns: 2, [a], [b], [c], [d]),
  table(columns: 2, [e], [f], [g], [h])), caption: [Two side by side.]) <tbl:pair>
"""


class Tmp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, text: str) -> None:
        (self.root / "project.toml").write_text("schema_version = 1\n" + text)

    def export(self) -> tuple[int, str]:
        import export_docx
        from unittest.mock import patch
        source = self.root / "paper.resolved.typ"
        source.write_text(SOURCE)
        out = io.StringIO()
        with patch.multiple(export_docx, ROOT=self.root, SRC=source,
                            OUT=self.root / "paper.docx"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = export_docx.main()
        return rc, out.getvalue()

    def part(self, name: str) -> str:
        with zipfile.ZipFile(self.root / "paper.docx") as z:
            return z.read(name).decode()


class Validation(Tmp):
    def test_table_keys_are_validated(self):
        self.write('[word.style]\ntable_font_size = 9\ntable_header_bold = true\n'
                   'table_header_shading = "f2f2f2"\ntable_borders = "booktabs"\n'
                   'table_layout = "fixed"\ntable_cell_margin = "0.04in"\n'
                   'table_compact = true\ntable_valign = "center"\n'
                   'table_unnest = true\ntitle_bold = false\npage_numbers = true\n'
                   '[word.tables."tbl.runtime"]\nwidths = [3, 1, 1.5]\n'
                   'font_size = 8\nheader_rows = 2\n')
        word = ph.load(self.root).word
        self.assertEqual(word.style["table_header_shading"], "F2F2F2")
        self.assertIs(word.style["page_numbers"], True)
        self.assertEqual(word.tables, {"tbl:runtime": {"widths": [3, 1, 1.5],
                                                       "font_size": 8, "header_rows": 2}})
        for bad in ('[word.style]\ntable_font_size = 30',
                    '[word.style]\ntable_borders = "double"',
                    '[word.style]\ntable_compact = "yes"',
                    '[word.style]\npage_numbers = 1',
                    '[word.style]\ntable_cell_margin = "2in"',
                    '[word.tables."fig:x"]\nwidths = [1]',
                    '[word.tables."tbl:x"]\nwidths = [0, 1]',
                    '[word.tables."tbl:x"]\nwidth = [1, 1]',
                    '[word.tables."tbl:x"]\nheader_rows = true',
                    '[word.tables."tbl:x"]\nfont_size = 9\n[word.tables."tbl.x"]\nfont_size = 8'):
            with self.subTest(bad=bad):
                self.write(bad + "\n")
                with self.assertRaises(ValueError):
                    ph.load(self.root)

    def test_table_keys_may_sit_beside_a_hand_made_reference(self):
        self.write('[word]\nreference = "word/custom.docx"\n'
                   '[word.style]\ntable_font_size = 9\n')
        self.assertEqual(ph.load(self.root).word.style, {"table_font_size": 9})
        self.write('[word]\nreference = "word/custom.docx"\n'
                   '[word.style]\ntitle_bold = true\n')
        with self.assertRaisesRegex(ValueError, "exclusive"):
            ph.load(self.root)


class Export(Tmp):
    def test_no_table_keys_leave_the_tables_alone(self):
        self.write('[word.style]\nfont_size = 11\n')
        self.assertEqual(self.export()[0], 0)
        doc = self.part("word/document.xml")
        self.assertNotIn("tblBorders", doc)
        self.assertNotIn('w:type="fixed"', doc)
        # pandoc's layout table around the pair stays nested.
        self.assertRegex(doc, r"<w:tc>(?:(?!</w:tc>).)*<w:tbl>")

    def test_the_table_keys_reach_every_table(self):
        self.write('[word.style]\ntable_font_size = 9\ntable_header_bold = true\n'
                   'table_header_shading = "F2F2F2"\ntable_borders = "booktabs"\n'
                   'table_layout = "fixed"\ntable_compact = true\n'
                   'table_valign = "center"\ntable_unnest = true\n'
                   '[word.tables."tbl:grouped"]\nwidths = [2, 1, 1]\nfont_size = 8\n')
        rc, out = self.export()
        self.assertEqual(rc, 0, out)
        doc = self.part("word/document.xml")
        body = doc[doc.index("<w:body>"):]
        # Un-nested: no table inside a cell, three top-level tables.
        self.assertNotRegex(body, r"<w:tc>(?:(?!</w:tc>).)*<w:tbl>")
        self.assertEqual(body.count("<w:tbl>"), 3)
        grouped = body[body.index('w:name="tbl:grouped"'):]
        grouped = grouped[grouped.index("<w:tbl>"):grouped.index("</w:tbl>")]
        cols = [int(w) for w in re.findall(r'<w:gridCol w:w="(\d+)"', grouped)]
        self.assertEqual(len(cols), 3)
        self.assertEqual(cols[0], 2 * cols[1])
        self.assertIn('<w:tblLayout w:type="fixed"', grouped)
        # Its own size wins over the global one; both header rows are bold
        # and shaded, the body rows are not.
        self.assertIn('<w:sz w:val="16"', grouped)
        self.assertNotIn('<w:sz w:val="18"', grouped)
        rows = grouped.split("<w:tr>")[1:]
        self.assertEqual(len(rows), 4)
        for row in rows[:2]:
            self.assertIn("<w:tblHeader", row)
            self.assertIn('w:fill="F2F2F2"', row)
            self.assertIn("<w:b", row)
        for row in rows[2:]:
            self.assertNotIn("F2F2F2", row)
            self.assertNotIn("<w:b ", row)
        # The caption still leads each table, and the pair takes the global size.
        pair = body[body.index('w:name="tbl:pair"'):]
        self.assertIn('<w:sz w:val="18"', pair)

    def test_a_widths_list_of_the_wrong_length_stops_the_export(self):
        self.write('[word.tables."tbl:grouped"]\nwidths = [1, 1]\n')
        rc, out = self.export()
        self.assertEqual(rc, 1)
        self.assertIn("2 widths for a 3-column table", out)

    def test_an_unknown_label_is_a_note(self):
        self.write('[word.tables."tbl:missing"]\nfont_size = 8\n')
        rc, out = self.export()
        self.assertEqual(rc, 0, out)
        self.assertIn("tbl:missing", out)

    def test_page_numbers_and_title_weight(self):
        self.write('[word.style]\npage_numbers = true\ntitle_bold = true\n')
        self.assertEqual(self.export()[0], 0)
        doc = self.part("word/document.xml")
        self.assertIn("<w:footerReference", doc)
        rels = self.part("word/_rels/document.xml.rels")
        target = re.search(r'Target="([^"]*footer[^"]*)"', rels)
        self.assertIsNotNone(target)
        self.assertIn(" PAGE ", self.part(f"word/{target[1]}"))
        self.assertIn(target[1], self.part("[Content_Types].xml"))
        styles = self.part("word/styles.xml")
        title = styles[styles.index('w:styleId="Title"'):]
        self.assertIn("<w:b />", title[:title.index("</w:style>")])


def run_cases() -> bool:
    suite = unittest.TestSuite()
    for case in (Validation, Export):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
