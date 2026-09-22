#!/usr/bin/env python3
"""Hold the manuscript to a journal's author guidelines.

WHY THIS EXISTS. Every limit a journal sets already has a checker here with a
hole where the journal's number goes: word-limits.toml takes a max per section
scope, prose-check.toml takes a figure resolution floor, assets.json knows
every figure and table. What was missing is the number itself, which authors
carry in their heads, half-remember, and discover at submission. A profile
under journals/ carries the numbers WITH the URL they were read from and the
date, and journal.toml picks one. Nothing here is a parallel checker: the word
limits join `just check-words`, the resolution floor joins `just prose-check`,
and this tool checks the rest -- keywords, figure and table counts, and the
graphical abstract -- and prints the whole card on demand.

THE NUMBERS ARE NOT TRUSTED FROM MEMORY. A profile without `source`,
`guidelines-dated` and `checked` does not load. When a limit changes, re-read
the source, change the number, and move `checked`; the file's own header says
so. `just journals` lists what ships.

THE GRAPHICAL ABSTRACT is the one thing a profile changes about the OUTPUT
rather than the checks. ACS journals want it on the last page of the
manuscript, labeled "For Table of Contents Only"; an archive server wants it
under the abstract. journal.toml's [placement] says which layout each output
gets, and build_state.py passes that to the PDF compile (`--input toc=...`)
and to the Word projection. The PDF defaults to the preprint layout and the
Word file to the journal's, because that is where each one goes.

Usage (via `just journal`, `just check-journal`, `just journals`):
    uv run python tools/journal.py report [--json]
    uv run python tools/journal.py check [--json]
    uv run python tools/journal.py list
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from document_project import keys as _keys, tomllib  # noqa: E402

CONFIG = "journal.toml"
PROFILES = "journals"
PLACEMENTS = ("preprint", "journal", "none")
DEFAULT_PLACEMENT = {"pdf": "preprint", "docx": "journal"}
# Section roles a profile may name. journal.toml maps each to a section path
# of the manuscript at hand, because "the experimental section" is called
# Methods in one paper and Experimental Procedures in the next.
ROLES = ("methods",)
# Regions the word counter can add to the main text when a journal's limit
# covers them. "references" is the main text's reference list as citeproc
# sets it for the Word file -- see reference_words().
COUNTABLE = ("abstract", "si", "references")

PROFILE_KEYS = {"schema_version", "label", "journal", "type", "source",
                "guidelines-dated", "checked", "words", "floats", "figures",
                "graphical-abstract", "notes"}
WORD_KEYS = {"main-max", "counts", "excludes", "abstract-max", "keywords-max"}
FLOAT_KEYS = {"figures-max", "tables-max", "figures-and-tables-max"}
FIGURE_KEYS = {"min-dpi"}
GRAPHIC_KEYS = {"required", "width-in", "height-in", "min-dpi", "label",
                "source", "guidelines-dated"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class JournalError(ValueError):
    """A profile or journal.toml that cannot be trusted as written."""


def keys(data, allowed: set[str], where: str) -> None:
    """document_project.keys, raised as this tool's own error."""
    try:
        _keys(data, allowed, where)
    except ValueError as e:
        raise JournalError(str(e)) from None


@dataclass
class Profile:
    id: str
    label: str
    journal: str
    type: str
    source: str
    guidelines_dated: str
    checked: str
    words: dict = field(default_factory=dict)
    floats: dict = field(default_factory=dict)
    figures: dict = field(default_factory=dict)
    graphic: dict = field(default_factory=dict)
    notes: dict = field(default_factory=dict)


@dataclass
class Finding:
    level: str      # "error" | "warn" | "note"
    subject: str
    message: str


# ---------------------------------------------------------------- loading ---

def _positive(table: dict, key: str, where: str, *, number=False) -> None:
    if key not in table:
        return
    v = table[key]
    ok = (isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0) if number \
        else (type(v) is int and v > 0)
    if not ok:
        raise JournalError(f"{where}: {key} must be a positive "
                           f"{'number' if number else 'integer'}, got {v!r}")


def available(root: Path = ROOT) -> list[str]:
    folder = root / PROFILES
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.toml"))


