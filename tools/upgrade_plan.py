#!/usr/bin/env python3
"""Plan a scaffold upgrade for a derived manuscript, file by file.

WHY THIS EXISTS. There is deliberately no automatic upgrade (HISTORY.md,
"Upgrading a project"): a manuscript diverges from the scaffold the moment real
writing starts, and a merge tool cannot tell a project's customization from the
placeholder it replaced. That rule stands. What it did not require was doing the
BOOKKEEPING by hand: ten derived papers walked 3.6 -> 3.20 one release at a
time, reading every "Upgrade:" line, diffing every tool against upstream, and
copying files that the project had never touched. Most of those files are
byte-identical to the release the project came from, and replacing them is not
a merge at all.

So this tool answers two questions and changes nothing unless asked:

  1. What do the "Upgrade:" lines in HISTORY.md and docs/history-archive.md
     say, for every release between the project's version and the target, in
     order?
  2. For each scaffold-owned file, is it pristine (identical to upstream at the
     project's CURRENT version, so replacing it with the target loses nothing),
     customized (needs a hand merge; a three-way summary says how much each
     side changed), new upstream, removed upstream, project-only, or unchanged?

`--apply-pristine` copies ONLY the pristine and new-upstream files, never a
customized one, and refuses when git reports any of those paths dirty.

Which files the scaffold owns is derived, not listed: the files tracked at a
release, minus what scripts/new-paper.sh at that release leaves out of a copy,
minus what CLAUDE.md says the project owns (the manuscript, its declarations,
analysis/ apart from the shared helpers, the generated figures/ and si/).

Old versions are read with `git show`; there is no network access.

Usage:
    uv run python tools/upgrade_plan.py [TARGET] [--scaffold PATH]
        [--project PATH] [--json] [--apply-pristine] [--all]
"""
from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What the project owns, per CLAUDE.md ("This project owns the manuscript").
# Everything else in a new-paper.sh copy is the scaffold's. The analysis/
# helpers imported by every generator are the exception inside analysis/: the
# Upgrade lines tell projects to copy them (e.g. analysis/scripts/_stats.py).
PROJECT_OWNED = (
    "paper.typ", "config.typ", "si-body.typ", "stats.json", "assets.json",
    "references.bib", "journal.toml", "word-limits.toml", "word-watchlist.toml",
    "prose-check.toml", "*.csl", "figures/*", "si/*", "slides/config.typ",
    "slides/talk.typ", "analysis/*",
    # The extension hooks (docs/hooks.md): the paper's config, recipes and
    # scripts, read by the scaffold and never shipped by it.
    "project.toml", "project.just", "hooks/*",
    # Regenerated from pyproject.toml by `uv lock`; carries the project's name.
    "uv.lock",
    # Replaced by new-paper.sh with a symlink into the scaffold checkout.
    ".agents/skills",
)
SCAFFOLD_HELPERS_IN_ANALYSIS = ("analysis/scripts/_*.py",)

# Copied under another name by new-paper.sh.
RENAMED = {"LICENSE": "LICENSE.scaffold"}

# Directories whose every file is the scaffold's; a project file in one of
# these that upstream never had is reported as project-only.
OWNED_DIRS = ("tools/", "tests/", "journals/", "word/", "audio/")

# Fallback when a release predates scripts/new-paper.sh.
DEFAULT_EXCLUDES = ("./.git", "./.github", "./scripts", "./plugins",
                    "./.claude-plugin", "./examples", "./REVIEW.md",
                    "./MIGRATING.md", "./docs/migrating.md",
                    "./docs/history-archive.md", "*__pycache__*", "*.pyc")

VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
CLASSES = ("customized", "pristine", "new-upstream", "removed-upstream",
           "at-target", "project-only", "unchanged")


class PlanError(Exception):
    """A condition the user must fix; printed without a traceback."""


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------

def git(repo: Path, *args: str, check: bool = True) -> bytes:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                       check=False)
    if check and r.returncode != 0:
        raise PlanError(f"git {' '.join(args)} in {repo}: "
                        f"{r.stderr.decode(errors='replace').strip()}")
    return r.stdout


