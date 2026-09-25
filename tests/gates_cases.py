"""The gates around a manuscript's life: availability, stats safety, the agent
loop, a revision round, and the review ledger's writer.

What this guards: an accession cited in the text but not in the availability
statement, a placeholder, a missing section and an unarchived code base each
fail, and project.toml opts out; project.toml's [availability], [stats] and
[response] tables are validated strictly; `_stats.write()` refuses to retire
an id without --prune, reports every failing guard at once and records them
for `just assets --explain`; a whole float with no fmt prints as an integer;
[stats] globs exempt ids from "unused"; the build lock re-enters inside
`just paper`, waits, and refuses a second holder; a stale output names the
changed file; the verify stamp records a pass only for an unmoved tree; the
edit guard's --revision mode allows new ids and refs but not a typed numeral;
ledger ids never collide, `Closes:` trailers close rows, and a recorded hash
that disagrees with the trailer fails; the response letter's points are held
to the ledger.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))

import actions
import availability
import build_state
import check_actions as ca
import check_stats
import gate
import project_hooks
import prose_edit_guard
import response
import typst_prose

HEADER = ("| id | severity | status | source | summary | fix | closed |\n"
          "|---|---|---|---|---|---|---|\n")


def ledger_text(*rows: str) -> str:
    return "# Review actions\n\nRules.\n\n" + HEADER + "".join(r + "\n" for r in rows)


class Temp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def put(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True,
                              text=True, env={**os.environ, "GIT_AUTHOR_NAME": "t",
                                              "GIT_AUTHOR_EMAIL": "t@example.org",
                                              "GIT_COMMITTER_NAME": "t",
                                              "GIT_COMMITTER_EMAIL": "t@example.org"}).stdout


STATEMENT = """
= Data and Code Availability