def load_profile(root: Path, id: str) -> Profile:
    path = root / PROFILES / f"{id}.toml"
    if not path.is_file():
        known = ", ".join(available(root)) or "none"
        raise JournalError(f"{CONFIG}: no profile {id!r} under {PROFILES}/ "
                           f"(available: {known})")
    where = f"{PROFILES}/{id}.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise JournalError(f"{where}: not valid TOML: {e}") from None
    keys(data, PROFILE_KEYS, where)
    if data.get("schema_version") != 1 or type(data.get("schema_version")) is not int:
        raise JournalError(f"{where}: schema_version must be 1")
    for k in ("label", "journal", "type", "source", "guidelines-dated", "checked"):
        if not isinstance(data.get(k), str) or not data[k].strip():
            raise JournalError(
                f"{where}: {k} is required. A limit with no source and no date "
                f"is a number someone remembered; say where it was read and when.")
    for k in ("guidelines-dated", "checked"):
        if not DATE.match(data[k]):
            raise JournalError(f"{where}: {k} must be a YYYY-MM-DD date, got {data[k]!r}")
    if not data["source"].startswith(("http://", "https://")):
        raise JournalError(f"{where}: source must be a URL, got {data['source']!r}")

    words = data.get("words", {})
    keys(words, WORD_KEYS, f"{where} [words]")
    for k in ("main-max", "abstract-max", "keywords-max"):
        _positive(words, k, where)
    for k in ("counts", "excludes"):
        v = words.get(k, [])
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            raise JournalError(f"{where}: [words].{k} must be a list of strings")
        words[k] = v
    bad = set(words["counts"]) - set(COUNTABLE)
    if bad:
        raise JournalError(f"{where}: [words].counts has unknown region(s) "
                           f"{sorted(bad)}; expected {', '.join(COUNTABLE)}")
    bad = set(words["excludes"]) - set(ROLES)
    if bad:
        raise JournalError(f"{where}: [words].excludes has unknown role(s) "
                           f"{sorted(bad)}; expected {', '.join(ROLES)}")

    floats = data.get("floats", {})
    keys(floats, FLOAT_KEYS, f"{where} [floats]")
    for k in FLOAT_KEYS:
        _positive(floats, k, where)

    figures = data.get("figures", {})
    keys(figures, FIGURE_KEYS, f"{where} [figures]")
    _positive(figures, "min-dpi", where)

    graphic = data.get("graphical-abstract", {})
    keys(graphic, GRAPHIC_KEYS, f"{where} [graphical-abstract]")
    if "required" in graphic and not isinstance(graphic["required"], bool):
        raise JournalError(f"{where}: [graphical-abstract].required must be true or false")
    for k in ("width-in", "height-in"):
        _positive(graphic, k, where, number=True)
    _positive(graphic, "min-dpi", where)
    if ("width-in" in graphic) != ("height-in" in graphic):
        raise JournalError(f"{where}: [graphical-abstract] needs both width-in and height-in")
    if "guidelines-dated" in graphic and not DATE.match(str(graphic["guidelines-dated"])):
        raise JournalError(f"{where}: [graphical-abstract].guidelines-dated must be YYYY-MM-DD")

    notes = data.get("notes", {})
    if not isinstance(notes, dict) or any(not isinstance(v, str) for v in notes.values()):
        raise JournalError(f"{where}: [notes] must map rule names to quoted text")

    return Profile(id=id, label=data["label"], journal=data["journal"],
                   type=data["type"], source=data["source"],
                   guidelines_dated=data["guidelines-dated"], checked=data["checked"],
                   words=words, floats=floats, figures=figures, graphic=graphic,
                   notes=notes)


def load_selection(root: Path = ROOT) -> dict | None:
    """journal.toml as {profile, sections, placement}, or None without the file.

    `profile` is None when the file says "" -- the manuscript is held to no
    journal, deliberately, and the placement defaults still apply.
    """
    path = root / CONFIG
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise JournalError(f"{CONFIG}: not valid TOML: {e}") from None
    keys(data, {"schema_version", "profile", "sections", "placement"}, CONFIG)
    if data.get("schema_version") != 1 or type(data.get("schema_version")) is not int:
        raise JournalError(f"{CONFIG}: schema_version must be 1")
    profile = data.get("profile", "")
    if not isinstance(profile, str):
        raise JournalError(f"{CONFIG}: profile must be a string (\"\" for none)")
    sections = data.get("sections", {})
    keys(sections, set(ROLES), f"{CONFIG} [sections]")
    for role, v in sections.items():
        if not isinstance(v, str) or v.endswith("/"):
            raise JournalError(f"{CONFIG}: [sections].{role} must be a section path "
                               f"such as \"main/Methods\", or \"\" for none")
    placement = dict(DEFAULT_PLACEMENT)
    given = data.get("placement", {})
    keys(given, set(DEFAULT_PLACEMENT), f"{CONFIG} [placement]")
    for output, v in given.items():
        if v not in PLACEMENTS:
            raise JournalError(f"{CONFIG}: [placement].{output} must be one of "
                               f"{', '.join(PLACEMENTS)}, got {v!r}")
        placement[output] = v
    return {"profile": profile or None, "sections": sections, "placement": placement}


