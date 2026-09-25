#!/usr/bin/env python3
"""The journal upload set, written into submission/ with a manifest.

WHY THIS EXISTS. `just paper` and `just docx` build ONE document, main text
and Supporting Information together, so every cross-reference resolves in a
single label namespace. A journal's upload form wants them apart: the
manuscript, the SI, the graphical abstract as its own file in the format the
journal names, and a cover letter. Four projects built those separately, each
with its own recipes and a tool that did the same split three different ways.
This is the one upstream version, and it adds no second source of truth:

  manuscript.pdf / supporting-information.pdf
      The captured manuscript `just paper` recorded, compiled once more with
      the `submission` placement from journal.toml (the journal's layout by
      default: graphical abstract on the last page of the main text) and cut
      at the <si-start> probe in paper.typ into two page ranges. Every page,
      figure and reference number is the combined document's, which is the
      point: the SI is an appendix of the same compilation, so nothing is
      renumbered and nothing can disagree with paper.pdf.
  manuscript.docx / supporting-information.docx
      The Word projection of the same capture, cut at the SI heading the
      resolver writes, each half converted by tools/export_docx.py unchanged.
  toc-graphic.<format>
      The graphic paper.typ declares as `toc-graphic`, in the profile's
      [graphical-abstract] file-format, flattened to RGB on white, with the
      resolution metadata set so it measures no larger than the journal's box.
      A vector source is rasterized by Typst at the profile's min-dpi.
  cover-letter.pdf
      cover-letter.typ, compiled with the profile's journal and article type
      as inputs. Optional: without the file, no letter, and no stale one left.
      Its words and pages are measured and recorded, and `check` holds them
      to the profile's [cover-letter] max-words and max-pages (docs/submission.md).

WITHOUT AN APPENDIX SI. The cut above assumes paper.typ includes si-body.typ.
When it does not, the main files are the whole capture, and the SI is either
the non-default document target manuscript.toml declares for it (compiled on
its own, PDF only: no SI Word file) or absent, in which case the si-* steps
write nothing and remove any SI file left from before (see si_layout).

ONE REFERENCE LIST. A paper whose SI cites the main list's keys (no si-
list of its own) would ship an SI whose citations point at a list in the
other file. Then both SI files are compiled on their own from the SI half of
the Word projection, closed by the main list's #bibliography call, so the
list holds only what the SI cites, numbered 1..n in SI order; references to
main-text floats and sections gain "of the main text" (standalone_si).

STALENESS. Every output is recorded in .build-state/submission.json with the
hashes of what it was built from, in the same shape as paper.pdf's record,
and `check` recompares them without building anything. The split outputs are
built from the captured manuscript only while that capture still matches the
source, so a submission file can never describe an edit the PDF has not seen.
The set is deliberately OUTSIDE `just verify`: it is a day-of-submission
artifact, rebuilt by `just preflight`, and failing the everyday gate after
every prose edit until someone rebuilt an upload set they are not uploading
would be the audiobook nag again. `just check` prints a note when it is stale;
`just check-submission` is the strict check, and preflight runs it.

Usage (via the just recipes):
    uv run python tools/submission.py {main-pdf,si-pdf,main-docx,si-docx,
                                       toc-graphic,cover-letter,all}
    uv run python tools/submission.py check [--note]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

from paths import ROOT, locate, tool  # the manuscript (tools/paths.py)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from atomic_io import write_text
from build_state import build_lock, changed_note, digest, snapshot, stats_digest

OUT_DIR = "submission"
RECORD = Path(".build-state") / "submission.json"
LETTER_SOURCE = "cover-letter.typ"
# The heading tools/resolve_typst.py opens the SI with in the Word projection.
SI_HEADING = re.compile(
    r"(?m)^#heading\(level: 1, numbering: none, outlined: false\)"
    r"\[Supporting Information\]")

# Output name -> what it is, for the manifest and the printed summary.
OUTPUTS = {
    "manuscript.pdf": "main text alone (PDF)",
    "supporting-information.pdf": "Supporting Information alone (PDF)",
    "manuscript.docx": "main text alone (Word)",
    "supporting-information.docx": "Supporting Information alone (Word)",
    "toc-graphic": "graphical abstract as a standalone file",
    "cover-letter.pdf": "cover letter",
}
KIND_FILE = {"main-pdf": "manuscript.pdf", "si-pdf": "supporting-information.pdf",
             "main-docx": "manuscript.docx", "si-docx": "supporting-information.docx"}


# What the manifest says about numbering, by where the SI lives (si_layout).
SI_NOTES = {
    "appendix": "Page, figure and reference numbers are those of the combined "
                "manuscript; the SI is an appendix of the same compilation.",
    "separate": "The main files are the whole of paper.typ; the SI PDF is its own "
                "manuscript.toml document target, and there is no SI Word file.",
    "none": "The manuscript has no Supporting Information; the main files are the "
            "whole document.",
    "standalone": "The main files are pages and text of the combined manuscript. The "
                  "SI files are compiled on their own with a local reference list: "
                  "only the works the SI cites, numbered in SI citation order. The SI "
                  "calls main-text figures, tables and sections '... of the main text'.",
}
# The note the manifest carries: the most specific layout any record names.
NOTE_ORDER = ("standalone", "separate", "none", "appendix")


class SubmissionError(ValueError):
    """A submission output that cannot be built truthfully."""


# ------------------------------------------------------------- records ---

def load_records(root: Path) -> dict:
    path = root / RECORD
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise SubmissionError(f"{RECORD}: unsupported record; delete it and rebuild")
    return data.get("outputs", {})


def save_records(root: Path, outputs: dict) -> None:
    (root / RECORD).parent.mkdir(exist_ok=True)
    write_text(root / RECORD, json.dumps({"schema_version": 1, "outputs": outputs},
                                         indent=2, sort_keys=True))


def tool_digest() -> str:
    return digest(Path(__file__).resolve())


def file_sources(root: Path, names) -> dict[str, str | None]:
    """{name: hash} for a small explicit input set (graphic, letter)."""
    out = {}
    for name in sorted(set(names)):
        path = Path(name) if Path(name).is_absolute() else locate(root, name)
        if name in ("stats.json", "stats-rendered.json"):
            # Derived from stats.json by every compile; hash the source instead,
            # so a stats edit not yet rendered still reads as a change.
            out["stats.json"] = stats_digest(root)
            continue
        out[name] = digest(path) if path.is_file() else None
    return out


def current_sources(root: Path, record: dict) -> dict:
    if record["kind"] == "manuscript":
        now = snapshot(root, record["dependencies"])
    else:
        now = file_sources(root, record["sources"])
    now["tools/submission.py"] = tool_digest()
    return now


def status(root: Path, name: str, record: dict) -> str:
    path = root / OUT_DIR / name
    try:
        if not path.is_file():
            return "missing"
        if current_sources(root, record) != record["sources"]:
            return "stale"
        if digest(path) != record["output_hash"]:
            return "replaced"
    except (OSError, ValueError, KeyError, TypeError):
        return "unknown"
    return "current"


def publish(root: Path, staged: Path, name: str, record: dict) -> None:
    out = root / OUT_DIR
    out.mkdir(exist_ok=True)
    os.replace(staged, out / name)
    record["output_hash"] = digest(out / name)
    records = load_records(root)
    records[name] = record
    save_records(root, records)
    write_manifest(root)


def forget(root: Path, prefix: str) -> None:
    """Drop an output whose source is gone, so no stale copy ships."""
    records = load_records(root)
    for name in [n for n in records if n.startswith(prefix)]:
        (root / OUT_DIR / name).unlink(missing_ok=True)
        del records[name]
    for path in (root / OUT_DIR).glob(prefix + "*") if (root / OUT_DIR).is_dir() else ():
        path.unlink()
    save_records(root, records)
    write_manifest(root)


def write_manifest(root: Path) -> None:
    """submission/manifest.json: what each file is, its hash, what built it."""
    out = root / OUT_DIR
    if not out.is_dir():
        return
    try:
        from journal import current
        profile, _ = current(root)
    except ValueError:
        profile = None
    version = re.search(r'(?m)^version\s*=\s*"([^"]+)"',
                        (root / "pyproject.toml").read_text()) \
        if (root / "pyproject.toml").is_file() else None
    files = {}
    for name, record in sorted(load_records(root).items()):
        path = out / name
        if not path.is_file():
            continue
        role = OUTPUTS.get(name) or OUTPUTS.get(name.rsplit(".", 1)[0], "")
        files[name] = {"role": role, "bytes": path.stat().st_size,
                       "sha256": digest(path), "status": status(root, name, record),
                       **{k: record[k] for k in ("manuscript_id", "pages", "placement",
                                                 "format", "dpi", "pixels", "si",
                                                 "words", "pages")
                          if k in record}}
    write_text(out / "manifest.json", json.dumps({
        "schema_version": 1,
        "scaffold_version": version.group(1) if version else None,
        "journal": ({"profile": profile.id, "journal": profile.journal,
                     "type": profile.type} if profile else None),
        "files": files,
        "note": SI_NOTES[next((k for k in NOTE_ORDER if k in
                               {r.get("si") for r in load_records(root).values()}),
                              "appendix")],
    }, indent=2) + "\n")
    (out / "manifest.json").chmod(0o644)


# ------------------------------------------------ the captured manuscript ---

def capture(root: Path) -> tuple[Path, dict]:
    """The captured manuscript, validated and still matching the source."""
    from manuscript_snapshot import validate
    pointer = root / ".build-state" / "manuscript.json"
    if not pointer.is_file():
        raise SubmissionError("no captured manuscript yet; run: just paper")
    data = json.loads(pointer.read_text())
    folder = root / data["path"]
    manifest = validate(folder)
    if snapshot(root, manifest["dependencies"]) != manifest["sources"]:
        raise SubmissionError("the source changed since the last build; run: just paper")
    return folder, manifest


def manuscript_record(root: Path, manifest: dict, **extra) -> dict:
    sources = dict(manifest["sources"])
    sources["tools/submission.py"] = tool_digest()
    return {"kind": "manuscript", "manuscript_id": manifest["id"],
            "dependencies": manifest["dependencies"], "sources": sources, **extra}


def si_start(folder: Path, placement: str) -> int:
    try:
        raw = subprocess.run(
            ["typst", "query", "--root", str(folder), "--input", f"toc={placement}",
             str(folder / "paper.typ"), "<si-start>", "--field", "value", "--one"],
            capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError as exc:
        raise SubmissionError(
            "paper.typ has no <si-start> probe. Add this line directly after the "
            "#pagebreak() that opens the Supporting Information:\n"
            "    #context [#metadata(here().page()) <si-start>]\n"
            f"(typst: {exc.stderr.strip().splitlines()[-1] if exc.stderr.strip() else exc})"
        ) from None
    page = int(json.loads(raw))
    if page <= 1:
        raise SubmissionError(f"<si-start> is on page {page}; it must follow the main text")
    return page


# ------------------------------------------------ where the SI lives ---
# Three shapes, read from the capture and manuscript.toml, never configured:
#   appendix  paper.typ includes si-body.typ (the scaffold's layout): the SI
#             is cut out of the one compilation, PDF at <si-start>, Word at
#             the SI heading the resolver writes for exactly that include.
#   separate  paper.typ does not include the SI, and manuscript.toml declares
#             another document target for it (cascade/paper): main = the
#             whole capture, SI PDF = that target compiled on its own, and no
#             SI Word file, since document targets are PDF-only.
#   none      no SI at all (exclusionms-paper): main = the whole capture, and
#             the si-* steps write nothing and clear any stale SI file.

def separate_si_entry(root: Path) -> str | None:
    """The entrypoint of the SI's own document target in manuscript.toml.

    The SI target is the non-default document that is not paper.typ and
    either is named "si" or carries the part whose source is si-body.typ.
    """
    if not (root / "manuscript.toml").is_file():
        return None
    from document_project import load_project
    project = load_project(root)
    si_parts = {p.id for p in project.parts.values() if p.source == "si-body.typ"}
    found = [d for d in project.documents.values()
             if d.id != project.default and d.entrypoint != "paper.typ"
             and (d.id == "si" or si_parts & set(d.parts))]
    if len(found) > 1:
        raise SubmissionError("manuscript.toml declares more than one SI document target: "
                              + ", ".join(d.id for d in found))
    return found[0].entrypoint if found else None


def si_layout(root: Path, folder: Path) -> tuple[str, str | None]:
    """("appendix" | "separate" | "none", the separate SI entrypoint or None)."""
    if SI_HEADING.search((folder / "paper.word.typ").read_text()):
        return "appendix", None
    entry = separate_si_entry(root)
    return ("separate", entry) if entry else ("none", None)


def no_si(root: Path, kind: str) -> str:
    name = KIND_FILE[kind]
    forget(root, name)
    return f"note: paper.typ includes no Supporting Information; no {OUT_DIR}/{name} written"


def split_pdf(root: Path, kind: str) -> str:
    from journal import placement as toc_placement
    name = KIND_FILE[kind]
    placement = toc_placement(root, "submission")
    with build_lock(root):
        folder, manifest = capture(root)
        layout, entry = si_layout(root, folder)
        standalone = standalone_si((folder / "paper.word.typ").read_text()) \
            if kind == "si-pdf" and layout == "appendix" else None
        if standalone:
            compile_standalone_si(root, folder, manifest, standalone, placement)
            return (f"wrote {OUT_DIR}/{name} (the SI on its own, with a local "
                    f"reference list of {len(standalone.keys)} works)")
        from_capture = kind == "main-pdf" or layout == "appendix"
        if from_capture:
            if layout == "appendix":
                start = si_start(folder, placement)
                pages = f"1-{start - 1}" if kind == "main-pdf" else f"{start}-"
            else:
                pages = "1-"   # paper.typ is the main text alone
            with tempfile.TemporaryDirectory(dir=root / ".build-state") as tmp:
                staged = Path(tmp) / name
                # A page range cannot carry PDF tags; journals do not read them.
                subprocess.run(["typst", "compile", "--root", str(folder), "--no-pdf-tags",
                                "--input", f"toc={placement}", "--pages", pages,
                                str(folder / "paper.typ"), str(staged)], check=True)
                if snapshot(root, manifest["dependencies"]) != manifest["sources"]:
                    raise SubmissionError("the source changed during the export; rerun it")
                publish(root, staged, name, manuscript_record(
                    root, manifest, pages=pages, placement=placement, si=layout))
    if not from_capture:
        # Outside the lock: the separate target takes it itself.
        return separate_si_pdf(root, entry) if layout == "separate" else no_si(root, kind)
    what = (f"pages {pages} of the combined manuscript" if layout == "appendix"
            else "the whole manuscript; paper.typ carries no SI")
    return f"wrote {OUT_DIR}/{name} ({what}, graphical abstract: {placement})"


def separate_si_pdf(root: Path, entry: str) -> str:
    """The SI's own manuscript.toml target, compiled and recorded by its inputs."""
    name = KIND_FILE["si-pdf"]
    subprocess.run([sys.executable, str(tool("render_stats.py"))], cwd=root,
                   check=True, stdout=subprocess.DEVNULL)
    with build_lock(root), tempfile.TemporaryDirectory(dir=root / ".build-state") as tmp:
        staged, deps = Path(tmp) / name, Path(tmp) / "deps.json"
        subprocess.run(["typst", "compile", "--root", str(root), "--deps", str(deps),
                        entry, str(staged)], cwd=root, check=True)
        sources = file_sources(root, ["manuscript.toml", *compile_inputs(root, deps)])
        sources["tools/submission.py"] = tool_digest()
        publish(root, staged, name, {"kind": "files", "sources": sources, "si": "separate"})
    return f"wrote {OUT_DIR}/{name} (the separate SI target {entry})"


