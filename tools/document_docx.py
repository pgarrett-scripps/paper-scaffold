#!/usr/bin/env python3
"""Build a dissertation or chapter Word file from the existing Typst pipeline.

Typst evaluates the current source and numbering. Each chapter is projected to
plain Typst and processed independently by Pandoc/citeproc, so ACS reference
numbers restart per chapter. The resulting Pandoc trees are joined BEFORE the
single DOCX write, preserving native math, tables, links and embedded artwork.
Publication is atomic and the existing content fingerprint guards freshness.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import io
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

from atomic_io import write_text
from bibliography import entries
from build_state import build_lock, digest
from document_build import build as build_pdf, fingerprint, state_path as pdf_state, status as pdf_status
from document_project import load_project
from word_reference import REFERENCE
from word_xml import order_properties
from manuscript_snapshot import content_text
from word_capture import capture, composed_artwork
from word_content import WordContent, escape
from word_pagination import paginate

from paths import ROOT, locate  # the manuscript (tools/paths.py)
TOOLS = ('document_docx.py', 'word_capture.py', 'word_content.py', 'export_docx.py',
         'export_text.py', 'manuscript_snapshot.py', 'bibliography.py', 'word_pagination.py', 'word_reference.py', 'word_xml.py')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W, 'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math',
      'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture'}


def word_state(project, document):
    return project.root / '.build-state/word' / (document.id + '.json')


def sources_fingerprint(project, document, dependencies):
    result = fingerprint(project, document, dependencies)
    for name in TOOLS:
        result['@word-tool/' + name] = digest(Path(__file__).parent / name)
    result['@word-reference'] = digest(locate(project.root, REFERENCE.as_posix()))
    result['american-chemical-society.csl'] = digest(project.root / 'american-chemical-society.csl')
    return result


def check(project, document):
    path = word_state(project, document)
    if not path.exists():
        raise ValueError(f'{document.id}: missing Word build; run just docx {document.id}')
    state = json.loads(path.read_text())
    output = project.root / Path(document.output).with_suffix('.docx')
    if (not output.is_file() or digest(output) != state['output_hash']
            or sources_fingerprint(project, document, state['dependencies']) != state['sources']):
        raise ValueError(f'{document.id}: stale Word document; run just docx {document.id}')
    return state


def node(kind, content):
    return {'t': kind, 'c': content}


def paragraph(text):
    return node('Para', [node('Str', text)])


def heading(level, text, identifier=''):
    return node('Header', [level, [identifier, [], []], [node('Str', text)]])


def styled(style, blocks):
    return node('Div', [['', [], [['custom-style', style]]], blocks])


def pagebreak():
    return node('RawBlock', ['openxml', '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'])


def pandoc(src, *, bibliography=None, root=ROOT):
    import pypandoc
    args = ['--fail-if-warnings']
    if bibliography:
        args += ['--citeproc', '--bibliography', str(bibliography),
                 '--csl', str(root / 'american-chemical-society.csl')]
    return json.loads(pypandoc.convert_text(src, 'json', format='typst', extra_args=args))


def namespace_ids(value, prefix):
    """Keep citeproc reference anchors distinct across chapter bibliographies."""
    if isinstance(value, list):
        for child in value:
            namespace_ids(child, prefix)
    elif isinstance(value, dict):
        kind, c = value.get('t'), value.get('c')
        if kind == 'Div' and c[0][0] == 'refs':
            # Namespacing disables Pandoc's special handling of id="refs".
            # Keep the Word bibliography style explicit after changing its ID.
            c[0][2].append(['custom-style', 'Bibliography'])
        if kind in ('Div', 'Span', 'CodeBlock', 'Code', 'Link', 'Image', 'Table', 'Figure'):
            if c[0][0] in ('refs',) or c[0][0].startswith('ref-'):
                c[0][0] = prefix + c[0][0]
        if kind == 'Link' and c[2][0].startswith('#ref-'):
            c[2][0] = '#' + prefix + c[2][0][1:]
        for child in value.values():
            namespace_ids(child, prefix)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def regular_weight(value):
    """Remove prose bolding from list captions, preserving other inline content."""
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict) and item.get('t') == 'Strong':
                result.extend(regular_weight(item['c']))
            else:
                result.append(regular_weight(item))
        return result
    if isinstance(value, dict):
        return {key: regular_weight(item) for key, item in value.items()}
    return value


def caption_title(inlines):
    """Bold the opening sentence consistently, keeping the entire caption.

    Work on the inline tree so italics, citations, code and native math survive.
    Decimal/version dots are not sentence boundaries. A one-sentence caption
    is entirely a title; existing emphasis in the explanation is normalized.
    """
    wrappers = {'Emph', 'Underline', 'Strikeout', 'Superscript', 'Subscript', 'SmallCaps'}
    attributed = {'Span', 'Cite', 'Link', 'Quoted'}

    def children(item):
        if item['t'] in wrappers:
            return item['c']
        if item['t'] in attributed:
            return item['c'][1]
        return None

    def visible(item):
        if item['t'] == 'Str':
            return item['c']
        if item['t'] in ('Space', 'SoftBreak', 'LineBreak'):
            return ' '
        nested = children(item)
        # Atomic math/code content cannot introduce a prose sentence boundary.
        return ''.join(visible(c) for c in nested) if nested is not None else '\ufffc'

    def split(items, remaining):
        before, after = [], []
        for item in items:
            length = len(visible(item))
            if remaining >= length:
                before.append(item)
            elif remaining <= 0:
                after.append(item)
            elif item['t'] == 'Str':
                before.append(node('Str', item['c'][:remaining]))
                after.append(node('Str', item['c'][remaining:]))
            else:
                left, right = split(children(item), remaining)
                for target, content in ((before, left), (after, right)):
                    if content:
                        clone = copy.deepcopy(item)
                        if item['t'] in wrappers:
                            clone['c'] = content
                        else:
                            clone['c'][1] = content
                        target.append(clone)
            remaining -= length
        return before, after

    normalized = regular_weight(inlines)
    text = ''.join(visible(item) for item in normalized)
    boundary = re.search(r'[.!?](?=\s|$)', text)
    title, explanation = split(normalized, boundary.end() if boundary else len(text))
    return ([node('Strong', title)] if title else []) + explanation


def index_blocks(title, rows):
    blocks = [heading(1, title)]
    for label, text, level in rows:
        inlines = [node('Str', text)] if isinstance(text, str) else copy.deepcopy(text)
        if level == 3:
            inlines = caption_title(inlines)
        blocks.append(styled('Dissertation Index ' + str(level), [node('Para', [
            node('Link', [['', [], []], inlines, ['#' + label, '']]),
            node('RawInline', ['openxml', '<w:r><w:tab/></w:r>']),
            node('RawInline', ['openxml', '<w:fldSimple w:instr=" PAGEREF ' + label
                 + ' \\h "><w:r><w:t>999</w:t></w:r></w:fldSimple>'])])]))
    return blocks + [pagebreak()]


def front_blocks(data, renderer, chapter_order, chapter_tocs):
    front = data['front']
    if not front:
        return []
    def blocks(value):
        return pandoc(renderer.text(value))['blocks'] if value is not None else []
    title = styled('Title', [paragraph(front['title'])])
    presentation = [paragraph('A dissertation presented'), paragraph('by'),
                    paragraph(front['author']), paragraph('to')]
    presentation += blocks(front['graduate_school'])
    presentation += [paragraph('in partial fulfillment of the requirements'),
                     paragraph('for the degree of'), paragraph(front['degree']),
                     paragraph('for'), paragraph(front['institution']), paragraph(front['location']),
                     paragraph(front['submission_date'] or ('[Month] ' + str(front['year'])))]
    result = [title, styled('Dissertation Title Details', presentation), pagebreak(),
              styled('Dissertation Copyright', [paragraph(f'© {front["year"]} by {front["author"]}'),
                                                    paragraph('All rights reserved.')]), pagebreak()]
    toc = []
    if front['acknowledgments'] is not None:
        result += [heading(1, 'Acknowledgments', 'front-acknowledgments')] + blocks(front['acknowledgments']) + [pagebreak()]
        toc.append(('front-acknowledgments', 'Acknowledgments', 1))
    toc += [('front-contributions', 'Dissertation Co-Author Contributions', 1),
            ('front-figures', 'List of Figures', 1), ('front-tables', 'List of Tables', 1)]
    if front['abbreviations'] is not None:
        toc.append(('front-abbreviations', 'List of Abbreviations', 1))
    toc.append(('dissertation-abstract', 'Dissertation Abstract', 1))
    for chap in data['chapters']:
        identifier = chap['word_chapter']; num = chapter_order.index(identifier) + 1
        toc.append(('chap-' + identifier, f'Chapter {num}. {chap["title"]}', 1))
        toc.extend(chapter_tocs.get(identifier, []))
    result += index_blocks('Table of Contents', toc)
    result += [heading(1, 'Dissertation Co-Author Contributions', 'front-contributions')]
    for chap in data['chapters']:
        num = chapter_order.index(chap['word_chapter']) + 1
        result += [heading(2, f'Chapter {num}. {chap["title"]}')]
        result += blocks(chap['contributions']) + blocks(chap['inclusion'])
    result += [pagebreak()]
    for kind, title in (('Figure', 'List of Figures'), ('Table', 'List of Tables')):
        listing = index_blocks(title, data['caption_lists'][kind])
        listing[0]['c'][1][0] = 'front-' + kind.lower() + 's'
        result += listing
    if front['abbreviations'] is not None:
        result += [heading(1, 'List of Abbreviations', 'front-abbreviations')] + blocks(front['abbreviations']) + [pagebreak()]
    result += [heading(1, 'Dissertation Abstract', 'dissertation-abstract')] + blocks(next(r['body'] for r in data['bodies'] if r['id'] == 'abstract')) + [pagebreak()]
    return result


def format_docx(path):
    """Match manuscript typography and fit native tables to the text area."""
    with zipfile.ZipFile(path) as archive:
        files = {n: archive.read(n) for n in archive.namelist()}
    ET.register_namespace('w', W)
    def serialize(element, original=None):
        namespaces = dict((prefix, uri) for _, (prefix, uri) in ET.iterparse(io.BytesIO(original), events=('start-ns',))) if original else {}
        for prefix, uri in namespaces.items():
            if not prefix.startswith('ns'):
                ET.register_namespace(prefix, uri)
        return ET.tostring(element, encoding='utf-8', xml_declaration=True)
    def tag(n): return '{' + W + '}' + n
    def child(parent, name, **attrs):
        e = parent.find(tag(name))
        if e is None:
            e = ET.SubElement(parent, tag(name))
        e.attrib.update({tag(k): str(v) for k, v in attrs.items()})
        return e
    document = ET.fromstring(files['word/document.xml'])
    for section in document.findall('.//w:sectPr', NS):
        child(section, 'pgSz', w=12240, h=15840)
        child(section, 'pgMar', top=1440, right=1440, bottom=1440, left=1440, header=720, footer=720, gutter=0)
    for table in document.findall('.//w:tbl', NS):
        props = child(table, 'tblPr')
        child(props, 'tblW', type='dxa', w=9360)
        child(props, 'tblLayout', type='fixed')
        cols = table.findall('w:tblGrid/w:gridCol', NS)
        if cols:
            original = [int(col.get(tag('w'))) for col in cols]
            widths = [round(9360 * width / sum(original)) for width in original]
            widths[-1] += 9360 - sum(widths)
            for col, width in zip(cols, widths):
                col.set(tag('w'), str(width))
            for row in table.findall('w:tr', NS):
                before = row.find('w:trPr/w:gridBefore', NS)
                column = int(before.get(tag('val'))) if before is not None else 0
                for cell in row.findall('w:tc', NS):
                    cp = child(cell, 'tcPr')
                    span = cp.find('w:gridSpan', NS)
                    count = int(span.get(tag('val'))) if span is not None else 1
                    child(cp, 'tcW', type='dxa', w=sum(widths[column:column+count]))
                    column += count
        for p in table.findall('.//w:p', NS):
            pp = child(p, 'pPr')
            child(pp, 'pStyle', val='DissertationTableText')
        for row in table.findall('w:tr', NS):
            # Repeating headers continue long tables across page boundaries.
            if row.find('w:trPr/w:tblHeader', NS) is not None:
                continue
            child(child(row, 'trPr'), 'cantSplit')
    # Scale tall/wide inline artwork to the available portrait page area.
    drawing_ns = {'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
                  'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
    for drawing in document.findall('.//w:drawing', NS):
        extent = drawing.find('.//wp:extent', drawing_ns)
        if extent is None:
            continue
        cx, cy = int(extent.get('cx')), int(extent.get('cy'))
        scale = min(1, 5943600 / cx, 6400800 / cy)
        if scale < 1:
            for e in [extent] + drawing.findall('.//a:xfrm/a:ext', drawing_ns):
                e.set('cx', str(round(cx * scale))); e.set('cy', str(round(cy * scale)))
    # Native PAGE fields, Roman front matter and Arabic numbering from Abstract.
    relns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    footer_id = 'rIdDissertationFooter'
    for section in document.findall('.//w:sectPr', NS):
        footer = ET.Element(tag('footerReference'), {tag('type'): 'default', '{'+relns+'}id': footer_id})
        section.insert(0, footer)
        child(section, 'pgNumType', fmt='decimal', start=1)
    body = document.find('w:body', NS)
    # Major divisions are page boundaries even when the source has no explicit
    # break. Chapter abstracts also end before the next peer heading. Ordinary
    # sections/subsections continue naturally; short declarations stay together.
    after_abstract = False
    for p in body.findall('w:p', NS):
        sid = p.find('w:pPr/w:pStyle', NS)
        style = sid.get(tag('val'), '') if sid is not None else ''
        if not re.fullmatch(r'Heading[1-9]', style):
            continue
        level = int(style[7:])
        text = ' '.join(''.join(n.text or '' for n in p.findall('.//w:t', NS)).split())
        props = child(p, 'pPr')
        child(props, 'keepNext', val=1)
        child(props, 'keepLines', val=1)
        major = (level == 1 or (level == 2 and
                 (text.casefold() in ('abstract', 'references', 'bibliography') or
                  re.match(r'^(supplemental|supplementary|appendix|appendices)\b', text, re.I))))
        if major or (after_abstract and level <= 2):
            child(props, 'pageBreakBefore', val=1)
        if level <= 2:
            after_abstract = level == 2 and text.casefold() == 'abstract'
    # A separate page-break paragraph can itself overflow and create a blank
    # page. Put the break on the next content paragraph instead.
    for p in list(body):
        br = p.find('.//w:br', NS)
        if (p.tag == tag('p') and br is not None and br.get(tag('type')) == 'page'
                and not p.findall('.//w:t', NS)):
            index = list(body).index(p)
            following = next((e for e in list(body)[index+1:] if e.tag in (tag('p'), tag('tbl'))), None)
            if following is not None and following.tag == tag('p'):
                child(child(following, 'pPr'), 'pageBreakBefore')
                body.remove(p)
    # Paragraphs with images must stay with the following caption; table
    # captions must stay with at least the first table row.
    for p in body.findall('w:p', NS):
        sid = p.find('w:pPr/w:pStyle', NS)
        if p.find('.//w:drawing', NS) is not None or (sid is not None and sid.get(tag('val')) == 'TableCaption'):
            child(child(p, 'pPr'), 'keepNext')
    paragraphs = body.findall('w:p', NS)
    for p, following in zip(paragraphs, paragraphs[1:]):
        sid = p.find('w:pPr/w:pStyle', NS)
        next_sid = following.find('w:pPr/w:pStyle', NS)
        if (sid is not None and next_sid is not None
                and sid.get(tag('val')) == 'DissertationIndex1'
                and next_sid.get(tag('val')) == 'DissertationIndex2'):
            child(child(p, 'pPr'), 'keepNext')
    # Vertically centered, dedicated title and copyright pages. End each
    # section on its last content paragraph to avoid accidental empty pages.
    for style_id in ('DissertationTitleDetails', 'DissertationCopyright'):
        paragraphs = [p for p in body.findall('w:p', NS)
                      if p.find('w:pPr/w:pStyle', NS) is not None
                      and p.find('w:pPr/w:pStyle', NS).get(tag('val')) == style_id]
        if not paragraphs:
            continue
        section = copy.deepcopy(body.find('w:sectPr', NS))
        child(section, 'type', val='nextPage')
        # Writer ignores Word's vertical section alignment. Explicit top
        # insets and line spacing reproduce the source title/copyright layout
        # consistently in both applications instead of relying on vAlign.
        child(section, 'pgMar', top=3840 if style_id == 'DissertationTitleDetails' else 7560)
        child(section, 'pgNumType', fmt='lowerRoman', start=1 if style_id == 'DissertationTitleDetails' else 2)
        child(child(paragraphs[-1], 'pPr'), 'spacing', before=0, after=0, line=526, lineRule='exact')
        child(paragraphs[-1], 'pPr').append(section)
        following = next((p for p in list(body)[list(body).index(paragraphs[-1])+1:] if p.tag == tag('p')), None)
        if following is not None:
            child(child(following, 'pPr'), 'pageBreakBefore', val=0)
    for index, p in enumerate(list(body)):
        text = ''.join(n.text or '' for n in p.findall('.//w:t', NS))
        if p.tag == tag('p') and text == 'Dissertation Abstract':
            child(child(p, 'pPr'), 'pageBreakBefore', val=0)
            previous = body[index-1]
            if previous.find('.//w:br', NS) is not None:
                body.remove(previous)
                index -= 1
            ending = ET.Element(tag('p'))
            props = child(ending, 'pPr')
            front_section = copy.deepcopy(body.find('w:sectPr', NS))
            child(front_section, 'type', val='nextPage')
            child(front_section, 'pgNumType', fmt='lowerRoman', start=1)
            if any(p.find('w:pPr/w:sectPr', NS) is not None for p in body.findall('w:p', NS)):
                child(front_section, 'pgNumType', fmt='lowerRoman', start=3)
            props.append(front_section)
            body.insert(index, ending)
            break
    files['word/footer-dissertation.xml'] = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<w:ftr xmlns:w="'+W+'"><w:p><w:pPr><w:jc w:val="right"/></w:pPr>'
        '<w:fldSimple w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple></w:p></w:ftr>').encode()
    relationships = ET.fromstring(files['word/_rels/document.xml.rels'])
    ET.SubElement(relationships, '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',
                  Id=footer_id, Type=relns+'/footer', Target='footer-dissertation.xml')
    files['word/_rels/document.xml.rels'] = serialize(relationships, files['word/_rels/document.xml.rels'])
    types = ET.fromstring(files['[Content_Types].xml'])
    ET.SubElement(types, '{http://schemas.openxmlformats.org/package/2006/content-types}Override',
                  PartName='/word/footer-dissertation.xml', ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml')
    files['[Content_Types].xml'] = serialize(types, files['[Content_Types].xml'])
    order_properties(document)
    files['word/document.xml'] = serialize(document, files['word/document.xml'])
    # Word recalculates every PAGEREF field on open, so Word's own pagination
    # decides the contents, figure and table page numbers for the reader.
    # word_pagination.py's cached values remain the fallback for viewers that
    # do not update fields, and for the front-matter Roman entries it has to
    # write as literal text.
    settings = ET.fromstring(files['word/settings.xml'])
    if settings.find(tag('updateFields')) is None:
        # CT_Settings is an ordered sequence: updateFields belongs before the
        # note, compatibility and revision blocks that follow it.
        tail = ('hdrShapeDefaults', 'footnotePr', 'endnotePr', 'compat', 'docVars',
                'rsids', 'attachedSchema', 'themeFontLang', 'clrSchemeMapping')
        positions = [i for i, e in enumerate(settings) if e.tag in {tag(n) for n in tail}]
        element = ET.Element(tag('updateFields'), {tag('val'): 'true'})
        settings.insert(positions[0] if positions else len(settings), element)
    files['word/settings.xml'] = serialize(settings, files['word/settings.xml'])
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)


def build(project, document):
    # Reuse the scaffold's native compile and dependency discovery. Its PDF is
    # authoritative for source validation; Word never converts that PDF.
    print(f'{document.id}: validating current Typst source', flush=True)
    os.environ['TYPST_FONT_PATHS'] = os.pathsep.join(filter(None, (str(project.root/'fonts'), os.environ.get('TYPST_FONT_PATHS'))))
    if pdf_status(project, document) != 'current':
        build_pdf(project, document)
    native = json.loads(pdf_state(project, document).read_text())
    dependencies = native['dependencies']
    with build_lock(project.root), tempfile.TemporaryDirectory(prefix='word-build-', dir=project.root/'.build-state') as folder:
        temp = Path(folder)
        if fingerprint(project, document, dependencies) != native['sources']:
            raise ValueError('sources changed after native validation; rerun Word export')
        before = sources_fingerprint(project, document, dependencies)
        data, sources = capture(project, document, temp/'capture')
        data['caption_lists'] = {'Figure': [], 'Table': []}
        artwork = composed_artwork(project, data, sources, temp/'capture')
        chapter_order = [p for p in project.documents[project.default].parts
                         if project.parts[p].source != project.documents[project.default].entrypoint]
        all_blocks, chapter_tocs = [], {}
        expected = Counter()
        renderers = []
        for row in data['bodies']:
            if row['id'] == 'abstract':
                continue
            part = project.parts[row['id']]
            keys = {e['_key'] for e in entries(project.root/part.bibliography)} if part.bibliography else set()
            renderer = WordContent(project.root, part.source, part.citation_prefix, keys,
                                   data['inventory'], chapter_order, artwork)
            chapter = next(c for c in data['chapters'] if c['word_chapter'] == part.id)
            num = chapter_order.index(part.id) + 1
            title = f'Chapter {num}. {chapter["title"]}'
            prefix = '= ' + escape(title) + ' <chap-' + part.id + '>\n\n'
            for field in ('authors', 'citation'):
                prefix += renderer.text(chapter[field]) + '\n\n'
            prefix += '== Co-Author Contributions\n\n' + renderer.text(chapter['contributions']) + '\n\n' + renderer.text(chapter['inclusion']) + '\n\n'
            title_tree = pandoc(prefix)['blocks'] + [pagebreak()]
            src = renderer.text(row['body'])
            (temp/(part.id+'.word.typ')).write_text(src)
            tree = pandoc(src + '\n\n== References\n', bibliography=project.root/part.bibliography if part.bibliography else None, root=project.root)
            namespace_ids(tree['blocks'], part.id + '-')
            # Give section headings stable Word bookmarks and use those same
            # bookmarks in the front-matter navigation list.
            sections = []
            section_index = 0
            for item in tree['blocks']:
                if item['t'] == 'Header':
                    section_index += 1
                    if not item['c'][1][0]:
                        item['c'][1][0] = f'{part.id}-section-{section_index}'
                    if item['c'][0] == 2:
                        sections.append((item['c'][1][0], copy.deepcopy(item['c'][2]), 2))
            chapter_tocs[part.id] = sections
            actual = Counter(n.get('t') for n in walk(tree['blocks']))
            if actual['Table'] != renderer.tables or actual['Math'] != renderer.equations:
                raise ValueError(f'{part.id}: Pandoc lost native tables or equations: {actual["Table"]}/{renderer.tables}, {actual["Math"]}/{renderer.equations}')
            if actual['Figure'] + actual['Table'] != len(renderer.used_figures):
                raise ValueError(f'{part.id}: Pandoc did not preserve every figure/caption')
            floats = [n for n in walk(tree['blocks']) if n.get('t') in ('Figure', 'Table')]
            for label, item in zip(renderer.used_figures, floats):
                caption = [inline for block in item['c'][1][1] for inline in block['c']]
                # A linked list entry cannot contain a nested external link.
                def unlink(items):
                    out = []
                    for inline in items:
                        if inline['t'] == 'Link':
                            out.extend(unlink(inline['c'][1]))
                        else:
                            out.append(copy.deepcopy(inline))
                    return out
                data['caption_lists'][item['t']].append((label, unlink(caption), 3))
            refs = [n for n in walk(tree['blocks']) if n.get('t') == 'Div' and n['c'][0][0].startswith(part.id+'-ref-')]
            if len(refs) != len(renderer.citations):
                raise ValueError(f'{part.id}: bibliography entries differ from cited keys')
            expected.update(tables=renderer.tables, equations=renderer.equations,
                            figures=len(renderer.used_figures)-renderer.tables, references=len(refs))
            renderers.append(renderer)
            all_blocks += title_tree + tree['blocks'] + [pagebreak()]
            print(f'{part.id}: {len(refs)} references, {renderer.tables} editable tables, {renderer.equations} native equations', flush=True)
        used = [label for r in renderers for label in r.used_figures]
        inventory_figures = [r['label'] for r in data['inventory'] if r['kind']=='figure']
        if used != inventory_figures:
            raise ValueError('Word figures/tables differ from compiled source order')
        renderer = WordContent(project.root, document.entrypoint, '', set(), data['inventory'], chapter_order, artwork)
        front = front_blocks(data, renderer, chapter_order, chapter_tocs)
        expected['equations'] += renderer.equations
        tree['blocks'] = front + all_blocks[:-1]
        tree['meta'] = {}
        expected['equations'] = sum(n.get('t') == 'Math' for n in walk(tree['blocks']))
        import pypandoc
        output = temp/'output.docx'
        pypandoc.convert_text(json.dumps(tree), 'docx', format='json', outputfile=str(output), extra_args=['--fail-if-warnings', '--reference-doc', str(locate(project.root, REFERENCE.as_posix()))])
        format_docx(output)
        if data['front']:
            print('dissertation: calculating Word contents and list page numbers', flush=True)
            try:
                paginate(output, project.root)
            except Exception as error:
                # Word repopulates the page numbers itself through updateFields.
                # Other viewers show the uncached placeholders until then, so
                # this degrades the contents lists rather than the document.
                print(f'dissertation: page-number cache unavailable ({error}); '
                      'Word will fill the contents lists on open, other viewers '
                      'will show placeholders', flush=True)
        with zipfile.ZipFile(output) as z:
            xml = ET.fromstring(z.read('word/document.xml'))
        counts = dict(tables=len(xml.findall('.//w:tbl', NS)), equations=len(xml.findall('.//m:oMath', NS)),
                      figures=len(xml.findall('.//pic:pic', NS)), references=expected['references'])
        if any(counts[k] != expected[k] for k in ('tables', 'equations', 'figures')):
            raise ValueError(f'DOCX content count mismatch: {counts} vs {dict(expected)}')
        bookmark_names = [e.get('{'+W+'}name') for e in xml.findall('.//w:bookmarkStart', NS)]
        anchors = {e.get('{'+W+'}anchor') for e in xml.findall('.//w:hyperlink', NS) if e.get('{'+W+'}anchor')}
        if len(bookmark_names) != len(set(bookmark_names)) or anchors - set(bookmark_names):
            raise ValueError('Word contains duplicate bookmarks or broken internal links')
        if sources_fingerprint(project, document, dependencies) != before:
            raise ValueError('sources changed during Word export; last good DOCX preserved')
        target = project.root / Path(document.output).with_suffix('.docx')
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(output, target)
        state = dict(document=document.id, dependencies=dependencies, sources=before,
                     output_hash=digest(target), counts=counts)
        write_text(word_state(project, document), json.dumps(state, indent=2)+'\n')
        return target, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document', nargs='?', default='')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        project = load_project(args.root)
        for document in project.select(args.document):
            if args.check:
                check(project, document)
                print(f'{document.id}: Word document is current')
            else:
                output, state = build(project, document)
                print(f'wrote {output} ({output.stat().st_size/1e6:.1f} MB): {state["counts"]}')
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as exc:
        print(f'Word export incomplete: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
