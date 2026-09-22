"""Explicitly regenerate the single-paper Word template; builds preserve edits."""
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from export_docx import style_code
from word_xml import order_properties, W

ROOT = Path(__file__).resolve().parent.parent


def create_reference(root=ROOT, *, black_headings=False):
    """Write word/paper-reference.docx from pandoc's default template.

    `black_headings` sets the Title, Subtitle and Heading styles in black
    instead of pandoc's blue, which most journals ask for (five downstream
    papers recoloured them locally). Off by default: the template is the
    author's to edit, and this only seeds it.
    """
    import pypandoc
    target = root / 'word/paper-reference.docx'
    target.parent.mkdir(parents=True, exist_ok=True)
    pypandoc.convert_text('Template seed.', 'docx', format='markdown', outputfile=str(target))
    style_code(target)
    with zipfile.ZipFile(target) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    styles = ET.fromstring(files['word/styles.xml'])
    ns = {'w': W}
    tag = lambda name: '{' + W + '}' + name
    for style in styles.findall('w:style', ns):
        if style.get(tag('styleId')) in ('Figure', 'CaptionedFigure', 'Bibliography'):
            props = style.find('w:pPr', ns)
            if props is None:
                props = ET.SubElement(style, tag('pPr'))
            spacing = props.find('w:spacing', ns)
            if spacing is None:
                spacing = ET.SubElement(props, tag('spacing'))
            spacing.set(tag('line'), '240')
            spacing.set(tag('lineRule'), 'auto')
        name = style.get(tag('styleId')) or ''
        if black_headings and (name in ('Title', 'Subtitle') or name.startswith('Heading')):
            props = style.find('w:rPr', ns)
            if props is None:
                props = ET.SubElement(style, tag('rPr'))
            color = props.find('w:color', ns)
            if color is None:
                color = ET.SubElement(props, tag('color'))
            color.attrib.clear()
            color.set(tag('val'), '000000')
    # Concrete choices must win over theme attributes in Word and Writer alike.
    for element in styles.iter():
        if element.tag == tag('color') and element.get(tag('val')) not in (None, 'auto'):
            for attr in list(element.attrib):
                if 'theme' in attr.lower():
                    del element.attrib[attr]
        if element.tag == tag('rFonts'):
            for face in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
                if element.get(tag(face)):
                    element.attrib.pop(tag('cstheme' if face == 'cs' else face + 'Theme'), None)
    order_properties(styles)
    files['word/styles.xml'] = ET.tostring(styles, encoding='utf-8', xml_declaration=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return target


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--black-headings', action='store_true',
                        help='set the title and headings in black, not blue')
    print(create_reference(black_headings=parser.parse_args().black_headings))
