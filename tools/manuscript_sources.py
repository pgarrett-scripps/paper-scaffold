"""Locate literal includes/imports and helper uses without reading raw examples.

This is a source index, not a Typst evaluator. Dynamic paths and computed IDs
cannot be inferred; callers must report that limit instead of guessing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from paths import ROOT  # the manuscript (tools/paths.py)
ENTRYPOINTS = ("paper.typ", "config.typ", "si-body.typ")

# Slide decks. A deck is a .typ file directly under slides/; theme.typ and any
# `_`-prefixed file are shared includes, reached THROUGH a deck and never built
# as one. The glob is the manifest on purpose: a list of decks in a config file
# is a second place to update and therefore a place to drift.
SLIDES = "slides"
CALL = re.compile(r'(?<![\w-])#?(s|n|ci|fig|tbl)\(\s*"([^"\n]+)"')
DEPENDENCY = re.compile(r'#(?:include|import)\s+"([^"\n]+)"')

# The Supporting Information's own reference list. Typst allows exactly one
# native #bibliography per document ("multiple bibliographies are not yet
# supported"), so a manuscript whose SI ships as a separate file sets the SI
# list with Alexandria instead: a `#show: alexandria(prefix: "si-", ...)` in
# paper.typ, and a matching `#bibliographyx(..., prefix: "si-")` in si-body.typ.
#
# Both prefixes are read from the source as STRING LITERALS, not evaluated. A
# manuscript that computes either one from a variable is not supported here and
# reads as "no SI bibliography"; the two literals sitting next to their calls is
# what lets a text-only tool -- this index, prose_check, the resolver -- see the
# arrangement at all.
ALEXANDRIA_SHOW = re.compile(r'#show:\s*alexandria\(\s*prefix:\s*"([^"\n]*)"')
BIBLIOGRAPHYX = "#bibliographyx("
BIBLIOGRAPHY = "#bibliography("


def mask(src: str, *, strings: bool = False) -> str:
    """Blank comments/raw spans (and optionally strings), preserving offsets."""
    out = list(src)
    i = 0
    while i < len(src):
        start = i
        if src.startswith("//", i):
            end = src.find("\n", i)
            i = len(src) if end < 0 else end
        elif src.startswith("/*", i):
            depth, i = 1, i + 2
            while i < len(src) and depth:
                if src.startswith("/*", i):
                    depth += 1; i += 2
                elif src.startswith("*/", i):
                    depth -= 1; i += 2
                else:
                    i += 1
        elif src[i] == "`":
            fence = re.match(r"`+", src[i:]).group()
            end = src.find(fence, i + len(fence))
            i = len(src) if end < 0 else end + len(fence)
        elif src[i] == '"':
            i += 1
            while i < len(src):
                if src[i] == "\\":
                    i += 2
                elif src[i] == '"':
                    i += 1; break
                else:
                    i += 1
            if not strings:
                continue
        elif src[i] == "\\":
            i += 2
        else:
            i += 1
            continue
        out[start:i] = ["\n" if c == "\n" else " " for c in src[start:i]]
    return "".join(out)


def call_span(src: str, opener: str, *, start: int = 0) -> tuple[int, int] | None:
    """(start, end) of `opener ... )` with balanced parens, or None.

    Commented-out and quoted occurrences are skipped: the opener is located in
    the masked source, so `// #bibliography(...)` in a note is not the call.
    Parentheses are then balanced over the masked text too, so a `")"` inside a
    string argument cannot close the call early.
    """
    code = mask(src, strings=True)
    at = code.find(opener, start)
    if at < 0:
        return None
    depth = 0
    for i in range(at + len(opener) - 1, len(src)):
        if code[i] == "(":
            depth += 1
        elif code[i] == ")":
            depth -= 1
            if depth == 0:
                return at, i + 1
    return None


def _string_args(call: str, suffixes: tuple[str, ...]) -> list[str]:
    return [a.lstrip("/") for a in re.findall(r'"([^"\n]+)"', call)
            if a.endswith(suffixes)]


def si_bibliography(root: Path = ROOT, sources: dict[str, str] | None = None) -> dict | None:
    """The SI's own reference list, as the sources declare it, or None.

    Returns the prefix paper.typ routes to Alexandria, alongside whatever
    si-body.typ's #bibliographyx call says. The two are reported separately
    and deliberately NOT reconciled here: disagreeing prefixes is a real
    manuscript defect, and `just prose-check` names it. Typst also refuses to
    compile it, but with a message pointing inside the Alexandria package.

    A manuscript with no SI list -- the scaffold's default until one is added
    -- returns None, and every caller then behaves exactly as it did before
    this existed.
    """
    def read(name: str) -> str:
        if sources is not None:
            return sources.get(name, "")
        path = root / name
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    paper, si = read("paper.typ"), read("si-body.typ")
    m = ALEXANDRIA_SHOW.search(mask(paper))
    span = call_span(si, BIBLIOGRAPHYX)
    if m is None and span is None:
        return None
    out = {"prefix": m.group(1) if m else None, "file": "si-body.typ",
           "call": None, "span": None, "block": None, "list_prefix": None,
           "paths": [], "style": None}
    if span is not None:
        call = si[span[0]:span[1]]
        prefix = re.search(r'prefix:\s*"([^"\n]*)"', call)
        style = re.search(r'style:\s*"([^"\n]*)"', call)
        out.update(call=call, span=span, block=_bibliography_block(si, span),
                   list_prefix=prefix.group(1) if prefix else None,
                   paths=_string_args(call, (".bib", ".yml", ".yaml", ".json")),
                   style=style.group(1) if style else None)
    return out


def without_si_bibliography(si_src: str, paper_src: str = "", *,
                            replacement: str = "") -> str:
    """si-body.typ with its Alexandria reference list taken out of the way.

    Two tools need this and neither can use Alexandria's output: the Word
    projection, which replaces the call with the plain #bibliography pandoc
    understands, and the plain-text review copy, which omits reference lists
    outright. Both also need the "si-" prefix off the SI's citations -- it is
    Alexandria's routing tag, not part of any key in the .bib -- because
    without the list to route to, a prefixed citation resolves to nothing.

    Returns the source unchanged when there is no SI bibliography.
    """
    si = si_bibliography(sources={"paper.typ": paper_src, "si-body.typ": si_src})
    if si is None or si["block"] is None:
        return si_src
    start, end = si["block"]
    out = si_src[:start] + replacement + si_src[end:]
    prefix = si["prefix"] or si["list_prefix"]
    if prefix:
        out = re.sub(r"(?<![\w\\:./-])@" + re.escape(prefix)
                     + r"([A-Za-z0-9_-]+)", r"@\1", out)
    return out


def si_citations(si_src: str, prefix: str) -> list[str]:
    """The keys si_src cites through the SI list's prefix, in order.

    `@si-key` and `#cite(<si-key>)` both count; comments, strings and raw
    text do not. The template's `bibliographyx` prints nothing -- not even
    its heading -- when this is empty, and the Word projection has to drop
    the list by the same rule, or the SI docx ends on a bare "References".
    """
    if not prefix:
        return []
    code = mask(si_src, strings=True)
    key = re.escape(prefix) + r"[A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*"
    return [m.group(1) or m.group(2) for m in re.finditer(
        r"(?<![\w\\:./-])@(" + key + r")|\bcite\(\s*<(" + key + r")>", code)]


def _bibliography_block(si: str, span: tuple[int, int]) -> tuple[int, int]:
    """The call plus the layout wrapped around it: `#set` line, and label.

    The whole arrangement is one unit to every tool that removes or rewrites
    the list -- the Word projection, the review text -- because a `#set
    heading(numbering: none)` left behind with no list under it silences the
    numbering of whatever follows, and an orphaned label reaches the
    converter as stray markup.
    """
    start, end = span
    tail = re.match(r"[ \t]*<[A-Za-z0-9_:.-]+>", si[end:])
    if tail:
        end += tail.end()
    head = re.search(r"\n#set heading\([^\n]*\)\n\s*$", si[:start])
    if head:
        start = head.start() + 1
    return start, end


def matches(pattern, src: str):
    visible = mask(src)
    code = mask(src, strings=True)
    return [m for m in pattern.finditer(visible) if code[m.start():m.start()+1].strip()]


def source_files(root: Path = ROOT, entrypoints=None) -> dict[str, str]:
    if entrypoints is None:
        if (root / "manuscript.toml").is_file():
            from document_project import load_project
            entrypoints = tuple(d.entrypoint for d in load_project(root).documents.values())
        else:
            entrypoints = ENTRYPOINTS
    found = {}
    active = set()
    manifest: list[dict] = []

    def tables() -> dict:
        if not manifest:
            try:
                values = json.loads((root / "assets.json").read_text(encoding="utf-8"))["values"]
            except (OSError, ValueError, KeyError, TypeError):
                values = {}
            manifest.append(values if isinstance(values, dict) else {})
        return manifest[0]

    def visit(path: Path):
        path = path.resolve()
        if path in active:
            raise ValueError(f"cyclic manuscript include/import: {path}")
        try:
            name = path.relative_to(root.resolve()).as_posix()
        except ValueError:
            raise ValueError(f"manuscript source is outside the project: {path}") from None
        if name in found:
            return
        if not path.is_file():
            raise ValueError(f"missing manuscript source: {name}")
        active.add(path)
        src = path.read_text(encoding="utf-8")
        found[name] = src
        for m in matches(DEPENDENCY, src):
            target = m.group(1)
            if target.startswith("@") or not target.endswith(".typ"):
                continue
            visit(root / target.lstrip("/") if target.startswith("/")
                  else path.parent / target)
        # A generated table is a source too: `tbl("id")` includes the file
        # assets.json names, and that file calls `#s()` for its own numbers.
        # Without following it, those ids read as unused to check-stats and
        # trace, and a regenerated table did not mark the PDF stale. Only a
        # table that exists is followed; a missing or malformed declaration is
        # check-assets' error to report, not a reason for the index to fail.
        for m in matches(CALL, src):
            if m.group(1) != "tbl":
                continue
            row = tables().get(m.group(2))
            if not isinstance(row, dict):
                continue
            target = root / str(row.get("path", ""))
            if row.get("kind") == "table" and target.suffix == ".typ" and target.is_file():
                visit(target)
        active.remove(path)

    for name in entrypoints:
        if (root / name).is_file():
            visit(root / name)
    return found


# The two shared files in slides/ that are not decks: every deck imports the
# theme, and the theme imports the talks' identity. Naming them here is what
# stops `just slides` from trying to compile either one as a talk. A partial a
# project adds itself is named with a leading underscore.
SLIDE_SHARED = ("theme.typ", "config.typ")


def slide_targets(root: Path = ROOT) -> tuple[str, ...]:
    """Every buildable deck name under slides/, sorted."""
    folder = root / SLIDES
    if not folder.is_dir():
        return ()
    # A theme project.toml declares ([slides] theme) is shared, not a deck.
    try:
        from project_hooks import load
        own = load(root).slides_theme
    except (OSError, ValueError):
        own = None
    return tuple(sorted(p.stem for p in folder.glob("*.typ")
                        if p.name not in SLIDE_SHARED
                        and not p.name.startswith("_")
                        and f"{SLIDES}/{p.name}" != own))


def slide_files(root: Path = ROOT, *, strict: bool = True) -> dict[str, str]:
    """The decks and everything they literally import.

    SEPARATE FROM source_files() ON PURPOSE, and the separation is the whole
    design. build_state.snapshot() fingerprints source_files(), so a deck that
    entered there would mark paper.pdf and paper.docx stale on every slide
    edit -- and decks are outside that gate by decision. A deck is allowed to
    READ a declared id; it is not part of the paper.

    strict=False skips a deck whose imports are broken, which is what usages()
    passes: a half-written talk must not be able to turn `just verify` red
    through the id index. `just slides-check` passes strict=True, so the same
    breakage is reported where it can be acted on.
    """
    out: dict[str, str] = {}
    for name in slide_targets(root):
        try:
            out.update(source_files(root, entrypoints=(f"{SLIDES}/{name}.typ",)))
        except ValueError:
            if strict:
                raise
    return out


def usages(root: Path = ROOT, *, slides: bool = True) -> list[dict]:
    out = []
    # Decks are included by default: a number restated on a slide is still in
    # use, and an asset a talk shows is not an orphan. See slide_files() for
    # why this is the only index that widens.
    sources = dict(source_files(root))
    if slides:
        sources.update(slide_files(root, strict=False))
    for path, src in sources.items():
        for m in matches(CALL, src):
            line = src.count("\n", 0, m.start()) + 1
            start = src.rfind("\n", 0, m.start()) + 1
            closing = src.find(")", m.end())
            end = src.find("\n", closing if closing >= 0 else m.end())
            context = " ".join(src[start:end if end >= 0 else len(src)].split())
            out.append({"id": m.group(2), "helper": m.group(1), "path": path,
                        "line": line, "context": context})
    return out
