"""tools/upgrade_plan.py classifies files and orders Upgrade: lines correctly.

A throwaway scaffold repository gets three tagged releases and a derived
project copied from the first, then customized. Everything the plan claims is
checked against what was done to each file, and --apply-pristine is checked to
touch exactly the pristine and new files and to refuse on a dirty tree.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

import upgrade_plan as up  # noqa: E402

IDENT = ["-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false"]

NEW_PAPER = """#!/usr/bin/env bash
tar -C "$SCAFFOLD" -cf - \\
    --exclude='./.git' \\
    --exclude='./scripts' \\
    --exclude='./examples' \\
    --exclude='*__pycache__*' \\
    . | tar -C "$DEST" -xf -
"""

HISTORY_V1 = "# History\n\n---\n\n## 1.0.0\n\nFirst.\n"
HISTORY_V11 = """# History

---

## 1.1.0

Changed a and b, added c; "Upgrade:" lines are quoted here in passing.
Upgrade: copy `tools/a.py`.

Also this. Upgrade: copy `tools/b.py` and `tools/c.py`, then merge the
justfile recipe.

## 1.0.0

First.
"""
HISTORY_V12 = HISTORY_V11.replace("---\n\n", """---

## 1.2.0

Upgrade: copy `tools/` wholesale.

Unrelated. Upgrade: nothing to do.

