#!/usr/bin/env python3
"""Build and check the Typst + Touying slide decks under slides/.

WHY THIS IS ITS OWN TOOL, and not another mode of build_state.py. A deck is a
different kind of output from the paper:

  - It is OUTSIDE the gate. `just check` answers "is the manuscript I would
    submit current?", and a talk is not that. A deck falls behind the moment a
    sentence changes, the fix costs one recompile, and a warning that is almost
    always present is one people stop reading. So the deck's staleness lives in
    its own records and is asked for deliberately: `just slides-check`.
  - Its fingerprint is NARROWER. build_state.snapshot() hashes every file under
    figures/ and si/, because the paper could show any of them. A deck shows a
    handful, and Typst's own `--deps` output says which -- so regenerating a
    figure a talk does not use leaves that talk current.
  - Its build is ONE compile. build_state needs a throwaway probe compile
    because a transformation stage (the Word projection) sits between
    discovering the real inputs and publishing the output. A deck has no such
    stage, so the `--deps` compile IS the published compile.

WHAT IT SHARES. The build lock, deliberately: a deck build runs render_stats,
which rewrites the root stats-rendered.json that a concurrent `just paper` also
rewrites. The lock is project-wide and its refusal message is already right.
It also shares the status vocabulary (current/missing/unknown/stale/replaced)
and the stats.json digest, so the two agree about what a source change is.

Usage (via `just slides`, `just slides-check`, `just slides-notes`):
    uv run python tools/slides.py list
    uv run python tools/slides.py build [name] [--handout] [--draft]
    uv run python tools/slides.py check [name]
    uv run python tools/slides.py notes <name>
    uv run python tools/slides.py prose [name] [--strict] [--show-suppressed]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from atomic_io import write_text  # noqa: E402
from build_state import (  # noqa: E402
    INTERMEDIATES, build_lock, digest, stats_digest,
)
from manuscript_sources import (  # noqa: E402
    SLIDE_SHARED, SLIDES, slide_targets, source_files,
)

# The tools whose behaviour decides what a deck PDF contains. A change to any of
# them can change the output without any manuscript source changing, which is
# what a staleness record exists to notice.
DECK_TOOLS = ("slides.py", "render_stats.py", "typst_prose.py",
              "manuscript_sources.py", "manifest_validation.py",
              "atomic_io.py", "build_state.py")


def source(root: Path, name: str) -> Path:
    """slides/<name>.typ, or a ValueError naming what does exist.

    Checked against slide_targets() rather than against the filesystem, so the
    glob that decides what `just slides` builds is also what decides what
    `just slides <name>` accepts. `just slides theme` otherwise compiled the
    shared theme as though it were a talk: it is a real file, so an is_file()
    test let it through, and the result was a one-slide PDF of nothing.
    """
    path = root / SLIDES / f"{name}.typ"
    if name not in slide_targets(root):
        known = ", ".join(slide_targets(root)) or "none"
        shared = (f"; {SLIDES}/{name}.typ is shared by every deck, not one"
                  if path.is_file() else "")
        raise ValueError(
            f"no deck named {name!r} in {SLIDES}/ (found: {known}){shared}")
    return path


def output(root: Path, name: str, *, handout: bool = False,
           draft: bool = False) -> Path:
    suffix = "-handout" if handout else ("-draft" if draft else "")
    return root / SLIDES / f"{name}{suffix}.pdf"


def _key(name: str, *, handout: bool) -> str:
    """The build-state filename for a deck.

    build_state.state_path() builds `.build-state/<output>.json`, which cannot
    take the `/` in `slides/talk.pdf`. The key is flattened here rather than
    bending that function, because the paper's outputs sit at the root and
    genuinely have no separator to lose.
    """
    return f"slides-{name}{'-handout' if handout else ''}.pdf"


def state_path(root: Path, name: str, *, handout: bool = False) -> Path:
    return root / ".build-state" / f"{_key(name, handout=handout)}.json"


def dependency_path(root: Path, name: str, *, handout: bool = False) -> Path:
    return root / ".build-state" / f"{_key(name, handout=handout)}.deps.json"


def dependency_list(root: Path, name: str, *, handout: bool = False) -> list[str]:
    path = dependency_path(root, name, handout=handout)
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if not isinstance(data, list) or any(not isinstance(p, str) for p in data):
        raise ValueError(f"invalid dependency state: {path}")
    return data


def snapshot(root: Path, name: str, dependencies=()) -> dict[str, str | None]:
    """The deck's source fingerprint.

    Deliberately NOT build_state.snapshot(): that one hashes paper.typ,
    si-body.typ, the word-count sources and every file under figures/ and si/,
    none of which a deck necessarily reads. Here the inputs are the deck's own
    literal import closure (which reaches slides/theme.typ and slides/config.typ,
    and through them stats.typ and assets.typ), the two manifests, the
    bibliography, and whatever the compiler itself reported reading.
    """
    deck = f"{SLIDES}/{name}.typ"
    paths = {root / n for n in source_files(root, entrypoints=(deck,))}
    paths.update(root / n for n in ("assets.json", "pyproject.toml",
                                    "uv.lock", "justfile"))
    paths.update(root / "tools" / n for n in DECK_TOOLS)
    paths.update(root.glob("*.bib"))
    paths.update(root.glob("*.csl"))
    paths.update(Path(p) if Path(p).is_absolute() else root / p
                 for p in dependencies)
    result: dict[str, str | None] = {}
    for path in sorted(paths):
        if path.name in INTERMEDIATES:
            continue
        try:
            key = path.relative_to(root).as_posix()
        except ValueError:
            key = str(path)
        result[key] = digest(path) if path.is_file() else None
    result["stats.json"] = stats_digest(root)
    return result


def _compile(root: Path, name: str, target: Path, deps: Path, *,
             handout: bool, draft: bool) -> None:
    # --root is mandatory. Typst otherwise roots at the input file's parent,
    # which for slides/talk.typ is slides/, and every `#import "/stats.typ"` in
    # the theme then fails to resolve.
    args = ["typst", "compile", "--root", str(root), "--deps", str(deps)]
    if handout:
        args += ["--input", "handout=true"]
    if draft:
        args += ["--input", "draft=true"]
    args += [str(root / SLIDES / f"{name}.typ"), str(target)]
    subprocess.run(args, cwd=root, check=True)


def build(name: str, *, handout: bool = False, draft: bool = False,
          root: Path = ROOT) -> int:
    """Compile one deck and record what it was built from.

    Draft mode writes slides/<name>-draft.pdf and records NOTHING, the same
    trade `just draft` makes for the paper: an unresolved id renders as a
    placeholder, so the file must not be one anyone could mistake for the deck
    they are about to present, and no staleness record should claim it is.
    """
    source(root, name)
    out = output(root, name, handout=handout, draft=draft)
    with build_lock(root), tempfile.TemporaryDirectory(dir=root / ".build-state") as tmp:
        staged = Path(tmp) / out.name
        deps = Path(tmp) / "deps.json"
        subprocess.run([sys.executable, str(root / "tools/render_stats.py")],
                       cwd=root, check=True)
        before = snapshot(root, name, dependency_list(root, name, handout=handout))
        _compile(root, name, staged, deps, handout=handout, draft=draft)
        if draft:
            os.replace(staged, out)
            print(f"wrote {out.relative_to(root)} -- unresolved numbers appear "
                  f"as ?id?; `just slides {name}` is the real build")
            return 0
        dependencies = json.loads(deps.read_text())["inputs"]
        # Re-hash EXACTLY what was hashed before the compile -- the same paths,
        # from the previous build's dependency list -- so the only thing this
        # comparison can report is a file whose content changed while typst ran.
        #
        # It deliberately does not compare against the fresh dependency list.
        # The compile is what discovers dependencies, so that list legitimately
        # changes between builds in both directions: it gains the images and
        # package files a new slide reads, and it LOSES a file the deck stopped
        # importing. An earlier version compared the two lists key by key, which
        # read a dropped dependency as a source vanishing mid-build and refused
        # every build after a theme import was removed.
        if snapshot(root, name, dependency_list(root, name, handout=handout)) != before:
            raise ValueError("sources changed during the build; last good deck "
                             "preserved, rerun the build")
        after = snapshot(root, name, dependencies)
        write_text(dependency_path(root, name, handout=handout),
                   json.dumps(dependencies))
        os.replace(staged, out)
        write_text(state_path(root, name, handout=handout), json.dumps({
            "schema_version": 1, "target": name, "handout": handout,
            "sources": after, "dependencies": dependencies,
            "output_hash": digest(out)}, indent=2))
    print(f"wrote {out.relative_to(root)}")
    return 0


def status(root: Path, name: str, *, handout: bool = False) -> str:
    """current | missing | unknown | stale | replaced, as build_state reports."""
    out = output(root, name, handout=handout)
    try:
        if not out.is_file():
            return "missing"
        record = state_path(root, name, handout=handout)
        if not record.is_file():
            return "unknown"
        state = json.loads(record.read_text())
        if state.get("schema_version") != 1:
            return "unknown"
        if snapshot(root, name, state["dependencies"]) != state["sources"]:
            return "stale"
        if digest(out) != state["output_hash"]:
            return "replaced"
        return "current"
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return "unknown"


def check(root: Path = ROOT, name: str | None = None) -> list[dict]:
    """One row per deck, plus a row per handout that has ever been built.

    A handout nobody has built is absent, not stale, so it is only reported
    once a record for it exists.
    """
    rows = []
    for deck in ([name] if name else slide_targets(root)):
        rows.append({"target": deck,
                     "output": output(root, deck).relative_to(root).as_posix(),
                     "status": status(root, deck),
                     "command": f"just slides {deck}"})
        if state_path(root, deck, handout=True).is_file():
            rows.append({
                "target": deck,
                "output": output(root, deck, handout=True).relative_to(root).as_posix(),
                "status": status(root, deck, handout=True),
                "command": f"just slides-handout {deck}"})
    return rows


def notes(name: str, root: Path = ROOT) -> int:
    """Export a deck's #speaker-note text to slides/<name>.pdfpc.

    Touying records every note as pdfpc metadata inside the document; this is
    the query its own documentation prescribes for pulling it back out, so
    pdfpc, Impressive and Slide Presenter can show notes on the second screen.
    """
    source(root, name)
    out = root / SLIDES / f"{name}.pdfpc"
    result = subprocess.run(
        ["typst", "query", "--root", str(root),
         str(root / SLIDES / f"{name}.typ"), "--field", "value",
         "--one", "<pdfpc-file>"],
        cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"no speaker notes in {SLIDES}/{name}.typ "
              f"-- nothing written ({result.stderr.strip().splitlines()[0] if result.stderr.strip() else 'no <pdfpc-file>'})",
              file=sys.stderr)
        return 2
    write_text(out, result.stdout)
    print(f"wrote {out.relative_to(root)}")
    return 0


def check_prose(root: Path = ROOT, name: str | None = None, *,
                strict: bool = False, show_suppressed: bool = False) -> int:
    """The four rules a slide is held to. See prose_check.SLIDE_RULES."""
    import prose_check
    import readability
    from manuscript_sources import slide_files
    from prose_rules import load_config, report

    cfg = load_config(root)
    readability.add_abbreviations(sorted(cfg.vocabulary("abbreviations", set())))
    sources = {k: v for k, v in slide_files(root, strict=True).items()
               if k.startswith(f"{SLIDES}/")}
    if name:
        source(root, name)
        # The shared files come along with any single deck: a talk title with an
        # em dash in it is written in slides/config.typ, not in the deck.
        keep = {name} | {Path(n).stem for n in SLIDE_SHARED}
        sources = {k: v for k, v in sources.items() if Path(k).stem in keep}
    findings = prose_check.check_slides(sources, cfg)
    return report(findings, cfg, show_suppressed=show_suppressed, strict=strict)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and check slide decks")
    parser.add_argument("command",
                        choices=("list", "build", "check", "notes", "prose"))
    parser.add_argument("name", nargs="?", default="")
    parser.add_argument("--handout", action="store_true")
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--show-suppressed", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root, name = args.root.resolve(), args.name or None

    decks = slide_targets(root)
    if not decks:
        print(f"no decks in {SLIDES}/ -- a deck is a .typ file there; "
              f"see {SLIDES}/theme.typ", file=sys.stderr)
        return 2
    try:
        if args.command == "list":
            for deck in decks:
                print(f"  {deck}  ({status(root, deck)})")
            return 0
        if args.command == "notes":
            if not name:
                print("just slides-notes needs a deck name", file=sys.stderr)
                return 2
            return notes(name, root=root)
        if args.command == "prose":
            return check_prose(root, name, strict=args.strict,
                               show_suppressed=args.show_suppressed)
        if args.command == "build":
            for deck in ([name] if name else decks):
                build(deck, handout=args.handout, draft=args.draft, root=root)
            return 0
        rows = check(root, name)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for row in rows:
                if row["status"] != "current":
                    print(f"{row['status'].upper()}: {row['output']} "
                          f"-- rebuild: {row['command']}")
        if all(row["status"] == "current" for row in rows):
            if not args.json:
                print(f"{len(rows)} deck output(s) current with the source")
            return 0
        return 1
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"slides failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