def compile_inputs(root: Path, deps: Path) -> list[str]:
    """The files a `typst compile --deps` read, relative to root where possible."""
    inputs = []
    for p in json.loads(deps.read_text())["inputs"]:
        path = Path(p)
        try:
            inputs.append(path.resolve().relative_to(root.resolve()).as_posix())
        except ValueError:
            inputs.append(str(path))
    return inputs


# ------------------------------------------- an SI on the main reference list ---

class StandaloneSI(NamedTuple):
    text: str        # SI half, qualified, closed by the main #bibliography call
    keys: set[str]   # the works it cites


def standalone_si(text: str) -> StandaloneSI | None:
    """The SI as its own document, when it cites the main reference list.

    Applies when the SI half of the Word projection cites keys but has no
    #bibliography of its own (a si- paper's resolver-written list is one) and
    the main half has exactly one. None otherwise: the page-range split
    stands, which is right for a si- list and for an SI that cites nothing.
    """
    from export_docx import cited_keys
    from manuscript_sources import BIBLIOGRAPHY, call_span
    main, si = split_word_source(text)
    keys = cited_keys(si)
    if not keys or call_span(si, BIBLIOGRAPHY) is not None:
        return None
    calls, at = [], 0
    while (span := call_span(main, BIBLIOGRAPHY, start=at)) is not None:
        calls.append(main[span[0]:span[1]])
        at = span[1]
    if len(calls) != 1:
        return None
    return StandaloneSI(qualify_main_text_references(si).rstrip() + "\n\n" + calls[0] + "\n",
                        keys)


