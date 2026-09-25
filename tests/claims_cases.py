"""Claims held to the numbers (5.0.0): uncertainty fields, `expect` relations,
`#ci()`, `#lit(..., unlike:)`, the wording rules, claims.toml, the cover
letter, shared vocabularies and [[software]].

Every case builds its own stats.json / project.toml in a temporary directory;
nothing here reads the manuscript's.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))

import check_stats as cs
import claim_rules as cr
import project_hooks as ph
import prose_check as pc
import prose_rules as pr
import typst_prose as tp
from manifest_validation import relation_errors, uncertainty_errors


def gen(value, **kw) -> dict:
    rec = {"value": value, "fmt": ".1f", "unit": "", "desc": "", "expect": {},
           "origin": {"by": "analysis/scripts/gen_stats.py"}}
    rec.update(kw)
    return rec


class Tmp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def stats(self, values: dict) -> Path:
        p = self.root / "stats.json"
        p.write_text(json.dumps({"values": values}))
        return p

    def project(self, text: str) -> None:
        (self.root / "project.toml").write_text("schema_version = 1\n" + text)


class Uncertainty(unittest.TestCase):
    def test_consistent_fields_pass(self):
        self.assertEqual(uncertainty_errors(
            {"value": 1, "lo": 0.5, "hi": 1.5, "level": 0.95, "n": 12,
             "sd": 0.2, "measurement": "replicated"}), [])

    def test_each_inconsistency_is_an_error(self):
        for rec in ({"lo": 2, "hi": 1}, {"lo": 1}, {"lo": 0, "hi": 1, "level": 95},
                    {"level": 0.95}, {"n": 0}, {"n": 2.5}, {"sd": -1},
                    {"measurement": "twice"}):
            with self.subTest(rec=rec):
                self.assertTrue(uncertainty_errors({"value": 1, **rec}))

    def test_v3_checksum_covers_the_interval(self):
        import _stats
        unc = {"lo": 1.0, "hi": 3.0}
        rec = gen(2.0, checksum=_stats._checksum(2.0, unc), **unc)
        self.assertTrue(rec["checksum"].startswith("v3:"))
        self.assertEqual(cs._checksum({"a": rec}), [])
        rec["hi"] = 2.5                      # a hand-narrowed interval
        self.assertTrue(cs._checksum({"a": rec}))

    def test_v2_is_unchanged_without_uncertainty(self):
        import _stats
        want = "v2:" + hashlib.sha256(b"2.0").hexdigest()[:16]
        self.assertEqual(_stats._checksum(2.0), want)


class RoundTrip(Tmp):
    def test_add_writes_uncertainty_and_relations(self):
        import contextlib, io
        from _stats import Stats
        st = Stats()
        st.add("m.b", 3.0, fmt=".1f")
        st.add("m.a", 9.0, fmt=".1f", lo=8.0, hi=10.0, level=0.95, n=5,
               measurement="replicated", gt="m.b", ratio_to=("m.b", 3, None))
        with contextlib.redirect_stdout(io.StringIO()):
            st.write(out=self.root / "stats.json")
        e = json.loads((self.root / "stats.json").read_text())["values"]["m.a"]
        self.assertEqual((e["lo"], e["hi"], e["level"], e["n"], e["measurement"]),
                         (8.0, 10.0, 0.95, 5, "replicated"))
        self.assertEqual(e["expect"]["gt"], "m.b")
        self.assertEqual(e["expect"]["ratio_to"], {"id": "m.b", "min": 3})
        self.assertTrue(e["checksum"].startswith("v3:"))


class Relations(unittest.TestCase):
    values = {"a": gen(9.0), "b": gen(3.0), "z": gen(0.0), "t": gen("label")}

    def errs(self, expect, **kw):
        return relation_errors("a", {"value": 9.0, "expect": expect}, self.values, **kw)

    def test_held_relations_are_silent(self):
        for expect in ({"gt": "b"}, {"ge": ["b", "a"]}, {"ratio_to": {"id": "b", "min": 3}},
                       {"diff_to": {"id": "b", "min": 5, "max": 7}}):
            with self.subTest(expect=expect):
                self.assertEqual(self.errs(expect), [])

    def test_broken_relations_are_errors(self):
        for expect in ({"lt": "b"}, {"ratio_to": {"id": "b", "min": 4}},
                       {"diff_to": {"id": "b", "max": 1}}, {"ratio_to": {"id": "z", "min": 1}},
                       {"gt": "t"}, {"gt": "missing"}):
            with self.subTest(expect=expect):
                self.assertTrue(self.errs(expect))

    def test_missing_id_waits_while_generating(self):
        self.assertEqual(self.errs({"gt": "missing"}, missing_ok=True), [])

    def test_bad_shape_is_a_guard_error(self):
        from manifest_validation import guard_errors
        self.assertTrue(guard_errors(9.0, {"ratio_to": {"min": 3}}))
        self.assertTrue(guard_errors(9.0, {"gt": 3}))
        self.assertEqual(guard_errors(9.0, {"gt": "b", "ratio_to": [{"id": "b", "min": 1}]}), [])


class Intervals(Tmp):
    def test_own_and_sibling_intervals_resolve(self):
        p = self.stats({"m": gen(2.04, lo=1.51, hi=2.63, level=0.95, fmt=".2f"),
                        "k.lo": gen(0.3), "k.hi": gen(0.9), "k": gen(0.6)})
        out = tp.resolve_stats('#ci("m") and #ci("m", level: true); #ci("k")', p)
        self.assertEqual(out, "1.51–2.63 and 95% CI 1.51–2.63; 0.3–0.9")

    def test_unknown_interval_fails_like_s(self):
        p = self.stats({"m": gen(1.0)})
        with self.assertRaises(SystemExit):
            tp.resolve_stats('#ci("m")', p)


class NamedVouch(Tmp):
    def test_unlike_silences_only_the_named_collision(self):
        p = self.stats({"a": gen(84.2), "b": gen(84.2)})
        for src, want in (('#lit("84.2")', 1),                    # plain lit never bypasses
                          ('#lit("84.2", unlike: ("a", "b"))', 0),
                          ('#lit("84.2", unlike: "a")', 1)):      # b still collides
            with self.subTest(src=src):
                self.assertEqual(len(pc.check_derivable_numbers({"t": src}, p)), want)

    def test_stale_vouch(self):
        values = {"a": gen(84.2), "c": gen(12.5)}
        for src, want in (('#lit("84.2", unlike: "a")', 0),
                          ('#lit("84.2", unlike: "gone")', 1),
                          ('#lit("84.2", unlike: "c")', 1)):
            with self.subTest(src=src):
                self.assertEqual(len(cr.check_stale_vouches({"t": src}, values)), want)

    def test_counts(self):
        self.assertEqual(cr.vouch_counts({"t": '#lit("1") #lit("2", unlike: "x")'}), (1, 1))


class Wording(unittest.TestCase):
    values = {"acc": gen(92.2, fmt=".0f"), "err": gen(2.13, fmt=".1f"),
              "ex": gen(2.0, fmt=".1f"), "e2": gen(2.07, fmt=".1f"), "pct": gen(0.994, fmt=".0%"),
              "d": gen(0.4, lo=-0.1, hi=0.9, fmt=".1f"),
              "p": gen(0.5, lo=0.2, hi=0.8, fmt=".1f"),
              "t": gen(12.0, measurement="single-run"),
              "r": gen(12.0, measurement="replicated")}

    def bound(self, src):
        return len(cr.check_bound_rounding({"t": src}, self.values))

    def test_bound_rounding(self):
        for src, want in (('accuracy was #s("acc")% or less.', 1),   # 92.2 shown as 92
                          ('error fell below #s("err") units.', 1),  # 2.13 shown as 2.1
                          ('error stayed above #s("err") units.', 0),
                          ('error was below #s("ex") units.', 0),    # exact: nothing lost
                          ('the error exceeded #s("e2") units.', 1),  # 2.07 shown as 2.1
                          ('No error exceeded #s("e2") units.', 0),   # negation: an upper bound
                          ('No error exceeded #s("err") units.', 1),
                          ('values range over #s("err") to 5.', 0),
                          ('coverage under #s("pct").', 1)):         # 0.994 shown as 99%
            with self.subTest(src=src):
                self.assertEqual(self.bound(src), want)

    def test_interval_wording(self):
        f = lambda src: len(cr.check_interval_wording({"t": src}, self.values))
        self.assertEqual(f('The interval #ci("d") excludes zero.'), 1)
        self.assertEqual(f('The interval #ci("p") excludes zero.'), 0)
        self.assertEqual(f('The interval #ci("p") includes zero.'), 1)
        self.assertEqual(f('The interval #ci("d") includes zero.'), 0)

    def test_single_run_timing(self):
        f = lambda src: len(cr.check_single_run_timing({"t": src}, self.values))
        self.assertEqual(f('The search took #s("t") s.'), 1)
        self.assertEqual(f('It was #s("t")-fold faster.'), 1)
        self.assertEqual(f('The search took #s("r") s.'), 0)
        self.assertEqual(f('We found #s("t") peptides.'), 0)


class Claims(Tmp):
    def test_retired_wording_is_an_error(self):
        (self.root / "claims.toml").write_text(
            '[[claim]]\nid = "speed"\nphrase = "about twice as fast"\n'
            'retired = ["an order of magnitude faster"]\n')
        texts = {"paper.typ": "It is an order of\nmagnitude *faster* today.",
                 "si-body.typ": "// an order of magnitude faster (old)\nclean."}
        found = cr.check_retired_claims(self.root, texts)
        self.assertEqual([(f.rule, f.severity, f.where) for f in found],
                         [("retired-claim", "error", "paper.typ")])

    def test_no_registry_is_silent_and_a_bad_one_is_reported(self):
        self.assertEqual(cr.check_retired_claims(self.root, {"p": "x"}), [])
        (self.root / "claims.toml").write_text('[[claim]]\nid = "x"\n')
        self.assertEqual([f.rule for f in cr.check_retired_claims(self.root, {})],
                         ["project-config"])


class CoverLetter(Tmp):
    def test_letterhead_is_not_prose(self):
        src = ('#let x = 1\n#set page(margin: 1in)\n#corresponding.name \\\n'
               'Dear Editor, we report #s("a") gains.\n')
        body = cr.cover_letter_prose(src)
        self.assertNotIn("corresponding", body)
        self.assertIn('#s("a")', body)

    def test_letter_findings_are_capped_at_warn(self):
        self.stats({"a": gen(84.2)})
        (self.root / "cover-letter.typ").write_text(
            "#let x = 1\nDear Editor, recovery reached 84.2% overall.\n")
        found, cap = pc.claim_checks(self.root, pr.Config(), {})
        self.assertIn("derivable-number", {f.rule for f in found})
        self.assertEqual(cap, frozenset({"cover-letter.typ"}))
        self.project('[prose]\ncover_letter = "error"\n')
        self.assertEqual(pc.claim_checks(self.root, pr.Config(), {})[1], frozenset())
        self.project('[prose]\ncover_letter = "off"\n')
        found, _ = pc.claim_checks(self.root, pr.Config(), {})
        self.assertNotIn("derivable-number", {f.rule for f in found})


class Hooks(Tmp):
    def test_prose_and_software_load(self):
        self.project('[prose]\nvocab = ["proteomics"]\n\n[[software]]\nname = "x"\n'
                     'repo = "https://example.org/x"\nref = "v1.2.0"\ndocs = ["README.md"]\n')
        p = ph.load(self.root)
        self.assertEqual(p.prose_vocab, ("proteomics",))
        self.assertEqual(p.cover_letter, "warn")
        self.assertEqual(p.software[0]["ref"], "v1.2.0")

    def test_bad_tables_are_rejected(self):
        for text in ('[prose]\nvocabs = ["x"]\n', '[prose]\ncover_letter = "loud"\n',
                     '[prose]\nvocab = "proteomics"\n',
                     '[[software]]\nname = "x"\nrepo = "r"\n',
                     '[[software]]\nname = "x"\nrepo = "r"\nref = "v1"\nextra = 1\n'):
            with self.subTest(text=text):
                self.project(text)
                with self.assertRaises(ValueError):
                    ph.load(self.root)

    def test_shipped_vocabulary_merges(self):
        self.project('[prose]\nvocab = ["proteomics"]\n')
        cfg = pr._with_shared_vocab(self.root, pr.Config())
        self.assertIn("lc-ms", cfg.allow["unexpanded-acronym"])


def run_cases() -> bool:
    suite = unittest.TestSuite()
    for case in (Uncertainty, RoundTrip, Relations, Intervals, NamedVouch, Wording, Claims,
                 CoverLetter, Hooks):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
