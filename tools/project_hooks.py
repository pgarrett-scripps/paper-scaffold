"""Project-owned extension hooks, declared in project.toml.

The scaffold owns the justfile, tools/ and tests/; a paper that needs one
more gate stage, a Word touch-up or an extra source file used to get it by
editing those files, and every upgrade then had to merge the edit back in by
hand. project.toml is the paper's file instead: the scaffold reads it and
never writes it, and `just upgrade-plan` never offers to replace it.

Every hook is opt-in. With no project.toml, every function here returns the
empty answer and every recipe behaves exactly as it did before the file
existed. docs/hooks.md is the reference; this is the reader.

    uv run python tools/project_hooks.py show            # what is declared
    uv run python tools/project_hooks.py stages verify   # run one gate's stages
    uv run python tools/project_hooks.py bib-audit-args  # preflight's flags
    uv run python tools/project_hooks.py typst-sources   # for fmt / fmt-check
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:            # Python 3.10
    import tomli as tomllib            # type: ignore

from paths import ROOT  # the manuscript (tools/paths.py)

FILE = "project.toml"
# Where each gate's project stages run:
#   verify     -- at the end of `just verify`, after the scaffold's stages
#   check      -- at the end of `just check` (so also inside verify)
#   preflight  -- at the end of `just preflight`, before its verdict
#   submission -- after the upload set, in `just submission` and `just all`
GATES = ("verify", "check", "preflight", "submission")
STAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.:/+-]*")


@dataclass(frozen=True)
class Stage:
    name: str
    run: str


@dataclass(frozen=True)
class Word:
    """[word]: the paper's steps in the Word export (tools/export_docx.py).

    lua_filters        pandoc Lua filters on the final conversion to .docx
    before_pagination  Python scripts run on the written .docx, before the
                       scaffold's pagination pass (keep-with-next, repeated
                       table headers)
    after_pagination   Python scripts run after it; property order is
                       restored afterwards, so a script may append freely
    inputs             other files those steps read (a helper module, a
                       table of widths), so they are hashed and captured too
    style              [word.style]: the generated reference document's
                       settings (tools/paper_word_reference.py) and the
                       table_* keys tools/word_tables.py applies
    tables             [word.tables."tbl:x"]: one table's column widths,
                       type size and header rows (tools/word_tables.py)
    reference          a hand-made reference .docx used instead; exclusive
                       with `style`
    """
    lua_filters: tuple[str, ...] = ()
    before_pagination: tuple[str, ...] = ()
    after_pagination: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    style: dict = field(default_factory=dict)
    reference: str | None = None
    tables: dict = field(default_factory=dict)

    def files(self) -> tuple[str, ...]:
        return (self.lua_filters + self.before_pagination
                + self.after_pagination + self.inputs
                + ((self.reference,) if self.reference else ()))


# [word.style]: each key, its check, and what it means. Every key is
# optional; one left out keeps the stock reference document's value
# (tools/paper_word_reference.py applies them). docs/word-export.md.
HEX = re.compile(r"[0-9A-Fa-f]{6}")
LENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*(in|cm|mm|pt)")
TWIPS_PER = {"in": 1440, "cm": 1440 / 2.54, "mm": 144 / 2.54, "pt": 20}


def length_twips(value: str) -> int:
    """'1in', '2.5cm', '25mm' or '72pt' in twentieths of a point."""
    m = LENGTH.fullmatch(value.strip())
    if not m:
        raise ValueError(value)
    return round(float(m.group(1)) * TWIPS_PER[m.group(2)])


def _number(low: float, high: float, step: float):
    def check(v):
        return (type(v) in (int, float) and low <= v <= high
                and abs(v / step - round(v / step)) < 1e-9)
    return check, f"a number from {low:g} to {high:g} in steps of {step:g}"


STYLE_KEYS = {
    "font": (lambda v: isinstance(v, str) and 0 < len(v.strip()) <= 64,
             "a font family name"),
    "font_size": _number(6, 36, 0.5),
    "line_spacing": _number(1, 3, 0.05),
    "margins": (lambda v: isinstance(v, str) and LENGTH.fullmatch(v.strip()) is not None
                and 0 < length_twips(v) <= 3 * 1440,
                'a length up to 3in, such as "1in", "2.5cm", "25mm" or "72pt"'),
    "title_size": _number(8, 72, 0.5),
    "title_align": (lambda v: v in ("left", "center"), '"left" or "center"'),
    "title_color": (lambda v: isinstance(v, str) and HEX.fullmatch(v) is not None,
                    'six hex digits, such as "000000"'),
    "heading_color": (lambda v: isinstance(v, str) and HEX.fullmatch(v) is not None,
                      'six hex digits, such as "000000"'),
    "title_bold": (lambda v: type(v) is bool, "true or false"),
    "page_numbers": (lambda v: type(v) is bool, "true or false"),
    # Tables: applied to the written .docx (tools/word_tables.py), not the
    # reference, so they also work beside a hand-made `reference`.
    "table_font_size": _number(5, 14, 0.5),
    "table_header_bold": (lambda v: type(v) is bool, "true or false"),
    "table_header_shading": (lambda v: isinstance(v, str) and HEX.fullmatch(v) is not None,
                             'six hex digits, such as "F2F2F2"'),
    "table_borders": (lambda v: v in ("booktabs", "grid", "none"),
                      '"booktabs", "grid" or "none"'),
    "table_layout": (lambda v: v in ("auto", "fixed"), '"auto" or "fixed"'),
    "table_cell_margin": (lambda v: isinstance(v, str) and LENGTH.fullmatch(v.strip()) is not None
                          and length_twips(v) <= 720,
                          'a length up to 0.5in, such as "0.04in" or "3pt"'),
    "table_compact": (lambda v: type(v) is bool, "true or false"),
    "table_valign": (lambda v: v in ("top", "center", "bottom"),
                     '"top", "center" or "bottom"'),
    "table_unnest": (lambda v: type(v) is bool, "true or false"),
}
# The keys word_tables.py applies after conversion; the rest shape the
# generated reference document.
TABLE_STYLE_KEYS = frozenset(k for k in STYLE_KEYS if k.startswith("table_"))
HEX_KEYS = ("title_color", "heading_color", "table_header_shading")
TABLE_KEYS = {
    "widths": (lambda v: isinstance(v, list) and 0 < len(v) <= 40
               and all(type(x) in (int, float) and x > 0 for x in v),
               "a list of positive relative column widths, such as [3, 1, 1]"),
    "font_size": _number(5, 14, 0.5),
    "header_rows": (lambda v: type(v) is int and 0 <= v <= 10, "a whole number from 0 to 10"),
}
TABLE_LABEL = re.compile(r"(tbl|tab)[:.][A-Za-z0-9_.:-]+")


def _style(value, where: str) -> dict:
    keys(value, set(STYLE_KEYS), where)
    out = {}
    for key, v in value.items():
        check, expected = STYLE_KEYS[key]
        if (isinstance(v, bool) and expected != "true or false") or not check(v):
            raise ValueError(f"{where}: {key} must be {expected}, got {v!r}")
        out[key] = v.strip().upper() if key in HEX_KEYS else (
            v.strip() if isinstance(v, str) else v)
    return out


def _tables(value, where: str) -> dict:
    """[word.tables."tbl:x"]: one table's widths, font_size, header_rows.
    A label written tbl.x (the assets.json id) is the same table."""
    if not isinstance(value, dict):
        raise ValueError(f"{where}: expected tables keyed by label, such as [word.tables.\"tbl:x\"]")
    out = {}
    for label, spec in value.items():
        if not TABLE_LABEL.fullmatch(label):
            raise ValueError(f"{where}: {label!r} is not a table label such as \"tbl:x\"")
        here = f"{where}.{label}"
        keys(spec, set(TABLE_KEYS), here)
        for key, v in spec.items():
            check, expected = TABLE_KEYS[key]
            if isinstance(v, bool) or not check(v):
                raise ValueError(f"{here}: {key} must be {expected}, got {v!r}")
        name = label[:3] + ":" + label[4:]
        if name in out:
            raise ValueError(f"{where}: {name} is declared twice")
        out[name] = dict(spec)
    return out


@dataclass(frozen=True)
class Project:
    stages: dict[str, tuple[Stage, ...]] = field(
        default_factory=lambda: {g: () for g in GATES})
    bib_audit_require_complete: bool = True
    typst_sources: tuple[str, ...] = ()
    word: Word = field(default_factory=lambda: Word())
    single_bibliography: bool = False
    # [slides] theme: the paper's own deck theme. `paper sync` then never
    # writes slides/theme.typ and lists this file under the lock's overrides.
    slides_theme: str | None = None
    declared: bool = False


def keys(data, allowed: set[str], where: str) -> None:
    # Standalone on purpose: a captured build carries this file among its
    # tools (tools/build_state.py BUILD_TOOLS), and nothing it imports.
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError(f"{where}: expected only {', '.join(sorted(allowed))}")


def _stages(value, where: str) -> tuple[Stage, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{where}: expected a list of {{name, run}} tables")
    out, seen = [], set()
    for i, item in enumerate(value):
        here = f"{where}[{i}]"
        keys(item, {"name", "run"}, here)
        name, run = item.get("name"), item.get("run")
        if not isinstance(name, str) or not STAGE_NAME.fullmatch(name):
            raise ValueError(f"{here}: name must be a short label, got {name!r}")
        if name in seen:
            raise ValueError(f"{here}: stage {name!r} is declared twice")
        if not isinstance(run, str) or not run.strip():
            raise ValueError(f"{here}: run must be a nonempty shell command")
        seen.add(name)
        out.append(Stage(name, run))
    return tuple(out)


def load(root: Path = ROOT) -> Project:
    """project.toml, validated; the empty Project when there is none.

    Unknown keys are an error, not ignored: a misspelt `[stages.verfiy]`
    that silently ran nothing would be a gate that never fails.
    """
    path = root / FILE
    if not path.is_file():
        return Project()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{FILE}: {exc}") from None
    keys(data, {"schema_version", "stages", "preflight", "sources", "word",
                "bibliography", "slides"}, FILE)
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError(f"{FILE}: schema_version must be 1")

    stages = {g: () for g in GATES}
    table = data.get("stages", {})
    keys(table, set(GATES), f"{FILE} [stages]")
    for gate, value in table.items():
        stages[gate] = _stages(value, f"{FILE} stages.{gate}")

    preflight = data.get("preflight", {})
    keys(preflight, {"bib_audit_require_complete"}, f"{FILE} [preflight]")
    complete = preflight.get("bib_audit_require_complete", True)
    if not isinstance(complete, bool):
        raise ValueError(f"{FILE} [preflight]: bib_audit_require_complete must be true or false")

    sources = data.get("sources", {})
    keys(sources, {"typst"}, f"{FILE} [sources]")
    typst = _paths(sources.get("typst", []), f"{FILE} sources.typst", (".typ",))

    table = data.get("word", {})
    keys(table, {"lua_filters", "before_pagination", "after_pagination", "inputs",
                 "style", "reference", "tables"}, f"{FILE} [word]")
    style = _style(table.get("style", {}), f"{FILE} [word.style]")
    tables = _tables(table.get("tables", {}), f"{FILE} [word.tables]")
    reference = None
    if "reference" in table:
        if set(style) - TABLE_STYLE_KEYS:
            raise ValueError(f"{FILE} [word]: reference and [word.style] are "
                             "exclusive (the table_* keys aside); a hand-made reference "
                             "carries its own styles")
        reference = _paths([table["reference"]], f"{FILE} word.reference", (".docx",))[0]
    word = Word(
        lua_filters=_paths(table.get("lua_filters", []), f"{FILE} word.lua_filters", (".lua",)),
        before_pagination=_paths(table.get("before_pagination", []),
                                 f"{FILE} word.before_pagination", (".py",)),
        after_pagination=_paths(table.get("after_pagination", []),
                                f"{FILE} word.after_pagination", (".py",)),
        inputs=_paths(table.get("inputs", []), f"{FILE} word.inputs", None),
        style=style, reference=reference, tables=tables)

    table = data.get("bibliography", {})
    keys(table, {"single"}, f"{FILE} [bibliography]")
    single = table.get("single", False)
    if not isinstance(single, bool):
        raise ValueError(f"{FILE} [bibliography]: single must be true or false")

    table = data.get("slides", {})
    keys(table, {"theme"}, f"{FILE} [slides]")
    theme = None
    if "theme" in table:
        theme = _paths([table["theme"]], f"{FILE} slides.theme", (".typ",))[0]
        if not theme.startswith("slides/"):
            raise ValueError(f"{FILE} [slides]: theme must be a file under "
                             f"slides/, got {theme!r}")

    return Project(stages=stages, bib_audit_require_complete=complete,
                   typst_sources=typst, word=word, single_bibliography=single,
                   slides_theme=theme, declared=True)


def _paths(value, where: str, suffixes: tuple[str, ...] | None) -> tuple[str, ...]:
    """Project-relative file paths with one of `suffixes` (any when None),
    in order, once each."""
    if not isinstance(value, list):
        raise ValueError(f"{where}: expected a list of project-relative paths")
    out: list[str] = []
    for item in value:
        path = Path(item) if isinstance(item, str) and item else None
        if (path is None or path.is_absolute() or ".." in path.parts
                or (suffixes is not None and path.suffix not in suffixes)):
            kind = f"{' or '.join(suffixes)} " if suffixes else ""
            raise ValueError(f"{where}: expected a project-relative "
                             f"{kind}path, got {item!r}")
        if path.as_posix() not in out:
            out.append(path.as_posix())
    return tuple(out)


def typst_sources(root: Path = ROOT, defaults: tuple[str, ...] = (),
                  project: Project | None = None) -> list[str]:
    """The hand-written Typst sources: the justfile's list, then the paper's.

    A default that does not exist is skipped (the cover letter is optional);
    a file the paper DECLARED and that does not exist is an error, since the
    likeliest cause is a typo that would otherwise go unformatted and
    unchecked for good.
    """
    project = project or load(root)
    missing = [p for p in project.typst_sources if not (root / p).is_file()]
    if missing:
        raise ValueError(f"{FILE} sources.typst names missing file(s): "
                         + ", ".join(missing))
    out = [d for d in defaults if (root / d).is_file()]
    return out + [p for p in project.typst_sources if p not in out]


def build_inputs(root: Path = ROOT) -> list[str]:
    """What the paper adds to the PDF and Word builds' inputs.

    project.toml itself (it steers the Word export, as the justfile steers
    the build) and every file its [word] table names. tools/build_state.py
    hashes these into the staleness record and captures them with the
    manuscript, so a changed Word step marks paper.docx stale and a captured
    build converts the way it was built. A missing one is an error here, not
    at the end of a long build.

    So is a word/paper-reference.docx nothing declares: before 3.27.0 the
    export read that file, and one left behind would otherwise stop styling
    the Word file without a word.
    """
    project = load(root)
    legacy = "word/paper-reference.docx"
    if (root / legacy).is_file() and project.word.reference != legacy:
        raise ValueError(
            f"{legacy} is no longer read (scaffold 3.27.0): delete it if it is "
            "the stock file, else move its settings to [word.style] "
            "(uv run paper tool paper_word_reference --translate "
            f"{legacy}), or declare [word] reference = \"{legacy}\"")
    if not (root / FILE).is_file():
        return []
    missing = [p for p in project.word.files() if not (root / p).is_file()]
    if missing:
        raise ValueError(f"{FILE} [word] names missing file(s): " + ", ".join(missing))
    return [FILE, *project.word.files()]


def run_word_steps(steps: tuple[str, ...], docx: Path, root: Path, tools: Path) -> None:
    """Run each [word] script as `python <script> <docx>`, editing it in place.

    The interpreter is the one running the export, so a step has the
    toolchain's packages; `tools/` is on its path, so it may import
    word_xml. It runs from the manuscript root (the captured copy during a
    build), with $PAPER_ROOT set to it. A failing step fails the export.
    """
    env = {**os.environ, "PAPER_ROOT": str(root),
           "PYTHONPATH": os.pathsep.join(filter(None, [str(tools), os.environ.get("PYTHONPATH")]))}
    for step in steps:
        done = subprocess.run([sys.executable, str(root / step), str(docx)],
                              cwd=root, env=env)
        if done.returncode:
            raise ValueError(f"{FILE} Word step {step} failed (exit {done.returncode})")


def run_stages(gate: str, root: Path = ROOT, project: Project | None = None) -> int:
    """Run one gate's project stages, every one even after a failure.

    Each prints under its own `=== name ===` header, the shape verify and
    preflight already use, so a failing project stage is named in the same
    place as a failing scaffold one. Nothing prints when nothing is declared.
    """
    project = project or load(root)
    rc = 0
    env = {**os.environ, "PAPER_ROOT": str(root)}
    for stage in project.stages[gate]:
        print(f"\n=== {stage.name} (project.toml) ===", flush=True)
        done = subprocess.run(["bash", "-c", stage.run], cwd=root, env=env)
        if done.returncode:
            print(f"project stage {stage.name!r} failed (exit {done.returncode}): {stage.run}")
            rc = 1
    return rc


def describe(project: Project) -> list[str]:
    if not project.declared:
        return [f"no {FILE}: no project hooks declared (see docs/hooks.md)"]
    lines = []
    for gate in GATES:
        for stage in project.stages[gate]:
            lines.append(f"stage      {gate:<10} {stage.name}: {stage.run}")
    for path in project.typst_sources:
        lines.append(f"source     typst      {path} (fmt, prose-check)")
    for kind in ("lua_filters", "before_pagination", "after_pagination", "inputs"):
        for path in getattr(project.word, kind):
            lines.append(f"word       {kind:<17} {path}")
    for key, value in project.word.style.items():
        lines.append(f"word       style.{key:<11} {value!r}")
    for label, spec in project.word.tables.items():
        lines.append(f"word       tables.{label} {spec!r}")
    if project.word.reference:
        lines.append(f"word       reference         {project.word.reference}")
    if project.single_bibliography:
        lines.append("bibliography one reference list; the SI cites @key (no @si- list)")
    if project.slides_theme:
        lines.append(f"slides     theme             {project.slides_theme} "
                     "(the paper's own; paper sync writes no slides/theme.typ)")
    if not project.bib_audit_require_complete:
        lines.append("preflight  bib-audit runs without --require-complete")
    return lines or [f"{FILE} declares no hooks"]


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="list the hooks project.toml declares")
    stages = sub.add_parser("stages", help="run one gate's project stages")
    stages.add_argument("gate", choices=GATES)
    sub.add_parser("bib-audit-args", help="the flags preflight passes bib-audit")
    sources = sub.add_parser("typst-sources",
                             help="the existing hand-written Typst sources, one per line")
    sources.add_argument("defaults", nargs="*", help="the justfile's typst_sources")
    args = parser.parse_args(argv)
    try:
        project = load(root)
    except (OSError, ValueError) as exc:
        if args.command == "stages":
            # Inside verify/preflight: name the failure where it is read.
            print(f"\n=== {FILE} ===", flush=True)
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.command == "show":
        print("\n".join(describe(project)))
        return 0
    if args.command == "typst-sources":
        try:
            print("\n".join(typst_sources(root, tuple(args.defaults), project)))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "bib-audit-args":
        print("--require-complete" if project.bib_audit_require_complete else "")
        return 0
    return run_stages(args.gate, root, project)


if __name__ == "__main__":
    raise SystemExit(main())
