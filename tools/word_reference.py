"""Create the reusable Pandoc Word style reference; builds never overwrite it."""
from __future__ import annotations
import argparse
import io
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
from export_docx import style_code
from word_xml import order_properties

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
ROOT = Path(__file__).resolve().parent.parent
REFERENCE = Path('word/reference.docx')


def style_reference(path):
    style_code(path)
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
    styles = ET.fromstring(files['word/styles.xml'])
    defaults = child(child(styles, 'docDefaults'), 'rPrDefault')
    rp = child(defaults, 'rPr')
    child(rp, 'rFonts', ascii='Times New Roman', hAnsi='Times New Roman', eastAsia='Times New Roman', cs='Times New Roman')
    child(rp, 'sz', val=22)
    for style in styles.findall('w:style', NS):
        sid = style.get(tag('styleId'))
        if sid == 'Hyperlink':
            rp = child(style, 'rPr')
            child(rp, 'color', val='000000')
            child(rp, 'u', val='none')
        if style.get(tag('type')) != 'paragraph':
            continue
        rp, pp = child(style, 'rPr'), child(style, 'pPr')
        child(rp, 'color', val='000000')
        child(pp, 'spacing', before=0, after=120, line=480, lineRule='auto')
        if sid in ('Normal', 'BodyText', 'FirstParagraph', 'Compact'):
            child(rp, 'sz', val=22)
        if sid and sid.startswith('Heading'):
            level = int(sid[7:])
            child(rp, 'sz', val=28 if level == 1 else 24 if level == 2 else 22)
            child(rp, 'b')
            child(pp, 'spacing', before=240, after=120, line=240, lineRule='auto')
            child(pp, 'keepNext')
        if sid in ('Caption', 'ImageCaption', 'TableCaption', 'Bibliography'):
            child(rp, 'sz', val=18 if sid != 'Bibliography' else 22)
            child(pp, 'spacing', before=80, after=120, line=240, lineRule='auto')
        if sid == 'Title':
            child(rp, 'sz', val=28); child(rp, 'b')
            child(pp, 'jc', val='center')
            child(pp, 'spacing', before=0, after=480, line=360, lineRule='auto')
        if sid in ('DissertationTitleDetails', 'DissertationCopyright'):
            child(rp, 'sz', val=24)
            child(pp, 'jc', val='center')
            child(pp, 'spacing', before=0, after=0, line=526, lineRule='exact')
        if sid in ('DissertationIndex1', 'DissertationIndex2', 'DissertationIndex3'):
            child(rp, 'sz', val=22)
            child(rp, 'b', val=1 if sid == 'DissertationIndex1' else 0)
            child(pp, 'spacing', before=100 if sid == 'DissertationIndex1' else 0,
                  after=80, line=240, lineRule='auto')
            child(pp, 'ind', left=360 if sid == 'DissertationIndex2' else 0, right=360)
            child(pp, 'keepLines')
            child(pp, 'keepNext', val=0)
            child(child(pp, 'tabs'), 'tab', val='right', leader='dot', pos=9360)
        if sid == 'SourceCode':
            child(rp, 'sz', val=16)
            child(pp, 'spacing', before=100, after=100, line=200, lineRule='auto')
        if sid in ('Figure', 'CaptionedFigure'):
            # Double-spacing an inline image also doubles its line box.
            child(pp, 'spacing', before=0, after=0, line=240, lineRule='auto')
        if sid == 'DissertationTableText':
            child(rp, 'sz', val=18)
            child(pp, 'spacing', before=0, after=40, line=220, lineRule='auto')
    for fonts in styles.findall('.//w:rFonts', NS):
        for attr in list(fonts.attrib):
            if 'theme' in attr.lower():
                del fonts.attrib[attr]
    for color in styles.findall('.//w:color', NS):
        # Word resolves themeColor ahead of val; Writer can use val instead.
        for attr in list(color.attrib):
            if 'theme' in attr.lower():
                del color.attrib[attr]
    for rp in styles.findall('.//w:rPr', NS):
        size = rp.find('w:sz', NS)
        if size is not None:
            child(rp, 'szCs', val=size.get(tag('val')))
    order_properties(styles)
    files['word/styles.xml'] = serialize(styles, files['word/styles.xml'])
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)


def create_reference(root=ROOT):
    import pypandoc
    target = root / REFERENCE
    target.parent.mkdir(parents=True, exist_ok=True)
    styles = ['Dissertation Title Details', 'Dissertation Copyright',
              'Dissertation Index 1', 'Dissertation Index 2', 'Dissertation Index 3',
              'Dissertation Table Text']
    sample = '\n\n'.join('::: {custom-style="' + name + '"}\nSample\n:::' for name in styles)
    pypandoc.convert_text(sample, 'docx', format='markdown', outputfile=str(target))
    style_reference(target)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    print(create_reference(args.root))
