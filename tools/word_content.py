"""Project evaluated Typst content into Pandoc's native Typst reader.

Layout-only wrappers are deliberately flattened. Unknown semantic content,
references and citation keys fail closed. Equations and table cells remain
native editable Word objects; composed figure artwork is rendered by Typst.
"""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path

from manuscript_snapshot import content_text


def escape(text: str) -> str:
    return re.sub(r'([\\#*$@_<>\[\]`])', r'\\\1', text)


def descendants(value, kind):
    if isinstance(value, dict):
        if value.get('func') == kind:
            yield value
        for child in value.values():
            yield from descendants(child, kind)
    elif isinstance(value, list):
        for child in value:
            yield from descendants(child, kind)


def math(value) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    kind = value['func']
    if kind == 'sequence':
        return ' '.join(math(c) for c in value['children'])
    if kind in ('space', 'h'):
        return ' '
    if kind == 'text':
        text = value['text']
        return text if re.fullmatch(r'[A-Za-z]|[0-9]+(?:\.[0-9]+)?', text) else json.dumps(text, ensure_ascii=False)
    if kind == 'symbol':
        return value['text']
    if kind == 'frac':
        return f'frac({math(value["num"])}, {math(value["denom"])})'
    if kind == 'attach':
        args = [math(value['base'])]
        args += [f'{k}: {math(value[k])}' for k in ('t', 'b', 'tl', 'tr', 'bl', 'br') if k in value]
        return 'attach(' + ', '.join(args) + ')'
    if kind == 'op':
        return 'op(' + json.dumps(content_text(value['text'])) + ', limits: #' + str(value.get('limits', False)).lower() + ')'
    if kind == 'lr':
        return 'lr(' + math(value['body']) + ')'
    if kind == 'styled':
        return math(value['child'])
    if kind in ('upright', 'bold', 'italic', 'cancel'):
        return kind + '(' + math(value['body']) + ')'
    raise ValueError(f'unsupported mathematical content {kind!r}')