_NOUN = r"(?:Figures?|Tables?|Sections?)"
_NUM = r"\d+(?:\.\d+)*[a-z]?"
# "Figure 3", "Figures 2 and 3", "Section 2.3 and Section 2.4": main-text
# numbers, never S-numbered ones, never a caption label ("Figure 3:"), and
# never one already qualified. Atomic, so "Figure 12" cannot match as "1";
# written as lookahead plus backreference because `(?>...)` needs Python 3.11.
MAIN_REF = re.compile(
    rf"(?=(?P<ref>\b{_NOUN} {_NUM}(?:(?:,? and |, |–|-)(?:{_NOUN} )?{_NUM})*))"
    r"(?P=ref)"
    r"(?![\w:])(?!\.\d)(?! (?:of|in) the main text)")


def qualify_main_text_references(si: str) -> str:
    """'Figure 3' -> 'Figure 3 of the main text' in the SI's prose.

    The resolver has already turned @fig/@tbl/@sec into literal numbers; once
    the SI is its own file, a bare "Figure 3" reads as the SI's own. Comments,
    raw text and strings are left alone.
    """
    from manuscript_sources import mask
    ends = [m.end() for m in MAIN_REF.finditer(mask(si, strings=True))]
    for end in reversed(ends):
        si = si[:end] + " of the main text" + si[end:]
    return si


