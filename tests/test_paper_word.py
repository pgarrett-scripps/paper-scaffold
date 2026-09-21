"""Paper template edits survive export and invalidate cached deliverables."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import export_docx
from build_state import snapshot
from word_xml import W


class PaperWordTests(unittest.TestCase):
    def test_custom_reference_survives_export_and_is_fingerprinted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reference = root / 'word/paper-reference.docx'
            reference.parent.mkdir()
            with zipfile.ZipFile(ROOT / 'word/paper-reference.docx') as archive:
                files = {n: archive.read(n) for n in archive.namelist()}
            styles = ET.fromstring(files['word/styles.xml'])
            ns = {'w': W}
            # This would be overwritten by the old post-export code formatter.
            size = styles.find('w:style[@w:styleId="SourceCode"]/w:rPr/w:sz', ns)
            size.set('{' + W + '}val', '26')
            ET.register_namespace('w', W)
            files['word/styles.xml'] = ET.tostring(styles)
            with zipfile.ZipFile(reference, 'w') as archive:
                for n, data in files.items():
                    archive.writestr(n, data)
            source = root / 'paper.resolved.typ'
            source.write_text('= Test\n\n```python\nprint("editable")\n```\n\n$ x^2 $\n')
            output = root / 'paper.docx'
            with patch.multiple(export_docx, ROOT=root, SRC=source, OUT=output):
                self.assertEqual(export_docx.main(), 0)
            with zipfile.ZipFile(output) as archive:
                styled = ET.fromstring(archive.read('word/styles.xml'))
                self.assertEqual(styled.find('w:style[@w:styleId="SourceCode"]/w:rPr/w:sz', ns).get('{' + W + '}val'), '26')
                self.assertIn(b'<m:oMath>', archive.read('word/document.xml'))
            before = snapshot(root)
            reference.write_bytes(b'edited template')
            self.assertNotEqual(before['word/paper-reference.docx'], snapshot(root)['word/paper-reference.docx'])

    def test_supporting_information_keeps_its_own_reference_list(self):
        """Two lists, numbered independently, each holding only its own works.

        Citeproc sets one reference list per run, so the exporter converts
        each stretch of the projection separately and joins the trees. The
        anchors of the second list are renamed: a work cited in both halves
        would otherwise be two Word bookmarks with one id.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'references.bib').write_text(
                '@article{main2020, author={Ada, A}, title={Main work}, '
                'year={2020}}\n'
                '@article{si2021, author={Bee, B}, title={SI only work}, '
                'year={2021}}\n')
            source = root / 'paper.resolved.typ'
            source.write_text(
                '= Main\n\nMain prose @main2020.\n\n'
                '#bibliography("references.bib", title: [References])\n\n'
                '= Supporting Information\n\nSI prose @si2021.\n\n'
                '#bibliography("references.bib", title: [References])\n')
            output = root / 'paper.docx'
            with patch.multiple(export_docx, ROOT=root, SRC=source, OUT=output):
                self.assertEqual(export_docx.main(), 0)
            import pypandoc
            text = pypandoc.convert_file(str(output), 'plain')
            self.assertEqual(text.count('References'), 2)
            main, si = text.split('Supporting Information')
            # Default (Chicago) styling title-cases the titles: no CSL file
            # is in this fixture's root, which the exporter says out loud.
            self.assertIn('Main Work', main)
            self.assertNotIn('SI Only Work', main)
            self.assertIn('SI Only Work', si)
            self.assertNotIn('Main Work', si)
            with zipfile.ZipFile(output) as archive:
                document = archive.read('word/document.xml').decode()
            self.assertIn('ref-main2020', document)
            self.assertIn('s1-ref-si2021', document)

    def test_legacy_project_without_template_still_exports(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'paper.resolved.typ'
            source.write_text('= Heading\n\nBody.\n')
            output = root / 'paper.docx'
            with patch.multiple(export_docx, ROOT=root, SRC=source, OUT=output):
                self.assertEqual(export_docx.main(), 0)
            self.assertTrue(zipfile.is_zipfile(output))


if __name__ == '__main__':
    unittest.main()
