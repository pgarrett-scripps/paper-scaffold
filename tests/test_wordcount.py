"""Word limits must select real evaluated sections and never hide bad scopes."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import wordcount as wc


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def load(self, tail):
        (self.root / wc.CONFIG).write_text('schema_version = 1\n' + tail)
        return wc.load_checks(self.root)

    def test_invalid_configuration_never_silently_disables_checks(self):
        prefix = '[[checks]]\nname = "Body"\ninclude = ["main"]\n'
        for tail in ('min = -1', 'max = true', 'min = 10\nmax = 9',
                     'max = 2.5', 'max_words = 20', 'exclude = "main/Methods"'):
            with self.subTest(tail=tail), self.assertRaises(ValueError):
                self.load(prefix + tail)
        for tail in ('checks = {}', '[[checks]]\nname = "Body"',
                     '[[checks]]\nname = "Body"\ninclude = []',
                     prefix + prefix):
            with self.subTest(tail=tail), self.assertRaises(ValueError):
                self.load(tail)

    def test_absent_and_empty_config_are_optional(self):
        self.assertEqual(wc.load_checks(self.root), [])
        self.assertEqual(self.load(''), [])
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(wc.main(['--root', str(self.root), '--check', '--json']), 0)
        self.assertEqual(json.loads(output.getvalue())['status'], 'unconfigured')

    def test_overlap_exclusions_and_inclusive_bounds(self):
        sections = [{'id': name, 'words': n, 'heading': '/' in name} for name, n in (
            ('abstract', 4), ('main', 1), ('main/Methods', 3),
            ('main/Methods/Sampling', 5), ('main/Results', 7), ('si', 2))]
        checks = self.load('''[[checks]]
name = "Body"
include = ["main", "main/Results", "abstract"]
exclude = ["main/Methods"]
min = 12
max = 12
''')
        row, = wc.evaluate(checks, sections)
        self.assertEqual((row['words'], row['status']), (12, 'ok'))
        self.assertNotIn('main/Methods/Sampling', row['selected_sections'])
        for low, high, status in ((13, 20, 'below-min'), (0, 11, 'above-max')):
            checks[0].update(min=low, max=high)
            self.assertEqual(wc.evaluate(checks, sections)[0]['status'], status)

    def test_zero_bounds_missing_ambiguous_and_unrelated_sections(self):
        rows = [{'id': 'main', 'words': 0, 'heading': False},
                {'id': 'main/Results', 'words': 4, 'heading': True}]
        spec = dict(name='Empty', include=['main'], exclude=['main/Results'], max=0)
        self.assertEqual(wc.evaluate([spec], rows)[0]['status'], 'ok')
        for exclude in (['main/Result'], ['si']):
            with self.assertRaises(ValueError):
                wc.evaluate([{**spec, 'exclude': exclude}], rows)
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            wc.evaluate([spec], rows + [rows[1]])

    def test_read_only_stat_check_rejects_stale_display(self):
        (self.root / 'stats.json').write_text(json.dumps({'values': {
            'n': {'value': 42, 'fmt': 'd', 'origin': {'by': 'hand', 'note': 'fixture'}}}}))
        with self.assertRaisesRegex(ValueError, 'missing or stale'):
            wc.current_stats(self.root)
        path = self.root / 'stats-rendered.json'
        path.write_text(json.dumps({'values': {'n': {'value': 42, 'display': '41'}}}))
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'missing or stale'):
            wc.current_stats(self.root)
        self.assertEqual(path.read_bytes(), original)
        path.write_text(json.dumps({'values': {'n': {'value': 42, 'display': '42'}}}))
        wc.current_stats(self.root)


@unittest.skipUnless(shutil.which('typst'), 'Typst is required')
class TypstTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('wordcount.typ', 'wordcount-sections.typ'):
            shutil.copyfile(ROOT / name, self.root / name)
        (self.root / 'config.typ').write_text(
            '#let paper-title = "Title excluded"\n#let paper-abstract = [Short abstract.]\n')
        (self.root / 'stats.typ').write_text(
            '#let s(id) = "forty two"\n#let n(id) = 42\n'
            '#let lit(v, unlike: none) = v\n#let ci(id, level: false) = "1-2"\n'
            '#let todo(v) = none\n')
        (self.root / 'assets.typ').write_text(
            '#let fig(id) = []\n#let tbl(id) = []\n'
            '#let dfile(id) = [Data File 1]\n#let dfile-short(id) = [File 1]\n'
            '#let dfile-number(id) = 1\n#let dfile-count() = 1\n')
        (self.root / 'paper.typ').write_text('''Front matter excluded.
// >>> BODY START
Opening words.
= Methods
Two words.
#include "nested.typ"
= Results
Read #s("n") and `inline`.
#figure(rect[Invisible image text], caption: [Invisible caption words.])
$ a + b $
```python
block code excluded
```
@missing-citation
// <<< BODY END
Back matter excluded.
''')
        (self.root / 'nested.typ').write_text('== Sampling\nNested body.\n')
        (self.root / 'si-body.typ').write_text('SI opening.\n= Details\nExtra words.\n')

    def test_evaluated_counts_nested_includes_and_existing_exemptions(self):
        data = wc.counts(self.root)
        self.assertEqual(data['abstract_words'], 2)
        self.assertEqual(data['main_words'], 14)
        self.assertEqual(data['si_words'], 5)
        sections = {r['id']: r['words'] for r in data['sections']}
        self.assertEqual(sections, {'abstract': 2, 'main': 2, 'main/Methods': 3,
            'main/Methods/Sampling': 3, 'main/Results': 6, 'si': 2, 'si/Details': 3})
        row, = wc.evaluate([dict(name='Without methods', include=['main'],
                                exclude=['main/Methods'])], data['sections'])
        self.assertEqual(row['words'], 8)
        # No PDF or manuscript intermediate is built by the query.
        self.assertFalse((self.root / 'paper.pdf').exists())
        (self.root / 'nested.typ').write_text('== Sampling\nChanged body with more words.\n')
        self.assertEqual(wc.counts(self.root)['main_words'], 17)

    def test_data_file_calls_count_as_the_words_they_print(self):
        # uno-paper: the sliced body's eval scope lacked dfile, and one call
        # failed the whole count.
        paper = self.root / 'paper.typ'
        paper.write_text(paper.read_text().replace(
            'Two words.', 'Two words #dfile("a") of #dfile-count().'))
        self.assertEqual(wc.counts(self.root)['main_words'], 19)

    def test_cli_reports_limits_but_only_gate_blocks_drafting(self):
        (self.root / wc.CONFIG).write_text('''schema_version = 1
[[checks]]
name = "Abstract"
include = ["abstract"]
min = 3
max = 10
''')
        for args, expected in (([], 0), (['--check'], 1)):
            with redirect_stdout(io.StringIO()) as output:
                code = wc.main(['--root', str(self.root), '--json', *args])
            self.assertEqual(code, expected)
            self.assertEqual(json.loads(output.getvalue())['checks'][0]['status'], 'below-min')
        (self.root / wc.CONFIG).write_text('''schema_version = 1
[[checks]]
name = "Missing"
include = ["main/Old heading"]
max = 10
''')
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(wc.main(['--root', str(self.root), '--check', '--json']), 2)
        self.assertEqual(json.loads(output.getvalue())['status'], 'incomplete')
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(wc.main(['--root', str(self.root), '--sections']), 0)
        self.assertIn('main/Methods/Sampling: 3', output.getvalue())

    def test_markup_wrappers_explicit_headings_and_escaped_titles(self):
        (self.root / 'nested.typ').write_text('''#block[
#heading(level: 2)[Study / *setup*]
Don't split *inline* prose.
]
''')
        data = wc.counts(self.root)
        self.assertIn('main/Methods/Study %2F setup', [r['id'] for r in data['sections']])

    def test_missing_body_marker_fails_instead_of_counting_back_matter(self):
        path = self.root / 'paper.typ'
        path.write_text(path.read_text().replace('// <<< BODY END', ''))
        with self.assertRaisesRegex(ValueError, 'marker comments'):
            wc.counts(self.root)


if __name__ == '__main__':
    unittest.main()