# The page setup the Word projection lacks (it never compiles the preamble).
# Captions already carry their literal "Figure S1:" label from the resolver.
SI_PREAMBLE = """#set page(paper: "us-letter", margin: 1in, numbering: "S-1")
#set heading(numbering: none)
#show figure.caption: it => it.body
"""


def compile_standalone_si(root: Path, folder: Path, manifest: dict, si: StandaloneSI,
                          placement: str) -> None:
    """Compile the standalone SI inside the capture, so its paths resolve."""
    name = KIND_FILE["si-pdf"]
    fd, tmp_name = tempfile.mkstemp(dir=folder, prefix=".submission-si-", suffix=".typ")
    os.close(fd)
    source = Path(tmp_name)
    try:
        write_text(source, SI_PREAMBLE + si.text)
        with tempfile.TemporaryDirectory(dir=root / ".build-state") as tmp:
            staged = Path(tmp) / name
            subprocess.run(["typst", "compile", "--root", str(folder),
                            str(source), str(staged)], check=True)
            if snapshot(root, manifest["dependencies"]) != manifest["sources"]:
                raise SubmissionError("the source changed during the export; rerun it")
            publish(root, staged, name, manuscript_record(
                root, manifest, placement=placement, si="standalone"))
    finally:
        source.unlink(missing_ok=True)