@dataclass
class Entry:
    mode: str
    sha: str


def tree(scaffold: Path, ref: str) -> dict[str, Entry]:
    out = git(scaffold, "ls-tree", "-r", "-z", "--full-tree", ref)
    files: dict[str, Entry] = {}
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, kind, sha = meta.decode().split()
        if kind == "blob":
            files[path.decode()] = Entry(mode, sha)
    return files


class Blobs:
    """Scaffold blobs by id, each read once."""

    def __init__(self, scaffold: Path):
        self.scaffold = scaffold
        self.cache: dict[str, bytes] = {}

    def get(self, sha: str) -> bytes:
        if sha not in self.cache:
            self.cache[sha] = git(self.scaffold, "cat-file", "blob", sha)
        return self.cache[sha]

    def show(self, ref: str, path: str) -> bytes | None:
        r = subprocess.run(["git", "-C", str(self.scaffold), "show",
                            f"{ref}:{path}"], capture_output=True, check=False)
        return r.stdout if r.returncode == 0 else None


# ---------------------------------------------------------------------------
# versions and locations
# ---------------------------------------------------------------------------

def vkey(v: str) -> tuple[int, int, int]:
    m = VERSION_RE.match(v)
    if not m:
        raise PlanError(f"not a version: {v!r}")
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def project_version(project: Path) -> str:
    py = project / "pyproject.toml"
    if not py.is_file():
        raise PlanError(f"{project} has no pyproject.toml; is it a manuscript?")
    m = re.search(r'^version = "([^"]+)"', py.read_text(), re.MULTILINE)
    if not m:
        raise PlanError(f"no `version = ...` line in {py}")
    return m.group(1)


def release_tags(scaffold: Path) -> list[str]:
    tags = git(scaffold, "tag", "--list", "v*").decode().split()
    return sorted((t for t in tags if VERSION_RE.match(t)), key=vkey)


def looks_like_scaffold(p: Path) -> bool:
    return (p / "scripts" / "new-paper.sh").is_file() and (
        (p / ".git").exists())


def find_scaffold(explicit: str | None, project: Path) -> Path:
    """--scaffold, then $PAPER_SCAFFOLD, then where .agents/skills points (a
    derived paper's link into <scaffold>/plugins/paper/skills), then the usual
    checkout places. Each candidate must be a git checkout with new-paper.sh."""
    tried: list[str] = []
    cands: list[tuple[str, Path]] = []
    if explicit:
        cands.append(("--scaffold", Path(explicit).expanduser()))
    elif os.environ.get("PAPER_SCAFFOLD"):
        cands.append(("$PAPER_SCAFFOLD",
                      Path(os.environ["PAPER_SCAFFOLD"]).expanduser()))
    else:
        link = project / ".agents" / "skills"
        if link.is_symlink():
            tgt = (link.parent / os.readlink(link)).resolve()
            # <scaffold>/plugins/paper/skills
            cands.append((".agents/skills", tgt.parent.parent.parent))
        cands.append(("sibling", project.parent / "paper-scaffold"))
        cands.append(("sibling", project.parent.parent / "paper-scaffold"))
        cands.append(("default", Path.home() / "Repos" / "paper-scaffold"))
    for how, c in cands:
        c = c.resolve()
        if looks_like_scaffold(c):
            return c
        tried.append(f"{how}: {c}")
    raise PlanError(
        "no paper-scaffold checkout found (need a git clone with "
        "scripts/new-paper.sh and its release tags). Tried:\n  "
        + "\n  ".join(tried)
        + "\nPass --scaffold PATH or set PAPER_SCAFFOLD.")


# ---------------------------------------------------------------------------
# which files the scaffold owns
# ---------------------------------------------------------------------------

def excludes_from_new_paper(src: str | None) -> tuple[str, ...]:
    if not src:
        return DEFAULT_EXCLUDES
    pats = tuple(re.findall(r"--exclude='([^']+)'", src))
    return pats or DEFAULT_EXCLUDES


