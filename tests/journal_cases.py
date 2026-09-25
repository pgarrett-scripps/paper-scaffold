"""Journal profiles: sourced limits, and the graphical abstract's placement.

The contract this guards is small and easy to erode: a limit in journals/
carries the URL it was read from and two dates, or it does not load; the
profile's rules join the EXISTING checkers rather than duplicating them; and
the graphical abstract lands where journal.toml says for each output, without
the manuscript changing.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import journal
import prose_check
import prose_rules
import resolve_typst
import wordcount
from PIL import Image

PROFILE = '''schema_version = 1
label = "Test Article"
journal = "Journal of Tests"
type = "Article"
source = "https://example.org/authors"
guidelines-dated = "2026-01-01"
checked = "2026-01-02"
[words]
main-max = 100
excludes = ["methods"]
abstract-max = 20
keywords-max = 2
[floats]
figures-max = 1
figures-and-tables-max = 2
[figures]
min-dpi = 600
[graphical-abstract]
required = true
width-in = 3.25
height-in = 1.75
min-dpi = 300
'''

PAPER = '''#let toc-graphic = fig("fig.toc", width: 3.25in)
#let toc-caption = [At a glance.]
// >>> BODY START
= Introduction
Words @a2020.
#figure(fig("fig.a"), caption: [One.]) <fig:a>
#figure(table(columns: 1, [x]), caption: [A table.]) <tbl:a>
#include "extra.typ"
= Methods
More words.
// <<< BODY END
#figure(fig("fig.si"), caption: [Not counted, it is back matter.])
'''

CONFIG = '''#let paper-title = "T"
#let paper-authors = ((name: "A. Uthor", affiliation: "Lab"),)
#let paper-keywords = ("one", "two (2)", "thr\\"ee")
#let paper-abstract = [Short.]
#let paper-bib-style = "ieee"
'''


def png(path: Path, w: int, h: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), "white").save(path)


class JournalCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "journals").mkdir()
        self.put("journals/test-article.toml", PROFILE)
        self.put("journal.toml", 'schema_version = 1\nprofile = "test-article"\n'
                                 '[sections]\nmethods = "main/Methods"\n')
        self.put("paper.typ", PAPER)
        self.put("extra.typ", "#figure(fig(\"fig.b\"), caption: [Two.])\n")
        self.put("config.typ", CONFIG)
        self.put("assets.json", json.dumps({"values": {
            "fig.toc": {"path": "figures/toc.png", "kind": "figure"},
            "fig.a": {"path": "figures/a.png", "kind": "figure"},
            "fig.b": {"path": "figures/b.png", "kind": "figure"},
            "fig.si": {"path": "figures/si.png", "kind": "figure"}}}))
        png(self.root / "figures/toc.png", 975, 525)
        png(self.root / "figures/a.png", 1000, 600)

    def put(self, name: str, text: str) -> None:
        (self.root / name).write_text(text)

    # --- the profiles that ship ------------------------------------------

    def test_every_shipped_profile_loads_with_its_provenance(self):
        names = journal.available(ROOT)
        self.assertEqual(names, ["jasms-article", "jasms-technical-note",
                                 "jpr-article", "jpr-technical-note"])
        for name in names:
            with self.subTest(profile=name):
                p = journal.load_profile(ROOT, name)
                self.assertTrue(p.source.startswith("https://"))
                self.assertTrue(p.graphic.get("required"))
                self.assertEqual((p.graphic["width-in"], p.graphic["height-in"]), (3.25, 1.75))

    def test_a_limit_without_provenance_does_not_load(self):
        for drop in ("source", "checked", "guidelines-dated"):
            with self.subTest(missing=drop):
                lines = [ln for ln in PROFILE.splitlines() if not ln.startswith(drop + " ")]
                self.put("journals/bad.toml", "\n".join(lines) + "\n")
                with self.assertRaisesRegex(journal.JournalError, drop):
                    journal.load_profile(self.root, "bad")

    def test_unknown_keys_roles_and_regions_are_refused(self):
        for tail, msg in (("[words]\nmax = 5\n", "expected only"),
                          ("[words]\nexcludes = [\"appendix\"]\n", "unknown role"),
                          ("[words]\ncounts = [\"figures\"]\n", "unknown region"),
                          ("[graphical-abstract]\nwidth-in = 3\n", "both width-in")):
            with self.subTest(tail=tail):
                base = PROFILE.split("[words]")[0]
                self.put("journals/bad.toml", base + tail)
                with self.assertRaisesRegex(journal.JournalError, msg):
                    journal.load_profile(self.root, "bad")

    # --- cover letter --------------------------------------------------------

    def test_shipped_profiles_carry_the_cover_letter_rules_without_a_limit(self):
        # JPR and JASMS state what the letter must say and no length limit
        # (guidelines dated 2026-08-27); a limit here would be invented.
        for name in journal.available(ROOT):
            with self.subTest(profile=name):
                letter = journal.load_profile(ROOT, name).letter
                self.assertIn("journal-fit", letter["required"])
                self.assertNotIn("max-words", letter)
                self.assertNotIn("max-pages", letter)
                self.assertTrue(letter["source"].startswith("https://"))
        jasms = journal.load_profile(ROOT, "jasms-article").letter
        self.assertEqual(jasms["reviewers-min"], 4)

    def test_cover_letter_table_is_validated_strictly(self):
        for tail, msg in (("max-letters = 5\n", "expected only"),
                          ("max-words = 0\n", "positive integer"),
                          ("max-pages = 1.5\n", "positive integer"),
                          ('required = ["significance"]\n', "unknown item"),
                          ('required = ["title", "title"]\n', "twice"),
                          ('required = "title"\n', "list of strings"),
                          ("reviewers-min = 4\n", "suggested-reviewers"),
                          ('checked = "25 Sep"\n', "YYYY-MM-DD"),
                          ('source = "acs.org"\n', "must be a URL")):
            with self.subTest(tail=tail):
                self.put("journals/bad.toml", PROFILE + "[cover-letter]\n" + tail)
                with self.assertRaisesRegex(journal.JournalError, msg):
                    journal.load_profile(self.root, "bad")
        self.put("journals/ok.toml", PROFILE + '[cover-letter]\nmax-words = 500\n'
                 'required = ["title", "suggested-reviewers"]\nreviewers-min = 3\n')
        self.assertEqual(journal.load_profile(self.root, "ok").letter["max-words"], 500)

    def test_cover_letter_limits_are_checked_against_the_built_counts(self):
        self.put("journals/test-article.toml",
                 PROFILE + "[cover-letter]\nmax-words = 100\nmax-pages = 1\n")
        profile = journal.load_profile(self.root, "test-article")
        self.assertEqual(journal.letter_findings(profile, {"words": 100, "pages": 1}), [])
        over = journal.letter_findings(profile, {"words": 101, "pages": 2})
        self.assertEqual([f.level for f in over], ["error", "error"])
        self.assertIn("101 words", over[0].message)
        self.assertIn("2 pages", over[1].message)
        unmeasured = journal.letter_findings(profile, {"words": None, "pages": 1})
        self.assertIn("not measured", unmeasured[0].message)
        # No letter built, or no rules: nothing to hold it to.
        self.assertEqual(journal.letter_findings(profile, None), [])
        self.assertEqual(journal.letter_findings(
            journal.load_profile(self.root, "test-article").__class__(
                **{**profile.__dict__, "letter": {}}), {"words": 10**6}), [])
        # The verify-side check never looks at the letter.
        self.assertFalse(any(f.subject == "cover letter" for f in journal.check(self.root)))

    # --- journal.toml ------------------------------------------------------

    def test_no_profile_holds_the_manuscript_to_nothing(self):
        self.put("journal.toml", 'schema_version = 1\nprofile = ""\n')
        self.assertEqual(journal.word_checks(self.root), [])
        self.assertEqual(journal.check(self.root), [])
        self.assertIsNone(journal.min_figure_dpi(self.root))
        self.assertEqual(journal.placement(self.root, "pdf"), "preprint")
        self.assertEqual(journal.placement(self.root, "docx"), "journal")

    def test_placement_is_validated_and_defaults_per_output(self):
        self.put("journal.toml", 'schema_version = 1\nprofile = ""\n[placement]\npdf = "journal"\n')
        self.assertEqual(journal.placement(self.root, "pdf"), "journal")
        self.assertEqual(journal.placement(self.root, "docx"), "journal")
        self.put("journal.toml", 'schema_version = 1\nprofile = ""\n[placement]\npdf = "top"\n')
        with self.assertRaisesRegex(journal.JournalError, "preprint, journal, none"):
            journal.placement(self.root, "pdf")

    # --- the word limits join the word counter -----------------------------

    def test_word_checks_take_the_word_counters_shape(self):
        checks = journal.word_checks(self.root)
        self.assertEqual([c["name"] for c in checks],
                         ["Test Article: main text", "Test Article: abstract"])
        self.assertEqual(checks[0]["exclude"], ["main/Methods"])
        self.assertEqual(checks[0]["max"], 100)
        sections = [{"id": "abstract", "heading": False, "words": 5},
                    {"id": "main", "heading": False, "words": 0},
                    {"id": "main/Introduction", "heading": True, "words": 90},
                    {"id": "main/Methods", "heading": True, "words": 40}]
        rows = wordcount.evaluate(checks, sections)
        self.assertEqual([(r["words"], r["status"]) for r in rows], [(90, "ok"), (5, "ok")])

    def test_an_unmapped_role_is_a_loud_error_naming_the_fix(self):
        self.put("journal.toml", 'schema_version = 1\nprofile = "test-article"\n')
        with self.assertRaisesRegex(journal.JournalError, 'methods = "main/Methods"'):
            journal.word_checks(self.root)
        self.put("journal.toml", 'schema_version = 1\nprofile = "test-article"\n'
                                 '[sections]\nmethods = ""\n')
        self.assertEqual(journal.word_checks(self.root)[0]["exclude"], [])

    def test_a_limit_that_counts_references_selects_the_rendered_list(self):
        self.put("journals/note.toml", PROFILE.replace('excludes = ["methods"]',
                                                       'counts = ["abstract", "references"]'))
        self.put("journal.toml", 'schema_version = 1\nprofile = "note"\n')
        check = journal.word_checks(self.root)[0]
        self.assertEqual(check["include"], ["main", "abstract", "references"])
        self.assertIn("citeproc", check["note"])

    def test_the_main_texts_reference_list_is_counted_as_citeproc_sets_it(self):
        self.put("references.bib", '''@article{a2020, author={Ada Lovelace and Grace Hopper},
  title={A title of several words}, journal={J. Tests}, year={2020}, volume={1}, pages={1--9}}
@article{b2021, author={Alan Turing}, title={Another}, journal={J. Tests}, year={2021}}
@article{c2022, author={Only In SI}, title={Unused here}, journal={J. Tests}, year={2022}}
''')
        self.put("si-body.typ", "SI text @si-c2022.\n")
        self.put("paper.typ", PAPER.replace("More words.", "More words @b2021 and @a2020 again, "
                                            "but not \"@quoted\" nor @fig:a.")
                 + '#bibliography("references.bib", style: paper-bib-style)\n'
                 + '#include "si-body.typ"\n')
        self.assertEqual(journal.main_text_citations(self.root), ["a2020", "b2021"])
        refs = journal.reference_words(self.root)
        self.assertEqual(refs["entries"], 2)
        self.assertGreater(refs["words"], 15)
        self.assertIsNone(refs["csl"], "no ieee.csl in this root: pandoc's default style")
        # No bibliography call, or nothing cited: nothing to count.
        self.put("paper.typ", PAPER)
        self.assertIsNone(journal.reference_words(self.root))

    # --- what check-journal itself covers ----------------------------------

    def test_keywords_and_main_text_floats_are_counted_from_the_source(self):
        self.assertEqual(journal.keyword_count(self.root), 3)
        # Two figures (one through an include), one table; the float after
        # BODY END is back matter and does not count.
        self.assertEqual(journal.main_text_floats(self.root), {"figures": 2, "tables": 1})
        subjects = {(f.level, f.subject) for f in journal.check(self.root)}
        self.assertIn(("error", "keywords"), subjects)
        self.assertIn(("error", "figures"), subjects)
        self.assertIn(("error", "figures and tables"), subjects)

    def test_the_graphical_abstract_is_measured_against_the_box(self):
        ok = [f for f in journal.check(self.root) if f.subject == "graphical abstract"]
        self.assertEqual(ok, [], "975 x 525 px is exactly 300 dpi in a 3.25 x 1.75 in box")
        png(self.root / "figures/toc.png", 600, 323)
        low = [f for f in journal.check(self.root) if f.subject == "graphical abstract"]
        self.assertEqual(len(low), 1)
        self.assertIn("~185 dpi", low[0].message)
        self.put("paper.typ", PAPER.replace('fig("fig.toc", width: 3.25in)', "none"))
        missing = [f for f in journal.check(self.root) if f.subject == "graphical abstract"]
        self.assertEqual(missing[0].level, "error")
        self.assertIn("requires a TOC graphic", missing[0].message)

    def test_toc_graphic_resolves_by_id_or_by_path(self):
        self.assertEqual(journal.toc_graphic(self.root)["path"], "figures/toc.png")
        self.put("paper.typ", PAPER.replace('fig("fig.toc", width: 3.25in)',
                                            'image("/figures/hand.png", width: 50%)'))
        self.assertEqual(journal.toc_graphic(self.root)["path"], "figures/hand.png")
        self.put("paper.typ", PAPER.split("// >>> BODY START")[1])
        self.assertIsNone(journal.toc_graphic(self.root))

    # --- the rules that join other checkers --------------------------------

    def test_the_profiles_resolution_floor_reaches_prose_check(self):
        with patch.object(prose_rules, "CONFIG_NAME", "absent.toml"):
            self.assertEqual(prose_rules.load_config(self.root).limit("min-figure-dpi"), 600)
        self.put("prose-check.toml", "[limits]\nmin-figure-dpi = 250\n")
        self.assertEqual(prose_rules.load_config(self.root).limit("min-figure-dpi"), 250,
                         "the project's own file still wins over the profile")

    def test_figure_resolution_follows_fig_ids_and_absolute_widths(self):
        cfg = prose_rules.Config(limits={**prose_rules.DEFAULT_LIMITS, "min-figure-dpi": 300,
                                         "figure-text-width-mm": 160})
        self.put("paper.typ", '#figure(fig("fig.a", width: 50%))\n')
        self.assertEqual(prose_check.check_figure_resolution(self.root, cfg), [],
                         "1000 px over half of 160 mm is ~317 dpi")
        self.put("paper.typ", '#figure(fig("fig.a"))\n')
        found = prose_check.check_figure_resolution(self.root, cfg)
        self.assertEqual(len(found), 1)
        self.assertIn("~159 dpi", found[0].message)
        self.put("paper.typ", '#let toc-graphic = fig("fig.toc", width: 3.25in)\n')
        self.assertEqual(prose_check.check_figure_resolution(self.root, cfg), [],
                         "975 px over 3.25 in is exactly 300 dpi")
        self.put("paper.typ", '#let toc-graphic = fig("fig.toc", width: 5in)\n')
        self.assertEqual(len(prose_check.check_figure_resolution(self.root, cfg)), 1)

    # --- placement in the Word projection ----------------------------------

    def test_word_projection_places_the_graphic_where_asked(self):
        # No include: the resolver inlines one with an empty manifest.
        self.put("paper.typ", PAPER.replace("@a2020", "").replace('#include "extra.typ"\n', ""))
        meta = {"title": "T", "authors": [{"name": "A. Uthor", "affils": [1]}],
                "affils": ["Lab"], "keywords": ["k"]}
        with patch.object(resolve_typst, "ROOT", self.root), \
                patch.object(resolve_typst, "ASSETS", self.root / "assets.json"), \
                patch.object(resolve_typst, "NATIVE_NUMBERING", None):
            preprint = resolve_typst.build(meta, "preprint")
            journal_ = resolve_typst.build(meta, "journal")
            none = resolve_typst.build(meta, "none")
            with self.assertRaisesRegex(resolve_typst.ResolveError, "preprint, journal, none"):
                resolve_typst.build(meta, "top")
        toc = 'image("figures/toc.png", width: 3.25in)'
        self.assertLess(preprint.index(toc), preprint.index("Introduction"))
        self.assertNotIn(resolve_typst.TOC_LABEL, preprint)
        self.assertGreater(journal_.index(toc), journal_.index("More words."))
        self.assertIn(resolve_typst.TOC_LABEL, journal_)
        self.assertLess(journal_.index(resolve_typst.TOC_LABEL), journal_.index(toc))
        self.assertNotIn(toc, none)


def run_cases() -> bool:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(JournalCases)
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
