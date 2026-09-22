"""Capture chapter bodies, front matter and native numbering without source edits."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

from export_text import overlay, instrument
from manuscript_sources import mask

PROBE = r'''
#context [#metadata((word_inventory: true,
  elements: query(selector(figure).or(heading).or(math.equation)).map(e => {
    let num = if e.numbering == none { none } else {
      let c = if e.func() == figure { e.counter } else { counter(e.func()) }
      numbering(e.numbering, ..c.at(e.location()))
    }
    (kind: repr(e.func()), label: if e.has("label") { str(e.label) } else { none },
     number: num, supplement: e.at("supplement", default: none), element: e)
  }),
)) <word-export>]
'''


def run(args, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise ValueError(result.stderr.strip() or f'command failed: {args}')
    if result.stderr.strip():
        print(result.stderr.strip())
    return result.stdout


def replace_once(source, needle, replacement):
    if source.count(needle) != 1:
        raise ValueError('Word capture template changed; update its explicit adapter: ' + needle)
    return source.replace(needle, replacement, 1)


def capture(project, document, destination):
    for name in ('lib/template.typ', 'lib/supplements.typ'):
        if not (project.root / name).is_file():
            raise ValueError('This Word adapter requires the dissertation template contract; '
                             'see docs/multi-document.md and examples/dissertation (missing ' + name + ')')
    sources = project.sources(document)
    overlay(project.root, destination, sources)
    for identifier in document.parts:
        name = project.parts[identifier].source
        (destination / name).write_text(instrument(sources[name], name, identifier))
    path = destination / 'lib/template.typ'
    src = path.read_text()
    src = replace_once(src, '  set document(title: title, author: author)', '''  [#metadata((word_front: true, title: title, author: author, year: year, degree: degree,
    graduate_school: graduate-school, institution: institution, location: location,
    submission_date: submission-date, acknowledgments: acknowledgments,
    abbreviations: abbreviations)) <word-export>]
  set document(title: title, author: author)''')
    src = replace_once(src, '  let number = chapter-number(id)', '''  [#metadata((word_chapter: id, title: title, authors: authors, citation: citation,
    contributions: contributions, inclusion: inclusion)) <word-export>]
  let number = chapter-number(id)''')
    path.write_text(src)
    path = destination / 'lib/supplements.typ'
    src = replace_once(path.read_text(), '  body\n}',
                      '  metadata((word_skip: "supplement-counter"))\n  body\n}')
    path.write_text(src)
    probe = destination / 'word-probe.typ'
    probe.write_text('#include ' + json.dumps(document.entrypoint) + '\n' + PROBE)
    result = run(['typst', 'query', '--root', str(destination), '--font-path', str(project.root / 'fonts'),
                  str(probe), 'metadata', '--field', 'value'], cwd=destination)
    rows = [r for r in json.loads(result) if isinstance(r, dict)]
    bodies = [r for r in rows if set(r) == {'id', 'body'}]
    if [r['id'] for r in bodies] != list(document.parts):
        raise ValueError('Word body order differs from manuscript.toml')
    inventory = [r['elements'] for r in rows if r.get('word_inventory')]
    front = [r for r in rows if r.get('word_front')]
    chapters = [r for r in rows if 'word_chapter' in r]
    expected = [p for p in document.parts if project.parts[p].source != document.entrypoint]
    # A standalone wrapper's sole part is also a chapter.
    if [r['word_chapter'] for r in chapters] != expected or len(inventory) != 1:
        raise ValueError('Word chapter metadata differs from the selected document')
    if len(front) != (1 if document.id == project.default else 0):
        raise ValueError('unexpected dissertation front matter')
    return dict(bodies=bodies, chapters=chapters, front=front[0] if front else None,
                inventory=inventory[0]), sources


def composed_artwork(project, data, sources, destination):
    """Compile composed artwork from its original expression, preserving crops.

    Single images embed directly. Only composed image figures need rasterizing;
    their captions and every table/equation outside artwork remain editable.
    """
    artwork = {'__directory__': destination}
    for row in data['inventory']:
        if row['kind'] != 'figure' or row['element']['kind'] != 'image':
            continue
        if row['element']['body']['func'] == 'image':
            continue
        label = row['label']
        found = []
        for name, src in sources.items():
            visible = mask(src, strings=True)
            for start in re.finditer(r'#figure\s*\(', visible):
                depth, end = 1, start.end()
                while depth and end < len(visible):
                    depth += (visible[end] == '(') - (visible[end] == ')')
                    end += 1
                tail = re.match(r'\s*<([^>]+)>', src[end:])
                if tail and tail[1] == label:
                    found.append((name, src, start.start(), end))
        if len(found) != 1:
            raise ValueError(f'cannot locate original composed artwork {label}')
        name, src, start, end = found[0]
        # Imports/local drawing helpers precede the chapter title. This retains
        # lexical image paths and native font definitions in the captured tree.
        preamble = src[:src.index('#chapter-title-page(')]
        target = destination / Path(name).parent / ('word-art-' + label + '.typ')
        target.write_text(preamble + '\n#set page(width: 6.5in, height: auto, margin: 0pt)\n'
                          '#show figure: it => it.body\n' + src[start:end])
        output = destination / ('word-art-' + label + '.png')
        run(['typst', 'compile', '--root', str(destination), '--font-path', str(project.root/'fonts'),
             '--ppi', '220', str(target), str(output)], cwd=destination)
        artwork[label] = output
    return artwork
