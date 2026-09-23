"""Word export must retain content and keep chapter bibliographies independent."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from document_docx import (pandoc, namespace_ids, walk, check, word_state,
    sources_fingerprint, format_docx, NS, node, styled, paragraph, heading,
    pagebreak, index_blocks, caption_title)
from word_pagination import destinations, cache_pages
from document_project import Project, Part, Document
from build_state import digest
from word_content import WordContent, math
from word_reference import REFERENCE
from word_xml import ORDERS

ROOT = Path(__file__).resolve().parents[1]


def render(prefix='a-', keys=None, inventory=None):
    return WordContent(ROOT, 'chapter.typ', prefix, keys or {'shared'},
                       inventory or [], ['first', 'second'], {})


class WordExportTests(unittest.TestCase):
    def test_major_divisions_start_new_pages_without_breaking_every_section(self):
        import pypandoc
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'boundaries.docx'
            tree = pandoc('Text.')
            tree['blocks'] = [paragraph('Preceding text.')]
            headings = [(1, 'Chapter 1. Title', True),
                        (2, 'Co-Author Contributions', False),
                        (2, 'Abstract', True),
                        (3, 'Abstract detail', False),
                        (2, 'Introduction', True),
                        (2, 'Results', False),
                        (3, 'An ordinary subsection', False),
                        (2, 'Acknowledgments', False),
                        (2, 'Supplemental Methods and Results', True),
                        (3, 'S1 Protocol', False),
                        (2, 'References', True),
                        (1, 'Chapter 2. Title', True),
                        (2, 'Appendix A', True)]
            for level, title, _ in headings:
                tree['blocks'] += [heading(level, title), paragraph('Section content.')]
            pypandoc.convert_text(json.dumps(tree), 'docx', format='json', outputfile=str(output))
            format_docx(output)
            with zipfile.ZipFile(output) as archive:
                doc = ET.fromstring(archive.read('word/document.xml'))
            paragraphs = {''.join(t.text or '' for t in p.findall('.//w:t', NS)): p
                          for p in doc.findall('w:body/w:p', NS)}
            for _, title, starts_page in headings:
                props = paragraphs[title].find('w:pPr', NS)
                br = props.find('w:pageBreakBefore', NS)
                self.assertEqual(br is not None and br.get('{'+NS['w']+'}val', '1') != '0',
                                 starts_page, title)
                self.assertEqual(props.find('w:keepNext', NS).get('{'+NS['w']+'}val'), '1')
                self.assertEqual(props.find('w:keepLines', NS).get('{'+NS['w']+'}val'), '1')
            self.assertFalse(doc.findall('.//w:br[@w:type="page"]', NS))

    def test_source_table_proportions_and_merged_widths_survive(self):
        import pypandoc
        for columns in (['1fr', '3fr'], ['25% + 0pt', '75% + 0pt']):
            value = dict(func='table', columns=columns, children=[
                dict(func='header', children=[dict(func='cell', body=dict(func='text', text=t)) for t in ('A', 'B')]),
                dict(func='cell', colspan=2, body=dict(func='text', text='Spanning row'))])
            tree = pandoc(render().text(value))
            with tempfile.TemporaryDirectory() as folder:
                output = Path(folder)/'widths.docx'
                pypandoc.convert_text(json.dumps(tree), 'docx', format='json', outputfile=str(output),
                                     extra_args=['--reference-doc', str(ROOT/REFERENCE)])
                format_docx(output)
                with zipfile.ZipFile(output) as archive:
                    doc = ET.fromstring(archive.read('word/document.xml'))
                    self.assertEqual([int(c.get('{'+NS['w']+'}w')) for c in doc.findall('.//w:gridCol', NS)], [2340, 7020])
                    self.assertEqual([int(c.get('{'+NS['w']+'}w')) for c in doc.findall('.//w:tcW', NS)], [2340, 7020, 9360])

    def test_reference_styles_are_preserved_and_theme_independent(self):
        import pypandoc
        with tempfile.TemporaryDirectory() as folder:
            reference = Path(folder)/'custom.docx'
            with zipfile.ZipFile(ROOT/REFERENCE) as archive:
                files = {n: archive.read(n) for n in archive.namelist()}
            styles = ET.fromstring(files['word/styles.xml'])
            self.assertFalse(any('theme' in attr.lower() for e in styles.iter() for attr in e.attrib
                                 if e.tag in ('{'+NS['w']+'}rFonts', '{'+NS['w']+'}color')))
            target = styles.find('w:style[@w:styleId="Heading2"]/w:rPr/w:sz', NS)
            target.set('{'+NS['w']+'}val', '30')
            files['word/styles.xml'] = ET.tostring(styles)
            with zipfile.ZipFile(reference, 'w') as archive:
                for name, content in files.items():archive.writestr(name, content)
            output = Path(folder)/'styled.docx'
            pypandoc.convert_text('== A heading\n\nParagraph.', 'docx', format='typst', outputfile=str(output),
                                 extra_args=['--reference-doc', str(reference)])
            format_docx(output)
            with zipfile.ZipFile(output) as archive:
                styles = ET.fromstring(archive.read('word/styles.xml'))
                self.assertEqual(styles.find('w:style[@w:styleId="Heading2"]/w:rPr/w:sz', NS).get('{'+NS['w']+'}val'), '30')
                self.assertEqual(styles.find('w:style[@w:styleId="CaptionedFigure"]/w:pPr/w:spacing', NS).get('{'+NS['w']+'}line'), '240')
                for root in (styles, ET.fromstring(archive.read('word/document.xml'))):
                    for element in root.iter():
                        name = element.tag.rsplit('}', 1)[-1]
                        if name not in ORDERS:continue
                        ranks = {tag: i for i, tag in enumerate(ORDERS[name].split())}
                        order = [ranks.get(e.tag.rsplit('}', 1)[-1], len(ranks)) for e in element]
                        self.assertEqual(order, sorted(order), name)

    def test_captions_never_split_across_a_page(self):
        # A two-line caption broken across a page leaves its first line under
        # the wrong float (dissertation).
        with zipfile.ZipFile(ROOT/REFERENCE) as archive:
            styles = ET.fromstring(archive.read('word/styles.xml'))
        for sid in ('Caption', 'ImageCaption', 'TableCaption'):
            style = styles.find(f'w:style[@w:styleId="{sid}"]', NS)
            self.assertIsNotNone(style, sid)
            self.assertIsNotNone(style.find('w:pPr/w:keepLines', NS), sid)

    def test_word_updates_page_fields_on_open(self):
        # PAGEREF values cached by word_pagination.py are only a fallback; Word
        # recomputes them from its own pagination when updateFields is set.
        import pypandoc
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'fields.docx'
            pypandoc.convert_text('Text.', 'docx', format='markdown', outputfile=str(output),
                                  extra_args=['--reference-doc', str(ROOT/REFERENCE)])
            format_docx(output)
            format_docx(output)          # idempotent: one element, not two
            with zipfile.ZipFile(output) as archive:
                settings = ET.fromstring(archive.read('word/settings.xml'))
            found = settings.findall('w:updateFields', NS)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].get('{'+NS['w']+'}val'), 'true')
            names = [e.tag.rsplit('}', 1)[-1] for e in settings]
            for later in ('footnotePr', 'endnotePr', 'compat', 'rsids'):
                if later in names:
                    self.assertLess(names.index('updateFields'), names.index(later), later)

    def test_front_pages_and_live_contents(self):
        import pypandoc
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'test.docx'
            tree = pandoc('Text.')
            tree['blocks'] = [styled('Title', [paragraph('Dissertation')]),
                styled('Dissertation Title Details', [paragraph('Author')]), pagebreak(),
                styled('Dissertation Copyright', [paragraph('© 2026 Author'), paragraph('All rights reserved.')]),
                pagebreak(), heading(1, 'Acknowledgments', 'ack'), paragraph('Thanks.')]
            tree['blocks'] += index_blocks('Table of Contents', [
                ('ack', 'Acknowledgments', 1), ('dissertation-abstract', 'Dissertation Abstract', 1),
                ('chapter', 'Chapter 1. Title', 1), ('section', 'Section', 2)])
            tree['blocks'] += [heading(1, 'Dissertation Abstract', 'dissertation-abstract'),
                paragraph('Abstract.'), pagebreak(), heading(1, 'Chapter 1. Title', 'chapter'),
                heading(2, 'Section', 'section'), paragraph('Body.')]
            pypandoc.convert_text(json.dumps(tree), 'docx', format='json', outputfile=str(output))
            format_docx(output)
            with zipfile.ZipFile(output) as archive:
                doc = ET.fromstring(archive.read('word/document.xml'))
                sections = doc.findall('.//w:sectPr', NS)
                self.assertEqual([s.find('w:pgNumType', NS).get('{'+NS['w']+'}start') for s in sections], ['1','2','3','1'])
                self.assertEqual([s.find('w:pgMar', NS).get('{'+NS['w']+'}top') for s in sections],
                                 ['3840', '7560', '1440', '1440'])
                self.assertEqual(len(doc.findall('.//w:fldSimple', NS)), 4)
                self.assertFalse(doc.findall('.//w:br[@w:type="page"]', NS))
            pages = {'ack':3, 'dissertation-abstract':7, 'chapter':9, 'section':10}
            self.assertTrue(cache_pages(output, pages))
            self.assertFalse(cache_pages(output, pages))
            with zipfile.ZipFile(output) as archive:
                doc = ET.fromstring(archive.read('word/document.xml'))
                values = [''.join(f.itertext()) for f in doc.iter()
                          if f.tag == '{'+NS['w']+'}fldSimple'
                          or f.get('{'+NS['w']+'}tooltip') == 'Dissertation page number']
                self.assertEqual(values, ['iii','1','3','4'])

    def test_caption_lists_preserve_full_legends_and_formatting(self):
        import pypandoc
        inlines = [node('Str', 'Figure 1:'), node('Space', []),
                   node('Strong', [node('Emph', [node('Str', 'Measured')])]), node('Space', []),
                   node('Str', '0.05'), node('Space', []), node('Str', 'error.'),
                   node('Space', []), node('Str', 'Detailed legend follows.')]
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'captions.docx'
            tree = pandoc('Text.')
            tree['blocks'] = index_blocks('List of Figures', [('figure-one', inlines, 3)])
            pypandoc.convert_text(json.dumps(tree), 'docx', format='json', outputfile=str(output))
            with zipfile.ZipFile(output) as archive:
                doc = ET.fromstring(archive.read('word/document.xml'))
                entry = doc.find('.//w:hyperlink', NS)
                self.assertEqual(''.join(t.text or '' for t in entry.findall('.//w:t', NS)),
                                 'Figure 1: Measured 0.05 error. Detailed legend follows.')
                self.assertIsNotNone(entry.find('.//w:i', NS))
                bold = ''.join(''.join(t.text or '' for t in r.findall('w:t', NS))
                    for r in entry.findall('.//w:r', NS) if r.find('w:rPr/w:b', NS) is not None)
                self.assertEqual(bold, 'Figure 1: Measured 0.05 error.')
                self.assertEqual(inlines[2]['t'], 'Strong')  # source/body caption unchanged
                self.assertIn('figure-one', doc.find('.//w:fldSimple', NS).get('{'+NS['w']+'}instr'))

    def test_titles_are_bold_without_relying_on_source_emphasis(self):
        for text, expected in [
            ('Table 1: Version 4.0.0 supports 0.05 error. Further details.',
             'Table 1: Version 4.0.0 supports 0.05 error.'),
            ('Figure 2: A single sentence.', 'Figure 2: A single sentence.'),
        ]:
            result = caption_title([node('Str', text)])
            self.assertEqual(result[0], node('Strong', [node('Str', expected)]))
            self.assertEqual(''.join(n['c'] for n in result[0]['c']) +
                             ''.join(n['c'] for n in result[1:]), text)
        equation = node('Math', [node('InlineMath', []), 'x^2'])
        value = [node('Str', 'Figure 3: '), equation,
                 node('Emph', [node('Str', ' accuracy. Explanation '),
                               node('Strong', [node('Str', 'with emphasis.')])])]
        result = caption_title(value)
        self.assertIn(equation, result[0]['c'])
        self.assertEqual(result[0]['c'][-1], node('Emph', [node('Str', ' accuracy.')]))
        self.assertFalse(any(n.get('t') == 'Strong' for n in walk(result[1:])))
        self.assertEqual(value[-1]['c'][-1]['t'], 'Strong')

    def test_pdf_bookmark_destinations(self):
        self.assertEqual(destinations('Page  Destination  Name\n  7 [ XYZ 72 720 null ] "dissertation-abstract"\n  31 [ XYZ 72 505 null ] "fig-test"\n'),
                         {'dissertation-abstract':7, 'fig-test':31})

    def test_formatted_package_and_page_number_sections(self):
        import pypandoc
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'test.docx'
            pypandoc.convert_text('= Front matter\n\nText.\n\n= Dissertation Abstract\n\nAbstract text.',
                                 'docx', format='typst', outputfile=str(output))
            format_docx(output)
            with zipfile.ZipFile(output) as archive:
                # OPC package containers must preserve their default namespace
                # for LibreOffice's DOCX importer, even though prefixed XML parses.
                self.assertIn(b'<Types xmlns=', archive.read('[Content_Types].xml'))
                self.assertIn(b'<Relationships xmlns=', archive.read('word/_rels/document.xml.rels'))
                document = ET.fromstring(archive.read('word/document.xml'))
                sections = document.findall('.//w:sectPr/w:pgNumType', NS)
                self.assertEqual([s.get('{'+NS['w']+'}fmt') for s in sections], ['lowerRoman', 'decimal'])
                self.assertIn('word/footer-dissertation.xml', archive.namelist())

    def test_freshness_detects_source_and_output_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = '// >>> BODY START\nOriginal prose.\n// <<< BODY END\n'
            (root/'chapter.typ').write_text(source)
            (root/'american-chemical-society.csl').write_bytes((ROOT/'american-chemical-society.csl').read_bytes())
            (root/REFERENCE).parent.mkdir(parents=True)
            (root/REFERENCE).write_bytes((ROOT/REFERENCE).read_bytes())
            document = Document('chapter', 'chapter.typ', 'chapter.pdf', ('chapter',))
            project = Project(root, 'chapter', {'chapter': Part('chapter', 'chapter.typ')}, {'chapter': document})
            output = root/'chapter.docx'; output.write_bytes(b'last successful output')
            state = word_state(project, document); state.parent.mkdir(parents=True)
            state.write_text(json.dumps(dict(dependencies=[], sources=sources_fingerprint(project, document, []), output_hash=digest(output))))
            check(project, document)
            (root/REFERENCE).write_bytes(b'changed template')
            with self.assertRaisesRegex(ValueError, 'stale Word'):
                check(project, document)
            (root/REFERENCE).write_bytes((ROOT/REFERENCE).read_bytes())
            (root/'chapter.typ').write_text(source.replace('Original', 'Edited'))
            with self.assertRaisesRegex(ValueError, 'stale Word'):
                check(project, document)
            (root/'chapter.typ').write_text(source)
            output.write_bytes(b'manual Word edits')
            with self.assertRaisesRegex(ValueError, 'stale Word'):
                check(project, document)

    def test_unknown_content_fails(self):
        with self.assertRaisesRegex(ValueError, 'refusing to omit'):
            render().text({'func': 'context'})

    def test_missing_citation_fails(self):
        with self.assertRaisesRegex(ValueError, 'missing from chapter'):
            render().text({'func': 'ref', 'target': '<a-absent>'})
        with self.assertRaisesRegex(ValueError, 'foreign chapter'):
            render().text({'func': 'ref', 'target': '<b-shared>'})

    def test_chapter_and_supplement_references_use_native_numbers(self):
        r = render(inventory=[dict(label='sec-test', number='S3.2', supplement='Supplemental Section')])
        self.assertEqual(r.text({'func': 'ref', 'target': '<chap-second>'}), '2')
        self.assertEqual(r.text({'func': 'ref', 'target': '<sec-test>'}), 'Supplemental Section S3.2')
        self.assertEqual(r.text({'func': 'ref', 'target': '<sec-test>', 'supplement': None}), 'S3.2')

    def test_citation_group_is_one_cluster(self):
        state = dict(func='state-update', key='__alexandria-config')
        value = dict(func='sequence', children=[state, dict(func='ref', target='<a-shared>'),
            dict(func='context'), dict(func='ref', target='<a-other>'), state])
        r = render(keys={'shared', 'other'})
        self.assertEqual(r.text(value), '@shared @other')
        self.assertEqual(r.citations, {'shared', 'other'})

    def test_code_is_verbatim(self):
        value = dict(func='raw', text='print("@a-shared", "$m/z$", "#table()")\n  indented', block=True, lang='python')
        tree = pandoc(render().text(value))
        code = next(n for n in walk(tree) if n.get('t') == 'CodeBlock')
        self.assertEqual(code['c'][1], value['text'])

    def test_equation_is_native_math(self):
        value = dict(func='equation', block=True, body=dict(func='frac',
            num=dict(func='attach', base=dict(func='text', text='x'), t=dict(func='text', text='2')),
            denom=dict(func='text', text='n')))
        tree = pandoc(render().text(value))
        equation = next(n for n in walk(tree) if n.get('t') == 'Math')
        self.assertEqual(equation['c'][1], r'\frac{x^{2}}{n}')

    def test_table_header_and_spanning_cell_survive(self):
        value = dict(func='table', columns=['auto', 'auto'], children=[
            dict(func='header', children=[dict(func='cell', body=dict(func='text', text=t)) for t in ('A', 'B')]),
            dict(func='cell', colspan=2, body=dict(func='text', text='Both columns'))])
        tree = pandoc(render().text(value))
        table = next(n for n in walk(tree) if n.get('t') == 'Table')
        self.assertEqual(len(table['c'][2]), 2)
        self.assertIn('Both', json.dumps(table))
        cell = table['c'][4][0][3][0][1][0]
        self.assertEqual(cell[3], 2)

    def test_repeated_keys_are_resolved_per_chapter(self):
        with tempfile.TemporaryDirectory() as folder:
            trees = []
            for prefix, title in [('a-', 'Alpha chapter study'), ('b-', 'Beta chapter study')]:
                bib = Path(folder)/(prefix+'.bib')
                bib.write_text('@article{shared, author={Doe, Jane}, title={' + title + '}, journal={Test Journal}, year={2025}}')
                r = render(prefix=prefix)
                tree = pandoc(r.text(dict(func='ref', target='<'+prefix+'shared>'))+'\n\n== References', bibliography=bib)
                namespace_ids(tree, prefix)
                trees.append(tree)
            self.assertIn('Alpha', json.dumps(trees[0]))
            self.assertNotIn('Beta', json.dumps(trees[0]))
            self.assertIn('Beta', json.dumps(trees[1]))
            for prefix, tree in zip(('a-', 'b-'), trees):
                ids = [n['c'][0][0] for n in walk(tree) if n.get('t') == 'Div']
                self.assertIn(prefix+'ref-shared', ids)
                bibliography = next(n for n in walk(tree) if n.get('t') == 'Div' and n['c'][0][0] == prefix+'refs')
                self.assertIn(['custom-style', 'Bibliography'], bibliography['c'][0][2])
                # ACS numbering starts at 1 independently in each chapter.
                superscripts = [n for n in walk(tree) if n.get('t') == 'Superscript']
                self.assertEqual(superscripts[0]['c'][0]['c'], '1')


if __name__ == '__main__':
    unittest.main()
