"""Build and fingerprint deliverables, publishing only a complete stable build.

State is per output. Compiler dependency files supplement literal source
discovery; newly discovered dependencies trigger a second build with those
inputs fingerprinted before any transformation. Checks never compile anything.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil

from atomic_io import write_text
from manuscript_sources import source_files
from manifest_validation import load
from project_hooks import build_inputs

from paths import DATA, ROOT, locate, tool  # the manuscript (tools/paths.py)
# Every tool a captured build runs, AND every tools/ module they import (lazy
# imports included): submission.py runs the captured export_docx.py with only
# the captured tools/ on its path, so a missing import is a ModuleNotFoundError
# at `just main-docx` (4.1.1: paths.py and document_project.py were missing).
# tests/submission_cases.py checks the closure.
BUILD_TOOLS = ("render_stats.py", "typst_prose.py", "journal.py",
               "resolve_typst.py", "export_docx.py", "word_xml.py",
               "paper_word_reference.py", "readability.py",
               "refs_div.lua", "manuscript_sources.py", "manifest_validation.py",
               "atomic_io.py", "build_state.py", "bibliography.py",
               "manuscript_snapshot.py", "review.py", "paper_report.py",
               "wordcount.sh", "wordcount.py", "report.py", "project_hooks.py",
               "paths.py", "document_project.py", "word_tables.py")
INTERMEDIATES = {"stats-rendered.json", "paper.resolved.typ"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(root: Path, dependencies=()) -> dict[str, str | None]:
    paths = {root / name for name in source_files(root)}
    paths.update(root / name for name in ("wordcount.typ", "wordcount-sections.typ", "assets.json",
                                         "pyproject.toml", "uv.lock", "justfile", "journal.toml"))
    # The selected journal profile steers where the graphical abstract lands,
    # so a placement change is a source change to both outputs.
    # Journals and build tools may come from the installed toolchain
    # (tools/paths.py): hash their CONTENTS under the manuscript-relative
    # name, so an upgrade that changes one is a source change and a paper's
    # own override is captured the same way. The Word reference document is
    # not a file here (3.27.0): it is generated from project.toml's
    # [word.style] by paper_word_reference.py, both hashed, or it is the
    # paper's [word] reference, which build_inputs() names. uv.lock records
    # the installed release, so any pin move is a source change too.
    toolchain = {f"tools/{name}" for name in BUILD_TOOLS}
    toolchain.update(f"journals/{p.name}" for base in (root, DATA)
                     for p in (base / "journals").glob("*.toml"))
    # project.toml and the Word steps it names (docs/hooks.md), captured with
    # the manuscript so a build of it converts the way it was built.
    paths.update(root / name for name in build_inputs(root))
    paths.update(root.glob("*.bib"))
    paths.update(root.glob("*.csl"))
    for folder in ("figures", "si", "csl"):
        paths.update(p for p in (root / folder).rglob("*") if p.is_file())
    paths.update(Path(p) if Path(p).is_absolute() else root / p for p in dependencies)
    result = {}
    for path in sorted(paths):
        if path.name in INTERMEDIATES:
            continue
        try:
            name = path.relative_to(root).as_posix()
        except ValueError:
            name = str(path)
        result[name] = digest(path) if path.is_file() else None
    for name in sorted(toolchain):
        path = locate(root, name)
        result[name] = digest(path) if path.is_file() else None
    result["stats.json"] = stats_digest(root)
    return result


def stats_digest(root: Path) -> str | None:
    """stats.json's hash with `pinned` dropped.

    `just pin` re-records the hashes of files the numbers only WATCH, and that
    must not read as a source change: the values are untouched and the PDF
    cannot differ. Shared with tools/slides.py so a deck and the paper agree
    about what a change to stats.json is.
    """
    stats = root / "stats.json"
    if not stats.is_file():
        return None
    doc = load(stats, "stats")
    doc.pop("pinned", None)
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()


def state_path(root: Path, output: str) -> Path:
    return root / ".build-state" / f"{output}.json"


def dependency_list(root: Path, output: str) -> list[str]:
    path = root / ".build-state" / f"{output}.deps.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if not isinstance(data, list) or any(not isinstance(p, str) for p in data):
        raise ValueError(f"invalid dependency state: {path}")
    return data


def free_space_error(root: Path) -> str | None:
    """Why a build should not start for lack of disk, or None.

    A full disk fails a build halfway, after the temporary capture is written
    and before the output is, and the error Typst or pandoc gives names neither
    the disk nor the fix. PAPER_MIN_FREE_MB sets the floor (default 500; 0
    disables).
    """
    try:
        floor = float(os.environ.get("PAPER_MIN_FREE_MB", "500"))
    except ValueError:
        floor = 500.0
    if floor <= 0:
        return None
    import shutil
    free = shutil.disk_usage(root).free / 2**20
    if free < floor:
        return (f"only {free:,.0f} MB free on the disk holding {root}; builds need "
                f"{floor:,.0f} MB (PAPER_MIN_FREE_MB). Free space, then rebuild.")
    return None


def _try_lock(stream) -> bool:
    try:
        if os.name == "nt":
            import msvcrt
            stream.seek(0); stream.write(b"0"); stream.flush(); stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(stream) -> None:
    if os.name == "nt":
        import msvcrt
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_UN)


HELD = "PAPER_BUILD_LOCK_HELD"


@contextmanager
def build_lock(root: Path, wait: float | None = None, owner: str = ""):
    """One manuscript build at a time, per manuscript directory.

    `wait` seconds (PAPER_BUILD_WAIT, default 0) are spent waiting for another
    build before giving up, naming it from build.lock.owner. `just paper`
    takes the lock once for the whole build (tools/gate.py locked) and marks
    it held in the environment, so the steps inside it re-enter here instead
    of refusing their own parent.
    """
    folder = root / ".build-state"
    folder.mkdir(exist_ok=True)
    lock = folder / "build.lock"
    if os.environ.get(HELD) == str(lock.resolve()):
        yield
        return
    problem = free_space_error(root)
    if problem:
        raise ValueError(problem)
    if wait is None:
        try:
            wait = float(os.environ.get("PAPER_BUILD_WAIT", "0"))
        except ValueError:
            wait = 0.0
    import time
    deadline, told = time.monotonic() + wait, False
    with lock.open("a+b") as stream:
        while not _try_lock(stream):
            try:
                who = (folder / "build.lock.owner").read_text().strip()
            except OSError:
                who = ""
            if time.monotonic() >= deadline:
                raise ValueError("another manuscript build is running"
                                 + (f" ({who})" if who else "")
                                 + "; retry after it finishes") from None
            if not told:
                print(f"waiting for another manuscript build{f' ({who})' if who else ''} "
                      f"to finish, up to {wait:.0f} s", file=sys.stderr, flush=True)
                told = True
            time.sleep(0.5)
        try:
            if owner:
                (folder / "build.lock.owner").write_text(owner + "\n")
            yield
        finally:
            if owner:
                (folder / "build.lock.owner").unlink(missing_ok=True)
            _unlock(stream)


def changed_sources(root: Path, recorded: dict, dependencies=()) -> list[str]:
    """The recorded source paths whose hash moved (or appeared, or vanished)."""
    now = snapshot(root, dependencies)
    return sorted(k for k in set(now) | set(recorded) if now.get(k) != recorded.get(k))


def prepare_snapshot(root: Path, folder: Path, sources: dict, dependencies: list, *,
                     toc_pdf: str = "preprint", toc_word: str = "journal") -> dict:
    from manuscript_snapshot import materialize, query_numbers, project_word, seal
    from review import make_document
    materialize(root, folder, sources)
    # Both paths read the captured sources. Neither consumes the other's
    # output, so Word numbering/adaptation can overlap PDF compilation.
    # Join even on failure before the caller removes the temporary tree;
    # sealing and publication require both paths to have succeeded.
    with ThreadPoolExecutor(max_workers=1) as pool:
        # The graphical abstract's placement is the one thing journal.toml
        # changes about the OUTPUT: the PDF and the Word file each get theirs.
        pdf = pool.submit(subprocess.run,
                         ["typst", "compile", "--root", str(folder),
                          "--input", f"toc={toc_pdf}",
                          str(folder / "paper.typ"), str(folder / "paper.pdf")],
                         cwd=folder, check=True)
        front_matter = folder / "front-matter.json"
        numbers = query_numbers(folder, front_matter=front_matter)
        project_word(folder, numbers, front_matter=front_matter, toc=toc_word)
        write_text(folder / "document.json", json.dumps(make_document(folder), ensure_ascii=False))
        pdf.result()
    return seal(folder, sources, dependencies)


def build(mode: str, root: Path = ROOT) -> int:
    output = "paper.pdf" if mode in ("paper", "resolve") else "paper.docx"
    from journal import placement as toc_placement
    toc_pdf, toc_word = toc_placement(root, "pdf"), toc_placement(root, "docx")
    with build_lock(root), tempfile.TemporaryDirectory(dir=root / ".build-state") as tmp:
        staged = Path(tmp) / output
        depfile = Path(tmp) / "deps.json"
        dependencies = dependency_list(root, output)
        # A first compilation discovers package files and dynamic image/data
        # paths. Repeat once with them in the pre-transform snapshot.
        for attempt in range(2):
            before = snapshot(root, dependencies)

            def run(*args):
                subprocess.run(args, cwd=root, check=True)

            run(sys.executable, str(tool("render_stats.py")))
            # Discover actual inputs before capturing them, including dynamic
            # image/data paths. This probe is never published as the final PDF.
            run("typst", "compile", "--deps", str(depfile), "--input", f"toc={toc_pdf}",
                "paper.typ", str(Path(tmp) / "probe.pdf"))
            dependencies = json.loads(depfile.read_text())["inputs"]
            after = snapshot(root, dependencies)
            write_text(root / ".build-state" / f"{output}.deps.json", json.dumps(dependencies))
            if before == after:
                folder = Path(tmp) / "manuscript"
                manifest = prepare_snapshot(root, folder, before, dependencies,
                                            toc_pdf=toc_pdf, toc_word=toc_word)
                if mode in ("paper", "resolve"):
                    shutil.copyfile(folder / "paper.pdf", staged)
                else:
                    run(sys.executable, str(tool("export_docx.py")),
                        "--root", str(folder), "--source", str(folder / "paper.word.typ"),
                        "--output", str(staged))
                if snapshot(root, dependencies) != before:
                    raise ValueError("sources changed during the build; last good output preserved, rerun the build")
                saved = root / ".build-state" / "manuscripts" / manifest["id"]
                saved.parent.mkdir(exist_ok=True)
                if saved.exists():
                    from manuscript_snapshot import validate
                    validate(saved)
                else:
                    os.replace(folder, saved)
                # Compatibility preview for people inspecting the Word adapter.
                write_text(root / "paper.resolved.typ", (saved / "paper.word.typ").read_text())
                write_text(root / ".build-state" / "manuscript.json", json.dumps({
                    "id": manifest["id"], "path": saved.relative_to(root).as_posix()}))
                os.replace(staged, root / output)
                write_text(state_path(root, output), json.dumps({
                    "schema_version": 1, "mode": mode, "sources": before,
                    "dependencies": dependencies, "manuscript_id": manifest["id"],
                    "output_hash": digest(root / output)}, indent=2))
                return 0
            # Only new dependencies justify automatic retry. Changed sources
            # are the author's edit, and must never be represented as built.
            changed = any(after.get(path) != value for path, value in before.items())
            if changed or attempt:
                raise ValueError("sources changed during the build; last good output preserved, rerun the build")
            print("new compiler dependencies discovered; rebuilding with their source hashes", flush=True)
    return 1


def check(root: Path = ROOT, outputs=("paper.pdf", "paper.docx")) -> list[dict]:
    out = []
    recipes = {"paper.pdf": "just paper", "paper.docx": "just docx"}
    for output, recipe in ((o, recipes[o]) for o in outputs):
        status = "current"
        changed: list[str] = []
        try:
            if not (root / output).is_file():
                status = "missing"
            elif not state_path(root, output).is_file():
                status = "unknown"
            else:
                state = json.loads(state_path(root, output).read_text())
                if state.get("schema_version") != 1:
                    status = "unknown"
                elif snapshot(root, state["dependencies"]) != state["sources"]:
                    status = "stale"
                    changed = changed_sources(root, state["sources"], state["dependencies"])
                elif digest(root / output) != state["output_hash"]:
                    status = "replaced"
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            status = "unknown"
        out.append({"output": output, "status": status, "command": recipe,
                    "changed": changed})
    return out


def changed_note(changed: list[str], limit: int = 5) -> str:
    """ "  (changed: paper.typ, stats.json and 3 more)", or "" for none."""
    if not changed:
        return ""
    more = f" and {len(changed) - limit} more" if len(changed) > limit else ""
    return f"  (changed: {', '.join(changed[:limit])}{more})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("paper", "resolve", "docx", "check", "stamp"))
    # A manuscript.toml project with no lib/template.typ builds its PDFs as
    # documents but still exports paper.docx by the paper's route: its
    # check-build asks about that one output (4.1.1).
    parser.add_argument("--output", choices=("paper.pdf", "paper.docx"), action="append")
    args = parser.parse_args()
    try:
        if args.command == "stamp":
            print(hashlib.sha256(json.dumps(snapshot(ROOT), sort_keys=True).encode()).hexdigest())
            return 0
        if args.command != "check":
            return build(args.command)
        rows = check(outputs=args.output or ("paper.pdf", "paper.docx"))
        for row in rows:
            if row["status"] != "current":
                print(f"{row['status'].upper()}: {row['output']} -- rebuild: {row['command']}"
                      + changed_note(row.get("changed", [])))
        if all(row["status"] == "current" for row in rows):
            print(" and ".join(r["output"] for r in rows) + " "
                  + ("is" if len(rows) == 1 else "are") + " current with the source")
            return 0
        return 1
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
