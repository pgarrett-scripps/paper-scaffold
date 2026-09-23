#!/usr/bin/env python3
"""Guard the mechanical invariants of a copy-edit pass.

STYLE.md permits dropping a number from the main text; it never permits editing
one. It also forbids adding, deleting, or renumbering a figure, table, heading,
or citation. Those are mechanical properties, so they get checked mechanically
rather than eyeballed.

    just edit-baseline          # before the editing pass
    just edit-check             # after it

Snapshots live in .edit-guard/ at the manuscript root: local state like
.build-state/, gitignored, disposable. A tag argument keeps several passes
apart (`just edit-baseline round2`); omitted, it is "default".

Upstreamed from the koth manuscript, which wrote it for exactly this and ran
it in anger first.

What it compares, across the manuscript (main text and SI together, because
content legitimately moves between them):

  numbers      Every numeric token. Must be a SUBSET after editing: a number may
               disappear (rule 7 permits thinning), but one that appears nowhere
               it appeared before is either invented or altered, and both are
               fatal.
  stats        Literal s()/n() calls, including IDs. May disappear, not change.
  assets       Literal fig()/tbl() calls, including IDs. Exact occurrences.
  labels       <fig:...>, <tbl:...>, <sec:...>, <eq:...> definitions. Exact counts.
  refs         Every @citekey and #ref(<...>) target. Exact counts.
  figures      Count of #figure( blocks. Exact.
  headings     The heading text, in order, per file. Exact.

Declarations must also survive unchanged. These checks cannot prove that a
wording change preserves meaning or evaluate arbitrary Typst code.

The numeric tokenizer deliberately does NOT use a greedy [\\d,]* : that swallows
a sentence comma into the token, so "12.6, and" becomes "12.6," and every such
token reads as changed. It also strips a trailing period, since a citation moved
to the end of a sentence picks one up.
"""
from __future__ import annotations

import json
import argparse
import re
import sys
from pathlib import Path

from manuscript_sources import mask, matches, CALL, source_files
from typst_prose import DIRECTIVE, _bracket_depth
from atomic_io import write_text

# The manuscript root, one level up: this file lives in tools/.
from paths import ROOT  # the manuscript (tools/paths.py)
SNAP_DIR = ROOT / ".edit-guard"
DOCUMENT = None

# A number: digits, optionally with internal separators, but never trailing
# punctuation. Handles 12.6, 1,177, 79.4, 0.01, 2026-07-31, 8-11.
NUM = re.compile(r"(?<![A-Za-z0-9_.])[+-]?\d(?:[\d.,:/-]*\d)?")
LABEL = re.compile(r"\)\s*<((?:fig|tbl|tab|eq|sec):[A-Za-z0-9_:-]+)>|"
                   r"^(?:=+|#heading)[^\n]*?<((?:sec):[A-Za-z0-9_:-]+)>", re.M)
REF = re.compile(r"@([A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*)|"
                 r"#refn?\(\s*<([^>]+)>")
HEADING = re.compile(r"(?m)^(=+)\s+([^\n<]+?)(?:\s*<[^>]+>)?\s*$")
# The path of an import: `#import "@preview/alexandria:0.2.0": ...` is neither
# a citation (@preview) nor a number (0.2.0), and adding the SI's reference
# list adds one such line to a pass that changed no prose.
IMPORT_PATH = re.compile(r'(?m)^([ \t]*#import[ \t]+)("[^"\n]*")')


def _blank_code(src: str) -> str:
    """Blank `#import`, `#set` and code-valued `#let` directives, newlines
    kept. Their numbers are code, not results: the SI's bibliographyx guard
    (`bib.references.len() > 0`) read as an invented `0`. A `#let` bound to
    content (`#let paper-abstract = [...]`) is prose and stays counted, as
    does every `#show`, whose arguments can carry printed text.
    """
    lines, i = src.split("\n"), 0
    while i < len(lines):
        m = DIRECTIVE.match(lines[i])
        if not m:
            i += 1
            continue
        first, depth = i, _bracket_depth(lines[i])
        while depth > 0 and i + 1 < len(lines):
            i += 1
            depth += _bracket_depth(lines[i])
        block = "\n".join(lines[first:i + 1])
        content = m.group(1) == "let" and re.search(r"=\s*\[", block) \
            and not re.search(r"=\s*\{", block)
        if m.group(1) != "show" and not content:
            lines[first:i + 1] = [" " * len(line) for line in lines[first:i + 1]]
        i += 1
    return "\n".join(lines)


