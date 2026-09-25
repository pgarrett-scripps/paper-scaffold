"""Parts ported from another scaffold repository: is the port still current?

A dissertation chapter is often a published paper carried over: its prose,
numbers and figures copied from the paper's repository at one commit. When the
paper moves on, nothing tells the chapter. A part records where it came from
in manuscript.toml:

    [parts.koth.upstream]
    repo = "~/Repos/koth-paper"     # absolute, ~, or relative to the project
    commit = "57abc15"              # the commit the chapter was ported from
    figures = "chapters/05_koth/figures"   # optional; default figures/ beside
                                           # the part source

and this tool reads it:

  check   (a `just verify` stage) for each part with an upstream:
          - the upstream HEAD has moved past the recorded commit;
          - a copied figure whose sha256 matches an upstream assets.json entry
            at the recorded commit, where that entry's hash has since changed
            (the copy is stale), or that matches only a newer commit (the
            record is behind the copy);
          - a Typst file under the part's directory that sets the page
            (`set page(`): a figure module written for its own page, such as a
            standalone CeTZ drawing, does not compile inside a chapter. Export
            it to PNG/SVG upstream, or make the module page-agnostic.
          Every finding is a warning; a part whose repo is not on this machine
          is skipped with one note, so the check never fails a build machine
          that lacks the upstream checkout. --strict makes warnings fail.

  diff PART   the upstream stats.json at the recorded commit against HEAD:
          ids added, removed, and values that changed, rendered with their
          `fmt`. This is the list of numbers to re-copy into the chapter.
          `--to REV` compares against another revision.

After re-porting, move `commit` to the new hash.

    uv run paper tool port check [--strict]
    uv run paper port-diff PART [--to REV]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from paths import ROOT

PAGE = re.compile(r"(?m)^\s*#?\s*set\s+page\s*\(")


def repo_path(root: Path, repo: str) -> Path:
    path = Path(os.path.expanduser(repo))
    return path if path.is_absolute() else (root / path).resolve()


def git(repo: Path, *args: str) -> str | None:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def is_repo(repo: Path) -> bool:
    return repo.is_dir() and git(repo, "rev-parse", "--git-dir") is not None


def manifest_at(repo: Path, rev: str, name: str) -> dict:
    """stats.json or assets.json's `values` at a revision ({} when absent)."""
    text = git(repo, "show", f"{rev}:{name}")
    if text is None:
        return {}
    try:
        values = json.loads(text).get("values", {})
    except (ValueError, AttributeError):
        return {}
    return values if isinstance(values, dict) else {}


def render(entry) -> str:
    if not isinstance(entry, dict):
        return json.dumps(entry)
    value, fmt = entry.get("value"), entry.get("fmt")
    try:
        text = format(value, fmt) if fmt and isinstance(value, (int, float)) else str(value)
    except (ValueError, TypeError):
        text = str(value)
    unit = entry.get("unit")
    return f"{text} {unit}" if unit and unit != "%" else f"{text}{unit or ''}"


def stats_diff(old: dict, new: dict) -> tuple[list[str], list[str], list[tuple[str, str, str]]]:
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = []
    for id in sorted(set(old) & set(new)):
        a, b = render(old[id]), render(new[id])
        if a != b:
            changed.append((id, a, b))
    return added, removed, changed


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def hashes(values: dict) -> dict[str, str]:
    """assets.json id -> recorded hash."""
    return {id: rec["hash"] for id, rec in values.items()
            if isinstance(rec, dict) and isinstance(rec.get("hash"), str)}


def figure_dir(root: Path, part) -> Path:
    if part.upstream.figures:
        return root / part.upstream.figures
    return (root / part.source).parent / "figures"


def figures(root: Path, part, repo: Path, head: str) -> list[str]:
    folder = figure_dir(root, part)
    if not folder.is_dir():
        return []
    then = hashes(manifest_at(repo, part.upstream.commit, "assets.json"))
    now = hashes(manifest_at(repo, head, "assets.json"))
    if not then and not now:
        return []
    by_then = {h: id for id, h in then.items()}
    by_now = {h: id for id, h in now.items()}
    out = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        h = sha256(path)
        rel = path.relative_to(root)
        if h in by_then:
            id = by_then[h]
            if id in now and now[id] != h:
                out.append(f"{rel} is {id} as of {part.upstream.commit}; "
                           f"upstream has regenerated it since")
            elif id not in now:
                out.append(f"{rel} is {id} as of {part.upstream.commit}; "
                           f"upstream no longer declares it")
        elif h in by_now:
            out.append(f"{rel} is {by_now[h]} from a commit newer than "
                       f"{part.upstream.commit}: move upstream.commit")
    return out