def current(root: Path = ROOT) -> tuple[Profile | None, dict | None]:
    sel = load_selection(root)
    if not sel or not sel["profile"]:
        return None, sel
    return load_profile(root, sel["profile"]), sel


# ------------------------------------------ what the other checkers read ---

def placement(root: Path = ROOT, output: str = "pdf") -> str:
    """Where the graphical abstract goes in `output` ("pdf" or "docx")."""
    sel = load_selection(root)
    table = sel["placement"] if sel else DEFAULT_PLACEMENT
    return table[output]


def min_figure_dpi(root: Path = ROOT) -> int | None:
    """The profile's floor for in-text raster figures, for prose-check."""
    profile, _ = current(root)
    if profile is None:
        return None
    return profile.figures.get("min-dpi")


def word_checks(root: Path = ROOT) -> list[dict]:
    """The profile's word limits in word-limits.toml's own check format.

    They join the project's checks in tools/wordcount.py rather than being
    evaluated here, so `just check-words` and `just verify` report them in the
    same table as everything else, and a `--json` reader sees one list.
    """
    profile, sel = current(root)
    if profile is None:
        return []
    w = profile.words
    out = []
    if "main-max" in w:
        include = ["main"] + [c for c in w["counts"] if c in COUNTABLE]
        exclude = []
        for role in w["excludes"]:
            path = sel["sections"].get(role)
            if path is None:
                raise JournalError(
                    f"{CONFIG}: profile {profile.id!r} leaves the {role} section out "
                    f"of its word limit, but [sections] does not say which section "
                    f"that is here. Add `{role} = \"main/Methods\"` (see: just "
                    f"wordcount --sections), or `{role} = \"\"` if this manuscript "
                    f"has no such section.")
            if path:
                exclude.append(path)
        check = {"name": f"{profile.label}: main text", "include": include,
                 "exclude": exclude, "max": w["main-max"], "source": profile.source}
        if "references" in w["counts"]:
            check["note"] = ("includes the main text's reference list as citeproc "
                             "sets it for the Word file")
        out.append(check)
    if "abstract-max" in w:
        out.append({"name": f"{profile.label}: abstract", "include": ["abstract"],
                    "exclude": [], "max": w["abstract-max"], "source": profile.source})
    return out


# ------------------------------------------------------ the manuscript ---

def _strip_comments(src: str) -> str:
    return re.sub(r"//[^\n]*", "", src)


def _front(root: Path) -> str:
    """paper.typ above the BODY START marker, comments removed."""
    import readability
    src = (root / "paper.typ").read_text(encoding="utf-8")
    m = readability.BODY_START.search(src)
    return _strip_comments(src[:m.start()] if m else src)


def keyword_count(root: Path = ROOT) -> int | None:
    """How many strings `#let paper-keywords = (...)` holds, or None if absent."""
    path = root / "config.typ"
    if not path.is_file():
        return None
    src = _strip_comments(path.read_text(encoding="utf-8"))
    m = re.search(r"#let\s+paper-keywords\s*=\s*\(", src)
    if not m:
        return None
    depth, i = 0, m.end() - 1
    for j in range(i, len(src)):
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if depth == 0:
                return len(re.findall(r'"(?:[^"\\]|\\.)*"', src[i:j]))
    raise JournalError("config.typ: paper-keywords never closes its parenthesis")


def main_text_floats(root: Path = ROOT) -> dict[str, int]:
    """Figures and tables in the main text: `#figure(` blocks between the BODY
    markers of paper.typ, following includes inside them. The SI does not
    count -- it is the journal's own distinction, and the markers' too."""
    import readability
    src = (root / "paper.typ").read_text(encoding="utf-8")
    body = readability.slice_body(src)

    def inline(m: re.Match) -> str:
        target = root / m.group(1).lstrip("/")
        return target.read_text(encoding="utf-8") if target.is_file() else ""

    body = _strip_comments(re.sub(r'#include\s+"([^"]+)"', inline, body))
    counts = {"figures": 0, "tables": 0}
    for m in re.finditer(r"#figure\(", body):
        rest = body[m.end():].lstrip()
        kind = "tables" if re.match(r"(table|tbl)\s*\(", rest) else "figures"
        counts[kind] += 1
    return counts


