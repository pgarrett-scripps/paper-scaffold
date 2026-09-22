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

ROOT = Path(__file__).resolve().parent.parent
BUILD_TOOLS = ("render_stats.py", "typst_prose.py", "typst2docx.py",
               "resolve_typst.py", "export_docx.py", "word_xml.py",
               "paper_word_reference.py", "readability.py",
               "refs_div.lua", "manuscript_sources.py", "manifest_validation.py",
               "atomic_io.py", "build_state.py", "bibliography.py",
               "manuscript_snapshot.py", "review.py", "paper_report.py",
               "wordcount.sh", "wordcount.py", "report.py")
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
                                         "pyproject.toml", "uv.lock", "justfile"))
    paths.update(root / "tools" / name for name in BUILD_TOOLS)
    paths.add(root / "word/paper-reference.docx")
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


@contextmanager
def build_lock(root: Path):
    folder = root / ".build-state"
    folder.mkdir(exist_ok=True)
    with (folder / "build.lock").open("a+b") as stream:
        try:
            if os.name == "nt":
                import msvcrt
                stream.seek(0); stream.write(b"0"); stream.flush(); stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError("another manuscript build is running; retry after it finishes") from None
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def prepare_snapshot(root: Path, folder: Path, sources: dict, dependencies: list) -> dict:
    from manuscript_snapshot import materialize, query_numbers, project_word, seal
    from review import make_document
    materialize(root, folder, sources)
    # Both paths read the captured sources. Neither consumes the other's
    # output, so Word numbering/adaptation can overlap PDF compilation.
    # Join even on failure before the caller removes the temporary tree;
    # sealing and publication require both paths to have succeeded.
    with ThreadPoolExecutor(max_workers=1) as pool:
        pdf = pool.submit(subprocess.run,
                         ["typst", "compile", "--root", str(folder),
                          str(folder / "paper.typ"), str(folder / "paper.pdf")],
                         cwd=folder, check=True)
        front_matter = folder / "front-matter.json"
        numbers = query_numbers(folder, front_matter=front_matter)
        project_word(folder, numbers, front_matter=front_matter)
        write_text(folder / "document.json", json.dumps(make_document(folder), ensure_ascii=False))
        pdf.result()
    return seal(folder, sources, dependencies)


def build(mode: str, root: Path = ROOT) -> int:
    output = "paper.pdf" if mode in ("paper", "resolve") else "paper.docx"
    # The old HTML route cannot carry a second reference list. Typst's HTML
    # export drops the grid Alexandria sets the SI's list in ("grid was
    # ignored during HTML export"), so the SI's references would be missing
    # from the Word file with nothing in the output saying so. `just docx`
    # converts each list with its own citeproc run and keeps both.
    if mode == "docx-html":
        from manuscript_sources import si_bibliography
        si = si_bibliography(root)
        if si and si["block"] is not None:
            raise ValueError(
                "the Supporting Information sets its own reference list, "
                "which Typst's HTML export discards -- this fallback route "
                "would ship a Word file missing every SI reference. Export "
                "with `just docx` (pandoc's Typst reader), which sets both "
                "lists.")
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

            run(sys.executable, str(root / "tools/render_stats.py"))
            # Discover actual inputs before capturing them, including dynamic
            # image/data paths. This probe is never published as the final PDF.
            run("typst", "compile", "--deps", str(depfile), "paper.typ", str(Path(tmp) / "probe.pdf"))
            dependencies = json.loads(depfile.read_text())["inputs"]
            after = snapshot(root, dependencies)
            write_text(root / ".build-state" / f"{output}.deps.json", json.dumps(dependencies))
            if before == after:
                folder = Path(tmp) / "manuscript"
                manifest = prepare_snapshot(root, folder, before, dependencies)
                if mode in ("paper", "resolve"):
                    shutil.copyfile(folder / "paper.pdf", staged)
                elif mode == "docx":
                    run(sys.executable, str(root / "tools/export_docx.py"),
                        "--root", str(folder), "--source", str(folder / "paper.word.typ"),
                        "--output", str(staged))
                else:
                    target = folder / "paper.html"
                    run("typst", "compile", "--root", str(folder), "--features", "html",
                        "--input", "docx=true", "-f", "html", str(folder / "paper.typ"), str(target))
                    run(sys.executable, str(root / "tools/typst2docx.py"), str(target), str(staged))
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


def check(root: Path = ROOT) -> list[dict]:
    out = []
    for output, recipe in (("paper.pdf", "just paper"), ("paper.docx", "just docx")):
        status = "current"
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
                elif digest(root / output) != state["output_hash"]:
                    status = "replaced"
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            status = "unknown"
        out.append({"output": output, "status": status, "command": recipe})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("paper", "resolve", "docx", "docx-html", "check", "stamp"))
    args = parser.parse_args()
    try:
        if args.command == "stamp":
            print(hashlib.sha256(json.dumps(snapshot(ROOT), sort_keys=True).encode()).hexdigest())
            return 0
        if args.command != "check":
            return build(args.command)
        rows = check()
        for row in rows:
            if row["status"] != "current":
                print(f"{row['status'].upper()}: {row['output']} -- rebuild: {row['command']}")
        if all(row["status"] == "current" for row in rows):
            print("paper.pdf and paper.docx are current with the source")
            return 0
        return 1
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