def split_word_source(text: str) -> tuple[str, str]:
    """(main, si) halves of the Word projection, cut at the SI heading."""
    hits = list(SI_HEADING.finditer(text))
    if len(hits) != 1:
        raise SubmissionError(
            f"expected one Supporting Information heading in the Word projection, "
            f"found {len(hits)}; rebuild with: just paper")
    at = hits[0].start()
    header = text[:text.find("\n\n") + 2] if text.startswith("//") else ""
    return text[:at].rstrip() + "\n", header + text[at:]


def split_docx(root: Path, kind: str) -> str:
    name = KIND_FILE[kind]
    with build_lock(root):
        folder, manifest = capture(root)
        layout, entry = si_layout(root, folder)
        if kind == "si-docx" and layout != "appendix":
            if layout == "separate":
                forget(root, name)
                return (f"note: the SI is the separate PDF target {entry}; "
                        f"no {OUT_DIR}/{name} written")
            return no_si(root, kind)
        text = (folder / "paper.word.typ").read_text()
        main, si = split_word_source(text) if layout == "appendix" else (text, "")
        standalone = standalone_si(text) if kind == "si-docx" else None
        if standalone:
            si, layout = standalone.text, "standalone"
        with tempfile.TemporaryDirectory(dir=root / ".build-state") as tmp:
            source = Path(tmp) / "part.word.typ"
            write_text(source, main if kind == "main-docx" else si)
            staged = Path(tmp) / name
            # The captured tools/, so a capture converts the way it was built.
            export = folder / "tools" / "export_docx.py"
            if not export.is_file():
                export = tool("export_docx.py")
            subprocess.run([sys.executable, str(export), "--root", str(folder),
                            "--source", str(source), "--output", str(staged)],
                           check=True, stdout=subprocess.DEVNULL)
            if snapshot(root, manifest["dependencies"]) != manifest["sources"]:
                raise SubmissionError("the source changed during the export; rerun it")
            publish(root, staged, name, manuscript_record(root, manifest, si=layout))
    return f"wrote {OUT_DIR}/{name} (from captured manuscript {manifest['id'][:12]})"


