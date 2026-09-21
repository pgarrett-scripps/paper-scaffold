#!/usr/bin/env python3
"""Export current manuscript prose and numbered captions as UTF-8 review text.

Typst evaluates a temporary source overlay, preserving include scopes and
computed values. BODY markers select prose; no PDF or stale resolved export is
read. Images, table bodies, and bibliographies are deliberately omitted.
Unknown evaluated constructs fail rather than silently removing manuscript text.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from atomic_io import write_text
from document_project import body_span, load_project
from manuscript_sources import matches, source_files, without_si_bibliography

ROOT = Path(__file__).resolve().parent.parent

INVENTORY = r'''
#context [#metadata((
  inventory: true,
  figures: query(figure).map(it => (
    label: if it.has("label") { str(it.label) } else { none },
    number: if it.numbering == none { none } else {
      numbering(it.numbering, ..it.counter.at(it.location()))
    },
    supplement: it.supplement,
    caption: it.caption,
  )),
)) <review-export>]
'''


def instrument_span(source: str, start: int, end: int, identifier: str) -> str:
    return (source[:start] + '#let scaffold-review-body = [\n'
            + source[start:end] + '\n]\n#scaffold-review-body\n'
            + '#metadata((id: ' + json.dumps(identifier)
            + ', body: scaffold-review-body)) <review-export>\n' + source[end:])


def instrument(source: str, name: str, identifier: str) -> str:
    return instrument_span(source, *body_span(source, name), identifier)


def overlay(root: Path, destination: Path, sources: dict[str, str]) -> None:
    """Copy Typst inputs; link other inputs without copying large datasets."""
    def visit(src: Path, dst: Path):
        dst.mkdir(exist_ok=True)
        for child in src.iterdir():
            name = child.relative_to(root).as_posix()
            target = dst / child.name
            if name in sources:
                target.write_text(sources[name], encoding="utf-8")
            elif any(path.startswith(name + '/') for path in sources):
                visit(child, target)
            elif not child.name.startswith('.'):
                target.symlink_to(child, target_is_directory=child.is_dir())
    visit(root, destination)


class Renderer:
    def __init__(self, figures: list[dict]):
        self.figures = figures
        self.by_label = {row['label']: row for row in figures if row['label']}
        self.used: set[int] = set()

    def figure_name(self, row: dict) -> str:
        return ' '.join(filter(None, (self.text(row['supplement']),
                                      self.text(row['number']))))

    def text(self, value) -> str:
        if value is None:
            return ''
        if isinstance(value, (str, int, float)):
            return str(value)
        if isinstance(value, list):
            return ''.join(self.text(item) for item in value)
        if not isinstance(value, dict):
            raise ValueError(f'unsupported content: {value!r}')
        kind = value.get('func')
        if kind in ('text', 'symbol', 'op'):
            return re.sub(r'\s+', ' ', self.text(value['text']))
        if kind == 'sequence':
            children = value['children']
            # Alexandria citegroup emits refs plus a context that only arranges
            # those citations. Keep their keys, without duplicating that context.
            citation_group = (len(children) >= 3
                              and children[0].get('func') == 'state-update'
                              and children[0].get('key') == '__alexandria-config'
                              and children[-1] == children[0]
                              and all(c.get('func') in ('ref', 'context', 'state-update')
                                      for c in children))
            return ''.join(self.text(c) for c in children
                           if not (citation_group and c.get('func') in
                                   ('context', 'state-update')))
        if kind in ('space', 'h'):
            return ' '
        if kind in ('parbreak', 'pagebreak', 'colbreak', 'v'):
            return '\n\n'
        if kind == 'linebreak':
            return '\n'
        if kind == 'smartquote':
            return '"' if value.get('double', True) else "'"
        if kind in ('image', 'table', 'bibliography', 'metadata', 'counter-update'):
            return ''
        if kind == 'ref':
            target = value['target'].strip('<>')
            if target in self.by_label:
                row = self.by_label[target]
                return (self.text(row['number']) if value.get('supplement', 'auto') is None
                        else self.figure_name(row))
            return '[' + target.strip('<>') + ']'
        if kind == 'cite':
            return '[' + ', '.join(str(k).strip('<>') for k in value['keys']) + ']'
        if kind == 'figure':
            label = value.get('label', '').strip('<>')
            matches = [(i, row) for i, row in enumerate(self.figures)
                       if i not in self.used and
                       (row['label'] == label if label else
                        (row['caption'] or {}).get('body') == (value.get('caption') or {}).get('body'))]
            if not matches:
                raise ValueError(f'cannot match caption {label!r} to compiled figures {[r["label"] for r in self.figures]}')
            index, row = matches[0]
            self.used.add(index)
            caption = self.text(value.get('caption'))
            return '\n\n' + self.figure_name(row) + (': ' + caption if caption else '') + '\n\n'
        if kind == 'equation':
            body = self.text(value['body'])
            return '\n\n' + body + '\n\n' if value.get('block') else body
        if kind == 'frac':
            return '(' + self.text(value['num']) + ')/(' + self.text(value['denom']) + ')'
        if kind == 'attach':
            body = self.text(value['base'])
            for key, mark in (('bl', '_'), ('tl', '^')):
                if key in value:
                    body = mark + '(' + self.text(value[key]) + ')' + body
            for key, mark in (('b', '_'), ('t', '^'), ('br', '_'), ('tr', '^')):
                if key in value:
                    body += mark + '(' + self.text(value[key]) + ')'
            return body
        if kind in ('super', 'sub'):
            return ('^' if kind == 'super' else '_') + '(' + self.text(value['body']) + ')'
        if kind == 'root':
            return ('sqrt' if value.get('index') is None else 'root[' + self.text(value['index']) + ']') + '(' + self.text(value['radicand']) + ')'
        if kind == 'accent':
            return self.text(value['base']) + self.text(value['accent'])
        if kind == 'raw':
            return '\n\n' + value['text'] + '\n\n' if value.get('block') else value['text']
        if kind in ('heading', 'block', 'quote', 'list', 'enum', 'item'):
            return '\n\n' + self.text(value['body']) + '\n\n'
        if kind == 'styled':
            return self.text(value['child'])
        if kind in ('emph', 'strong', 'underline', 'strike', 'smallcaps',
                    'box', 'align', 'pad', 'link', 'caption', 'lr', 'text',
                    'upright', 'bold', 'italic', 'cancel', 'class'):
            return self.text(value['body'])
        if kind == 'footnote':
            return ' [Footnote: ' + self.text(value['body']) + ']'
        raise ValueError(f'unsupported Typst content {kind!r}; export stopped to avoid losing text')


def normalize(text: str) -> str:
    # Preserve paragraph and code line boundaries; remove indentation on prose
    # only when Typst represents it as ordinary spaces, not raw code content.
    text = text.replace('\u00a0', ' ').replace('\u202f', ' ')
    text = re.sub(r'[ \t]+\n', '\n', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip() + '\n'


def export(root: Path, document: str | None = None) -> list[Path]:
    root = root.resolve()
    project = load_project(root) if (root / 'manuscript.toml').is_file() else None
    if project:
        selected = project.select(document)
    else:
        if document not in (None, '', 'paper', 'all'):
            raise ValueError('single-paper projects accept only paper or all')
        from document_project import Document
        selected = [Document('paper', 'paper.typ', 'paper.pdf', ('paper',))]
    outputs = []
    for doc in selected:
        sources = project.sources(doc) if project else source_files(root, (doc.entrypoint,))
        stats_before = (root / 'stats.json').read_bytes() if (root / 'stats.json').is_file() else None
        # Refresh numeric displays in the overlay, without altering live inputs.
        with tempfile.TemporaryDirectory(prefix='manuscript-review-') as folder:
            temp = Path(folder)
            overlay(root, temp, sources)
            if (root / 'stats.json').is_file():
                import render_stats
                rendered = temp / 'stats-rendered.json'
                if rendered.is_symlink():
                    rendered.unlink()
                if render_stats.render(root / 'stats.json', rendered):
                    raise ValueError('could not render current manuscript statistics')
            expected = list(doc.parts)
            if project:
                for identifier in doc.parts:
                    name = project.parts[identifier].source
                    (temp / name).write_text(instrument(sources[name], name, identifier), encoding='utf-8')
            else:
                paper = sources['paper.typ']
                # Preserve declarations and acknowledgments between BODY END
                # and the bibliography, while keeping the bibliography out.
                _, end = body_span(paper, 'paper.typ')
                start = paper.index('\n', end) + 1
                bibs = matches(re.compile(r'#bibliography\s*\('), paper)
                if bibs and bibs[0].start() > start:
                    paper = instrument_span(paper, start, bibs[0].start(), 'back')
                    expected.append('back')
                (temp / 'paper.typ').write_text(instrument(paper, 'paper.typ', 'paper'), encoding='utf-8')
                # SI has its own include scope and deliberately has no BODY markers.
                if 'si-body.typ' in sources:
                    name = 'si-body.typ'
                    # The SI's own reference list goes the way the main one
                    # does: cut from the source, not filtered out of the
                    # evaluated content. Alexandria renders it inside a
                    # `context`, which Typst hands back opaque -- and an
                    # opaque node is exactly what this exporter must keep
                    # refusing, rather than learn to drop and risk dropping
                    # prose with it.
                    si_src = without_si_bibliography(sources[name],
                                                     sources['paper.typ'])
                    (temp / name).write_text('#let scaffold-review-si = [\n' + si_src
                        + '\n]\n#scaffold-review-si\n#metadata((id: "si", body: scaffold-review-si)) <review-export>\n', encoding='utf-8')
                    expected.append('si')
            probe = '#include ' + json.dumps(doc.entrypoint) + '\n'
            if not project:
                probe += ('#import "config.typ": paper-title, paper-abstract\n'
                          '#metadata((id: "front", body: [#paper-title\n\nAbstract\n\n#paper-abstract])) <review-export>\n')
            (temp / 'review-export.typ').write_text(probe + INVENTORY, encoding='utf-8')
            result = subprocess.run(['typst', 'query', '--root', str(temp),
                                     str(temp / 'review-export.typ'), '<review-export>', '--field', 'value'],
                                    cwd=temp, check=True, text=True, capture_output=True)
            if result.stderr:
                print(result.stderr, file=sys.stderr, end='')
            rows = json.loads(result.stdout)
            inventory = [row for row in rows if row.get('inventory')]
            bodies = [row for row in rows if 'id' in row]
            actual = [row['id'] for row in bodies if row['id'] != 'front']
            if actual != expected or len(inventory) != 1:
                raise ValueError(f'exported parts differ from expected order: {actual} vs {expected}')
            renderer = Renderer(inventory[0]['figures'])
            blocks = ['REVIEW COPY: Images, table bodies, and reference lists omitted. '
                      'Bracketed citation/reference keys identify source labels. Equations use plain-text notation.']
            for row in sorted(bodies, key=lambda row: row['id'] != 'front'):
                if project or row['id'] == 'si':
                    blocks.append('Supporting Information' if row['id'] == 'si' else
                                  row['id'].replace('-', ' ').replace('_', ' ').title())
                blocks.append(renderer.text(row['body']))
            if any((root / name).read_text(encoding='utf-8') != src for name, src in sources.items()):
                raise ValueError('manuscript sources changed during export; rerun review-text')
            stats_after = (root / 'stats.json').read_bytes() if (root / 'stats.json').is_file() else None
            if stats_after != stats_before:
                raise ValueError('statistics changed during export; rerun review-text')
            output = root / Path(doc.output).with_suffix('.review.txt')
            write_text(output, normalize('\n\n'.join(blocks)))
            outputs.append(output)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document', nargs='?', help='named document, all, or the default document')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        for output in export(args.root, args.document):
            print(f'{output}: {output.stat().st_size:,} bytes')
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr, file=sys.stderr, end='')
        print(f'text export incomplete: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