def page_setters(root: Path, project, part) -> list[str]:
    """Typst files in the part's own directory that set the page."""
    folder = (root / part.source).parent
    if folder.resolve() == root.resolve():
        return []   # a part in the project root shares it with the entrypoints
    entrypoints = {(root / d.entrypoint).resolve() for d in project.documents.values()}
    out = []
    for path in sorted(folder.rglob("*.typ")):
        if path.resolve() in entrypoints:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        m = PAGE.search(text)
        if m:
            line = text.count("\n", 0, m.start()) + 1
            out.append(f"{path.relative_to(root)}:{line} sets the page; a module "
                       f"included in a chapter must not (export the figure, or "
                       f"drop the `set page`)")
    return out


def check(root: Path) -> tuple[list[str], list[str]]:
    """Warnings and notes for every part with an upstream."""
    from document_project import load_project
    project = load_project(root)
    warnings, notes = [], []
    for part in project.parts.values():
        up = part.upstream
        if up is None:
            continue
        repo = repo_path(root, up.repo)
        if not is_repo(repo):
            notes.append(f"{part.id}: upstream {up.repo} is not on this machine; skipped")
            continue
        if git(repo, "cat-file", "-e", f"{up.commit}^{{commit}}") is None:
            warnings.append(f"{part.id}: upstream commit {up.commit} is not in {up.repo}")
            continue
        head = (git(repo, "rev-parse", "--short", "HEAD") or "").strip()
        ahead = (git(repo, "rev-list", "--count", f"{up.commit}..HEAD") or "0").strip()
        if ahead != "0":
            old = manifest_at(repo, up.commit, "stats.json")
            new = manifest_at(repo, "HEAD", "stats.json")
            a, r, c = stats_diff(old, new)
            moved = (f"; stats.json: {len(c)} changed, {len(a)} added, {len(r)} removed"
                     if old or new else "")
            warnings.append(f"{part.id}: upstream {up.repo} is {ahead} commit(s) past "
                            f"{up.commit} (HEAD {head}){moved}. "
                            f"`just port-diff {part.id}` lists them")
        warnings += [f"{part.id}: {w}" for w in figures(root, part, repo, "HEAD")]
    for part in project.parts.values():
        if part.upstream is not None:
            warnings += [f"{part.id}: {w}" for w in page_setters(root, project, part)]
    return warnings, notes


def diff(root: Path, name: str, to: str) -> int:
    from document_project import load_project
    project = load_project(root)
    part = project.parts.get(name)
    if part is None:
        print(f"port-diff: no part {name!r} (parts: {', '.join(project.parts)})",
              file=sys.stderr)
        return 2
    if part.upstream is None:
        print(f"port-diff: part {name} has no upstream in manuscript.toml", file=sys.stderr)
        return 2
    repo = repo_path(root, part.upstream.repo)
    if not is_repo(repo):
        print(f"port-diff: {part.upstream.repo} is not a git repository here", file=sys.stderr)
        return 2
    for rev in (part.upstream.commit, to):
        if git(repo, "cat-file", "-e", f"{rev}^{{commit}}") is None:
            print(f"port-diff: {rev} is not a commit in {part.upstream.repo}", file=sys.stderr)
            return 2
    old = manifest_at(repo, part.upstream.commit, "stats.json")
    new = manifest_at(repo, to, "stats.json")
    added, removed, changed = stats_diff(old, new)
    head = (git(repo, "rev-parse", "--short", to) or to).strip()
    print(f"{name}: {part.upstream.repo} stats.json, {part.upstream.commit} -> {head}")
    for id, a, b in changed:
        print(f"  changed  {id}: {a} -> {b}")
    for id in added:
        print(f"  added    {id}: {render(new[id])}")
    for id in removed:
        print(f"  removed  {id}: was {render(old[id])}")
    print(f"{len(changed)} changed, {len(added)} added, {len(removed)} removed")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="warn where a ported part has fallen behind")
    c.add_argument("--strict", action="store_true", help="a warning fails")
    d = sub.add_parser("diff", help="upstream stats.json, recorded commit vs HEAD")
    d.add_argument("part")
    d.add_argument("--to", default="HEAD", help="compare against this revision")
    args = parser.parse_args(argv)
    if not (ROOT / "manuscript.toml").is_file():
        print("port: no manuscript.toml; nothing is ported")
        return 0 if args.cmd == "check" else 2
    if args.cmd == "diff":
        return diff(ROOT, args.part, args.to)
    try:
        warnings, notes = check(ROOT)
    except ValueError as exc:
        print(f"port: manuscript.toml: {exc}", file=sys.stderr)
        return 1
    for n in notes:
        print(f"note: {n}")
    for w in warnings:
        print(f"warn: {w}")
    if not warnings:
        from document_project import load_project
        ported = [p for p in load_project(ROOT).parts.values() if p.upstream]
        if not ported:
            print("port: no part records an upstream")
        elif len(notes) == len(ported):
            print("port: no upstream repository on this machine; nothing checked")
        else:
            print("port: every ported part matches its recorded upstream commit")
        return 0
    print(f"port: {len(warnings)} warning(s)" + ("" if args.strict else
                                                 " (warnings; --strict to fail)"))
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