def _nums(text: str) -> list[str]:
    return sorted(m.group(0).rstrip(".,:").lstrip("+") for m in NUM.finditer(text))


def profile(path: Path) -> dict:
    src = IMPORT_PATH.sub(lambda m: m.group(1) + " " * len(m.group(2)),
                          mask(path.read_text()))
    calls = matches(CALL, src)
    return {
        "numbers": _nums(_blank_code(src)),
        "stats": sorted(m.group(1) + ":" + m.group(2) for m in calls
                        if m.group(1) in ("s", "n")),
        "assets": sorted(m.group(1) + ":" + m.group(2) for m in calls
                         if m.group(1) in ("fig", "tbl")),
        "labels": sorted(g for m in LABEL.finditer(src) for g in m.groups() if g),
        "refs": sorted(g for m in REF.finditer(src) for g in m.groups() if g),
        "figures": src.count("#figure("),
        "headings": [f"{m.group(1)} {m.group(2).strip()}" for m in HEADING.finditer(src)],
    }


def current() -> dict:
    if DOCUMENT is None:
        files = source_files(ROOT)
    else:
        from document_project import load_project
        project = load_project(ROOT)
        files = project.sources(project.select(DOCUMENT)[0])
    # Includes/imports carry content and macros that can change rendered values.
    return {f: profile(ROOT / f) for f in files}


def declarations() -> dict:
    result = {name: json.loads((ROOT / name).read_text()).get("values", {})
            for name in ("stats.json", "assets.json") if (ROOT / name).is_file()}
    if DOCUMENT is not None:
        from document_project import load_project
        project = load_project(ROOT)
        doc = project.select(DOCUMENT)[0]
        # JSON normalizes tuples to arrays in the saved representation.
        result["document"] = json.loads(json.dumps({"target": vars(doc),
            "parts": [vars(project.parts[p]) for p in doc.parts]}))
    return result


def snapshot(tag: str) -> int:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    data = current()
    write_text(SNAP_DIR / f"{tag}.json", json.dumps(
        {"schema_version": 2, "files": data, "declarations": declarations()}, indent=1))
    n = sum(len(d["numbers"]) for d in data.values())
    print(f"snapshot '{tag}': {n:,} numeric tokens, "
          f"{sum(len(d['refs']) for d in data.values())} refs, "
          f"{sum(d['figures'] for d in data.values())} figures across {len(data)} files")
    return 0


