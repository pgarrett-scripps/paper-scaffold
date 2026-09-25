#!/usr/bin/env python3
"""A revision round: the response letter, the submitted version, the diff.

    init          copy the response template to reviewer-response.typ (or the
                  project.toml `[response] file`); never overwrites
    check         the letter against reviews/ACTIONS.md: point ids unique,
                  every row a point cites exists, every "done" point cites at
                  least one row and each of those rows is done with a commit
                  hash in `closed` (an `uncommitted:` note is not enough)
    build         compile the letter to PDF beside it
    tag NAME      record what was submitted: refuses a dirty tree or a stale
                  paper.pdf, saves the review version NAME (.review/versions/),
                  and makes the annotated git tag submitted/NAME whose message
                  carries the tree fingerprint and the PDF's sha256
    diff NAME     the text of the PDF saved as NAME against the current build,
                  word by word, rendered as .review/diff-NAME.pdf (insertions
                  underlined blue, deletions struck red) and .html

The diff method, stated so a reader can judge it: both PDFs are reduced to
text with `pdftotext` (poppler), so every number, table cell and reference
number is compared as printed, not as the source spells it; whitespace and
line breaks are normalized; the words are aligned with Python's difflib
SequenceMatcher (autojunk off). Layout, fonts, figure pixels and equation
typesetting are outside it; `just review NAME` is the structural comparison.
When the saved version is gone (a fresh clone: .review/ is local) but the tag
exists, the diff falls back to the tagged SOURCE text of paper.typ and
si-body.typ, where numbers appear as #s() ids, and says so.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

from paths import ROOT, TOOLS  # the manuscript (tools/paths.py)

TEMPLATE = TOOLS / "reviewer-response-template.typ"
DEFAULT = "reviewer-response.typ"
STATUSES = ("done", "partly", "rebut", "todo", "decide")
HASH = re.compile(r"^[0-9a-f]{7,40}\b")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")


def letter(root: Path) -> Path:
    from project_hooks import load
    configured = load(root).response
    return root / (configured or DEFAULT)


def init(root: Path) -> int:
    path = letter(root)
    if path.exists():
        print(f"{path.name} exists: left as is")
        return 0
    shutil.copyfile(TEMPLATE, path)
    print(f"wrote {path.name}. One #point(...) per reviewer comment; cite the "
          "reviews/ACTIONS.md rows that carry the work in `actions:`.")
    return 0


def points(root: Path, path: Path) -> list[dict]:
    """The letter's points, as Typst evaluates them (metadata <response-point>)."""
    subprocess.run(["uv", "run", "--quiet", "paper", "tool", "render_stats"],
                   cwd=root, check=True, capture_output=True)
    out = subprocess.run(["typst", "query", "--root", str(root), str(path),
                          "<response-point>", "--field", "value"],
                         cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        raise ValueError(f"{path.name} does not compile: {out.stderr.strip()[:600]}")
    return json.loads(out.stdout or "[]")


def problems(found: list[dict], rows: list[dict]) -> list[str]:
    by_id = {r["id"]: r for r in rows}
    seen: set[str] = set()
    out = []
    for p in found:
        pid, status = str(p.get("id", "?")), p.get("status", "")
        actions = p.get("actions") or []
        if isinstance(actions, str):
            actions = [actions]
        if pid in seen:
            out.append(f"{pid}: point id used twice")
        seen.add(pid)
        if status not in STATUSES:
            out.append(f"{pid}: unknown status {status!r} ({', '.join(STATUSES)})")
        for a in actions:
            if a not in by_id:
                out.append(f"{pid}: cites {a}, which is not a row of reviews/ACTIONS.md")
        if status == "done":
            if not actions:
                out.append(f"{pid}: marked done but cites no reviews/ACTIONS.md row")
            for a in actions:
                row = by_id.get(a)
                if row is None:
                    continue
                if row["status"] != "done":
                    out.append(f"{pid}: marked done but {a} is {row['status']}")
                elif not HASH.match(row["closed"]):
                    out.append(f"{pid}: marked done but {a} is closed as "
                               f"{row['closed']!r}, not a commit (commit with "
                               f"`Closes: {a}`, then just close-actions)")
    return out


def check(root: Path, ledger: Path | None = None) -> int:
    import check_actions as ca
    path = letter(root)
    if not path.is_file():
        print(f"no {path.name}: nothing to check (just response-init starts one)")
        return 0
    ledger = ledger or root / "reviews" / "ACTIONS.md"
    rows: list[dict] = []
    if ledger.is_file():
        rows, errors = ca.parse(ledger.read_text())
        if errors:
            print(f"reviews/ACTIONS.md is malformed: {errors[0]} (just check-actions)")
            return 1
    try:
        found = points(root, path)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"response check could not run: {exc}")
        return 1
    bad = problems(found, rows)
    for line in bad:
        print(f"RESPONSE: {line}")
    counts = {s: sum(1 for p in found if p.get("status") == s) for s in STATUSES}
    summary = ", ".join(f"{n} {s}" for s, n in counts.items() if n)
    print(f"{path.name}: {len(found)} point(s){': ' + summary if summary else ''}"
          + ("" if bad else "; every done point is backed by a committed ledger row"))
    return 1 if bad else 0