def tar_excluded(path: str, patterns: tuple[str, ...]) -> bool:
    """GNU tar --exclude semantics for `tar -C DIR -cf - .`: a pattern is
    matched against every member name (`./a`, `./a/b`, ...), wildcards cross
    slashes, and excluding a directory excludes what is under it."""
    parts = path.split("/")
    names = ["./" + "/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    for pat in patterns:
        for name in names:
            if fnmatch.fnmatchcase(name, pat):
                return True
            # an unanchored pattern also matches a trailing component run
            if not pat.startswith("./") and fnmatch.fnmatchcase(
                    name[2:], pat):
                return True
    return False


def project_owned(path: str) -> bool:
    if any(fnmatch.fnmatchcase(path, p) for p in SCAFFOLD_HELPERS_IN_ANALYSIS):
        return False
    return any(fnmatch.fnmatchcase(path, p) for p in PROJECT_OWNED)


def owned(files: dict[str, Entry], excludes: tuple[str, ...]) -> dict[str, Entry]:
    return {p: e for p, e in files.items()
            if not tar_excluded(p, excludes) and not project_owned(p)}


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------

_NAME = re.compile(rb'^name = ".*"$', re.MULTILINE)
_VERSION = re.compile(rb'^version = ".*"$', re.MULTILINE)
_CLAUDE_VER = re.compile(
    rb"(paper-scaffold\]\([^)]*\)\s+)v?\d+\.\d+\.\d+")


def normalize(path: str, data: bytes | None) -> bytes | None:
    """Remove what new-paper.sh fills in, so a copy that differs from the
    release only by its own identity still counts as pristine."""
    if data is None:
        return None
    if path == "pyproject.toml":
        data = _NAME.sub(b'name = "<project>"', data, count=1)
        data = _VERSION.sub(b'version = "<version>"', data, count=1)
    elif path == "CLAUDE.md":
        data = _CLAUDE_VER.sub(rb"\1SCAFFOLD_VERSION", data, count=1)
    return data


def read_project(project: Path, rel: str) -> bytes | None:
    p = project / rel
    if p.is_symlink():
        return os.readlink(p).encode()
    if p.is_file():
        return p.read_bytes()
    return None


def lines(b: bytes) -> list[str]:
    return b.decode("utf-8", errors="replace").splitlines(keepends=True)


def churn(a: bytes, b: bytes) -> dict[str, int]:
    add = rem = hunks = 0
    sm = difflib.SequenceMatcher(None, lines(a), lines(b), autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        hunks += 1
        rem += i2 - i1
        add += j2 - j1
    return {"added": add, "removed": rem, "hunks": hunks}


def merge_check(base: bytes, ours: bytes, theirs: bytes) -> int | None:
    """Conflict count `git merge-file` would report, or None if it cannot
    tell (binary). Nothing is written to the project: this only says whether
    the hand merge is mechanical or needs judgment."""
    if b"\0" in base + ours + theirs:
        return None
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for name, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            f = Path(d) / name
            f.write_bytes(data)
            paths.append(str(f))
        r = subprocess.run(["git", "merge-file", "-p", "--quiet", *paths],
                           capture_output=True, check=False)
    if r.returncode < 0 or r.returncode > 127:
        return None
    return r.returncode


# 3.27.0 generates the Word reference document from project.toml's
# [word.style] instead of shipping this binary. Its bytes always differ (the
# creation time), so it is compared as Word renders it.
LEGACY_WORD_TEMPLATE = "word/paper-reference.docx"


def legacy_template_note(project_copy: bytes, release_copy: bytes | None) -> str:
    """Delete, translate to [word.style], or declare [word] reference."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from paper_word_reference import differences, effective, toml_block, translate
        if release_copy is not None and not differences(
                effective(project_copy), effective(release_copy)):
            return ("the stock template: `git rm` it (the generated one has "
                    "black headings)")
        style, left = translate(project_copy, release_copy)
    except Exception as exc:  # a damaged file, or no pandoc: say so, do not stop
        return f"customized locally: compare by hand ({exc})"
    if not style and not left:
        return "equal to the generated stock: `git rm` it"
    if not left:
        return ("customized: add to project.toml, then `git rm` it: "
                + toml_block(style).replace("\n", "; "))
    return (f"customized beyond [word.style] ({len(left)} difference(s); "
            "`uv run python tools/paper_word_reference.py --translate "
            f"{LEGACY_WORD_TEMPLATE} --baseline OLD` lists them): keep it and declare "
            f'[word] reference = "{LEGACY_WORD_TEMPLATE}" in project.toml, '
            "or accept the closest settings: "
            + toml_block(style).replace("\n", "; "))


@dataclass
class FileRow:
    path: str                     # path in the project
    cls: str
    upstream_path: str = ""       # path in the scaffold, when renamed
    note: str = ""
    local: dict | None = None     # churn current-upstream -> project
    upstream: dict | None = None  # churn current-upstream -> target
    conflicts: int | None = None  # git merge-file conflict count
    mode: str = ""


def classify(project: Path, blobs: Blobs, cur: dict[str, Entry],
             tgt: dict[str, Entry], project_files: set[str]) -> list[FileRow]:
    rows: list[FileRow] = []
    for up in sorted(set(cur) | set(tgt)):
        rel = RENAMED.get(up, up)
        c, t = cur.get(up), tgt.get(up)
        pdata = read_project(project, rel)
        row = FileRow(rel, "", upstream_path=up if up != rel else "",
                      mode=(t or c).mode)  # type: ignore[union-attr]
        cdata = blobs.get(c.sha) if c else None
        tdata = blobs.get(t.sha) if t else None
        nc, nt, np_ = (normalize(up, cdata), normalize(up, tdata),
                       normalize(up, pdata))
        if c and t and (c.sha == t.sha or nc == nt):
            row.cls = "unchanged"
            if pdata is None:
                row.note = "absent locally"
            elif np_ != nc:
                row.note = "customized locally"
        elif c is None:
            row.cls = "new-upstream"
            if pdata is None:
                pass
            elif np_ == nt:
                row.cls, row.note = "at-target", "already copied"
            else:
                row.note = "a different project file is already at this path"
        elif t is None:
            row.cls = "removed-upstream"
            if pdata is None:
                row.note = "already gone"
            elif up == LEGACY_WORD_TEMPLATE:
                row.note = legacy_template_note(pdata, cdata)
            elif np_ == nc:
                row.note = "pristine: `git rm` it"
            else:
                row.note = "customized locally: decide by hand"
        elif pdata is None:
            row.cls, row.note = "customized", "deleted locally"
        elif np_ == nt:
            row.cls = "at-target"
        elif np_ == nc:
            row.cls = "pristine"
        else:
            row.cls = "customized"
            assert nc is not None and nt is not None
            row.local = churn(nc, np_)  # type: ignore[arg-type]
            row.upstream = churn(nc, nt)
            row.conflicts = merge_check(nc, np_, nt)  # type: ignore[arg-type]
        rows.append(row)
        project_files.discard(rel)
    for rel in sorted(project_files):
        if rel.startswith(OWNED_DIRS) and not project_owned(rel):
            rows.append(FileRow(rel, "project-only"))
    return rows


def project_listing(project: Path) -> set[str]:
    """Tracked and untracked-but-not-ignored files, so build junk and caches
    do not show up as project-only."""
    if _in_git(project):
        out = git(project, "ls-files", "-z", "--cached", "--others",
                  "--exclude-standard", "--full-name", ".")
        prefix = git(project, "rev-parse", "--show-prefix").decode().strip()
        files = set()
        for p in out.decode().split("\0"):
            if p:
                files.add(p.removeprefix(prefix))
        return {f for f in files if (project / f).exists()
                or (project / f).is_symlink()}
    files = set()
    for d in OWNED_DIRS:
        for f in (project / d).rglob("*") if (project / d).is_dir() else ():
            if f.is_file() and "__pycache__" not in f.parts:
                files.add(str(f.relative_to(project)))
    return files


def _in_git(project: Path) -> bool:
    r = subprocess.run(["git", "-C", str(project), "rev-parse",
                        "--is-inside-work-tree"], capture_output=True,
                       check=False)
    return r.returncode == 0 and r.stdout.strip() == b"true"


# ---------------------------------------------------------------------------
# HISTORY.md "Upgrade:" lines
# ---------------------------------------------------------------------------

_SECTION = re.compile(r"^## (\S+)(.*)$")
_PATHLIKE = re.compile(
    r"`?((?:[\w.-]+/)+[\w.*-]*|[\w-]+\.(?:py|typ|toml|json|md|lua|sh|docx|csl)"
    r"|justfile|\.gitignore)`?")


@dataclass
class UpgradeLine:
    version: str
    text: str
    paths: list[str] = field(default_factory=list)
    status: str = "do"            # do | nothing | superseded
    superseded_by: str = ""
    needs_merge: list[str] = field(default_factory=list)  # customized files


def history_sections(history: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    name, buf = None, []
    for line in history.splitlines():
        m = _SECTION.match(line)
        if m:
            if name is not None:
                out.append((name, "\n".join(buf)))
            name, buf = m.group(1), []
        elif name is not None:
            buf.append(line)
    if name is not None:
        out.append((name, "\n".join(buf)))
    return out


# Older entries move out of HISTORY.md into an archive (3.23.0 moved 1.0.0
# through 3.19.0). A project upgrading from one of those releases still needs
# their Upgrade: lines, so both files are read; a version heading that appears
# in both is taken once, from HISTORY.md.
HISTORY_FILES = ("HISTORY.md", "docs/history-archive.md")


def release_notes(blobs: "Blobs", ref: str) -> str:
    """HISTORY.md followed by every archive the ref carries, as one text."""
    seen: set[str] = set()
    parts: list[str] = []
    for path in HISTORY_FILES:
        text = (blobs.show(ref, path) or b"").decode()
        if not text:
            continue
        kept: list[str] = []
        skip = False
        for line in text.splitlines():
            m = _SECTION.match(line)
            if m:
                skip = m.group(1) in seen
                seen.add(m.group(1))
            if not skip:
                kept.append(line)
        parts.append("\n".join(kept))
    return "\n\n".join(parts)


def upgrade_lines(history: str, current: str, target: str,
                  include_unreleased: bool) -> list[UpgradeLine]:
    lo, hi = vkey(current), vkey(target) if VERSION_RE.match(target) else None
    picked: list[tuple[tuple[int, int, int], str, str]] = []
    for name, body in history_sections(history):
        if name.lower() == "unreleased":
            if include_unreleased:
                picked.append(((10**6, 0, 0), name, body))
            continue
        if not VERSION_RE.match(name):
            continue
        k = vkey(name)
        if k > lo and (hi is None or k <= hi):
            picked.append((k, name, body))
    picked.sort()
    result: list[UpgradeLine] = []
    for _, name, body in picked:
        for para in re.split(r"\n\s*\n", body):
            flat = " ".join(para.split())
            # A bare "Upgrade:" starting a sentence, not one quoted in prose
            # (an entry may well mention "Upgrade:" lines).
            m = re.search(r"(?:^|(?<=\s))Upgrade:(?=\s)", flat)
            if not m:
                continue
            text = flat[m.end():].strip()
            u = UpgradeLine(name, text)
            u.paths = sorted({m.group(1).rstrip(".,;")
                              for m in _PATHLIKE.finditer(text)})
            if re.match(r"(?i)nothing to do\b", text):
                u.status = "nothing"
            result.append(u)
    supersede(result)
    return result


def _without_paths(text: str) -> str:
    """The instruction with every path replaced, so `tests/run.py` does not
    read as the verb "run" and a filename's dot does not end a sentence."""
    return _PATHLIKE.sub("PATH", text)


def _pure_copy(text: str) -> bool:
    """One sentence that only says to copy files: safe to fold into a later
    copy of the same files. Anything with a second instruction (merge, delete,
    run, edit) is never folded, because its other half would be lost."""
    # Strict on purpose: once the paths are gone, only glue words may remain.
    # "copy X and the README description" keeps "README description" and is
    # therefore never folded, since the README half is not a path we track.
    rest = re.sub(r"(?i)\b(copy|and|the|new|updated|wholesale|together|PATH)\b",
                  " ", _without_paths(text))
    return bool(re.match(r"(?i)copy\b", text)) and not re.sub(
        r"[\s,.`]", "", rest)


def _copied_paths(text: str) -> list[str]:
    """The paths in a line's leading `copy ...` clause: up to the first
    semicolon, sentence end, or second verb. Empty when it is not a copy."""
    if not re.match(r"(?i)copy\b", text):
        return []
    masked = _without_paths(text)
    m = re.search(r";|\. |\b(then|merge|delete|remove|run|edit)\b", masked)
    end = len(text)
    if m:
        # Map the cut in the masked text back to the original by counting
        # the paths before it.
        n = masked[:m.start()].count("PATH")
        spans = list(_PATHLIKE.finditer(text))
        end = spans[n].start() if n < len(spans) else len(text)
    return [p.group(1).rstrip(".,;") for p in _PATHLIKE.finditer(text[:end])]


def supersede(items: list[UpgradeLine]) -> None:
    """An earlier pure-copy line is superseded when a later line's copy
    clause names every one of its paths (or a directory holding them):
    copying the newer file does both. The later line is kept in full, so a
    merge or delete it also asks for is not lost."""
    for i, u in enumerate(items):
        if u.status != "do" or not u.paths or not _pure_copy(u.text):
            continue
        for later in items[i + 1:]:
            copied = _copied_paths(later.text)
            if later.status == "do" and copied and all(
                    _covers(copied, p) for p in u.paths):
                u.status, u.superseded_by = "superseded", later.version


def _covers(paths: list[str], p: str) -> bool:
    return any(p == q or (q.endswith("/") and p.startswith(q)) for q in paths)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def dirty_paths(project: Path, rels: list[str]) -> list[str]:
    if not rels:
        return []
    out = git(project, "status", "--porcelain", "-z", "--", *rels)
    return [rec[3:] for rec in out.decode().split("\0") if len(rec) > 3]


def apply_pristine(project: Path, blobs: Blobs, tgt: dict[str, Entry],
                   rows: list[FileRow]) -> list[str]:
    todo = [r for r in rows
            if r.cls == "pristine"
            or (r.cls == "new-upstream" and read_project(project, r.path) is None)]
    if not todo:
        return []
    if not _in_git(project):
        raise PlanError(f"{project} is not a git work tree; --apply-pristine "
                        "only writes where git can show and undo the change")
    dirty = dirty_paths(project, [r.path for r in todo
                                  if (project / r.path).exists()])
    if dirty:
        raise PlanError("refusing --apply-pristine: uncommitted changes in "
                        + ", ".join(sorted(dirty))
                        + ". Commit or discard them first.")
    done = []
    for r in todo:
        up = r.upstream_path or r.path
        e = tgt[up]
        data = blobs.get(e.sha)
        if up == "pyproject.toml":
            # Keep the project's name and version: the version records what
            # the manuscript is on, and it moves only after the hand merges.
            old = (project / r.path).read_bytes()
            for rx in (_NAME, _VERSION):
                m = rx.search(old)
                if m:
                    data = rx.sub(m.group(0).replace(b"\\", b"\\\\"), data,
                                  count=1)
        dest = project / r.path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if e.mode == "120000":
            if dest.is_symlink() or dest.exists():
                dest.unlink()
            os.symlink(data.decode(), dest)
        else:
            if dest.is_symlink():
                dest.unlink()
            dest.write_bytes(data)
            os.chmod(dest, 0o755 if e.mode == "100755" else 0o644)
        done.append(f"{'added' if r.cls == 'new-upstream' else 'replaced'} "
                    f"{r.path}")
    return done


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def build_plan(project: Path, scaffold: Path, target: str | None,
               base: str | None = None) -> dict:
    project = project.resolve()
    if project == scaffold.resolve():
        raise PlanError("this is the scaffold itself; run from a derived "
                        "manuscript or pass --project PATH")
    current = (base or project_version(project)).lstrip("v")
    tags = release_tags(scaffold)
    if not tags:
        raise PlanError(f"{scaffold} has no v* release tags; fetch them "
                        "(git fetch --tags) in the scaffold clone")
    cur_ref = "v" + current.lstrip("v")
    if cur_ref not in tags:
        raise PlanError(f"project is on {current}, but the scaffold clone has "
                        f"no tag {cur_ref}; fetch tags or check the version")
    tgt_ref = target or tags[-1]
    if VERSION_RE.match(tgt_ref) and not tgt_ref.startswith("v"):
        tgt_ref = "v" + tgt_ref
    if git(scaffold, "rev-parse", "--verify", "--quiet",
           tgt_ref + "^{commit}", check=False).strip() == b"":
        raise PlanError(f"no such ref in the scaffold: {tgt_ref}")
    tagged = VERSION_RE.match(tgt_ref) is not None
    if tagged and vkey(tgt_ref) < vkey(cur_ref):
        raise PlanError(f"target {tgt_ref} is older than the project's "
                        f"{cur_ref}")

    blobs = Blobs(scaffold)
    ex_cur = excludes_from_new_paper(
        (blobs.show(cur_ref, "scripts/new-paper.sh") or b"").decode() or
        (blobs.show(tgt_ref, "scripts/new-paper.sh") or b"").decode())
    ex_tgt = excludes_from_new_paper(
        (blobs.show(tgt_ref, "scripts/new-paper.sh") or b"").decode())
    cur_files = owned(tree(scaffold, cur_ref), ex_cur)
    tgt_files = owned(tree(scaffold, tgt_ref), ex_tgt)
    rows = classify(project, blobs, cur_files, tgt_files,
                    project_listing(project))

    history = release_notes(blobs, tgt_ref)
    target_version = tgt_ref.lstrip("v") if tagged else tgt_ref
    ups = upgrade_lines(history, current, target_version,
                        include_unreleased=not tagged)

    for u in ups:
        u.needs_merge = [r.path for r in rows if r.cls == "customized"
                         and _covers(u.paths, r.upstream_path or r.path)]

    counts = {c: 0 for c in CLASSES}
    for r in rows:
        counts[r.cls] += 1
    return {
        "project": str(project),
        "scaffold": str(scaffold),
        "current": current,
        "target": tgt_ref,
        "counts": counts,
        "upgrade_lines": [asdict(u) for u in ups],
        "files": [asdict(r) for r in rows],
        "_rows": rows,
        "_blobs": blobs,
        "_tgt_files": tgt_files,
    }


def render(plan: dict, show_all: bool) -> str:
    out: list[str] = []
    w = out.append
    w(f"upgrade plan: {plan['project']}")
    w(f"  {plan['current']} -> {plan['target']}   (scaffold: {plan['scaffold']})")
    if plan["target"].lstrip("v") == plan["current"]:
        w("  already on the target; the file table shows local customizations")
    w("")
    ups = plan["upgrade_lines"]
    w(f"1. HISTORY.md Upgrade: lines, oldest first ({len(ups)})")
    if not ups:
        w("   none")
    n = 0
    for u in ups:
        if u["status"] == "do":
            n += 1
            w(f"   {n:>2}. [{u['version']}] {u['text']}")
            nm = u["needs_merge"]
            if nm:
                w("       hand-merge here: " + ", ".join(nm[:6])
                  + (f" and {len(nm) - 6} more" if len(nm) > 6 else ""))
    skipped = [u for u in ups if u["status"] != "do"]
    for u in skipped:
        why = ("superseded by " + u["superseded_by"]
               if u["status"] == "superseded" else "nothing to do")
        w(f"     - [{u['version']}] ({why}) {u['text'][:70]}"
          + ("..." if len(u["text"]) > 70 else ""))
    w("")
    c = plan["counts"]
    w("2. Scaffold-owned files: " + ", ".join(
        f"{c[k]} {k}" for k in CLASSES if c[k]))
    w("")
    order = ["customized", "pristine", "new-upstream", "removed-upstream",
             "project-only", "at-target"] + (["unchanged"] if show_all else [])
    for cls in order:
        rows = [r for r in plan["files"] if r["cls"] == cls]
        if not rows:
            continue
        w(f"   {cls} ({len(rows)})")
        for r in rows:
            extra = ""
            if r["local"] is not None:
                lo, up = r["local"], r["upstream"]
                conf = ("clean 3-way merge" if r["conflicts"] == 0 else
                        f"{r['conflicts']} conflict(s)" if r["conflicts"]
                        else "binary")
                extra = (f"  local +{lo['added']}/-{lo['removed']}"
                         f" upstream +{up['added']}/-{up['removed']}  [{conf}]")
            name = r["path"] + (f" (upstream {r['upstream_path']})"
                                if r["upstream_path"] else "")
            w(f"     {name}{extra}" + (f"  -- {r['note']}" if r["note"] else ""))
        w("")
    if not show_all and c["unchanged"]:
        local = sum(1 for r in plan["files"]
                    if r["cls"] == "unchanged" and r["note"])
        w(f"   ({c['unchanged']} unchanged upstream, {local} of them differing "
          "locally, which the upgrade does not touch; --all lists them)")
        w("")
    w("3. Next")
    w("   - read the Upgrade: lines above; a major entry needs a manuscript edit")
    if c["pristine"] or c["new-upstream"]:
        w("   - `just upgrade-plan --apply-pristine` copies the pristine and "
          "new-upstream files (never a customized one)")
    if c["customized"]:
        w("   - merge each customized file by hand: git -C <scaffold> diff "
          f"{'v' + plan['current'].lstrip('v')}..{plan['target']} -- <path>")
    w(f"   - then set version = \"{plan['target'].lstrip('v')}\" in "
      "pyproject.toml, `just paper`, `just verify`")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Plan a paper-scaffold upgrade: Upgrade: lines and a "
                    "per-file classification. Read-only unless "
                    "--apply-pristine.")
    ap.add_argument("target", nargs="?", default=None,
                    help="scaffold tag or ref (default: latest v* tag)")
    ap.add_argument("--scaffold", help="upstream clone (default: "
                    "$PAPER_SCAFFOLD, .agents/skills, ~/Repos/paper-scaffold)")
    ap.add_argument("--from", dest="base", default=None,
                    help="treat the project as on this release instead of "
                    "pyproject's version (when that line was bumped early "
                    "or never)")
    ap.add_argument("--project", default=None,
                    help="manuscript directory (default: this one)")
    ap.add_argument("--json", action="store_true", help="machine output")
    ap.add_argument("--all", action="store_true",
                    help="also list files upstream did not change")
    ap.add_argument("--apply-pristine", action="store_true",
                    help="copy pristine and new-upstream files into place")
    a = ap.parse_args(argv)
    project = Path(a.project).expanduser().resolve() if a.project else ROOT
    try:
        scaffold = find_scaffold(a.scaffold, project)
        plan = build_plan(project, scaffold, a.target, a.base)
        applied = None
        if a.apply_pristine:
            applied = apply_pristine(project, plan["_blobs"],
                                     plan["_tgt_files"], plan["_rows"])
    except PlanError as e:
        print(f"upgrade-plan: {e}", file=sys.stderr)
        return 2
    public = {k: v for k, v in plan.items() if not k.startswith("_")}
    if applied is not None:
        public["applied"] = applied
    if a.json:
        print(json.dumps(public, indent=2))
        return 0
    print(render(public, a.all))
    if applied is not None:
        print()
        print(f"applied ({len(applied)}):" if applied else
              "applied: nothing to copy")
        for line in applied:
            print("   " + line)
        if applied:
            print("   review with `git diff --stat`; customized files were "
                  "not touched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