def toc_graphic(root: Path = ROOT) -> dict | None:
    """The graphical abstract paper.typ declares, resolved to a file.

    The convention is paper.typ's own and the Word resolver reads the same
    binding: `#let toc-graphic = fig("fig.id", ...)` or `image("path", ...)`.
    `none` or no binding means the manuscript has none.
    """
    g = re.search(r"(?m)^#let\s+toc-graphic\s*=\s*(\S.*)$", _front(root))
    if not g or g.group(1).strip() == "none":
        return None
    expr = g.group(1).strip()
    out = {"expr": expr, "path": None, "id": None}
    f = re.search(r'\bfig\(\s*"([^"]+)"', expr)
    i = re.search(r'\bimage\(\s*"([^"]+)"', expr)
    if f:
        out["id"] = f.group(1)
        manifest = root / "assets.json"
        if manifest.is_file():
            values = json.loads(manifest.read_text(encoding="utf-8")).get("values", {})
            entry = values.get(f.group(1))
            if entry:
                out["path"] = entry.get("path")
    elif i:
        out["path"] = i.group(1).lstrip("/")
    return out


def main_text_citations(root: Path = ROOT) -> list[str]:
    """Keys the main text cites, in first-citation order; the SI's excluded.

    The main text is paper.typ and what it includes, less si-body.typ and
    what THAT includes. A key is a citation by the same rule the Word export
    applies (typst_prose.CITE, outside strings, not a float cross-reference),
    and a key carrying the SI's routing prefix belongs to the SI's list.
    """
    from manuscript_sources import mask, si_bibliography, source_files
    from resolve_typst import FLOAT_PREFIX
    from typst_prose import CITE
    si = si_bibliography(root)
    prefix = (si or {}).get("prefix") or None
    main = source_files(root, entrypoints=("paper.typ",))
    for name in source_files(root, entrypoints=("si-body.typ",)):
        main.pop(name, None)
    seen: dict[str, None] = {}
    for src in main.values():
        for m in re.finditer(r"(?<![\w\\:./-])" + CITE, mask(_strip_comments(src), strings=True)):
            key = m.group(0)[1:]
            if key.split(":", 1)[0] in FLOAT_PREFIX:
                continue
            if prefix and key.startswith(prefix):
                continue
            seen.setdefault(key, None)
    return list(seen)


def reference_words(root: Path = ROOT) -> dict | None:
    """Words in the main text's reference list, as the journal will see it.

    The list counted is the one citeproc sets from the .bib and the CSL for
    the Word export, because the Word file is what goes to the journal; the
    PDF's list is Typst's own rendering and differs by a few words of
    punctuation. Pandoc renders the cited entries to plain text through a
    `nocite` list, and the words are counted the way the rest of the count
    counts them: whitespace-separated tokens.

    None when the manuscript has no #bibliography call or cites nothing in
    the main text. A missing .csl falls back to pandoc's default style, as
    the export does, and is reported in the result.
    """
    import pypandoc
    from resolve_typst import bibliography_line, _strip_comments as strip
    paper, config = root / "paper.typ", root / "config.typ"
    if not paper.is_file():
        return None
    call = bibliography_line(paper.read_text(encoding="utf-8"),
                             config.read_text(encoding="utf-8") if config.is_file() else "")
    if not call:
        return None
    paths = re.findall(r'"([^"]+\.(?:bib|yml|yaml))"', call)
    style_m = re.search(r'style:\s*"([^"]+)"', call)
    style = style_m.group(1) if style_m else None
    keys = main_text_citations(root)
    if not keys or not paths:
        return None
    args = ["--citeproc", "--wrap=none"]
    args += [f"--bibliography={root / p.lstrip('/')}" for p in paths]
    csl = next((p for p in (root / f"{style}.csl", root / "csl" / f"{style}.csl")
                if style and p.is_file()), None)
    if csl:
        args += ["--csl", str(csl)]
    doc = "---\nnocite: |\n  " + ", ".join(f"@{k}" for k in keys) + "\n---\n"
    text = pypandoc.convert_text(doc, "plain", format="markdown", extra_args=args)
    return {"words": len(text.split()), "entries": len(keys), "style": style,
            "csl": csl.name if csl else None}