# ------------------------------------------------------ graphical abstract ---

def graphic_spec(root: Path) -> tuple[dict | None, dict]:
    """(toc-graphic declaration or None, the profile's [graphical-abstract])."""
    from journal import current, toc_graphic
    profile, _ = current(root)
    return toc_graphic(root), (profile.graphic if profile else {})


def export_graphic(src: Path, dest: Path, spec: dict) -> dict:
    """Write `src` as dest's format, measuring no larger than spec's box."""
    from PIL import Image
    fmt = dest.suffix.lstrip(".")
    box = (spec.get("width-in"), spec.get("height-in"))
    floor = spec.get("min-dpi")
    if src.suffix.lower() in (".svg", ".pdf"):
        # Typst rasterizes a vector at the size the journal prints it.
        ppi = floor or 300
        w_in, h_in = box if box[0] else (3.25, 1.75)
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "g.typ"
            shutil.copyfile(src, Path(tmp) / ("g" + src.suffix))
            write_text(doc, f'#set page(width: auto, height: auto, margin: 0pt)\n'
                            f'#box(width: {w_in}in, height: {h_in}in, '
                            f'image("g{src.suffix}", width: 100%, height: 100%, fit: "contain"))\n')
            png = Path(tmp) / "g.png"
            subprocess.run(["typst", "compile", "--root", tmp, "--format", "png",
                            "--ppi", str(ppi), str(doc), str(png)], check=True)
            image = Image.open(png)
            image.load()
    else:
        image = Image.open(src)
        image.load()
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.getchannel("A"))
        image = flat
    elif image.mode != "RGB":
        image = image.convert("RGB")
    w, h = image.size
    if box[0]:
        # The resolution at which the graphic measures no more than the box.
        dpi = max(w / box[0], h / box[1])
        if floor and dpi < floor - 0.5:
            raise SubmissionError(
                f"{src.name} is {w} x {h} px, which fits the {box[0]} x {box[1]} in box "
                f"only at ~{dpi:.0f} dpi; the journal's floor is {floor} dpi")
    else:
        dpi = (image.info.get("dpi") or (300, 300))[0]
    options = {"dpi": (dpi, dpi)}
    if fmt == "tif":
        options["compression"] = "tiff_lzw"
    elif fmt == "jpg":
        options["quality"] = 95
    image.save(dest, format={"tif": "TIFF", "png": "PNG", "jpg": "JPEG"}[fmt], **options)
    return {"format": fmt, "dpi": round(dpi), "pixels": [w, h]}


