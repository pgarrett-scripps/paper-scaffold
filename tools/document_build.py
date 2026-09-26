"""Native PDF builds with independent, content-based state for each document.

No Word adaptation is involved. Only a stable successful build replaces the
last good PDF. Counts are queried from a temporary instrumented source tree.
The compile, the count query and readability scoring run concurrently.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from atomic_io import write_text
from build_state import build_lock, digest
from document_project import Project, Document, body_span
import readability
import typst_prose

TOOLS = ("document_project.py", "document_build.py", "documents.py",
         "document_check.py", "manuscript_sources.py", "readability.py",
         "typst_prose.py", "prose_rules.py", "render_stats.py", "atomic_io.py", "build_state.py")


def state_path(project: Project, document: Document) -> Path:
    return project.root / ".build-state" / "documents" / f"{document.id}.json"


def fingerprint(project: Project, document: Document, dependencies=()) -> dict:
    root = project.root
    files = set(project.sources(document))
    files.update(("pyproject.toml", "uv.lock", "stats.json", "assets.json", "prose-check.toml"))
    files.update(f"tools/{name}" for name in TOOLS)
    files.update(dependencies)
    for name in document.parts:
        bib = project.parts[name].bibliography
        if bib:
            files.add(bib)
    # Hash the selected configuration, so a chapter B-only manifest change
    # does not invalidate chapter A. The full project is validated on load.
    # A part's upstream record (tools/port.py) does not change the PDF.
    config = {"document": vars(document),
              "parts": [{k: v for k, v in vars(project.parts[p]).items() if k != "upstream"}
                        for p in document.parts]}
    result = {"@document": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()}
    # --root may point at another manuscript. Fingerprint the executing tools,
    # not just a possibly older copy installed in that manuscript.
    for name in TOOLS:
        result[f"@tool/{name}"] = digest(Path(__file__).parent / name)
    for name in sorted(files):
        path = root / name
        result[name] = digest(path) if path.is_file() else None
    return result


def compiler_dependencies(root: Path, path: Path) -> list[str]:
    data = json.loads(path.read_text())["inputs"]
    if not isinstance(data, list) or any(not isinstance(s, str) for s in data):
        raise ValueError("invalid compiler dependency list")
    out = []
    for item in data:
        resolved = (root / item).resolve()
        out.append(resolved.relative_to(root).as_posix()
                   if resolved.is_relative_to(root) else str(resolved))
    return sorted(set(out))


@contextmanager
def running(args: list[str], **kwargs):
    """A subprocess that is killed if the build stops before it is collected."""
    proc = subprocess.Popen(args, **kwargs)
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate()


def count_query(project: Project, document: Document, sources: dict, temporary: Path) -> list[str]:
    """Keep include scopes and layout, adding count metadata only in the copy.

    Returns the query command for the copy at temporary/counts, so the query
    can run alongside the real compile.
    """
    root = project.root
    captured = temporary / "counts"
    shutil.rmtree(captured, ignore_errors=True)
    captured.mkdir()
    for name, checksum in sources.items():
        if name.startswith("@") or checksum is None or Path(name).is_absolute():
            continue
        dest = captured / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, dest)
    for name in document.parts:
        part = project.parts[name]
        path = captured / part.source
        src = path.read_text()
        a, b = body_span(src, part.source)
        path.write_text(
            '#import "@preview/wordometer:0.1.4": word-count-of as scaffold-count\n'
            + src[:a] + '#let scaffold-counted-body = [\n' + src[a:b]
            + '\n]\n#scaffold-counted-body\n'
            + '#metadata((id: ' + json.dumps(name)
            + ', words: scaffold-count(scaffold-counted-body, '
              'exclude: (figure, raw.where(block: true))).words)) <scaffold-part-count>\n'
            + src[b:])
    return ["typst", "query", "--root", str(captured), str(captured / document.entrypoint),
            "<scaffold-part-count>", "--field", "value"]


def readability_scores(project: Project, document: Document) -> tuple[list[dict], dict]:
    """Per-part and combined readability, in manifest part order."""
    root = project.root
    saved = typst_prose.STATS_JSON
    typst_prose.STATS_JSON = root / "stats.json"
    try:
        from prose_rules import load_config
        cfg = load_config(root)
        readability.add_abbreviations(sorted(cfg.vocabulary("abbreviations", set())))
        prose = [readability.clean(project.prose(project.parts[name])) for name in document.parts]
        return ([readability.metrics(text) for text in prose],
                readability.metrics("\n\n".join(prose)))
    finally:
        typst_prose.STATS_JSON = saved


def metrics(document: Document, values: list, scores: tuple[list[dict], dict]) -> dict:
    if (len(values) != len(document.parts)
            or [v["id"] for v in values] != list(document.parts)):
        raise ValueError(f"{document.id}: counted parts differ from manifest order; "
                         "check duplicate, conditional, or reordered includes")
    parts, combined = scores
    return {"document": document.id,
            "parts": [{"id": v["id"], "words": v["words"], "readability": r}
                      for v, r in zip(values, parts)],
            "words": sum(v["words"] for v in values),
            "readability": combined,
            "scope": "BODY markers in declared parts; excludes front/back matter, "
                     "citations, floats/captions, math and block code; includes headings "
                     "and inline code. Readability excludes headings."}


def build(project: Project, document: Document) -> dict:
    root = project.root
    with build_lock(root), tempfile.TemporaryDirectory(dir=root / ".build-state") as tmp:
        from render_stats import render
        if (root / "stats.json").is_file():
            if render(root / "stats.json", root / "stats-rendered.json"):
                raise ValueError("statistics could not be rendered")
        temporary = Path(tmp)
        staged, deps = temporary / "output.pdf", temporary / "deps.json"
        statefile = state_path(project, document)
        dependencies = []
        if statefile.exists():
            try:
                dependencies = json.loads(statefile.read_text())["dependencies"]
                if not isinstance(dependencies, list) or any(not isinstance(p, str) for p in dependencies):
                    dependencies = []
            except (ValueError, KeyError, TypeError):
                pass
        # Dependency discovery is the only reason to retry. An edited existing
        # input aborts instead of blessing a mixture of source revisions.
        for attempt in range(2):
            before = fingerprint(project, document, dependencies)
            # The count copy is taken from the same sources the compile reads.
            # Both are covered by the fingerprint checks below, as is the
            # readability pass that runs while the two compilers work.
            with running(count_query(project, document, before, temporary),
                         cwd=temporary / "counts", text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE) as query, \
                 running(["typst", "compile", "--root", str(root), "--deps", str(deps),
                          document.entrypoint, str(staged)], cwd=root) as compiler:
                scores = readability_scores(project, document)
                if compiler.wait():
                    raise subprocess.CalledProcessError(compiler.returncode, compiler.args)
                if fingerprint(project, document, dependencies) != before:
                    raise ValueError("sources changed during build; last good output preserved")
                dependencies = compiler_dependencies(root, deps)
                after = fingerprint(project, document, dependencies)
                if before != after:
                    if attempt:
                        raise ValueError("compiler dependencies did not stabilize; rerun build")
                    continue
                counted, errors = query.communicate()
                if query.returncode:
                    raise subprocess.CalledProcessError(query.returncode, query.args, counted, errors)
            report = metrics(document, json.loads(counted), scores)
            # Re-read the manifest too: the Project object predates compilation.
            from document_project import load_project
            fresh = load_project(root)
            if fingerprint(fresh, fresh.documents[document.id], dependencies) != before:
                raise ValueError("sources changed during build; last good output preserved")
            from pdf_outline import open_with_outline
            open_with_outline(staged)  # before output_hash, so freshness sees it
            output = root / document.output
            output.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, output)
            write_text(statefile, json.dumps({
                "schema_version": 1, "sources": before, "dependencies": dependencies,
                "output": document.output, "output_hash": digest(output), "metrics": report,
            }, indent=2) + "\n")
            return report
    raise ValueError("build did not complete")


def status(project: Project, document: Document) -> str:
    output = project.root / document.output
    if not output.is_file():
        return "missing"
    try:
        state = json.loads(state_path(project, document).read_text())
        if state["schema_version"] != 1 or state["output"] != document.output:
            return "unknown"
        if fingerprint(project, document, state["dependencies"]) != state["sources"]:
            return "stale"
        if digest(output) != state["output_hash"]:
            return "replaced"
        return "current"
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return "unknown"


def saved_metrics(project: Project, document: Document) -> dict:
    current = status(project, document)
    if current != "current":
        raise ValueError(f"{document.id}: metrics are {current}; run just document {document.id}")
    return json.loads(state_path(project, document).read_text())["metrics"]