def pixel_size(path: Path) -> tuple[int, int] | None:
    """(width, height) of a raster, or None for a vector or unreadable file."""
    if path.suffix.lower() in (".svg", ".pdf", ".eps"):
        return None
    try:
        with path.open("rb") as fh:
            head = fh.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", head[16:24])
            return w, h
    except OSError:
        return None
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


# --------------------------------------------------------------- checks ---

def check(root: Path = ROOT) -> list[Finding]:
    """Everything the profile says that no other checker covers."""
    profile, sel = current(root)
    if profile is None:
        return []
    out: list[Finding] = []

    kmax = profile.words.get("keywords-max")
    if kmax is not None:
        n = keyword_count(root)
        if n is not None and n > kmax:
            out.append(Finding("error", "keywords",
                               f"config.typ lists {n} keywords; {profile.label} "
                               f"allows at most {kmax}"))

    if profile.floats and (root / "paper.typ").is_file():
        counts = main_text_floats(root)
        limits = {"figures-max": ("figures", counts["figures"]),
                  "tables-max": ("tables", counts["tables"]),
                  "figures-and-tables-max": ("figures and tables",
                                             counts["figures"] + counts["tables"])}
        for key, (what, n) in limits.items():
            cap = profile.floats.get(key)
            if cap is not None and n > cap:
                out.append(Finding("error", what,
                                   f"the main text has {n} {what}; {profile.label} "
                                   f"allows at most {cap} (the SI does not count)"))

    g = profile.graphic
    if g:
        toc = toc_graphic(root) if (root / "paper.typ").is_file() else None
        if toc is None:
            if g.get("required"):
                out.append(Finding("error", "graphical abstract",
                                   f"{profile.label} requires a TOC graphic and paper.typ "
                                   f"declares none -- add `#let toc-graphic = fig(\"fig.toc\")` "
                                   f"(see: just new-figure, or `just adopt` for a drawn one)"))
        elif toc["path"] is None:
            out.append(Finding("error", "graphical abstract",
                               f"toc-graphic is {toc['expr']}, which resolves to no file "
                               f"(asset {toc['id']!r} is not declared in assets.json)"))
        elif not (root / toc["path"]).is_file():
            out.append(Finding("error", "graphical abstract",
                               f"toc-graphic points at {toc['path']}, which does not exist"))
        elif "width-in" in g:
            size = pixel_size(root / toc["path"])
            if size is None:
                out.append(Finding("note", "graphical abstract",
                                   f"{toc['path']} is a vector or unreadable file, so its "
                                   f"resolution at {g['width-in']} x {g['height-in']} in is "
                                   f"not measured"))
            else:
                w, h = size
                # Scaled to fit the journal's box, the graphic's printed width is
                # the box width unless it is taller than the box's proportions.
                printed_w = min(g["width-in"], g["height-in"] * w / h)
                dpi = w / printed_w
                floor = g.get("min-dpi")
                if floor and dpi < floor:
                    out.append(Finding("error", "graphical abstract",
                                       f"{toc['path']} is {w} x {h} px, which prints at "
                                       f"~{dpi:.0f} dpi when fitted to {profile.label}'s "
                                       f"{g['width-in']} x {g['height-in']} in box; the floor "
                                       f"is {floor} dpi"))
    return out


# --------------------------------------------------------------- report ---

def report(root: Path = ROOT) -> dict:
    """The whole card: the profile, and the manuscript against each rule."""
    profile, sel = current(root)
    out: dict = {"schema_version": 1, "configured": sel is not None,
                 "profile": None, "placement": (sel or {}).get("placement", DEFAULT_PLACEMENT)}
    if profile is None:
        return out
    out["profile"] = {"id": profile.id, "label": profile.label, "journal": profile.journal,
                      "type": profile.type, "source": profile.source,
                      "guidelines_dated": profile.guidelines_dated, "checked": profile.checked}
    import wordcount
    checks = word_checks(root)
    words = None
    if checks:
        data = wordcount.counts(root)
        words = wordcount.evaluate(checks, data["sections"])
    out["words"] = words
    out["keywords"] = {"count": keyword_count(root), "max": profile.words.get("keywords-max")}
    out["floats"] = {**main_text_floats(root),
                     **{k: v for k, v in profile.floats.items()}}
    out["figures"] = {"min_dpi": profile.figures.get("min-dpi")}
    toc = toc_graphic(root)
    out["graphical_abstract"] = {
        "declared": toc is not None, "path": toc["path"] if toc else None,
        "pixels": list(pixel_size(root / toc["path"])) if toc and toc["path"]
        and (root / toc["path"]).is_file() and pixel_size(root / toc["path"]) else None,
        **{k.replace("-", "_"): v for k, v in profile.graphic.items()}}
    out["findings"] = [f.__dict__ for f in check(root)]
    out["notes"] = profile.notes
    return out


