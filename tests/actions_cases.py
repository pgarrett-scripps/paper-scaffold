"""tools/check_actions.py: the review action ledger, reviews/ACTIONS.md.

Every case builds its own ledger in a temporary directory; nothing here reads
the manuscript's reviews/, which belongs to the paper and changes with it.
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_actions as ca

HEADER = ("| id | severity | status | source | summary | fix | closed |\n"
          "|---|---|---|---|---|---|---|\n")


def ledger(*rows: str) -> str:
    return "# Review actions\n\nRules.\n\n" + HEADER + "".join(r + "\n" for r in rows)


class Actions(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.path = self.dir / "reviews" / "ACTIONS.md"

    def run_main(self, text: str | None, *argv: str) -> tuple[int, str]:
        if text is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = ca.main(list(argv), ledger=self.path, template=ca.TEMPLATE)
        return rc, out.getvalue()

    def test_template_is_a_valid_empty_ledger(self):
        rows, errors = ca.parse(ca.TEMPLATE.read_text())
        self.assertEqual((rows, errors), ([], []))
        self.assertEqual(ca.next_id(rows), "A-0001")

    def test_missing_ledger_is_a_silent_pass(self):
        self.assertEqual(self.run_main(None), (0, ""))

    def test_counts_next_id_and_blocker_warning(self):
        rc, out = self.run_main(ledger(
            "| A-0001 | blocker | open | 2026-09-22-claim-audit.md#1 | Wrong sign | /paper:fix-verify | |",
            "| A-0002 | minor | done | 2026-09-22-prose-review.md#3 | Vague noun | /paper:copy-edit | abc1234 |",
            "| A-0009 | major | wontfix | x.md#2 | Out of scope | author decision | kept on purpose |",
            "| A-0003 | major | open | x.md#4 | Uses \\| pipe | /paper:copy-edit | reopened 2026-09-30: back |",
        ), "--open")
        self.assertEqual(rc, 0)
        self.assertIn("actions: 2 open (1 blocker, 1 major, 0 minor), 1 done, 1 wontfix; "
                      "next id A-0010", out)
        self.assertIn("WARNING: 1 open blocker(s) in reviews/ACTIONS.md: A-0001", out)
        self.assertIn("Uses | pipe", out)
        self.assertLess(out.index("A-0001  blocker"), out.index("A-0003  major"))

    def test_no_warning_without_open_blockers(self):
        rc, out = self.run_main(ledger(
            "| A-0001 | blocker | done | x.md#1 | Fixed | /paper:fix-verify | uncommitted: in tree |"))
        self.assertEqual(rc, 0)
        self.assertNotIn("WARNING", out)

    def test_malformed_rows_fail(self):
        cases = {
            "duplicate id": ("| A-0001 | minor | open | x.md | a | b | |",
                             "| A-0001 | minor | open | x.md | a | b | |"),
            "bad id": ("| 7 | minor | open | x.md | a | b | |",),
            "bad severity": ("| A-0001 | critical | open | x.md | a | b | |",),
            "bad status": ("| A-0001 | minor | fixed | x.md | a | b | |",),
            "done without closed": ("| A-0001 | minor | done | x.md | a | b | |",),
            "wontfix without closed": ("| A-0001 | minor | wontfix | x.md | a | b | |",),
            "empty summary": ("| A-0001 | minor | open | x.md |  | b | |",),
            "cell count": ("| A-0001 | minor | open | x.md | a | b | c | d |",),
        }
        for name, rows in cases.items():
            with self.subTest(name):
                rc, out = self.run_main(ledger(*rows))
                self.assertEqual(rc, 1, out)
                self.assertIn("malformed", out)

    def test_missing_or_doubled_header_fails(self):
        self.assertEqual(self.run_main("# Review actions\n\nNo table.\n")[0], 1)
        self.assertEqual(self.run_main(ledger() + "\n" + HEADER)[0], 1)
        self.assertEqual(self.run_main(
            "| id | severity | status | source | summary | fix | closed |\n| A-0001 |\n")[0], 1)

    def test_text_after_the_table_is_ignored(self):
        rc, _ = self.run_main(ledger("| A-0001 | minor | open | x.md | a | b | |")
                              + "\nNotes below the table.\n| not | a | ledger |\n")
        self.assertEqual(rc, 0)

    def test_init_creates_once(self):
        self.assertEqual(self.run_main(None, "--init")[0], 0)
        self.assertEqual(self.path.read_text(), ca.TEMPLATE.read_text())
        rc, out = self.run_main(None, "--init")
        self.assertEqual(rc, 2)
        self.assertIn("left untouched", out)


def run_cases() -> bool:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Actions)
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
