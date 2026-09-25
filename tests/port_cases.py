"""tools/port.py: a part ported from another repository (manuscript.toml
`upstream`), checked against that repository (docs/multi-document.md).

Each case builds a throwaway upstream git repository and a two-part project.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import port
from document_project import load_project

MANIFEST = '''schema_version = 1
default_document = "thesis"
[parts.intro]
source = "chapters/intro/chapter.typ"
[parts.method]
source = "chapters/method/chapter.typ"
{upstream}
[documents.thesis]
entrypoint = "thesis.typ"
output = "build/thesis.pdf"
parts = ["intro", "method"]
'''
CHAPTER = "Title.\n// >>> BODY START\nProse.\n// <<< BODY END\n"


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@unittest.skipUnless(shutil.which("git"), "git not installed")
class Port(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.up, self.root = base / "paper", base / "thesis"
        self.up.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.org")
        self.git("config", "user.name", "T")
        self.first = self.commit({"a.x": 1.234, "a.y": 10}, {"fig.a": b"A1", "fig.b": b"B1"})
        self.second = self.commit({"a.x": 1.5, "a.z": 3}, {"fig.a": b"A2", "fig.b": b"B1",
                                                           "fig.c": b"C1"})
        for rel, text in (("thesis.typ", '#include "chapters/intro/chapter.typ"\n'
                                         '#include "chapters/method/chapter.typ"\n'),
                          ("chapters/intro/chapter.typ", CHAPTER),
                          ("chapters/method/chapter.typ", CHAPTER),
                          ("chapters/method/schematic.typ",
                           '#import "@preview/cetz:0.3.4"\n#set page(width: auto)\n')):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text)
        figs = self.root / "chapters/method/figures"
        figs.mkdir()
        (figs / "a.png").write_bytes(b"A1")      # stale: fig.a was regenerated
        (figs / "b.png").write_bytes(b"B1")      # current
        (figs / "c.png").write_bytes(b"C1")      # newer than the recorded commit
        (figs / "drawn.png").write_bytes(b"x")   # not upstream's: not reported

    def git(self, *args) -> str:
        return subprocess.run(["git", "-C", str(self.up), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, stats: dict, assets: dict) -> str:
        (self.up / "stats.json").write_text(json.dumps({"values": {
            k: {"value": v, "fmt": ".2f" if isinstance(v, float) else "d"}
            for k, v in stats.items()}}))
        (self.up / "assets.json").write_text(json.dumps({"values": {
            k: {"path": f"figures/{k}.png", "kind": "figure", "hash": sha(v)}
            for k, v in assets.items()}}))
        self.git("add", "-A")
        self.git("commit", "-qm", "c")
        return self.git("rev-parse", "--short", "HEAD")

    def manifest(self, upstream: str) -> None:
        (self.root / "manuscript.toml").write_text(MANIFEST.format(upstream=upstream))

    def run_main(self, *argv) -> tuple[int, str]:
        out = io.StringIO()
        with patch.object(port, "ROOT", self.root), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(out):
            rc = port.main(list(argv))
        return rc, out.getvalue()

    def test_upstream_is_validated(self):
        self.manifest(f'upstream = {{ repo = "{self.up}", commit = "{self.first}" }}')
        up = load_project(self.root).parts["method"].upstream
        self.assertEqual((up.repo, up.commit, up.figures), (str(self.up), self.first, None))
        self.assertIsNone(load_project(self.root).parts["intro"].upstream)
        for bad in ('upstream = { repo = "x", commit = "HEAD" }',
                    'upstream = { repo = "", commit = "abcdef1" }',
                    'upstream = { repo = "x", commit = "abcdef1", branch = "main" }',
                    'upstream = { repo = "x", commit = "abcdef1", figures = "nope" }'):
            with self.subTest(bad=bad):
                self.manifest(bad)
                with self.assertRaises(ValueError):
                    load_project(self.root)

    def test_check_warns_on_a_moved_head_stale_figures_and_page_setup(self):
        self.manifest(f'upstream = {{ repo = "{self.up}", commit = "{self.first}" }}')
        rc, out = self.run_main("check")
        self.assertEqual(rc, 0, out)
        self.assertIn(f"1 commit(s) past {self.first}", out)
        self.assertIn("stats.json: 1 changed, 1 added, 1 removed", out)
        self.assertIn("figures/a.png is fig.a as of", out)
        self.assertIn("figures/c.png is fig.c from a commit newer", out)
        self.assertNotIn("b.png", out)
        self.assertNotIn("drawn.png", out)
        self.assertIn("chapters/method/schematic.typ:2 sets the page", out)
        self.assertEqual(self.run_main("check", "--strict")[0], 1)

    def test_a_current_port_is_quiet(self):
        (self.root / "chapters/method/schematic.typ").unlink()
        for name in ("a", "c"):
            (self.root / f"chapters/method/figures/{name}.png").write_bytes(
                {"a": b"A2", "c": b"C1"}[name])
        self.manifest(f'upstream = {{ repo = "{self.up}", commit = "{self.second}" }}')
        rc, out = self.run_main("check")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("warn:", out)
        self.assertIn("matches its recorded upstream commit", out)

    def test_a_missing_repository_is_skipped(self):
        (self.root / "chapters/method/schematic.typ").unlink()
        self.manifest('upstream = { repo = "../elsewhere", commit = "abcdef1" }')
        rc, out = self.run_main("check", "--strict")
        self.assertEqual(rc, 0, out)
        self.assertIn("not on this machine; skipped", out)
        self.assertIn("nothing checked", out)

    def test_diff_lists_the_numbers_to_recopy(self):
        self.manifest(f'upstream = {{ repo = "{self.up}", commit = "{self.first}" }}')
        rc, out = self.run_main("diff", "method")
        self.assertEqual(rc, 0, out)
        self.assertIn("changed  a.x: 1.23 -> 1.50", out)
        self.assertIn("added    a.z: 3", out)
        self.assertIn("removed  a.y: was 10", out)
        self.assertEqual(self.run_main("diff", "intro")[0], 2)
        self.assertEqual(self.run_main("diff", "nope")[0], 2)

    def test_no_manifest_is_a_pass(self):
        rc, out = self.run_main("check")
        self.assertEqual(rc, 0)
        self.assertIn("no manuscript.toml", out)


def run_cases() -> bool:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Port)
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
