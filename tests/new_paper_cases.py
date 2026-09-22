"""scripts/new-paper.sh actually produces a usable manuscript directory."""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

def run_cases() -> bool:
    """scripts/new-paper.sh actually produces a usable manuscript directory.

    This runs in the test suite rather than as its own recipe because the script
    is the front door: if it breaks, the failure lands on someone's first five
    minutes with the scaffold, which is the worst possible place to find out. It
    is also the one piece here with no other coverage -- everything else is
    exercised every time the manuscript is built.

    --no-build --no-git, so this needs neither the network (the arkheion template
    is fetched on a first compile) nor a git identity, and takes about a second.
    The build path is deliberately not covered: it is a straight `just paper`,
    already the most exercised code in the repository.
    """
    script = ROOT / "scripts" / "new-paper.sh"
    if not script.is_file():
        # Expected in a derived manuscript: new-paper.sh excludes scripts/ from
        # the copy, because a paper does not make papers.
        print("  new-paper.sh: absent, skipped (this is a derived manuscript)")
        return True

    ok = True
    # A title containing a double quote is the case the Python rewrite exists
    # for. Through sed it would close the Typst string early and the rest of the
    # line would be parsed as code.
    title = 'The "Quoted" Study: 20% Faster'
    with tempfile.TemporaryDirectory() as d:
        dest = Path(d) / "My Paper"
        proc = subprocess.run(
            [str(script), "--yes", "--no-build", "--no-git",
             "--title", title, "--author", "Ada Lovelace",
             "--email", "ada@example.edu", "--affiliation", "Dept, Uni",
             "--keywords", "one, two", str(dest)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(f"  new-paper.sh: exited {proc.returncode}\n{proc.stderr[:500]}")
            return False

        cfg = (dest / "config.typ").read_text()
        version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(),
                            re.M).group(1)
        checks = [
            # The identity actually landed, with the quotes escaped rather than
            # ending the string.
            ("title substituted",
             '#let paper-title = "The \\"Quoted\\" Study: 20% Faster"' in cfg),
            ("author substituted", 'name: "Ada Lovelace"' in cfg),
            # CLAUDE.md's scaffold paragraph names the release this copy came
            # from, not the placeholder the scaffold's own copy carries.
            ("scaffold version written into CLAUDE.md",
             "SCAFFOLD_VERSION" not in (dest / "CLAUDE.md").read_text()
             and ("paper-scaffold)\n" + version) in (dest / "CLAUDE.md").read_text()),
            ("keywords substituted", '#let paper-keywords = ("one", "two")' in cfg),
            # Matched on the author ENTRY, not the bare name: config.typ also
            # names both placeholder authors in a comment explaining how the
            # Word front matter derives its superscripts, and that comment is
            # documentation the new project should keep.
            ("placeholder author entry is gone", 'name: "Grace Hopper"' not in cfg),
            # The abstract is prose and is deliberately left for the author.
            ("abstract left alone", "This document is a working skeleton" in cfg),

            # What must NOT come along. The scaffold's history is the whole
            # reason this script exists instead of `cp -r`.
            ("no .git", not (dest / ".git").exists()),
            ("no scripts/", not (dest / "scripts").exists()),
            ("no built pdf", not (dest / "paper.pdf").exists()),
            # The scaffold's own build stamp describes the scaffold's outputs.
            # Inherited, it would claim the new paper was built from sources it
            # has never seen, and `just check` would report clean on day one.
            ("no .build-stamp", not (dest / ".build-stamp").exists()),
            # The scaffold's CI tests scripts/new-paper.sh and builds the
            # scaffold itself. Inherited into a manuscript it is a workflow that
            # fails on push, forever, over a script the copy does not contain.
            ("no .github/", not (dest / ".github").exists()),

            # What must. figures/, si/ and the stamp travel so the copy compiles
            # and `just check` is clean before the analysis has ever run.
            ("figures/ copied", (dest / "figures" / "example_figure.png").is_file()),
            ("si/ copied", (dest / "si" / "example_table.typ").is_file()),
            ("assets.json copied", (dest / "assets.json").is_file()),
            ("stats.json copied", (dest / "stats.json").is_file()),
            ("analysis/ copied", (dest / "analysis" / "justfile").is_file()),
            ("tools/ copied", (dest / "tools" / "prose_check.py").is_file()),
            # docs/ travels because CLAUDE.md links into it; the migration
            # guide and the pre-3.20 release notes do not, since a new paper
            # is neither migrating nor older than any release.
            ("docs/ copied", (dest / "docs" / "README.md").is_file()),
            ("no docs/migrating.md", not (dest / "docs" / "migrating.md").exists()),
            ("no docs/history-archive.md",
             not (dest / "docs" / "history-archive.md").exists()),
            # A bare `--exclude=__pycache__` only matched at the top level, so
            # the caches under tools/ rode along the moment the toolchain moved
            # one directory down.
            ("no __pycache__ anywhere", not list(dest.rglob("__pycache__"))),

            # tar rather than cp -r, so this stays a symlink. A copy here drifts
            # from CLAUDE.md and the drifted one is what some agent reads.
            ("AGENTS.md is still a symlink", (dest / "AGENTS.md").is_symlink()),

            # The scaffold's MIT notice travels, renamed so it does not read as
            # a licence for the paper.
            ("LICENSE renamed", (dest / "LICENSE.scaffold").is_file()
             and not (dest / "LICENSE").exists()),
        ]
        # The slug comes from the directory name, which here has a space and a
        # capital in it on purpose.
        pyproject = (dest / "pyproject.toml").read_text()
        checks.append(("pyproject name slugified",
                       'name = "my-paper"' in pyproject))

        for name, passed in checks:
            if not passed:
                print(f"  new-paper.sh [{name}]: failed")
                ok = False
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