""", 1)


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *IDENT, *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout


def write(root: Path, files: dict[str, str | None]) -> None:
    for rel, text in files.items():
        p = root / rel
        if text is None:
            p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def release(repo: Path, tag: str, files: dict[str, str | None]) -> None:
    write(repo, files)
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", tag)
    sh(repo, "tag", "-a", tag, "-m", tag)


def fixture(d: Path) -> tuple[Path, Path]:
    scaffold, project = d / "paper-scaffold", d / "proj"
    scaffold.mkdir()
    sh(scaffold, "init", "-q")
    v1 = {
        "scripts/new-paper.sh": NEW_PAPER,
        "examples/demo.typ": "demo\n",
        "HISTORY.md": HISTORY_V1,
        "pyproject.toml": '[project]\nname = "paper-scaffold"\nversion = "1.0.0"\n',
        "justfile": "version:\n  echo 1\n",
        "paper.typ": "placeholder\n",
        "tools/a.py": "a = 1\n",
        "tools/b.py": "b = 1\n" + "pad\n" * 5 + "keep = 1\n",
        "tools/same.py": "same = 1\n",
        "tools/gone.py": "gone = 1\n",
    }
    release(scaffold, "v1.0.0", v1)
    release(scaffold, "v1.1.0", {
        "HISTORY.md": HISTORY_V11,
        "pyproject.toml": v1["pyproject.toml"].replace("1.0.0", "1.1.0"),
        "tools/a.py": "a = 2\n",
        "tools/b.py": "b = 2\n" + "pad\n" * 5 + "keep = 1\n",
        "tools/c.py": "c = 1\n",
        "tools/gone.py": None,
    })
    release(scaffold, "v1.2.0", {
        "HISTORY.md": HISTORY_V12,
        "pyproject.toml": v1["pyproject.toml"].replace("1.0.0", "1.2.0"),
    })

    # The project: a v1.0.0 copy as new-paper.sh makes it, then written in.
    project.mkdir()
    for rel, text in v1.items():
        if not rel.startswith(("scripts/", "examples/")):
            write(project, {rel: text})
    write(project, {
        "pyproject.toml": '[project]\nname = "proj"\nversion = "1.0.0"\n',
        "paper.typ": "real prose\n",           # project-owned: never reported
        "tools/b.py": "b = 1\n" + "pad\n" * 5 + "keep = 99\n",  # disjoint edit
        "tools/same.py": "same = 'mine'\n",    # customized but upstream unchanged
        "tools/mine.py": "mine = 1\n",         # project-only
    })
    sh(project, "init", "-q")
    sh(project, "add", "-A")
    sh(project, "commit", "-q", "-m", "paper")
    return scaffold, project


def run_cases() -> bool:
    ok = True

    def check(name: str, cond: bool, detail: object = "") -> None:
        nonlocal ok
        if not cond:
            print(f"  upgrade-plan [{name}]: failed {detail}")
            ok = False

    with tempfile.TemporaryDirectory() as tmp:
        scaffold, project = fixture(Path(tmp))

        plan = up.build_plan(project, scaffold, None)
        cls = {f["path"]: f["cls"] for f in plan["files"]}
        check("default target is the latest tag", plan["target"] == "v1.2.0",
              plan["target"])
        check("current from pyproject", plan["current"] == "1.0.0")
        want = {"tools/a.py": "pristine", "tools/b.py": "customized",
                "tools/c.py": "new-upstream", "tools/gone.py": "removed-upstream",
                "tools/same.py": "unchanged", "tools/mine.py": "project-only",
                "pyproject.toml": "unchanged", "justfile": "unchanged",
                "HISTORY.md": "pristine"}
        for path, c in want.items():
            check(f"{path} is {c}", cls.get(path) == c, cls.get(path))
        for path in ("paper.typ", "scripts/new-paper.sh", "examples/demo.typ"):
            check(f"{path} not scaffold-owned", path not in cls)
        b = next(f for f in plan["files"] if f["path"] == "tools/b.py")
        check("three-way summary", b["local"] == {"added": 1, "removed": 1,
              "hunks": 1} and b["upstream"]["hunks"] == 1, b)
        check("disjoint edits merge cleanly", b["conflicts"] == 0, b)
        same = next(f for f in plan["files"] if f["path"] == "tools/same.py")
        check("unchanged notes a local edit", same["note"] == "customized locally")

        lines = plan["upgrade_lines"]
        check("Upgrade: lines in release order",
              [u["version"] for u in lines] == ["1.1.0", "1.1.0", "1.2.0", "1.2.0"],
              [u["version"] for u in lines])
        check("a quoted \"Upgrade:\" in prose is not the instruction",
              lines[0]["text"] == "copy `tools/a.py`.", lines[0])
        check("pure copy superseded by a later wholesale copy",
              lines[0]["status"] == "superseded"
              and lines[0]["superseded_by"] == "1.2.0", lines[0])
        check("a line with a merge step is never folded",
              lines[1]["status"] == "do", lines[1])
        check("nothing-to-do recognized", lines[3]["status"] == "nothing")
        check("customized files attached to the line naming them",
              "tools/b.py" in lines[2]["needs_merge"], lines[2])

        mid = up.build_plan(project, scaffold, "1.1.0")
        check("explicit target without the v", mid["target"] == "v1.1.0")
        check("range stops at the target",
              {u["version"] for u in mid["upgrade_lines"]} == {"1.1.0"})

        # Errors a user must see, not a traceback.
        for name, fn in [
            ("unknown target", lambda: up.build_plan(project, scaffold, "v9.9.9")),
            ("older target", lambda: up.build_plan(project, scaffold, "v1.0.0",
                                                    "1.1.0")),
            ("untagged current", lambda: up.build_plan(project, scaffold, None,
                                                        "0.5.0")),
            ("scaffold as project", lambda: up.build_plan(scaffold, scaffold, None)),
        ]:
            try:
                fn()
                check(name + " raises", False)
            except up.PlanError:
                pass
        old = os.environ.get("PAPER_SCAFFOLD")
        os.environ["PAPER_SCAFFOLD"] = str(Path(tmp) / "nowhere")
        try:
            up.find_scaffold(None, project)
            check("missing $PAPER_SCAFFOLD raises", False)
        except up.PlanError as e:
            check("error names the fix", "--scaffold" in str(e), e)
        finally:
            if old is None:
                os.environ.pop("PAPER_SCAFFOLD")
            else:
                os.environ["PAPER_SCAFFOLD"] = old
        check("sibling discovery", up.find_scaffold(None, project) == scaffold)

        # --json is parseable and carries no internals.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = up.main(["--project", str(project), "--scaffold",
                          str(scaffold), "--json"])
        data = json.loads(buf.getvalue())
        check("json output", rc == 0 and data["counts"]["pristine"] == 2
              and not any(k.startswith("_") for k in data), data.get("counts"))

        # --apply-pristine refuses while a path it would write is dirty: here
        # a committed customization reverted in the work tree, which reads as
        # pristine but would silently discard the commit's intent on apply.
        (project / "tools/a.py").write_text("a = 'wip'\n")
        sh(project, "commit", "-q", "-am", "customize a")
        (project / "tools/a.py").write_text("a = 1\n")
        with contextlib.redirect_stderr(io.StringIO()) as err:
            rc = up.main(["--project", str(project), "--scaffold",
                          str(scaffold), "--apply-pristine"])
        check("dirty tree refused", rc == 2 and "tools/a.py" in err.getvalue(),
              err.getvalue())
        check("nothing written on refusal",
              (project / "tools/a.py").read_text() == "a = 1\n"
              and not (project / "tools/c.py").exists())
        sh(project, "commit", "-q", "-am", "revert a")

        # ...and on a clean tree copies exactly the pristine and new files.
        with contextlib.redirect_stdout(io.StringIO()):
            rc = up.main(["--project", str(project), "--scaffold",
                          str(scaffold), "--apply-pristine"])
        check("apply succeeded", rc == 0)
        check("pristine replaced", (project / "tools/a.py").read_text() == "a = 2\n")
        check("new file added", (project / "tools/c.py").read_text() == "c = 1\n")
        check("customized untouched",
              (project / "tools/b.py").read_text().endswith("keep = 99\n"))
        check("removed-upstream left for a hand `git rm`",
              (project / "tools/gone.py").exists())
        check("project-only untouched", (project / "tools/mine.py").exists())
        check("project identity kept",
              'name = "proj"' in (project / "pyproject.toml").read_text())
        after = up.build_plan(project, scaffold, None)
        c2 = {f["path"]: f["cls"] for f in after["files"]}
        check("re-plan shows them at target",
              c2["tools/a.py"] == "at-target" and c2["tools/c.py"] == "at-target",
              c2)

    if ok:
        print("  upgrade-plan: classification, Upgrade: lines, apply guard ok")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run_cases() else 1)
