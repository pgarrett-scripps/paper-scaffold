"""Populate Word PAGEREF caches using LibreOffice's actual DOCX pagination.

Only cached page numbers are copied back: LibreOffice never rewrites the DOCX.
The temporary PDF is a pagination probe, not a source for document content.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
import zipfile

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
PAGE_LINK = 'Dissertation page number'


def destinations(text):
    return {name: int(page) for page, name in
            re.findall(r'^\s*(\d+)\s+\[.*?\]\s+"(.*)"\s*$', text, re.MULTILINE)}


def roman(number):
    result = ''
    for value, letters in ((1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'),
                          (100, 'c'), (90, 'xc'), (50, 'l'), (40, 'xl'),
                          (10, 'x'), (9, 'ix'), (5, 'v'), (4, 'iv'), (1, 'i')):
        while number >= value:
            result += letters
            number -= value
    return result


def cache_pages(path, pages):
    with zipfile.ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    original = files['word/document.xml']
    document = ET.fromstring(original)
    abstract = pages['dissertation-abstract']
    changed = False
    parents = {child: parent for parent in document.iter() for child in parent}
    for field in list(document.iter()):
        if field.tag == '{'+W+'}fldSimple':
            instruction = field.get('{'+W+'}instr', '').split()
            if not instruction or instruction[0] != 'PAGEREF':
                continue
            target = instruction[1]
        elif field.tag == '{'+W+'}hyperlink' and field.get('{'+W+'}tooltip') == PAGE_LINK:
            target = field.get('{'+W+'}anchor')
        else:
            continue
        if target not in pages:
            raise ValueError(f'Word pagination is missing bookmark {target}')
        page = pages[target]
        value = roman(page) if page < abstract else str(page - abstract + 1)
        # Writer ignores Roman PAGEREF formatting (and fldLock), converting
        # even correctly cached Roman references to Arabic. Use linked text
        # for these few front-matter entries; every pipeline build still
        # recalculates them. Body references remain live Word fields.
        if page < abstract and field.tag == '{'+W+'}fldSimple':
            parent = parents[field]
            link = ET.Element('{'+W+'}hyperlink', {'{'+W+'}anchor': target, '{'+W+'}tooltip': PAGE_LINK})
            link.extend(list(field))
            parent.insert(list(parent).index(field), link)
            parent.remove(field)
            field = link
            changed = True
        text = field.find('.//w:t', NS)
        if text.text != value:
            text.text = value
            changed = True
    if changed:
        for _, (prefix, uri) in ET.iterparse(io.BytesIO(original), events=('start-ns',)):
            if not prefix.startswith('ns'):
                ET.register_namespace(prefix, uri)
        files['word/document.xml'] = ET.tostring(document, encoding='utf-8', xml_declaration=True)
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
    return changed


def paginate(path: Path, root: Path):
    for binary in ('soffice', 'pdfinfo'):
        if shutil.which(binary) is None:
            raise ValueError('Word contents pagination requires LibreOffice (soffice) and Poppler (pdfinfo); install them and rerun just docx')
    with tempfile.TemporaryDirectory(prefix='word-pages-') as folder:
        temp = Path(folder)
        env = os.environ.copy()
        if Path('/etc/fonts/fonts.conf').is_file() and (root/'fonts').is_dir():
            config = temp/'fonts.conf'
            config.write_text('<?xml version="1.0"?><fontconfig><include>/etc/fonts/fonts.conf</include>'
                              '<dir>'+escape(str(root/'fonts'))+'</dir><cachedir>'+escape(str(temp/'font-cache'))
                              +'</cachedir></fontconfig>')
            env['FONTCONFIG_FILE'] = str(config)
        options = json.dumps({'ExportBookmarksToPDFDestination': {'type': 'boolean', 'value': 'true'}})
        for attempt in range(4):
            out = temp/str(attempt)
            out.mkdir()
            result = subprocess.run(['soffice', '-env:UserInstallation='+(temp/'profile').as_uri(),
                '--headless', '--convert-to', 'pdf:writer_pdf_Export:'+options,
                '--outdir', str(out), str(path.resolve())], env=env, capture_output=True, text=True, timeout=180)
            pdf = out/(path.stem+'.pdf')
            if result.returncode or not pdf.exists():
                raise ValueError('Word pagination failed: '+result.stdout+result.stderr)
            info = subprocess.run(['pdfinfo', '-dests', str(pdf)], check=True, capture_output=True, text=True)
            if not cache_pages(path, destinations(info.stdout)):
                return
        raise ValueError('Word page numbers did not stabilize; last successful document preserved')
