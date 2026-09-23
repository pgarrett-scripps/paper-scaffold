"""`paper migrate`: move a 3.x paper (a full toolchain copy) onto the package.

Every file the scaffold owned at the paper's release is classed against that
release's git tag with tools/upgrade_plan.py: pristine (identical, after the
identity fields new-paper.sh fills in) or customized. The policy, per
docs/package.md "Migration from 3.26.x":

- toolchain files (tools/, tests/, docs/, DOCUMENTATION.md, LICENSE.scaffold):
  pristine are removed, customized are refused;
- files paper sync generates: pristine are replaced, customized are refused;
- journals/ and word/: pristine are removed, customized stay as overrides;
- word/paper-reference.docx (no longer read from 3.27.0) by what Word
  renders from it: stock, or edited only as the new stock is (black
  headings), is removed; other edits [word.style] expresses are removed and
  written into project.toml as that block; edits it cannot express keep the
  file, declared as `[word] reference` in project.toml;
- HISTORY.md (package-owned from 4.0.0): pristine is removed, customized is
  refused (move the paper's own notes to notes/PROJECT-HISTORY.md);
- pyproject.toml: rewritten with the pin, extra dependencies kept, any other
  table or key refused;
- a file in tools/ or tests/ the scaffold never had: refused;
- a file in docs/ the scaffold never had (the paper's own notes): refused,
  since docs/ is the package's and would be removed (move it to notes/);
- Python in the paper, or in the repository around it, that reaches the
  paper's tools/ (sys.path, imports, globs): refused with file:line
  (use paper_scaffold.tools_dir()).

Everything else is the paper's and is not touched. A refusal changes nothing.
"""
from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import sync as sync_mod
from . import use_tools, version

REMOVE_OR_REFUSE = ("tools/", "tests/", "docs/")
REMOVE_OR_REFUSE_FILES = ("DOCUMENTATION.md", "LICENSE.scaffold")
OVERRIDABLE = ("journals/", "word/")
LEGACY_WORD = "word/paper-reference.docx"  # 3.27.0 generates it instead
GENERATED = (sync_mod.ALWAYS + sync_mod.ANALYSIS_HELPERS + sync_mod.AUDIO
             + sync_mod.SLIDES)
PYPROJECT_KEYS = {
    "project": {"name", "version", "description", "requires-python",
                "dependencies"},
    "dependency-groups": None,  # any group, each a list of strings
    "tool": {"uv"},
}
DEFAULT_PIN = "paper-scaffold @ git+https://github.com/pgarrett-scripps/paper-scaffold@v{v}"


class MigrateError(Exception):
    pass


@dataclass
class Plan:
    project: Path
    release: str
    pin: str
    remove: list[str] = field(default_factory=list)
    replace: list[str] = field(default_factory=list)
    overrides: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    pyproject: str = ""
    extra_deps: list[str] = field(default_factory=list)
    # project.toml's new text when the old Word template moves into it
    # ([word.style] or [word] reference), and one line saying why.
    project_toml: str | None = None
    word_note: str = ""


def _toml():
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib  # type: ignore[no-redef]
    return tomllib


def _dep_name(spec: str) -> str:
    import re
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec)
    return (m.group(1) if m else spec).lower().replace("_", "-")


def pyproject_for(name: str, pin: str, extra: list[str],
                  groups: dict[str, list[str]]) -> str:
    deps = "".join(f'  "{d}",\n' for d in [pin, *extra])
    out = [
        "[project]",
        f'name = "{name}"',
        '# Not the toolchain release: that is the paper-scaffold pin below, and',
        '# `paper version` / .paper/scaffold.lock.json say which one is installed.',
        'version = "0.0.0"',
        'requires-python = ">=3.10"',
        "# The toolchain (docs/package.md). Move the pin with `uv add`, then run",
        "# `uv run paper sync`.",
        "dependencies = [",
        deps.rstrip("\n"),
        "]",
        "",
        "[dependency-groups]",
    ]
    for g, items in groups.items():
        out.append(f"{g} = [" + ", ".join(f'"{i}"' for i in items) + "]")
    out += ["", "[tool.uv]", "package = false", ""]
    return "\n".join(out)


