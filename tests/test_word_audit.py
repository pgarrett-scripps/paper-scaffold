"""Behavioral tests for vocabulary review, extraction boundaries and failures."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from word_audit import audit, load_manifest, sources
import word_audit


class WordAuditTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest(ROOT / "word-watchlist.toml")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "config.typ").write_text(
            '#let paper-title = "boasts"\n'
            '#let paper-abstract = [We *delve* into [the data].]\n')
        (self.root / "paper.typ").write_text(
            'Front matter boasts.\n// >>> BODY START\n'
            '= Results\n#include "part.typ"\n// <<< BODY END\n'
            'Back matter boasts.\n')
        (self.root / "part.typ").write_text('This underscores the result.\n')
        (self.root / "si-body.typ").write_text('The SI delves into detail.\n')

    def test_published_surface_forms_are_preserved(self):
        expected = set('delves delved delving showcasing delve boasts underscores '
                       'comprehending intricacies surpassing intricate underscoring '
                       'garnered showcases emphasizing underscore realm surpasses '
                       'groundbreaking advancements aligns'.split())
        self.assertEqual({w for w, source in self.manifest['word_sources'].items()
                          if source == 'primary'}, expected)
        rows = audit('test', 'DELVE delves delved delving. '
                     'Underscored alignment realms realmish delve_tool.', self.manifest)
        self.assertEqual({r['word'] for r in rows['matches']},
                         {'delve', 'delves', 'delved', 'delving', 'underscored'})

    def test_expansion_matches_with_separate_attribution(self):
        expected = set('pivotal remarkable impressive invaluable transformative '
                       'comprehensive multifaceted nuanced meticulous meticulously '
                       'leveraging harnessing fostering bolstering elucidating '
                       'seamlessly unparalleled unlocking unveiling revolutionize streamlined '
                       'compelling crucial exceptional exceptionally innovative impactful '
                       'imperative noteworthy notable notably burgeoning foundational '
                       'interplay interconnectedness avenues endeavors illuminates illuminating '
                       'encapsulates propelling orchestrating poised uncharted unraveling'.split())
        extension = next(g for g in self.manifest['extensions']
                         if g['id'] == 'kobak-style-selection')
        self.assertEqual(set(extension['words']), expected)
        self.assertIn('Kobak', extension['source']['citation'])
        self.assertEqual(len(self.manifest['words']), 111)
        rows = audit('test', ' '.join(sorted(expected)).upper() + ' Delve.',
                     self.manifest)['matches']
        self.assertEqual({r['word'] for r in rows}, expected | {'delve'})
        for row in rows:
            self.assertEqual(row['source'], 'primary' if row['word'] == 'delve'
                             else 'kobak-style-selection')

    def test_author_preference_is_attributed_without_research_claim(self):
        group = next(g for g in self.manifest['extensions']
                     if g['id'] == 'author-preferences')
        self.assertEqual(group['source']['kind'], 'editorial')
        self.assertEqual(set(group['words']), set(
            'tractable amenable actionable robust scalable principled parsimonious '
            'elegant sophisticated intuitive versatile holistic synergistic synergy '
            'tapestry cornerstone linchpin'.split()))
        row, = audit('test', 'A tractable problem, unlike intractable problems.',
                     self.manifest)['matches']
        self.assertEqual((row['word'], row['count'], row['source']),
                         ('tractable', 1, 'author-preferences'))
        additions = audit('test', 'Amenable actionable robust scalable streamlined.',
                          self.manifest)
        self.assertEqual(additions['flagged_occurrences'], 5)
        self.assertEqual({r['word']: r['source'] for r in additions['matches']},
                         {w: 'author-preferences' for w in
                          ('amenable', 'actionable', 'robust', 'scalable')} |
                         {'streamlined': 'kobak-style-selection'})

    def test_explicit_word_forms_count_without_automatic_stemming(self):
        expected = set('leverage leveraged leverages harness harnessed harnesses '
                       'foster fostered fosters bolster bolstered bolsters elucidate '
                       'elucidated elucidates streamline streamlines streamlining showcase '
                       'showcased underscored revolutionized revolutionizes revolutionizing '
                       'tractability scalability robustly robustness'.split())
        group = next(g for g in self.manifest['extensions']
                     if g['id'] == 'word-form-extensions')
        self.assertEqual(set(group['words']), expected)
        self.assertEqual(group['source']['kind'], 'editorial')
        report = audit('test', ' '.join(sorted(expected)) +
                       ' re-harnessed leverage_tool intractability.', self.manifest)
        self.assertEqual(report['flagged_occurrences'], 28)
        self.assertEqual({r['word'] for r in report['matches']}, expected)
        self.assertTrue(all(r['source'] == 'word-form-extensions'
                            for r in report['matches']))

    def test_every_occurrence_counts_even_once_per_paragraph(self):
        paragraphs = ['We delve into the results.'] * 10
        separated = audit('test', '\n\n'.join(paragraphs), self.manifest)
        joined = audit('test', ' '.join(paragraphs), self.manifest)
        self.assertEqual(separated, joined)
        self.assertEqual(separated['flagged_occurrences'], 10)
        self.assertEqual(separated['distinct_flagged_words'], 1)
        self.assertEqual(separated['matches'][0]['count'], 10)
        self.assertNotIn('warning', separated['matches'][0])
        self.assertNotIn('per_1000', separated['matches'][0])
        self.assertNotIn('hits', separated['matches'][0])

    def test_counts_combine_across_scopes_and_sections(self):
        parts = {'Abstract': 'Delve.', 'Main': '= One\nWe delve.\n= Two\nWe delve.',
                 'SI': 'Robust, robust, scalable.'}
        row = audit('manuscript', parts, self.manifest)
        self.assertEqual(row['flagged_occurrences'], 6)
        self.assertEqual(row['distinct_flagged_words'], 3)
        self.assertEqual([(r['word'], r['count']) for r in row['matches']],
                         [('delve', 3), ('robust', 2), ('scalable', 1)])
        self.assertEqual(audit('empty', '', self.manifest)['flagged_occurrences'], 0)

    def test_exception_retains_counts_and_reason_but_is_not_flagged(self):
        self.manifest['allow']['aligns'] = 'Sequence alignment operation.'
        result = audit('test', 'It aligns and aligns. Delve.', self.manifest)
        self.assertEqual(result['flagged_occurrences'], 1)
        self.assertEqual(result['allowed_occurrences'], 2)
        self.assertEqual(result['distinct_flagged_words'], 1)
        row = result['matches'][0]
        self.assertEqual(row['count'], 2)
        self.assertEqual(row['exception'], 'Sequence alignment operation.')

    def test_prose_boundaries_and_excluded_content(self):
        src = '''= Intricate heading
Actual *delve* prose with `boasts` and $"realm"$ and @garnered.
// showcasing
/* surpasses */

#figure(rect(), caption: [intricacies

groundbreaking])
#table(columns: 1, [advancements])
#bibliography("realm.bib")
```python
underscores = "comprehending"
```
'''
        row = audit('test', src, self.manifest)
        self.assertEqual([r['word'] for r in row['matches']], ['delve'])
        scopes = sources(self.root, None)
        self.assertEqual(list(scopes), ['Abstract', 'Main text', 'SI'])
        found = {name: [r['word'] for r in audit(name, text, self.manifest)['matches']]
                 for name, text in scopes.items()}
        self.assertEqual(found, {'Abstract': ['delve'], 'Main text': ['underscores'],
                                 'SI': ['delves']})

    def test_bad_includes_and_missing_markers_fail_visibly(self):
        for body, error in [('#include "part.typ"', 'cyclic'),
                            ('#include filename', 'dynamic'),
                            ('#include "../outside.typ"', 'outside project')]:
            with self.subTest(body=body):
                (self.root / 'part.typ').write_text(body)
                with self.assertRaisesRegex(ValueError, error):
                    sources(self.root, None)
        (self.root / 'part.typ').write_text('#include "missing.typ"')
        with self.assertRaises(FileNotFoundError):
            sources(self.root, None)
        (self.root / 'paper.typ').write_text('No markers.')
        with self.assertRaisesRegex(ValueError, 'BODY START'):
            sources(self.root, None)

    def test_manifest_errors_do_not_silently_disable_checks(self):
        original = (ROOT / 'word-watchlist.toml').read_text()
        for before, after in [('schema_version = 2', 'schema_version = 1'),
                              ('schema_version = 2', 'schema_version = true'),
                              ('"delves", "delved"', '"delves", "delves"'),
                              ('[allow]', '[allow]\ndelve = ""'),
                              ('[allow]', '[allow]\nunknown = "reason"'),
                              ('[allow]', '[limits]\nmin_count = 3\n[allow]'),
                              ('"pivotal", "remarkable"', '"delve", "remarkable"'),
                              ('id = "kobak-style-selection"', 'id = "primary"'),
                              ('location = "results/excess_words.csv; entries annotated as style"',
                               'location = ""'),
                              ('kind = "editorial"', 'kind = "unsupported"'),
                              ('kind = "editorial"', 'kind = "research"')]:
            with self.subTest(after=after):
                path = self.root / 'watchlist.toml'
                path.write_text(original.replace(before, after))
                with self.assertRaises(ValueError):
                    load_manifest(path)

    def test_named_document_uses_declared_parts(self):
        (self.root / 'manuscript.toml').write_text('''schema_version = 1
default_document = "paper"
[parts.results]
source = "paper.typ"
[documents.paper]
entrypoint = "paper.typ"
output = "build/paper.pdf"
parts = ["results"]
''')
        scopes = sources(self.root, 'paper')
        self.assertEqual(list(scopes), ['paper/results'])
        row = audit('paper/results', scopes['paper/results'], self.manifest)
        self.assertEqual([r['word'] for r in row['matches']], ['underscores'])
        with (self.root / 'manuscript.toml').open('a') as f:
            f.write('\n[documents.alternative]\nentrypoint = "paper.typ"\n'
                    'output = "build/alternative.pdf"\nparts = ["results"]\n')
        targets = word_audit.documents(self.root, 'all')
        self.assertEqual(set(targets), {'paper', 'alternative'})
        self.assertEqual([audit(name, parts, self.manifest)['flagged_occurrences']
                          for name, parts in targets.items()], [1, 1])

    def test_cli_json_works_outside_project_directory(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/word_audit.py'),
                                 '--json'], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['schema_version'], 2)
        self.assertEqual(len(report['documents']), 1)

    def test_counts_succeed_without_rewriting_sources(self):
        path = self.root / 'part.typ'
        path.write_text('It delves into the data and delves into the methods.')
        before = {p: p.read_bytes() for p in self.root.glob('*.typ')}
        output = io.StringIO()
        with patch.object(word_audit, 'ROOT', self.root), redirect_stdout(output):
            rc = word_audit.main(['--manifest', str(ROOT / 'word-watchlist.toml')])
        self.assertEqual(rc, 0)
        self.assertIn('Flagged word occurrences: 4 (2 distinct words)', output.getvalue())
        self.assertIn('delves: 3', output.getvalue())
        self.assertNotIn('paragraph', output.getvalue())
        self.assertEqual({p: p.read_bytes() for p in self.root.glob('*.typ')}, before)


if __name__ == '__main__':
    unittest.main()
