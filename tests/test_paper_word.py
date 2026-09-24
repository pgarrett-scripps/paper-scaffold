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


def tiny_png() -> bytes:
    """A 1x1 PNG, so the image case needs no converter and no asset."""
    import struct
    import zlib

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data)))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\x00')) + chunk(b'IEND', b''))


class PaperWordTests(unittest.TestCase):
    def test_custom_reference_survives_export_and_is_fingerprinted(self):
        from paper_word_reference import generate
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reference = root / 'word/custom.docx'
            generate(reference, {})
            with zipfile.ZipFile(reference) as archive:
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
            (root / 'project.toml').write_text(
                'schema_version = 1\n[word]\nreference = "word/custom.docx"\n')
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
            self.assertNotEqual(before['word/custom.docx'], snapshot(root)['word/custom.docx'])

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

    def test_export_matches_the_pdf_layout(self):
        """The Word-export fixes downstream papers each made locally (3.23.0):
        title style, real page breaks, text-width image sizes, keep rules,
        label anchors folded away, no local paths in the file's properties,
        and a bibliography title given as a string."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'references.bib').write_text(
                '@article{main2020, author={Ada, A}, title={Main work}, year={2020}}\n')
            (root / 'fig.png').write_bytes(tiny_png())
            source = root / 'paper.resolved.typ'
            source.write_text(
                '= The Title\n\nAuthor line.\n\n== Methods\n\nProse @main2020.\n\n'
                '#figure(image("fig.png", width: 50%), caption: [A figure.])\n\n'
                '#figure(table(columns: 2, [a], [b], [c], [d]), caption: [A table.])'
                ' <tbl:x>\n\n*Run-in label*\n\nAfter the label.\n\n'
                '#bibliography("references.bib", title: "Cited Works")\n\n'
                '#pagebreak()\n\n= Supporting Information\n\nSI prose.\n')
            output = root / 'paper.docx'
            with patch.multiple(export_docx, ROOT=root, SRC=source, OUT=output):
                self.assertEqual(export_docx.main(), 0)
            with zipfile.ZipFile(output) as archive:
                document = ET.fromstring(archive.read('word/document.xml'))
                custom = archive.read('docProps/custom.xml').decode() \
                    if 'docProps/custom.xml' in archive.namelist() else ''
            ns = {'w': W}
            w = '{' + W + '}'
            body = document.find('w:body', ns)

            def text(p):
                return ''.join(t.text or '' for t in p.iter(w + 't'))

            def style(p):
                s = p.find('w:pPr/w:pStyle', ns)
                return '' if s is None else s.get(w + 'val')

            paragraphs = body.findall('w:p', ns)
            self.assertEqual(style(paragraphs[0]), 'Title')
            self.assertEqual(text(paragraphs[0]), 'The Title')
            si = next(p for p in paragraphs if text(p) == 'Supporting Information')
            self.assertIsNotNone(si.find('w:pPr/w:pageBreakBefore', ns))
            self.assertFalse([b for b in document.iter(w + 'br') if b.get(w + 'type') == 'page'])
            self.assertIsNone(document.find('.//w:pict', ns), 'pagebreak drawn as a rule')
            self.assertTrue(any(text(p) == 'Cited Works' for p in paragraphs))
            # Half the 6.5 in text width, not half pandoc's fixed 420 pt.
            extent = document.find('.//{http://schemas.openxmlformats.org/'
                                   'drawingml/2006/wordprocessingDrawing}extent')
            self.assertAlmostEqual(int(extent.get('cx')) / 914400, 3.25, places=2)
            drawing = next(p for p in paragraphs if p.find('.//w:drawing', ns) is not None)
            self.assertIsNotNone(drawing.find('w:pPr/w:keepNext', ns))
            caption = next(p for p in paragraphs if style(p) == 'TableCaption')
            self.assertIsNotNone(caption.find('w:pPr/w:keepNext', ns))
            self.assertIsNotNone(caption.find('w:pPr/w:keepLines', ns))
            label = next(p for p in paragraphs if text(p) == 'Run-in label')
            self.assertIsNotNone(label.find('w:pPr/w:keepNext', ns))
            rows = document.findall('.//w:tr', ns)
            self.assertTrue(all(r.find('w:trPr/w:cantSplit', ns) is not None for r in rows))
            self.assertIsNotNone(rows[0].find('w:trPr/w:tblHeader', ns))
            # The <tbl:x> label is a bookmark on the caption, not an empty line.
            self.assertFalse([p for p in paragraphs if not text(p).strip()
                              and p.find('w:bookmarkStart', ns) is not None
                              and p.find('.//w:drawing', ns) is None])
            self.assertTrue(any(b.get(w + 'name') == 'tbl:x'
                                for b in caption.iter(w + 'bookmarkStart')))
            self.assertNotIn(str(root), custom)

    def test_main_only_stops_before_the_supporting_information(self):
        from resolve_typst import SI_HEADING
        src = f'= T\n\nMain.\n\n#pagebreak()\n\n{SI_HEADING}\n\nSI.\n'
        self.assertEqual(export_docx.main_only(src), '= T\n\nMain.\n')
        self.assertEqual(export_docx.main_only('= T\n\nNo SI.\n'), '= T\n\nNo SI.\n')

    def test_stock_reference_has_black_title_and_headings(self):
        from paper_word_reference import generate
        ns = {'w': W}
        with tempfile.TemporaryDirectory() as folder:
            target = generate(Path(folder) / 'r.docx', {})
            with zipfile.ZipFile(target) as archive:
                styles = ET.fromstring(archive.read('word/styles.xml'))
            for sid in ('Title', 'Subtitle', 'Heading1', 'Heading6', 'Heading9Char'):
                color = styles.find(f'w:style[@w:styleId="{sid}"]/w:rPr/w:color', ns)
                self.assertEqual(color.attrib, {'{' + W + '}val': '000000'}, sid)

    def test_word_style_settings_reach_the_styles(self):
        from paper_word_reference import generate, guess, translate
        ns = {'w': W}
        val = '{' + W + '}val'
        style = {'font': 'Times New Roman', 'font_size': 11.5, 'line_spacing': 2.0,
                 'margins': '2.5cm', 'title_size': 20, 'title_align': 'left',
                 'title_color': '112233', 'heading_color': '0F4761'}
        with tempfile.TemporaryDirectory() as folder:
            target = generate(Path(folder) / 'r.docx', style)
            with zipfile.ZipFile(target) as archive:
                styles = ET.fromstring(archive.read('word/styles.xml'))
                document = ET.fromstring(archive.read('word/document.xml'))
            data = target.read_bytes()
            width = export_docx.text_width(target)
        run = styles.find('w:docDefaults/w:rPrDefault/w:rPr', ns)
        fonts = run.find('w:rFonts', ns)
        self.assertEqual(fonts.get('{' + W + '}ascii'), 'Times New Roman')
        self.assertIsNone(fonts.get('{' + W + '}asciiTheme'))
        self.assertEqual(run.find('w:sz', ns).get(val), '23')
        self.assertEqual(styles.find('w:docDefaults/w:pPrDefault/w:pPr/w:spacing', ns)
                         .get('{' + W + '}line'), '480')
        # Tables and tight lists stay single-spaced.
        self.assertEqual(styles.find('w:style[@w:styleId="Compact"]/w:pPr/w:spacing', ns)
                         .get('{' + W + '}line'), '240')
        # One family: the title and headings lose the theme's heading face.
        heading_font = styles.find('w:style[@w:styleId="Heading1"]/w:rPr/w:rFonts', ns)
        self.assertEqual(heading_font.get('{' + W + '}hAnsi'), 'Times New Roman')
        code_font = styles.find('w:style[@w:styleId="SourceCode"]/w:rPr/w:rFonts', ns)
        self.assertEqual(code_font.get('{' + W + '}ascii'), 'DejaVu Sans Mono')
        title = styles.find('w:style[@w:styleId="Title"]', ns)
        self.assertEqual(title.find('w:rPr/w:sz', ns).get(val), '40')
        self.assertEqual(title.find('w:pPr/w:jc', ns).get(val), 'left')
        self.assertEqual(title.find('w:rPr/w:color', ns).get(val), '112233')
        self.assertEqual(styles.find('w:style[@w:styleId="Heading2"]/w:rPr/w:color', ns)
                         .get(val), '0F4761')
        margin = document.find('.//w:sectPr/w:pgMar', ns)
        self.assertEqual({margin.get('{' + W + '}' + s) for s in ('top', 'left')}, {'1417'})
        # Figure widths follow the page the margins leave.
        self.assertAlmostEqual(width, (12240 - 2 * 1417) / 1440)
        # The translation reads the settings back, exactly.
        self.assertEqual(guess(data)['margins'], f'{1417 / 1440:g}in')
        found, left = translate(data)
        self.assertEqual(left, [])
        self.assertEqual({k: found[k] for k in ('font', 'title_align', 'heading_color')},
                         {k: style[k] for k in ('font', 'title_align', 'heading_color')})

    def test_guessed_line_spacing_is_one_project_toml_accepts(self):
        """A template at line=259 (1.079) guessed 1.08, which every
        project_hooks.load() then rejected (steps of 0.05)."""
        from paper_word_reference import generate, guess, toml_block, translate
        import project_hooks
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = generate(root / 'r.docx', {'line_spacing': 1.0})
            target = root / 'template.docx'
            with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, 'w') as out:
                for item in src.infolist():
                    data = src.read(item.filename)
                    if item.filename == 'word/styles.xml':
                        text = data.decode()
                        self.assertIn('w:line="240"', text)
                        data = text.replace('w:line="240"', 'w:line="259"', 1).encode()
                    out.writestr(item, data)
            data = target.read_bytes()
            self.assertEqual(guess(data)['line_spacing'], 1.1)
            found, left = translate(data)
            (root / 'project.toml').write_text('schema_version = 1\n\n' + toml_block(found) + '\n')
            self.assertEqual(project_hooks.load(root).word.style.get('line_spacing'), 1.1)
            # The rounding is reported, not hidden.
            self.assertTrue(any('spacing@line' in line for line in left), left)

    def test_reference_is_cached_by_its_settings(self):
        from paper_word_reference import reference_for
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = reference_for(root, {})
            self.assertEqual(first.parent, root / '.build-state/word-reference')
            stamp = first.stat().st_mtime_ns
            self.assertEqual(reference_for(root, {}), first)
            self.assertEqual(first.stat().st_mtime_ns, stamp)
            self.assertNotEqual(reference_for(root, {'font_size': 11}), first)
            # A captured build under .build-state/ shares the project's cache.
            capture = root / '.build-state/manuscripts/abc'
            capture.mkdir(parents=True)
            self.assertEqual(reference_for(capture, {}), first)

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