Spectra are at PRIDE (PXD000001). Code is archived at Zenodo
(doi:10.5281/zenodo.1234567).
"""


class Availability(Temp):
    def kinds(self, src, config=None):
        return sorted(f.kind for f in availability.check(self.root, {"paper.typ": src},
                                                          config or {}))

    def test_complete_statement_passes(self):
        self.assertEqual(self.kinds("= Methods\nWe used PXD000001.\n" + STATEMENT), [])

    def test_cited_accession_missing_from_statement(self):
        found = availability.check(self.root, {"paper.typ": "= Methods\nPXD999999.\n" + STATEMENT}, {})
        self.assertEqual([f.kind for f in found], ["missing"])
        self.assertIn("PXD999999", found[0].message)

    def test_placeholder_no_section_no_archive(self):
        self.assertIn("placeholder", self.kinds(
            STATEMENT.replace("PXD000001", "PXDXXXXXX")))
        self.assertIn("no-section", self.kinds("= Methods\nWe used PXD000001.\n"))
        self.assertEqual(self.kinds(STATEMENT.replace("doi:10.5281/zenodo.1234567",
                                                      "github.com/x/y")), ["no-archive"])

    def test_bold_run_in_section_and_opt_outs(self):
        src = "*Data Availability.* Data at PXD000001.\n\n= Next\nPXD000001.\n"
        self.assertEqual(self.kinds(src), ["no-archive"])
        self.assertEqual(self.kinds(src, {"require_code_archive": False}), [])
        self.assertEqual(self.kinds("PXD1234567", {"enabled": False}), [])
        self.assertEqual(self.kinds("= M\nPXD000002\n" + STATEMENT,
                                    {"disable": ["PRIDE/ProteomeXchange"]}), [])


class ProjectToml(Temp):
    def load(self, body: str):
        self.put("project.toml", "schema_version = 1\n" + body)
        return project_hooks.load(self.root)

    def test_valid_tables(self):
        p = self.load('[availability]\nenabled = false\npatterns = ["LAB-\\\\d+"]\n'
                      '[stats]\nsi-only = ["si.*"]\n[response]\nfile = "letters/r1.typ"\n')
        self.assertEqual(p.availability["enabled"], False)
        self.assertEqual(p.stats_scopes, {"si-only": ("si.*",)})
        self.assertEqual(p.response, "letters/r1.typ")

    def test_invalid_tables(self):
        for body in ('[availability]\nenabled = "no"\n',
                     '[availability]\nunknown = 1\n',
                     '[availability]\npatterns = ["("]\n',
                     '[stats]\nsi_only = ["x"]\n',
                     '[response]\nfile = "r.pdf"\n'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.load(body)


class StatsSafety(Temp):
    def test_retiring_an_id_needs_prune(self):
        from _stats import StatError, Stats
        out = self.root / "stats.json"
        quiet = contextlib.redirect_stdout(io.StringIO())
        with quiet:
            st = Stats(); st.add("a.one", 1); st.add("a.two", 2); st.write(out)
            st = Stats(); st.add("a.one", 1)
            with unittest.mock.patch.dict(os.environ, {"PAPER_STATS_PRUNE": ""}), \
                    unittest.mock.patch.object(sys, "argv", ["gen_stats.py"]):
                with self.assertRaisesRegex(StatError, "a.two"):
                    st.write(out)
            self.assertIn("a.two", json.loads(out.read_text())["values"])
            with unittest.mock.patch.dict(os.environ, {"PAPER_STATS_PRUNE": "1"}):
                st.write(out)
        self.assertNotIn("a.two", json.loads(out.read_text())["values"])

    def test_every_failing_guard_reported_and_recorded(self):
        from _stats import StatError, Stats
        out = self.root / "stats.json"
        st = Stats()
        st.add("g.one", 1.0, sign="-")
        st.add("g.two", 5.0, between=(0, 1))
        with contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaises(StatError) as caught:
            st.write(out)
        self.assertIn("g.one", str(caught.exception))
        self.assertIn("g.two", str(caught.exception))
        failures = json.loads((self.root / ".build-state/stats-guard-failures.json").read_text())
        self.assertEqual(sorted(failures), ["g.one", "g.two"])

    def test_whole_float_prints_as_integer(self):
        self.assertEqual(typst_prose.display_of({"value": 14.0}), "14")
        self.assertEqual(typst_prose.display_of({"value": 14.5}), "14.5")
        self.assertEqual(typst_prose.display_of({"value": 14.0, "fmt": ".1f"}), "14.0")

    def test_scoped_ids_are_not_unused(self):
        self.put("project.toml", 'schema_version = 1\n[stats]\nsi-only = ["si.*"]\n'
                 'evidence-only = ["nothing.*"]\n')
        self.put("paper.typ", '#s("used")\n')
        with unittest.mock.patch.object(check_stats, "ROOT", self.root):
            found = check_stats._unused({"used": {}, "si.a": {}, "other": {}})
        ids = sorted(f.id for f in found)
        self.assertEqual(ids, ["nothing.*", "other"])


class AgentLoop(Temp):
    def test_build_lock_refuses_then_reenters(self):
        with build_state.build_lock(self.root, wait=0):
            with self.assertRaisesRegex(ValueError, "another manuscript build"):
                with build_state.build_lock(self.root, wait=0):
                    pass
            held = str((self.root / ".build-state/build.lock").resolve())
            with unittest.mock.patch.dict(os.environ, {build_state.HELD: held}):
                with build_state.build_lock(self.root, wait=0):
                    pass

    def test_free_space_floor(self):
        with unittest.mock.patch.dict(os.environ, {"PAPER_MIN_FREE_MB": str(10 ** 12)}):
            self.assertIn("free", build_state.free_space_error(self.root))
            with self.assertRaises(ValueError):
                with build_state.build_lock(self.root, wait=0):
                    pass
        with unittest.mock.patch.dict(os.environ, {"PAPER_MIN_FREE_MB": "0"}):
            self.assertIsNone(build_state.free_space_error(self.root))

    def test_stale_output_names_changed_file(self):
        self.put("paper.typ", "a")
        self.put("stats.json", '{"values": {}}')
        recorded = build_state.snapshot(self.root)
        self.put("paper.typ", "b")
        changed = build_state.changed_sources(self.root, recorded)
        self.assertEqual(changed, ["paper.typ"])
        self.assertIn("paper.typ", build_state.changed_note(changed))

    def test_verify_stamp(self):
        self.put("paper.typ", "one")
        fp = gate.fingerprint(self.root)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            gate.stamp(self.root, fp, 0)
            self.assertEqual(gate.check_stamp(self.root), 0)
            self.put(".build-state/other.json", "{}")     # local state: ignored
            self.assertEqual(gate.check_stamp(self.root), 0)
            self.put("paper.typ", "two")
            self.assertEqual(gate.check_stamp(self.root), 1)
            gate.stamp(self.root, fp, 0)                  # moved during verify
            self.assertFalse((self.root / gate.STAMP).exists())
            gate.stamp(self.root, gate.fingerprint(self.root), 1)
            self.assertFalse((self.root / gate.STAMP).exists())


class RevisionEditGuard(Temp):
    def run_guard(self, before: str, after: str, revision: bool) -> tuple[int, str]:
        self.put("paper.typ", before)
        with unittest.mock.patch.object(prose_edit_guard, "ROOT", self.root), \
                unittest.mock.patch.object(prose_edit_guard, "SNAP_DIR", self.root / ".edit-guard"), \
                unittest.mock.patch.object(prose_edit_guard, "current",
                                           lambda: {"paper.typ": prose_edit_guard.profile(
                                               self.root / "paper.typ")}), \
                unittest.mock.patch.object(prose_edit_guard, "_si_prefix", lambda: None):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                prose_edit_guard.snapshot("t")
                self.put("paper.typ", after)
                rc = prose_edit_guard.check("t", revision)
        return rc, out.getvalue()

    BEFORE = '= Results\n\nThe rate was #s("rate") @smith.\n'

    def test_new_ids_refs_and_headings_pass_in_revision_only(self):
        after = (self.BEFORE + '\n= Controls\n\nThe control gave #s("ctl-2") '
                 '@jones.\n')
        self.assertEqual(self.run_guard(self.BEFORE, after, False)[0], 1)
        rc, out = self.run_guard(self.BEFORE, after, True)
        self.assertEqual(rc, 0, out)
        self.assertIn("note", out)

    def test_typed_numeral_still_fails_in_revision(self):
        rc, out = self.run_guard(self.BEFORE, self.BEFORE + "\nWe added 37 samples.\n", True)
        self.assertEqual(rc, 1)
        self.assertIn("37", out)

    def test_dropped_interval_is_a_dropped_number(self):
        before = self.BEFORE + '\nIts interval was #ci("rate").\n'
        self.assertEqual(self.run_guard(before, before, False)[0], 0)
        rc, out = self.run_guard(before, self.BEFORE + "\nIts interval was wide.\n", False)
        self.assertEqual(rc, 0, out)
        self.assertIn("statistic call(s) dropped", out)
        self.assertIn("ci:rate", out)
        # Pointing the interval at another id is a changed number.
        rc, out = self.run_guard(before, before.replace('#ci("rate")', '#ci("other")'), False)
        self.assertEqual(rc, 1, out)

    def test_lit_unlike_id_digits_are_names(self):
        before = self.BEFORE + '\nHeld at #lit("40") C.\n'
        after = self.BEFORE + '\nHeld at #lit("40", unlike: ("run-2", "t-3")) C.\n'
        rc, out = self.run_guard(before, after, False)
        self.assertEqual(rc, 0, out)


class Ledger(Temp):
    def setUp(self):
        super().setUp()
        self.ledger = self.root / "reviews" / "ACTIONS.md"

    def test_ids_never_collide(self):
        self.put("reviews/ACTIONS.md", ledger_text(
            "| A-0003 | minor | open | f.md#1 | s | /paper:copy-edit | |"))
        self.assertEqual(actions.reserve(self.ledger, 2), ["A-0004", "A-0005"])
        # A reserved id is never handed out again, though no row carries it.
        rid = actions.add(self.ledger, "major", "f.md#2", "a | pipe", "/paper:copy-edit")
        self.assertEqual(rid, "A-0006")
        rows, errors = ca.parse(self.ledger.read_text())
        self.assertEqual(errors, [])
        self.assertEqual([r["id"] for r in rows], ["A-0003", "A-0006"])
        self.assertEqual(rows[-1]["summary"], "a | pipe")
        with self.assertRaises(ValueError):
            actions.add(self.ledger, "huge", "f", "s", "x")

    def test_add_creates_the_ledger(self):
        self.assertEqual(actions.add(self.ledger, "minor", "f.md#1", "s", "x"), "A-0001")
        self.assertEqual(ca.parse(self.ledger.read_text())[1], [])

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_closes_trailer_and_hash_verification(self):
        self.git("init", "-q")
        self.put("reviews/ACTIONS.md", ledger_text(
            "| A-0001 | major | open | f.md#1 | s | /paper:copy-edit | |",
            "| A-0002 | minor | open | f.md#2 | s | /paper:copy-edit | uncommitted: x |",
            "| A-0003 | minor | open | f.md#3 | s | /paper:copy-edit | |"))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Fix wording\n\nCloses: A-0001, A-0002")
        sha = self.git("rev-parse", "HEAD").strip()
        closed, notes = actions.close(self.ledger, self.root)
        self.assertEqual(len(closed), 2, (closed, notes))
        rows = {r["id"]: r for r in ca.parse(self.ledger.read_text())[0]}
        self.assertEqual(rows["A-0001"]["status"], "done")
        self.assertTrue(sha.startswith(rows["A-0002"]["closed"]))
        self.assertEqual(rows["A-0003"]["status"], "open")
        errors, warnings = actions.verify_hashes(list(rows.values()), self.root)
        self.assertEqual((errors, warnings), ([], []))
        # A hand-typed hash that is not the trailer's commit fails.
        self.git("commit", "-q", "--allow-empty", "-m", "other")
        other = self.git("rev-parse", "--short=10", "HEAD").strip()
        bad = dict(rows["A-0001"], closed=other)
        errors, _ = actions.verify_hashes([bad], self.root)
        self.assertEqual(len(errors), 1)
        errors, warnings = actions.verify_hashes([dict(rows["A-0003"], status="done",
                                                       closed="deadbeef12")], self.root)
        self.assertEqual((len(errors), len(warnings)), (0, 1))


class ResponseLetter(unittest.TestCase):
    ROWS = [
        {"id": "A-0001", "status": "done", "closed": "3f2a91c0de"},
        {"id": "A-0002", "status": "done", "closed": "uncommitted: soon"},
        {"id": "A-0003", "status": "open", "closed": ""},
    ]

    def test_points_held_to_the_ledger(self):
        ok = [{"id": "R1.1", "status": "done", "actions": ["A-0001"]},
              {"id": "R1.2", "status": "rebut", "actions": []},
              {"id": "R1.3", "status": "todo", "actions": ["A-0003"]}]
        self.assertEqual(response.problems(ok, self.ROWS), [])
        bad = [{"id": "R1.1", "status": "done", "actions": []},
               {"id": "R1.1", "status": "done", "actions": ["A-0002"]},
               {"id": "R2.1", "status": "done", "actions": ["A-0003", "A-0099"]},
               {"id": "R2.2", "status": "maybe", "actions": []}]
        found = response.problems(bad, self.ROWS)
        text = "\n".join(found)
        for needle in ("cites no", "used twice", "not a commit", "A-0003 is open",
                       "A-0099, which is not", "unknown status"):
            self.assertIn(needle, text)

    def test_diff_ops(self):
        ops = response.diff_ops("a b c d".split(), "a x c d e".split())
        self.assertEqual(ops, [("same", "a"), ("del", "b"), ("ins", "x"),
                               ("same", "c d"), ("ins", "e")])
        self.assertIn("<del>b</del>", response.render_html(ops, "t"))

    @unittest.skipUnless(shutil.which("typst"), "typst is not installed")
    def test_template_compiles_and_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stats.typ").write_text("#let s(id) = id\n#let lit(x) = x\n")
            (root / "config.typ").write_text('#let paper-title = "T"\n')
            shutil.copy(response.TEMPLATE, root / "letter.typ")
            out = subprocess.run(["typst", "query", "--root", str(root), str(root / "letter.typ"),
                                  "<response-point>", "--field", "value"],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(json.loads(out.stdout),
                             [{"id": "R1.1", "status": "todo", "actions": []}])


CASES = (Availability, ProjectToml, StatsSafety, AgentLoop, RevisionEditGuard, Ledger,
         ResponseLetter)


def run_cases() -> bool:
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite(loader.loadTestsFromTestCase(c) for c in CASES)
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