def rewrite_pyproject(project: Path, scaffold_py: bytes | None, pin: str,
                      refused: list[str]) -> tuple[str, list[str]]:
    tomllib = _toml()
    data = tomllib.loads((project / "pyproject.toml").read_text())
    base = tomllib.loads(scaffold_py.decode()) if scaffold_py else {}
    for table, value in data.items():
        allowed = PYPROJECT_KEYS.get(table, "missing")
        if allowed == "missing":
            refused.append(f"pyproject.toml: [{table}] is not a table the "
                           "package-era pyproject keeps")
        elif allowed is not None and isinstance(value, dict):
            for key in value:
                if key not in allowed:
                    refused.append(f"pyproject.toml: {table}.{key} would be lost")
    uv = data.get("tool", {}).get("uv", {})
    for key in uv:
        if key != "package":
            refused.append(f"pyproject.toml: tool.uv.{key} would be lost")
    stock = {_dep_name(d) for d in base.get("project", {}).get("dependencies", [])}
    extra = [d for d in data.get("project", {}).get("dependencies", [])
             if _dep_name(d) not in stock and _dep_name(d) != "paper-scaffold"]
    groups = dict(data.get("dependency-groups") or
                  {"audio": ["piper-tts>=1.6", "imageio-ffmpeg", "pillow", "matplotlib"]})
    name = data.get("project", {}).get("name") or project.name
    return pyproject_for(name, pin, extra, groups), extra