def build(root: Path) -> int:
    path = letter(root)
    if not path.is_file():
        print(f"no {path.name}: just response-init starts one")
        return 1
    subprocess.run(["uv", "run", "--quiet", "paper", "tool", "render_stats"], cwd=root, check=True)
    pdf = path.with_suffix(".pdf")
    rc = subprocess.run(["typst", "compile", "--root", str(root), str(path), str(pdf)],
                        cwd=root).returncode
    if rc == 0:
        print(f"wrote {pdf.name}")
    return rc


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=check)


def tag(root: Path, name: str) -> int:
    import build_state
    import gate
    from review import save
    if not NAME.fullmatch(name) or name == "current":
        print("the name uses letters, digits, dots, hyphens or underscores")
        return 2
    ref = f"submitted/{name}"
    if _git(root, "rev-parse", "-q", "--verify", f"refs/tags/{ref}", check=False).returncode == 0:
        print(f"tag {ref} exists: a submission is recorded once. Pick a new name.")
        return 1
    dirty = _git(root, "status", "--porcelain", "--", ".").stdout.strip()
    if dirty:
        print("uncommitted changes: commit first, so the tag names what was built.\n" + dirty)
        return 1
    stale = [r for r in build_state.check(root, outputs=("paper.pdf",)) if r["status"] != "current"]
    if stale:
        r = stale[0]
        print(f"paper.pdf is {r['status']}{build_state.changed_note(r['changed'])}: "
              f"{r['command']} first")
        return 1
    pdf_sha = hashlib.sha256((root / "paper.pdf").read_bytes()).hexdigest()
    fp = gate.fingerprint(root)
    try:
        saved = save(root, name)
    except ValueError as exc:
        print(f"could not save the review version: {exc}")
        return 1
    message = (f"Submitted: {name}\n\npaper.pdf sha256: {pdf_sha}\n"
               f"tree fingerprint: {fp}\nreview version: {saved.relative_to(root)}\n")
    _git(root, "tag", "-a", ref, "-m", message)
    print(f"tagged {ref} at {_git(root, 'rev-parse', '--short', 'HEAD').stdout.strip()}; "
          f"saved {saved.relative_to(root)}. After revising: just diff-pdf {name}")
    return 0


def pdf_words(pdf: Path) -> list[str]:
    if not shutil.which("pdftotext"):
        raise ValueError("pdftotext is not installed (package: poppler-utils). See: just doctor")
    out = subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf), "-"],
                         capture_output=True, text=True, check=True).stdout
    return out.replace("­", "").split()


def diff_ops(old: list[str], new: list[str]) -> list[tuple[str, str]]:
    """[(kind, text)], kind one of same, del, ins; runs of words joined."""
    ops = []
    for tag_, i1, i2, j1, j2 in SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag_ == "equal":
            ops.append(("same", " ".join(old[i1:i2])))
            continue
        if tag_ in ("delete", "replace"):
            ops.append(("del", " ".join(old[i1:i2])))
        if tag_ in ("insert", "replace"):
            ops.append(("ins", " ".join(new[j1:j2])))
    return ops