def _print_findings(findings: list[Finding]) -> None:
    for f in findings:
        print(f"  {f.level:<5}  {f.subject}: {f.message}")


def _print_report(r: dict) -> None:
    if not r["configured"]:
        print(f"No {CONFIG}: the manuscript is held to no journal.")
        return
    if r["profile"] is None:
        print(f"{CONFIG} selects no profile: the manuscript is held to no journal.")
        return
    p = r["profile"]
    print(f"{p['journal']} -- {p['type']}  (profile {p['id']})")
    print(f"  source: {p['source']}")
    print(f"  guidelines dated {p['guidelines_dated']}, read {p['checked']}")
    print()
    print("Word limits (inclusive; also in `just check-words`):")
    if r["words"]:
        wordcount_print(r["words"])
    else:
        print("  none for this manuscript type")
    k = r["keywords"]
    if k["max"] is not None:
        print(f"Keywords: {k['count'] if k['count'] is not None else '?'} "
              f"of at most {k['max']}")
    fl = r["floats"]
    caps = ", ".join(f"{key.replace('-', ' ')} {v}" for key, v in fl.items()
                     if key.endswith("-max"))
    print(f"Main-text floats: {fl['figures']} figure(s), {fl['tables']} table(s)"
          + (f"; limit: {caps}" if caps else "; no limit"))
    if r["figures"]["min_dpi"]:
        print(f"Figure resolution: {r['figures']['min_dpi']} dpi as printed "
              f"(in `just prose-check`)")
    g = r["graphical_abstract"]
    if g.get("required") or g.get("declared"):
        where = (f"{g['path']} ({g['pixels'][0]} x {g['pixels'][1]} px)"
                 if g.get("pixels") else (g["path"] or "none declared"))
        box = (f"{g['width_in']} x {g['height_in']} in at {g.get('min_dpi', '?')} dpi"
               if g.get("width_in") else "no size given")
        print(f"Graphical abstract: {where}; box {box}")
        pl = r["placement"]
        print(f"  placed: PDF {pl['pdf']}, Word {pl['docx']}  ({CONFIG} [placement])")
    print()
    if r["findings"]:
        _print_findings([Finding(**f) for f in r["findings"]])
    else:
        print("  every checkable rule passes")
    if r["notes"]:
        print()
        print("In the journal's words:")
        for key, text in r["notes"].items():
            print(f"  {key}: {text}")


def wordcount_print(rows: list[dict]) -> None:
    import wordcount
    wordcount.print_checks(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Hold the manuscript to a journal profile")
    parser.add_argument("command", nargs="?", default="report",
                        choices=("report", "check", "list"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "list":
            names = available(root)
            sel = load_selection(root)
            chosen = sel["profile"] if sel else None
            if args.json:
                print(json.dumps({"profiles": names, "selected": chosen}))
            else:
                for name in names:
                    p = load_profile(root, name)
                    mark = "*" if name == chosen else " "
                    print(f" {mark} {name:<24} {p.journal} -- {p.type} "
                          f"(guidelines {p.guidelines_dated}, read {p.checked})")
                if not names:
                    print(f"no profiles under {PROFILES}/")
            return 0
        if args.command == "check":
            findings = check(root)
            profile, sel = current(root)
            if args.json:
                print(json.dumps({"schema_version": 1, "profile": profile.id if profile else None,
                                  "findings": [f.__dict__ for f in findings]}, indent=2))
            elif profile is None:
                print("journal: no profile selected, nothing to hold the manuscript to")
            else:
                _print_findings(findings)
                errors = sum(f.level == "error" for f in findings)
                print(f"  {profile.label}: {errors} error(s), "
                      f"{sum(f.level == 'warn' for f in findings)} warning(s)")
            return 1 if any(f.level == "error" for f in findings) else 0
        r = report(root)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
        else:
            _print_report(r)
        return 1 if any(f["level"] == "error" for f in r.get("findings", [])) else 0
    except (OSError, ValueError, KeyError) as exc:
        if args.json:
            print(json.dumps({"schema_version": 1, "status": "incomplete", "error": str(exc)}))
        else:
            print(f"journal: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