def classify(project: Path, scaffold: Path | None, base: str | None,
             pin: str | None) -> Plan:
    use_tools()
    import upgrade_plan as up
    project = project.resolve()
    if sync_mod.is_scaffold_checkout(project):
        raise MigrateError("this is the scaffold checkout, not a paper")
    if (project / sync_mod.LOCK).is_file():
        raise MigrateError(f"{project} already has {sync_mod.LOCK}: it is on "
                           "the package; upgrade with `uv add` + `paper sync`")
    try:
        clone = up.find_scaffold(str(scaffold) if scaffold else None, project)
        release = (base or up.project_version(project)).lstrip("v")
        ref = "v" + release
        if ref not in up.release_tags(clone):
            raise MigrateError(f"the scaffold clone {clone} has no tag {ref}; "
                               "fetch tags or pass --from")
        blobs = up.Blobs(clone)
        excludes = up.excludes_from_new_paper(
            (blobs.show(ref, "scripts/new-paper.sh") or b"").decode())
        files = up.owned(up.tree(clone, ref), excludes)
        listing = up.project_listing(project)
    except up.PlanError as e:
        raise MigrateError(str(e)) from None
    plan = Plan(project, release, pin or DEFAULT_PIN.format(v=version()))
    for upstream, entry in sorted(files.items()):
        rel = up.RENAMED.get(upstream, upstream)
        listing.discard(rel)
        local = up.read_project(project, rel)
        if local is None:
            continue
        pristine = up.normalize(upstream, local) == up.normalize(
            upstream, blobs.get(entry.sha))
        if rel == "pyproject.toml":
            continue
        if rel.startswith(REMOVE_OR_REFUSE) or rel in REMOVE_OR_REFUSE_FILES:
            (plan.remove if pristine else plan.refused).append(
                rel if pristine else f"{rel}: customized toolchain file "
                "(move the change to project.toml / project.just / hooks/, "
                "restore the stock file, rerun)")
        elif rel in GENERATED:
            (plan.replace if pristine else plan.refused).append(
                rel if pristine else f"{rel}: customized, and paper sync now "
                "writes it (move the change to project.just / project.toml / hooks/)")
        elif rel == LEGACY_WORD and not pristine:
            legacy_word(plan, local, blobs.get(entry.sha))
        elif rel.startswith(OVERRIDABLE):
            (plan.remove if pristine else plan.overrides).append(rel)
        elif rel == "HISTORY.md":
            (plan.remove if pristine else plan.refused).append(
                rel if pristine else f"{rel}: customized; from 4.0.0 it is the "
                "package's release history. Move this paper's own notes to "
                "notes/PROJECT-HISTORY.md, restore the stock file, rerun")
        else:
            plan.kept.append(rel)
    own_docs: list[str] = []
    for rel in sorted(listing):
        if rel.startswith(("tools/", "tests/")):
            plan.refused.append(f"{rel}: a file the scaffold never had in its "
                                "toolchain (move it to hooks/)")
        elif rel.startswith("docs/"):
            own_docs.append(rel)
    if own_docs:
        # docs/ is the package's (docs/package.md "What a paper holds"): apply
        # removes the directory and `paper sync --check` fails on one.
        plan.refused.append(
            f"docs/: {len(own_docs)} file(s) of the paper's own ("
            + ", ".join(r.removeprefix("docs/") for r in own_docs)
            + "); from 4.0.0 docs/ is the package's. `git mv` them to notes/ "
            "and update links to them (rg -n 'docs/'), then rerun")
    plan.refused += tools_references(project)
    # A generated file the release did not ship but this one writes, already
    # present and untracked by the scaffold: never overwrite blindly.
    wanted = sync_mod.generated(project)
    for target in wanted:
        if (target not in plan.replace and (project / target).is_file()
                and not any(target == r.split(":")[0] for r in plan.refused)):
            current = (project / target).read_bytes()
            if current != wanted[target][1].encode():
                plan.refused.append(f"{target}: exists, is not the stock file of "
                                    f"{release}, and paper sync writes it")
    scaffold_py = blobs.show(ref, "pyproject.toml")
    plan.pyproject, plan.extra_deps = rewrite_pyproject(
        project, scaffold_py, plan.pin, plan.refused)
    touched = plan.remove + plan.replace + ["pyproject.toml", ".gitignore"]
    if plan.project_toml is not None and (project / "project.toml").exists():
        touched.append("project.toml")
    if up._in_git(project):
        dirty = up.dirty_paths(project, [p for p in touched if (project / p).exists()])
        if dirty:
            plan.refused.append("uncommitted changes in " + ", ".join(sorted(dirty))
                                + ": commit or discard them first")
    return plan


# A path into the paper's tools/: `ROOT / "tools"`, "tools/x.py",
# "../tools", os.path.join(root, "tools"), or `import tools` / `from tools.x`.
TOOLS_PATH = re.compile(r"""/\s*["']tools["']"""
                        r"""|["'](?:[^"'\s]*/)?tools(?:/[^"'\s]*)?["']""")
TOOLS_IMPORT = re.compile(r"^\s*(?:from\s+tools[.\s]|import\s+tools\b)")
SCAN_SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__",
             ".build-state", ".paper", "site-packages"}
IGNORE_MARK = "paper-migrate: ignore"
TOOLS_FIX = ("tools/ leaves the paper: use `paper_scaffold.tools_dir()` "
             "(docs/package.md, \"Code that used tools/\")")


def _py_files(base: Path, git_root: Path | None) -> list[Path]:
    if git_root is not None:
        out = subprocess.run(["git", "-C", str(base), "ls-files", "-z", "--cached",
                              "--others", "--exclude-standard", "--", "*.py"],
                             capture_output=True, check=False).stdout
        files = [base / p for p in out.decode().split("\0") if p]
    else:
        files = list(base.rglob("*.py"))
    return sorted(f for f in files if f.is_file()
                  and not SCAN_SKIP.intersection(f.relative_to(base).parts))


