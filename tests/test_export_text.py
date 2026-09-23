"""Semantic regression checks for the review export, using real Typst."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from export_text import Renderer, export
from word_content import WordContent

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('typst'), 'Typst is required')
class ExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'config.typ').write_text(
            '#let paper-title = "Review fixture"\n'
            '#let paper-abstract = [An abstract with *important* detail.]\n')
        (self.root / 'references.bib').write_text(
            '@article{doe, author={Doe, Jane}, title={BIBLIOGRAPHY SECRET}, year={2024}}\n')
        (self.root / 'included.typ').write_text('Included prose with #str(7 * 6).\n')
        (self.root / 'paper.typ').write_text('''
#set heading(numbering: "1.")
// >>> BODY START
= Methods
Prose citing @doe and @odd-label. H#sub[2]O with $x^2 + frac(a, b)$.

#include "included.typ"

#figure(rect[GRAPH SECRET], kind: image, caption: [A *nested* caption.]) <odd-label>

#figure(table(columns: 1, [TABLE SECRET]), caption: [Table caption.])

```python
if True:
    print("indented")
```

// <<< BODY END
= Acknowledgments
Funding statement survives.
#bibliography("references.bib", title: "References")
''')

    def test_evaluated_prose_captions_equations_and_omissions(self):
        output, = export(self.root)
        text = output.read_text()
        for present in ('Review fixture', 'important detail', 'Methods', '[doe]',
                        'Figure 1', 'A nested caption.', 'Table 1: Table caption.',
                        'H_(2)O', 'x^(2)', '(a)/(b)', 'Included prose with 42.',
                        '    print("indented")', 'Funding statement survives.'):
            self.assertIn(present, text)
        for absent in ('GRAPH SECRET', 'TABLE SECRET', 'BIBLIOGRAPHY SECRET',
                       '\nReferences\n', '#figure', '#include'):
            self.assertNotIn(absent, text)
        self.assertEqual(text.count('A nested caption.'), 1)
        # Re-running reads current source, without needing an intermediate PDF.
        path = self.root / 'included.typ'
        path.write_text('Updated prose with #str(6 * 9).\n')
        export(self.root)
        self.assertIn('Updated prose with 54.', output.read_text())

    def test_failure_keeps_previous_export(self):
        output, = export(self.root)
        original = output.read_bytes()
        (self.root / 'included.typ').write_text('#context [Context-dependent prose.]\n')
        with self.assertRaisesRegex(ValueError, 'unsupported Typst content'):
            export(self.root)
        self.assertEqual(output.read_bytes(), original)

    def test_si_contents_becomes_the_word_sentence(self):
        """`#si-contents` is a `context` block the export refuses to drop;
        the review copy writes in the sentence the Word export uses."""
        paper = self.root / 'paper.typ'
        paper.write_text('#let si-contents = context [unused]\n'
                         + paper.read_text().replace('Funding statement survives.',
                                                     'Funding statement survives.\n\n#si-contents')
                         + '#include "si-body.typ"\n')
        (self.root / 'si-body.typ').write_text(
            '= Methods\n#figure(rect(), caption: [a]) <fig:a>\n')
        output, = export(self.root)
        self.assertIn('Section S1 Methods. Figure S1 (PDF).', output.read_text())

    def test_si_reference_list_is_omitted_like_the_main_one(self):
        """The SI's own list goes the way the main one does: cut, not filtered.

        Alexandria renders it inside a `context`, which Typst hands back
        opaque -- and an opaque node is exactly what this exporter must keep
        refusing rather than learn to drop.
        """
        paper = (self.root / 'paper.typ').read_text().replace(
            '#set heading(numbering: "1.")',
            '#import "@preview/alexandria:0.2.0": alexandria\n'
            '#show: alexandria(prefix: "si-", read: p => read(p))\n'
            '#set heading(numbering: "1.")')
        (self.root / 'paper.typ').write_text(paper + '#include "si-body.typ"\n')
        (self.root / 'si-body.typ').write_text(
            '#import "@preview/alexandria:0.2.0": bibliographyx\n'
            'SI prose citing @si-doe.\n'
            '#set heading(numbering: none)\n'
            '#bibliographyx("references.bib", prefix: "si-", '
            'title: [References], style: "ieee") <si-references>\n')
        output, = export(self.root)
        text = output.read_text()
        self.assertIn('SI prose citing [doe].', text)
        for absent in ('BIBLIOGRAPHY SECRET', 'bibliographyx', 'si-references'):
            self.assertNotIn(absent, text)

    def test_named_document_selection(self):
        (self.root / 'manuscript.toml').write_text('''
schema_version = 1
default_document = "chapter"
[parts.methods]
source = "paper.typ"
[documents.chapter]
entrypoint = "paper.typ"
output = "build/chapter.pdf"
parts = ["methods"]
''')
        output, = export(self.root, 'chapter')
        self.assertEqual(output, self.root / 'build/chapter.review.txt')
        self.assertIn('Table 1: Table caption.', output.read_text())
        self.assertNotIn('Funding statement survives.', output.read_text())
        with self.assertRaisesRegex(ValueError, 'unknown document'):
            export(self.root, 'missing')


class RendererTests(unittest.TestCase):
    def test_unknown_construct_is_not_silently_deleted(self):
        with self.assertRaisesRegex(ValueError, 'export stopped'):
            Renderer([]).text({'func': 'unsupported-new-construct', 'body': 'Important text'})

    def test_citation_group_keys_are_retained(self):
        state = {'func': 'state-update', 'key': '__alexandria-config'}
        group = {'func': 'sequence', 'children': [state,
            {'func': 'ref', 'target': '<one>'}, {'func': 'ref', 'target': '<two>'},
            {'func': 'context'}, state]}
        self.assertEqual(Renderer([]).text(group), '[one][two]')

    def test_reference_supplement_is_not_repeated(self):
        # `@fig:x[]` gives the reference an empty supplement because the prose
        # writes the word "Figure" itself. An exporter that always prepended
        # the figure's own supplement printed "Figure Figure 3" in the review
        # copy and the Word file while the PDF was correct. The forms below are
        # what `typst query` emits for auto, `[]`, `none` and `[Panel]`.
        figure = {'label': 'fig:x', 'number': '3',
                  'supplement': {'func': 'text', 'text': 'Figure'},
                  'caption': None}
        empty = {'func': 'sequence', 'children': []}
        panel = {'func': 'text', 'text': 'Panel'}
        cases = [('auto', 'Figure 3'), (empty, '3'), (None, '3'), (panel, 'Panel 3')]
        renderer = Renderer([figure])
        word = WordContent(ROOT, 'paper.typ', '', set(), [figure], [], {})
        for supplement, expected in cases:
            ref = {'func': 'ref', 'target': '<fig:x>', 'supplement': supplement}
            self.assertEqual(renderer.text(ref), expected, supplement)
            self.assertEqual(word.reference(ref), expected, supplement)


if __name__ == '__main__':
    unittest.main()