class WordContent:
    def __init__(self, root: Path, source: str, prefix: str, keys: set[str],
                 inventory: list[dict], chapters: list[str], artwork: dict[str, Path]):
        self.root, self.source, self.prefix, self.keys = root, source, prefix, keys
        self.inventory = inventory
        self.labels = {r['label']: r for r in inventory if r['label']}
        self.chapters, self.artwork = chapters, artwork
        self.used_figures = []
        self.equations = 0
        self.tables = 0
        self.citations = set()
        self.headings = []

    def reference(self, value):
        key = value['target'].strip('<>')
        if key.startswith('chap-'):
            return str(self.chapters.index(key[5:]) + 1)
        if key in self.labels:
            row = self.labels[key]
            if row['number'] is None:
                raise ValueError(f'reference to unnumbered target {key}')
            num = content_text(row['number'])
            return escape(num if value.get('supplement', 'auto') is None else
                          content_text(row['supplement']) + ' ' + num)
        if not self.prefix or not key.startswith(self.prefix):
            raise ValueError(f'unknown reference or foreign chapter citation {key}')
        local = key[len(self.prefix):]
        if local not in self.keys:
            raise ValueError(f'cited but missing from chapter bibliography: {key}')
        self.citations.add(local)
        return '@' + local

    def text(self, value) -> str:
        if value is None:
            return ''
        if isinstance(value, str):
            return escape(value)
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            return ''.join(self.text(v) for v in value)
        kind = value.get('func')
        if kind == 'sequence':
            children = value['children']
            # Alexandria's context formats this same sequence of references.
            if (len(children) >= 3 and children[0].get('func') == 'state-update'
                    and children[0].get('key') == '__alexandria-config'
                    and children[-1] == children[0]
                    and all(c.get('func') in ('ref', 'context', 'state-update') for c in children)):
                return ' '.join(self.reference(c) for c in children if c['func'] == 'ref')
            out = []
            for i, child in enumerate(children):
                # The capture overlay marks only the template's counter context.
                if (child.get('func') == 'context' and i + 1 < len(children)
                    and children[i+1].get('func') == 'metadata'
                    and children[i+1].get('value') == {'word_skip': 'supplement-counter'}):
                    continue
                out.append(self.text(child))
            return ''.join(out)
        if kind in ('text', 'symbol'):
            return escape(value['text'])
        if kind in ('space', 'h'):
            return ' '
        if kind in ('parbreak', 'pagebreak', 'v'):
            return '\n\n'
        if kind == 'linebreak':
            return '#linebreak()\n'
        if kind == 'smartquote':
            return '"' if value.get('double', True) else "'"
        if kind == 'ref':
            return self.reference(value)
        if kind == 'equation':
            self.equations += 1
            rendered = math(value['body'])
            return '\n\n$ ' + rendered + ' $\n\n' if value.get('block') else '$' + rendered + '$'
        if kind == 'heading':
            label = value.get('label', '').strip('<>')
            row = self.labels.get(label)
            prefix = content_text(row['number']) + ' ' if row and row['number'] is not None else ''
            title = prefix + self.text(value['body'])
            self.headings.append((value['depth'], title, label))
            return ('\n\n' + '=' * value['depth'] + ' ' + title
                    + (' <' + label + '>' if label else '') + '\n\n')
        if kind == 'raw':
            # raw() avoids delimiter collisions in verbatim code examples.
            return ('\n\n' if value.get('block') else '') + '#raw(' + json.dumps(value['text']) + ', block: ' + str(value.get('block', False)).lower() + (', lang: ' + json.dumps(value['lang']) if value.get('lang') else '') + ')' + ('\n\n' if value.get('block') else '')
        if kind in ('strong', 'emph', 'super', 'sub', 'underline', 'strike', 'smallcaps'):
            return '#' + kind + '[' + self.text(value['body']) + ']'
        if kind == 'styled':
            return self.text(value['child'])
        if kind in ('block', 'align', 'box', 'pad'):
            return self.text(value['body'])
        if kind == 'link':
            dest = value['dest']
            if not isinstance(dest, str):
                raise ValueError(f'unsupported link destination: {dest}')
            target = dest if dest.startswith('<') else json.dumps(dest)
            return '#link(' + target + ')[' + self.text(value['body']) + ']'
        if kind == 'figure':
            label = value.get('label', '').strip('<>')
            if label not in self.labels or label in self.used_figures:
                raise ValueError(f'unmatched or duplicate figure {label}')
            self.used_figures.append(label)
            row = self.labels[label]
            caption = self.text(value['caption']['body'])
            name = content_text(row['supplement']) + ' ' + content_text(row['number'])
            if label in self.artwork:
                body = '#image(' + json.dumps(str(self.artwork[label])) + ', width: 100%)'
            else:
                body = self.text(value['body'])
            # Pandoc gets the caption in the native figure or table caption.
            return '\n\n#figure([' + body + '], kind: ' + row['element']['kind'] + ', caption: [' + escape(name) + ': ' + caption + ']) <' + label + '>\n\n'
        if kind == 'image':
            path = Path(value['source'])
            path = self.root / str(path).lstrip('/') if path.is_absolute() else self.root / Path(self.source).parent / path
            if not path.is_file():
                raise ValueError(f'missing image {path}')
            if path.suffix.lower() == '.svg':
                import cairosvg
                cached = self.artwork['__directory__'] / (hashlib.sha256(path.read_bytes()).hexdigest() + '.png')
                if not cached.exists():
                    cairosvg.svg2png(url=str(path), write_to=str(cached), output_width=1800)
                path = cached
            return '#image(' + json.dumps(str(path.resolve())) + ', width: 100%)'
        if kind == 'table':
            self.tables += 1
            cols = value['columns']
            columns = len(cols) if isinstance(cols, list) else cols
            if isinstance(cols, list):
                if all(re.fullmatch(r'[\d.]+fr', c) for c in cols):
                    columns = '(' + ', '.join(cols) + ')'
                elif all(re.fullmatch(r'[\d.]+% \+ 0pt', c) for c in cols):
                    # Pandoc preserves fractional tracks but not percentages.
                    columns = '(' + ', '.join(c.split('%')[0] + 'fr' for c in cols) + ')'
                elif all(c == 'auto' or re.fullmatch(r'[\d.]+fr', c) for c in cols):
                    columns = '(' + ', '.join(cols) + ')'
            children = ',\n'.join(self.table_child(c) for c in value['children'] if c.get('func') != 'hline')
            return f'#table(columns: {columns},\n' + children + '\n)'
        if kind == 'metadata' and value.get('value') == {'word_skip': 'supplement-counter'}:
            return ''
        raise ValueError(f'unsupported Typst content {kind!r}; refusing to omit it')

    def table_child(self, value):
        kind = value['func']
        if kind in ('header', 'footer'):
            return 'table.' + kind + '(' + ', '.join(self.table_child(c) for c in value['children']) + ')'
        if kind == 'cell':
            attrs = ', '.join(f'{k}: {value[k]}' for k in ('colspan', 'rowspan', 'x', 'y') if k in value)
            return 'table.cell(' + attrs + ')[' + self.text(value['body']) + ']'
        raise ValueError(f'unsupported table child {kind}')