def tools_references(project: Path) -> list[str]:
    """Each line of the paper's Python (and, for a paper inside a larger
    repository, the rest of that repository) that puts the paper's tools/ on
    sys.path or reads a file from it. After migration there is no tools/.

    Inside the paper every .py outside the toolchain copies is scanned (the
    files paper sync writes are replaced, so they are not, and neither is a
    file with a nearer tools/ of its own, such as a vendored snapshot). Outside it, a
    reference counts only when the line also names the paper directory (as
    `PAPER / "tools"` or "paper/tools" do), so the repository's own tools/
    is left alone. A line carrying `paper-migrate: ignore` is skipped.
    """
    import os
    project = project.resolve()
    top = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=False)
    git_root = Path(top.stdout.strip()).resolve() if top.returncode == 0 else None
    generated = set(GENERATED) | set(sync_mod.ANALYSIS_HELPERS)
    found = []

    def scan(path: Path, inside: bool) -> None:
        rel = Path(os.path.relpath(path, project)).as_posix()
        if inside and (rel in generated or rel.startswith(
                ("tools/", "tests/", sync_mod.TOOLCHAIN_DIR + "/"))):
            return
        # A copy of the toolchain kept in the paper (a snapshot with its own
        # tools/ nearer the file) refers to that tools/, not the paper's.
        if inside and any((d / "tools").is_dir() for d in path.parents
                          if project in d.parents):
            return
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return
        for n, line in enumerate(lines, 1):
            code = line.strip()
            if not code or code.startswith("#") or IGNORE_MARK in line:
                continue
            if not (TOOLS_IMPORT.match(line) or TOOLS_PATH.search(line)):
                continue
            if not inside and project.name.lower() not in line.lower():
                continue
            found.append(f"{rel}:{n}: uses the paper's tools/ "
                         f"(`{code[:70]}`); {TOOLS_FIX}")

    for path in _py_files(project, git_root):
        scan(path, True)
    if git_root is not None and git_root != project:
        for path in _py_files(git_root, git_root):
            if project not in path.resolve().parents:
                scan(path, False)
    return found


def word_table(text: str, style: dict | None) -> str:
    """project.toml's `text` with the old template's replacement added:
    `style` as a [word.style] block, or None for [word] reference."""
    import re
    import paper_word_reference as pwr
    tomllib = _toml()
    word = tomllib.loads(text).get("word", {}) if text.strip() else {}
    if "style" in word or "reference" in word:
        raise MigrateError("project.toml already declares [word.style] or "
                           f"[word] reference, and {LEGACY_WORD} is still here: "
                           "settle it by hand (.paper/docs/word-export.md)")
    if not text.strip():
        text = "schema_version = 1\n"  # a new project.toml (docs/hooks.md)
    elif not text.endswith("\n"):
        text += "\n"
    if style is not None:
        out = (text + f"\n# From {LEGACY_WORD} (paper migrate).\n"
               + pwr.toml_block(style) + "\n")
    else:
        line = f'reference = "{LEGACY_WORD}"  # edits [word.style] cannot express\n'
        header = re.search(r"^\[word\][ \t]*(#.*)?$\n?", text, re.MULTILINE)
        if header:
            out = text[:header.end()] + line + text[header.end():]
        else:
            out = text + "\n[word]\n" + line
    tomllib.loads(out)  # a broken edit is a bug here, never a broken paper
    return out


def legacy_word(plan: Plan, local: bytes, release_copy: bytes | None) -> None:
    """Sort the paper's customized word/paper-reference.docx (3.27.0 rules)."""
    import paper_word_reference as pwr
    import upgrade_plan as up
    action, style, left, detail = up.legacy_template_decision(local, release_copy)
    if action == "unknown":
        plan.refused.append(f"{LEGACY_WORD}: cannot be compared ({detail}); "
                            "settle it by hand (.paper/docs/word-export.md)")
        return
    path = plan.project / "project.toml"
    text = path.read_text() if path.is_file() else ""
    try:
        if action == "delete":
            plan.remove.append(LEGACY_WORD)
            plan.word_note = f"{LEGACY_WORD}: {detail}, removed"
        elif action == "style":
            plan.project_toml = word_table(text, style)
            plan.remove.append(LEGACY_WORD)
            plan.word_note = (f"{LEGACY_WORD}: removed; project.toml gets "
                              + pwr.toml_block(style).replace("\n", "; "))
        else:
            plan.project_toml = word_table(text, None)
            plan.overrides.append(LEGACY_WORD)
            plan.word_note = (f"{LEGACY_WORD}: kept, declared as [word] reference "
                              f"({len(left)} edit(s) no [word.style] setting "
                              "expresses; `uv run paper tool paper_word_reference "
                              f"--translate {LEGACY_WORD}` lists them)")
    except MigrateError as e:
        plan.refused.append(str(e))


