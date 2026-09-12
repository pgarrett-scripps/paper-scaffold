"""Native code survives source resolution, prose extraction, PDF and Word."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

import pypandoc
import readability
from export_docx import style_code
from manuscript_snapshot import resolve_source
from resolve_typst import _protect_raw, _restore_raw

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "code-fixture.typ"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{" + NS["w"] + "}"


class CodeBlocks(unittest.TestCase):
    def test_resolution_and_metrics_preserve_code_boundary(self):
        source = FIXTURE.read_text()
        self.assertEqual(resolve_source(source, {}, {}, "code-fixture.typ"), source)
        protected, spans = _protect_raw(source)
        self.assertEqual(_restore_raw(protected, spans), source)
        prose = readability.clean(readability.slice_body(source))
        self.assertIn("values.max()", prose)
        for token in ("not-a-citation", "unknown_language", "normalize", "enabled"):
            self.assertNotIn(token, prose)

    def test_word_code_text_colors_and_editability(self):
        source = readability.slice_body(FIXTURE.read_text())
        ast = json.loads(pypandoc.convert_text(source, "json", format="typst"))
        expected = [b["c"][1] for b in ast["blocks"] if b["t"] == "CodeBlock"]
        self.assertEqual(len(expected), 6)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "code.docx"
            pypandoc.convert_text(source, "docx", format="typst", outputfile=str(path),
                                  extra_args=["--fail-if-warnings"])
            with zipfile.ZipFile(path) as archive:
                original = {n: archive.read(n) for n in archive.namelist()}
            style_code(path)
            with zipfile.ZipFile(path) as archive:
                for name, data in original.items():
                    if name != "word/styles.xml":
                        self.assertEqual(archive.read(name), data, name)
                document = ET.fromstring(archive.read("word/document.xml"))
                styles = ET.fromstring(archive.read("word/styles.xml"))
            actual = []
            for paragraph in document.findall(".//w:p", NS):
                style = paragraph.find("w:pPr/w:pStyle", NS)
                if style is not None and style.get(W + "val") == "SourceCode":
                    actual.append("".join(
                        node.text or "" if node.tag == W + "t" else
                        "\n" if node.tag == W + "br" else "\t"
                        for node in paragraph.iter()
                        if node.tag in (W + "t", W + "br", W + "tab")))
            self.assertEqual(actual, expected)
            self.assertFalse(document.findall(".//w:drawing", NS))
            tokens = {n.get(W + "val") for n in document.findall(".//w:rStyle", NS)}
            self.assertIn("KeywordTok", tokens)
            self.assertIn("CommentTok", tokens)
            keyword = styles.find("w:style[@w:styleId='KeywordTok']/w:rPr/w:color", NS)
            self.assertIsNotNone(keyword)
            self.assertNotIn(keyword.get(W + "val"), ("000000", "auto"))
            code = styles.find("w:style[@w:styleId='SourceCode']", NS)
            self.assertEqual(code.find("w:pPr/w:shd", NS).get(W + "fill"), "F4F6F8")
            self.assertEqual(code.find("w:pPr/w:keepLines", NS).get(W + "val"), "0")

    @unittest.skipUnless(shutil.which("typst"), "Typst not installed")
    def test_pdf_long_block_breaks_across_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(ROOT / "code.typ", root / "code.typ")
            source = ('#import "code.typ": code-style\n#show: code-style\n'
                      '#set page(height: 100mm, width: 140mm, margin: 12mm)\n'
                      '```python\n' + '\n'.join(f'value_{i} = {i}' for i in range(100))
                      + '\n```\n')
            (root / "code.typst").write_text(source)
            subprocess.run(["typst", "compile", str(root / "code.typst"),
                            str(root / "code-{p}.svg")], check=True, capture_output=True)
            self.assertGreater(len(list(root.glob("code-*.svg"))), 1)
            self.assertLess(len(list(root.glob("code-*.svg"))), 20)


def run_cases():
    result = unittest.TextTestRunner(verbosity=1).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(CodeBlocks))
    return result.wasSuccessful()