def toc_graphic(root: Path) -> str:
    toc, spec = graphic_spec(root)
    if toc is None or not toc.get("path"):
        forget(root, "toc-graphic.")
        return "note: paper.typ declares no toc-graphic; no graphical abstract written"
    src = root / toc["path"]
    if not src.is_file():
        raise SubmissionError(f"toc-graphic points at {toc['path']}, which does not exist")
    fmt = spec.get("file-format") or {"jpeg": "jpg", "tiff": "tif"}.get(
        src.suffix.lower().lstrip("."), src.suffix.lower().lstrip("."))
    if fmt not in ("tif", "png", "jpg"):
        fmt = "png"
    name = f"toc-graphic.{fmt}"
    with tempfile.TemporaryDirectory(dir=root / ".build-state") as tmp:
        staged = Path(tmp) / name
        info = export_graphic(src, staged, spec)
        forget(root, "toc-graphic.")
        from journal import CONFIG, load_selection
        sel = load_selection(root)
        inputs = [toc["path"], "paper.typ", "assets.json", CONFIG]
        if sel and sel["profile"]:
            inputs.append(f"journals/{sel['profile']}.toml")
        sources = file_sources(root, inputs)
        sources["tools/submission.py"] = tool_digest()
        publish(root, staged, name, {"kind": "files", "sources": sources, **info})
    box = f", fits {spec['width-in']} x {spec['height-in']} in" if spec.get("width-in") else ""
    return (f"wrote {OUT_DIR}/{name} ({info['pixels'][0]} x {info['pixels'][1]} px, "
            f"{info['dpi']} dpi{box})")


# ------------------------------------------------------------ cover letter ---

def letter_counts(root: Path, source: Path, args: list[str], tmp: Path) -> dict:
    """{"words": n, "pages": n} for the letter as compiled with `args`.

    Words are what wordometer counts in the letter's content, the same
    counter the manuscript's word count uses: everything the letter prints,
    the address block and signature included, with #s() numbers resolved.
    Pages are the pages Typst lays out. Either is None when it cannot be
    measured, which the limit check reports rather than passes.
    """
    out: dict = {"words": None, "pages": None}
    fd, name = tempfile.mkstemp(dir=root, prefix=".cover-letter-count-", suffix=".typ")
    os.close(fd)
    wrapper = Path(name)
    rel = source.resolve().relative_to(root.resolve()).as_posix()
    try:
        write_text(wrapper, '#import "@preview/wordometer:0.1.4": word-count-of\n'
                            f'#metadata(word-count-of(include "/{rel}").words) '
                            '<cover-letter-words>\n')
        proc = subprocess.run(["typst", "query", "--root", str(root), *args, str(wrapper),
                               "<cover-letter-words>", "--field", "value", "--one"],
                              cwd=root, capture_output=True, text=True)
        if proc.returncode == 0:
            out["words"] = int(json.loads(proc.stdout))
    finally:
        wrapper.unlink(missing_ok=True)
    pages = tmp / "pages"
    pages.mkdir()
    proc = subprocess.run(["typst", "compile", "--root", str(root), *args, "--format", "svg",
                           str(source), str(pages / "p{0p}.svg")],
                          cwd=root, capture_output=True, text=True)
    if proc.returncode == 0:
        out["pages"] = len(list(pages.glob("p*.svg")))
    return out


