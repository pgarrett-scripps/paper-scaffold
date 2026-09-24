"""Contracts for the slide decks under slides/.

Two of these are the whole reason the feature is shaped the way it is, and
both are invisible in a green build:

  1. A deck must NOT enter the paper's source fingerprint. Decks reach the id
     index through manuscript_sources.usages(), and the obvious way to do that
     -- widening ENTRYPOINTS -- also widens build_state.snapshot(), at which
     point every slide edit reports paper.pdf and paper.docx stale. The first
     two cases here are what stops a future refactor from collapsing the two
     back together.
  2. A deck must not be able to fail `just verify`. An undeclared asset id in a
     deck is a warning, not the error the same mistake is in the manuscript,
     and a deck whose imports are broken must not make the id index raise.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_state
import check_assets
import check_stats
import manuscript_sources
import prose_check
import readability
import slides
from prose_rules import Config

# Decks are opt-in: a derived manuscript with no slides/ must pass `just
# test` untouched (HISTORY 3.20.0). The cases that read the SHIPPED deck skip
# there; the ones that build decks in a temporary root always run.
SHIPPED_DECK = (ROOT / "slides/theme.typ").is_file()
no_shipped_deck = unittest.skipUnless(SHIPPED_DECK, "slides/: absent, skipped")

PAPER = """// >>> BODY START
Main prose with #s("paper.only") and #fig("fig.paper").
// <<< BODY END
"""

THEME = ('#import "config.typ": deck-title\n'
         '#import "/stats.typ": s\n#import "/assets.typ": fig\n')

DECK_CONFIG = '#let deck-title = "A Talk"\n'

DECK = """#import "theme.typ": *
== A slide
Reusing #s("deck.only") and #fig("fig.deck").
"""


class SlideCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put("paper.typ", PAPER)
        self.put("config.typ", '#let paper-title = "T"\n')
        self.put("si-body.typ", "SI prose.\n")
        self.put("stats.typ", "#let s(id) = id\n")
        self.put("assets.typ", "#let fig(id, ..a) = id\n")
        self.put("slides/theme.typ", THEME)
        self.put("slides/config.typ", DECK_CONFIG)
        self.put("slides/talk.typ", DECK)

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def _record(self, name, body="pdf bytes"):
        """A deck output and the state record a real build would leave."""
        out = self.put(f"slides/{name}.pdf", body)
        record = slides.state_path(self.root, name)
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({
            "schema_version": 1, "target": name, "handout": False,
            "sources": slides.snapshot(self.root, name), "dependencies": [],
            "output_hash": build_state.digest(out)}))
        return out

    # --- the separation ---------------------------------------------------

    def test_deck_sources_are_not_in_the_paper_fingerprint(self):
        """The regression that matters most: a slide edit must not stale the paper."""
        before = build_state.snapshot(self.root)
        self.assertEqual([k for k in before if k.startswith("slides/")], [])
        self.put("slides/talk.typ", DECK + "\n== One more slide\n")
        self.assertEqual(build_state.snapshot(self.root), before)

    def test_a_new_deck_does_not_stale_the_paper(self):
        before = build_state.snapshot(self.root)
        self.put("slides/lab-meeting.typ", DECK)
        self.assertEqual(build_state.snapshot(self.root), before)

    def test_deck_record_keys_are_machine_independent(self):
        """The deck tools come from the installed toolchain in a paper; their
        keys must not be its site-packages path, or a deck built on one
        checkout reads stale on every other."""
        keys = slides.snapshot(self.root, "talk")
        self.assertEqual([k for k in keys if Path(k).is_absolute()], [])
        self.assertIn("tools/slides.py", keys)
        self.assertIsNotNone(keys["tools/slides.py"])

    # --- reaching the id index --------------------------------------------

    def test_deck_ids_reach_the_usage_index(self):
        used = {(u["path"], u["helper"], u["id"])
                for u in manuscript_sources.usages(self.root)}
        self.assertIn(("slides/talk.typ", "s", "deck.only"), used)
        self.assertIn(("slides/talk.typ", "fig", "fig.deck"), used)
        self.assertIn(("paper.typ", "s", "paper.only"), used)

    def test_decks_can_be_excluded_from_the_index(self):
        paths = {u["path"] for u in manuscript_sources.usages(self.root, slides=False)}
        self.assertNotIn("slides/talk.typ", paths)

    def test_a_number_used_only_by_a_deck_is_not_reported_dead(self):
        values = {"deck.only": {"value": 1, "fmt": ""}}
        with patch.object(check_stats, "ROOT", self.root):
            self.assertEqual(check_stats._unused(values), [])
            self.assertTrue(check_stats._unused({"nobody.reads": {"value": 1}}))

    def test_slide_targets_skip_shared_includes(self):
        """config.typ and theme.typ are shared files, not talks to compile."""
        self.put("slides/_macros.typ", "#let x = 1\n")
        self.assertEqual(manuscript_sources.slide_targets(self.root), ("talk",))
        for shared in ("theme", "config", "_macros"):
            with self.subTest(shared=shared), self.assertRaises(ValueError):
                slides.source(self.root, shared)

    @no_shipped_deck
    def test_the_decks_identity_is_not_the_papers(self):
        """The whole point of slides/config.typ: a deck builds where the
        manuscript's own config.typ does not exist at all, which is what a
        manuscript.toml project (docs/multi-document.md) looks like."""
        theme = (ROOT / "slides/theme.typ").read_text()
        self.assertIn('#import "config.typ"', theme)
        self.assertNotIn('"/config.typ"', theme)
        closure = manuscript_sources.slide_files(self.root)
        self.assertIn("slides/config.typ", closure)
        self.assertNotIn("config.typ", closure)

    # --- a deck cannot fail the gate --------------------------------------

    def test_an_undeclared_deck_id_is_a_warning_not_an_error(self):
        with patch.object(check_assets, "ROOT", self.root):
            findings = {(f.level, f.id) for f in check_assets._references({})}
        self.assertIn(("error", "fig.paper"), findings)
        self.assertIn(("warn", "fig.deck"), findings)

    def test_an_asset_shown_only_in_a_talk_is_not_an_orphan(self):
        declared = {"fig.deck": {}, "fig.paper": {}, "fig.nobody": {}}
        with patch.object(check_assets, "ROOT", self.root):
            orphans = {f.id for f in check_assets._references(declared)
                       if "no .typ file references it" in f.msg}
        self.assertEqual(orphans, {"fig.nobody"})

    def test_a_broken_deck_import_does_not_break_the_index(self):
        self.put("slides/talk.typ", '#import "/missing.typ": x\n')
        paths = {u["path"] for u in manuscript_sources.usages(self.root)}
        self.assertIn("paper.typ", paths)
        with self.assertRaises(ValueError):
            manuscript_sources.slide_files(self.root, strict=True)

    # --- the narrow rule set ----------------------------------------------

    def test_slide_check_is_the_narrow_rule_set(self):
        src = ("== Slide\n"
               "- A dash — here, the colour of it, and the the repeat, in a "
               "bullet long enough that it would trip long-sentence in the "
               "manuscript because the splitter reads a whole slide as one "
               "sentence with well over forty words in it altogether now.\n")
        rules = {f.rule for f in
                 prose_check.check_slides({"slides/talk.typ": src}, Config())}
        self.assertEqual(rules, {"em-dash", "british-spelling", "doubled-word"})

    def test_a_typed_number_on_a_slide_is_reported(self):
        stats = self.put("stats.json", json.dumps(
            {"values": {"effect.fold": {"value": 2.07, "fmt": ".2f"}}}))
        with patch.object(prose_check.typst_prose, "STATS_JSON", stats):
            findings = prose_check.check_slides(
                {"slides/talk.typ": "A 2.07-fold change.\n"}, Config())
        self.assertEqual([(f.rule, f.subject) for f in findings],
                         [("derivable-number", "2.07")])

    def test_slide_findings_honour_prose_check_toml(self):
        src = "== S\nThe colour of it.\n"
        cfg = Config(allow={"british-spelling": {"colour"}})
        kept = [f for f in prose_check.check_slides({"slides/talk.typ": src}, cfg)
                if not cfg.suppresses(f)]
        self.assertEqual(kept, [])

    def test_slide_text_is_outside_the_word_count_and_readability(self):
        self.assertEqual(readability.PAPER.name, "paper.typ")
        self.assertEqual(readability.SI.name, "si-body.typ")
        counted = (ROOT / "wordcount.typ").read_text()
        self.assertNotIn("slides", counted)

    # --- build state -------------------------------------------------------

    def test_deck_state_tracks_the_deck_and_not_the_paper(self):
        self._record("talk")
        self.assertEqual(slides.status(self.root, "talk"), "current")

        self.put("paper.typ", PAPER + "\nAn edit the talk never shows.\n")
        self.assertEqual(slides.status(self.root, "talk"), "current")

        self.put("slides/theme.typ", THEME + "#let extra = 1\n")
        self.assertEqual(slides.status(self.root, "talk"), "stale")

    def test_renaming_the_talk_stales_the_deck(self):
        self._record("talk")
        self.assertEqual(slides.status(self.root, "talk"), "current")
        self.put("slides/config.typ", '#let deck-title = "A Better Talk"\n')
        self.assertEqual(slides.status(self.root, "talk"), "stale")

    def test_missing_and_replaced_are_distinguished(self):
        self.assertEqual(slides.status(self.root, "talk"), "missing")
        self.put("slides/talk.pdf", "pdf bytes")
        self.assertEqual(slides.status(self.root, "talk"), "unknown")
        out = self._record("talk")
        out.write_text("someone rebuilt this by hand")
        self.assertEqual(slides.status(self.root, "talk"), "replaced")

    def test_a_dropped_dependency_does_not_refuse_the_next_build(self):
        """The build guard asks whether a source changed WHILE typst ran, not
        whether the dependency set changed between builds.

        That set legitimately shrinks -- dropping an import from the theme
        removes a file from the compiler's list -- and an earlier version read
        the loss as a source vanishing mid-build, refusing every build after.
        """
        self.put("tools/render_stats.py", "")
        self.put("slides/_old.typ", "#let x = 1\n")   # read last time, not now
        slides.write_text(slides.dependency_path(self.root, "talk"),
                          json.dumps(["slides/_old.typ"]))

        def fake_compile(root, name, target, deps, *, handout, draft):
            target.write_bytes(b"%PDF-1.7 fake")
            deps.write_text(json.dumps({"inputs": ["slides/talk.typ"]}))

        with patch.object(slides, "_compile", fake_compile):
            self.assertEqual(slides.build("talk", root=self.root), 0)
        self.assertEqual(slides.status(self.root, "talk"), "current")

    def test_an_unknown_deck_name_says_what_exists(self):
        with self.assertRaisesRegex(ValueError, "talk"):
            slides.source(self.root, "keynote")

    def test_a_deck_named_like_a_variant_is_refused(self):
        """slides/talk-handout.typ would write slides/talk-handout.pdf, the
        same file `just slides-handout talk` writes; whichever built second
        silently replaced the other."""
        self.put("slides/talk-handout.typ", DECK)
        self.put("slides/talk-draft.typ", DECK)
        for name in ("talk-handout", "talk-draft"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "rename the deck"):
                    slides.source(self.root, name)
        # The plain deck beside them is still accepted.
        self.assertTrue(slides.source(self.root, "talk").is_file())

    # --- the real deck ------------------------------------------------------

    @no_shipped_deck
    def test_touying_pin_is_exact(self):
        theme = (ROOT / "slides/theme.typ").read_text()
        self.assertIn("@preview/touying:0.6.1", theme)

    @no_shipped_deck
    @unittest.skipUnless(shutil.which("typst"), "typst not installed")
    def test_the_shipped_deck_compiles_plain_and_as_a_handout(self):
        """Proves /stats.typ and /assets.typ resolve from slides/, which only
        holds because every typst call passes --root."""
        subprocess.run([sys.executable, str(ROOT / "tools/render_stats.py")],
                       cwd=ROOT, check=True, capture_output=True)
        for args in ([], ["--input", "handout=true"]):
            with self.subTest(args=args):
                out = self.root / "compiled.pdf"
                subprocess.run(
                    ["typst", "compile", "--root", str(ROOT), *args,
                     str(ROOT / "slides/talk.typ"), str(out)],
                    cwd=ROOT, check=True, capture_output=True)
                self.assertTrue(out.stat().st_size > 0)


def run_cases() -> bool:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SlideCases)
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