def _typ_str(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def render_typst(ops: list[tuple[str, str]], title: str) -> str:
    body = []
    for kind, text in ops:
        call = {"same": "same", "del": "del", "ins": "ins"}[kind]
        body.append(f"#{call}({_typ_str(text)})")
    return f"""#set page(paper: "us-letter", margin: 0.8in, numbering: "1")
#set text(size: 10pt)
#set par(justify: false)
#let same(t) = t + " "
#let del(t) = text(fill: rgb("#b71c1c"))[#strike(t)] + " "
#let ins(t) = text(fill: rgb("#0d47a1"))[#underline(t)] + " "
#text(size: 13pt, weight: "bold", {_typ_str(title)}) \\
#text(size: 8.5pt)[Text-level diff of the rendered PDFs (pdftotext, words aligned with difflib). #text(fill: rgb("#0d47a1"))[#underline[Inserted]], #text(fill: rgb("#b71c1c"))[#strike[deleted]]. Layout, figures and equations are not compared.]
#v(8pt)
{chr(10).join(body)}
"""


def render_html(ops: list[tuple[str, str]], title: str) -> str:
    parts = []
    for kind, text in ops:
        t = html.escape(text)
        parts.append(t if kind == "same" else f"<{kind}>{t}</{kind}>")
    return (f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>"
            "<style>body{max-width:52em;margin:2em auto;font:15px/1.6 serif;padding:0 1em}"
            "del{color:#b71c1c}ins{color:#0d47a1}</style>"
            f"<h1>{html.escape(title)}</h1><p>" + " ".join(parts) + "</p>")


def _source_words(root: Path, ref: str | None) -> list[str]:
    words = []
    for name in ("paper.typ", "si-body.typ"):
        if ref:
            got = _git(root, "show", f"{ref}:{name}", check=False)
            text = got.stdout if got.returncode == 0 else ""
        else:
            text = (root / name).read_text() if (root / name).is_file() else ""
        words += text.split()
    return words


def diff(root: Path, name: str) -> int:
    from review import current_snapshot, version_path
    try:
        old_dir = version_path(root, name)
    except ValueError as exc:
        print(exc)
        return 2
    out_dir = root / ".review"
    out_dir.mkdir(exist_ok=True)
    try:
        if (old_dir / "paper.pdf").is_file():
            new_dir = current_snapshot(root)
            old, new = pdf_words(old_dir / "paper.pdf"), pdf_words(new_dir / "paper.pdf")
            title = f"Changes since {name}"
        else:
            ref = f"submitted/{name}"
            if _git(root, "rev-parse", "-q", "--verify", f"refs/tags/{ref}",
                    check=False).returncode != 0:
                print(f"no saved version {name!r} and no tag {ref}: just tag-submission "
                      "records one at submission time")
                return 1
            print(f"note: no saved version {name!r} here (.review/ is local); diffing the "
                  f"source text of {ref} instead, where numbers appear as #s() ids")
            old, new = _source_words(root, ref), _source_words(root, None)
            title = f"Source changes since {ref}"
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"diff failed: {exc}")
        return 1
    ops = diff_ops(old, new)
    changed = sum(1 for k, _ in ops if k != "same")
    from atomic_io import write_text
    html_path = out_dir / f"diff-{name}.html"
    write_text(html_path, render_html(ops, title))
    typ = out_dir / f"diff-{name}.typ"
    write_text(typ, render_typst(ops, title))
    pdf = out_dir / f"diff-{name}.pdf"
    rc = subprocess.run(["typst", "compile", str(typ), str(pdf)], cwd=root).returncode
    print(f"{changed} changed run(s): {pdf.relative_to(root) if rc == 0 else '(PDF failed)'}, "
          f"{html_path.relative_to(root)}")
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("init", "check", "build", "tag", "diff"))
    ap.add_argument("name", nargs="?")
    args = ap.parse_args(argv)
    root = ROOT
    if args.command in ("tag", "diff") and not args.name:
        ap.error(f"{args.command} needs a name (the submission, e.g. v1)")
    try:
        if args.command == "init":
            return init(root)
        if args.command == "check":
            return check(root)
        if args.command == "build":
            return build(root)
        if args.command == "tag":
            return tag(root, args.name)
        return diff(root, args.name)
    except subprocess.CalledProcessError as exc:
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