def cover_letter(root: Path) -> str:
    source = root / LETTER_SOURCE
    if not source.is_file():
        forget(root, "cover-letter.")
        return f"note: no {LETTER_SOURCE}; no cover letter written"
    from journal import CONFIG, current, letter_findings, load_selection
    profile, _ = current(root)
    subprocess.run([sys.executable, str(tool("render_stats.py"))], cwd=root,
                   check=True, stdout=subprocess.DEVNULL)
    name = "cover-letter.pdf"
    args = []
    if profile:
        args += ["--input", f"journal={profile.journal}",
                 "--input", f"article-type={profile.type}"]
    (root / ".build-state").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root / ".build-state") as tmp:
        staged, deps = Path(tmp) / name, Path(tmp) / "deps.json"
        subprocess.run(["typst", "compile", "--root", str(root), "--deps", str(deps),
                        *args, str(source), str(staged)], cwd=root, check=True)
        counts = letter_counts(root, source, args, Path(tmp))
        inputs = compile_inputs(root, deps)
        sel = load_selection(root)
        inputs.append(CONFIG)
        if sel and sel["profile"]:
            inputs.append(f"journals/{sel['profile']}.toml")
        sources = file_sources(root, inputs)
        sources["tools/submission.py"] = tool_digest()
        publish(root, staged, name, {"kind": "files", "sources": sources, **counts})
    words = counts["words"] if counts["words"] is not None else "?"
    pages = counts["pages"] if counts["pages"] is not None else "?"
    msg = (f"wrote {OUT_DIR}/{name}" + (f" (to {profile.journal})" if profile else "")
           + f": {words} words, {pages} page(s)")
    for f in letter_findings(profile, counts):
        msg += f"\nLIMIT: {f.message}"
    return msg


def letter_limits(root: Path) -> list[str]:
    """The profile's cover-letter limits against the recorded letter."""
    record = load_records(root).get("cover-letter.pdf")
    if not record:
        return []
    from journal import current, letter_findings
    profile, _ = current(root)
    return [f.message for f in letter_findings(profile, record)]


# ------------------------------------------------------------------ check ---

def check(root: Path) -> list[dict]:
    rows = []
    for name, record in sorted(load_records(root).items()):
        row = {"output": f"{OUT_DIR}/{name}", "status": status(root, name, record)}
        if row["status"] == "stale":
            try:
                now = current_sources(root, record)
                row["changed"] = sorted(k for k in set(now) | set(record["sources"])
                                        if now.get(k) != record["sources"].get(k))
            except (OSError, ValueError, KeyError, TypeError):
                pass
        rows.append(row)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=(*KIND_FILE, "toc-graphic", "cover-letter",
                                            "all", "check"))
    parser.add_argument("--note", action="store_true",
                        help="check: report, but never fail (how `just check` runs it)")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "check":
            rows = check(root)
            bad = [r for r in rows if r["status"] != "current"]
            label = "note" if args.note else "STALE"
            for r in bad:
                print(f"{label}: {r['output']} is {r['status']} -- rebuild: just submission"
                      + changed_note(r.get("changed", [])))
            try:
                limits = letter_limits(root)
            except ValueError as exc:
                if not args.note:
                    raise
                print(f"note: cover-letter limits not checked: {exc}")
                limits = []
            for message in limits:
                print(f"{'note' if args.note else 'LIMIT'}: {message}")
            bad += limits
            if not args.note:
                # Data and code availability (tools/availability.py): an
                # integrity gap, so it fails check-submission, never `just check`.
                from availability import check as availability
                gaps = [f.message for f in availability(root)]
                for message in gaps:
                    print(f"AVAILABILITY: {message}")
                bad += gaps
            if not rows and not args.note:
                print("no submission set built yet -- build it: just submission")
                return 1
            if rows and not bad and not args.note:
                print(f"the submission set ({len(rows)} files) is current with the source")
            return 0 if args.note or not bad else 1
        steps = (list(KIND_FILE) + ["toc-graphic", "cover-letter"]
                 if args.command == "all" else [args.command])
        for step in steps:
            if step in ("main-pdf", "si-pdf"):
                print(split_pdf(root, step))
            elif step in ("main-docx", "si-docx"):
                print(split_docx(root, step))
            elif step == "toc-graphic":
                print(toc_graphic(root))
            else:
                print(cover_letter(root))
        if args.command == "all":
            print(f"manifest: {OUT_DIR}/manifest.json")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"submission failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