def report(plan: Plan) -> str:
    lines = [f"paper migrate: {plan.project}",
             f"  from {plan.release} (full toolchain copy) to the package, pin:",
             f"    {plan.pin}"]
    def block(title, items, limit=8):
        if not items:
            return
        lines.append(f"  {title} ({len(items)})")
        for i in items[:limit]:
            lines.append(f"    {i}")
        if len(items) > limit:
            lines.append(f"    ... and {len(items) - limit} more")
    block("REFUSED", plan.refused, 100)
    block("remove (pristine toolchain copies)", plan.remove)
    block("replace via paper sync (pristine)", plan.replace, 20)
    block("keep as a local override", plan.overrides, 20)
    block("keep (the paper's own)", [k for k in plan.kept
                                     if not fnmatch.fnmatch(k, ".claude/*")], 20)
    if plan.extra_deps:
        block("pyproject: extra dependencies kept", plan.extra_deps, 20)
    if plan.word_note:
        lines.append(f"  Word template (3.27.0)\n    {plan.word_note}")
    return "\n".join(lines)


def apply(plan: Plan, install: bool = True) -> None:
    project = plan.project
    for rel in plan.remove + plan.replace:
        path = project / rel
        if path.is_symlink() or path.is_file():
            path.unlink()
    # Only ignored leftovers (caches) can remain: every tracked or unignored
    # file under these was classified above.
    for d in sync_mod.PACKAGE_ONLY_DIRS:
        if (project / d).is_dir():
            shutil.rmtree(project / d)
    (project / "pyproject.toml").write_text(plan.pyproject)
    if plan.project_toml is not None:
        (project / "project.toml").write_text(plan.project_toml)
    gitignore = project / ".gitignore"
    text = gitignore.read_text() if gitignore.is_file() else ""
    if ".paper/docs/" not in text.split("\n"):
        text += ("" if text.endswith("\n") or not text else "\n") + (
            "\n# The package's docs, mirrored by `paper sync` for reading "
            "(docs/package.md).\n.paper/docs/\n")
        gitignore.write_text(text)
    if install:
        for cmd in (["uv", "lock"], ["uv", "sync"],
                    ["uv", "run", "--quiet", "paper", "sync", "--force"]):
            done = subprocess.run(cmd, cwd=project)
            if done.returncode:
                raise MigrateError(f"`{' '.join(cmd)}` failed in {project} "
                                   f"(exit {done.returncode}); the files are "
                                   "already moved, fix and rerun that command")
    else:
        sync_mod.sync(project, force=True)


def main(project: Path, scaffold: Path | None, base: str | None, pin: str | None,
         dry_run: bool, install: bool) -> int:
    try:
        plan = classify(project, scaffold, base, pin)
    except MigrateError as e:
        print(f"paper migrate: {e}", file=sys.stderr)
        return 2
    print(report(plan))
    if plan.refused:
        print("\nnothing changed: fix each REFUSED item and rerun", file=sys.stderr)
        return 1
    if dry_run:
        print("\n--dry-run: nothing changed")
        return 0
    try:
        apply(plan, install=install)
    except (MigrateError, sync_mod.SyncError) as e:
        print(f"paper migrate: {e}", file=sys.stderr)
        return 1
    print("\nmigrated. Next: just paper && just verify, then commit "
          "(git add -A).")
    return 0