def check(tag: str) -> int:
    """Compare against the snapshot, judging inventions across the MANUSCRIPT.

    Per-file would be wrong. Content legitimately moves between the main text and
    the SI -- that is most of what a "this belongs in the SI" edit is -- and a
    per-file test reads one move as a number dropped from paper.typ and a
    different number invented in si-body.typ. So the fatal tests (invented
    numbers, lost or gained references, float count) run on the union of both
    files, and per-file movement is reported as a note. A number that appears
    nowhere it appeared before still fails, which is the property that matters.
    """
    from collections import Counter
    saved = json.loads((SNAP_DIR / f"{tag}.json").read_text())
    if saved.get("schema_version") != 2:
        print("snapshot predates helper/abstract protection; record a new edit-baseline")
        return 2
    want, now = saved["files"], current()
    if set(want) != set(now):
        print("  FATAL -- manuscript source files changed")
        return 1
    ok = saved["declarations"] == declarations()
    if not ok:
        print("  FATAL -- statistic or asset declarations changed")

    def union(src, key):
        out = Counter()
        for f in src:
            out += Counter(src[f][key])
        return out

    # --- manuscript-wide, fatal ---
    ca, cb = union(want, "numbers"), union(now, "numbers")
    invented = sorted((cb - ca).elements())
    if invented:
        print(f"  FATAL -- {len(invented)} numeric token(s) appear nowhere in the "
              f"original: {invented[:12]}")
        ok = False
    dropped = sorted((ca - cb).elements())
    if dropped:
        print(f"  note -- {len(dropped)} numeric token(s) dropped from the "
              f"manuscript (allowed; confirm each is in a table): {dropped[:12]}")

    added_stats = union(now, "stats") - union(want, "stats")
    if added_stats:
        print(f"  FATAL -- statistic calls invented or changed: {dict(added_stats)}")
        ok = False
    prefix = _si_prefix()
    for key in ("labels", "refs", "assets"):
        a, b = union(want, key), union(now, key)
        if key == "refs" and prefix:
            a, b, moved = _prefix_renames(a, b, prefix)
            if moved:
                print(f"  note -- {moved} citation(s) moved between the main and "
                      f"the SI reference list by the {prefix!r} prefix alone")
        lost, gained = sorted((a - b).elements()), sorted((b - a).elements())
        if lost or gained:
            print(f"  FATAL -- {key} changed. lost={lost[:8]} gained={gained[:8]}")
            ok = False
    fa = sum(want[f]["figures"] for f in want)
    fb = sum(now[f]["figures"] for f in want)
    if fa != fb:
        print(f"  FATAL -- #figure count {fa} -> {fb}")
        ok = False

    # --- per-file, informational: where things moved ---
    for f in want:
        a, b = want[f], now[f]
        moved = len(set(a["numbers"]) ^ set(b["numbers"]))
        if a["headings"] != b["headings"]:
            lost = [x for x in a["headings"] if x not in b["headings"]]
            gained = [x for x in b["headings"] if x not in a["headings"]]
            print(f"  FATAL -- {f}: headings changed. lost={lost[:6]} gained={gained[:6]}")
            ok = False
        elif moved:
            print(f"  note -- {f}: {moved} numeric token(s) moved in or out")

    print("  prose-edit guard: PASS (no number invented, no reference or float lost)"
          if ok else "  prose-edit guard: FAIL")
    return 0 if ok else 1


def _si_prefix() -> str | None:
    """The SI reference list's citation prefix ("si-"), or None without one."""
    from manuscript_sources import si_bibliography
    si = si_bibliography(ROOT)
    return (si["list_prefix"] or si["prefix"]) if si else None


def _prefix_renames(before, after, prefix: str):
    """Cancel `@key` <-> `@si-key` pairs: the same work, routed to another list.

    Moving the SI onto its own reference list rewrites every SI citation from
    @key to @si-key. That changes which list prints the work, not what is
    cited, so a lost `key` matched by a gained `si-key` (or the reverse) is a
    move. Returns (before, after, the number of pairs cancelled).
    """
    before, after = before.copy(), after.copy()
    lost = before - after
    moved = 0
    for ref, n in list((after - before).items()):
        other = ref[len(prefix):] if ref.startswith(prefix) else prefix + ref
        k = min(n, lost.get(other, 0))
        if k:
            lost[other] -= k
            before[other] -= k
            after[ref] -= k
            moved += k
    return +before, +after, moved


def main() -> int:
    global DOCUMENT, SNAP_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("snapshot", "check"))
    parser.add_argument("tag", nargs="?", default="default")
    parser.add_argument("--document", help="guard one manuscript.toml target")
    args = parser.parse_args()
    tag = args.tag
    if args.document:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.document) or args.document == "all":
            print("--document must name one document")
            return 2
        DOCUMENT = args.document
        SNAP_DIR = ROOT / ".edit-guard" / "documents" / DOCUMENT
    if not re.fullmatch(r"[A-Za-z0-9_-]+", tag):
        print("tag must contain only letters, numbers, underscores, or hyphens")
        return 2
    if args.command == "check" and not (SNAP_DIR / f"{tag}.json").is_file():
        print(f"no snapshot '{tag}' -- record one BEFORE the editing pass: "
              f"just edit-baseline" + (f" {tag}" if tag != "default" else ""))
        return 1
    try:
        return snapshot(tag) if args.command == "snapshot" else check(tag)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"edit guard could not complete: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
