#!/usr/bin/env python3
"""The data and code availability gate, run by `just check-submission`.

A journal checks the availability statement last and by hand, and four papers
reached a submission build with it wrong: an accession cited in Methods but
missing from the statement, a DOI still reading `XXXXXXX`, "code is currently
private", an "[AUTHOR ACTION: add DOI]" note. Each is a fact about the text,
so it gets checked mechanically:

  missing      an accession the manuscript uses (a PRIDE PXD, a GEO GSE, a
               PDB id, a Zenodo DOI ...) that no availability section repeats
  placeholder  XXXXX, "currently private", "[AUTHOR ACTION", TBD, anywhere
  no-archive   no archived code: no Zenodo, figshare, Software Heritage, OSF
               or Dryad identifier in the availability sections
  no-section   accessions are used, or an archive is required, but no
               heading or bold run-in names data, code or software availability

An availability section is any heading, or bold run-in paragraph
(`*Data and Code Availability*`), whose title names data, code or software
and "availab..."; it runs to the next heading, bold run-in, or reference list.
The body is every manuscript source (main text, SI, generated tables) with
comments removed.

project.toml [availability] tunes it (docs/submission.md):

    enabled = true                 # false: skip the whole check
    require_code_archive = true    # false: a paper with no code of its own
    patterns = ["ABC\\\\d{5}"]       # extra accession patterns (regex)
    disable = ["PDB"]              # built-in pattern names to drop
    placeholders = ["to be added"] # extra placeholder patterns (regex)
    section = "Deposited data"     # extra section-title regex

    uv run paper tool availability           # report; exit 1 on a finding
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from paths import ROOT  # the manuscript (tools/paths.py)

# name -> accession regex. Group 1, when present, is the identifier itself.
# Field-neutral: proteomics, structures, sequencing, imaging, metabolomics and
# the general-purpose archives. A paper adds its own under `patterns`.
PATTERNS: dict[str, str] = {
    "PRIDE/ProteomeXchange": r"\bPXD\d{6}\b",
    "MassIVE": r"\bMSV\d{9}\b",
    "jPOST": r"\bJPST\d{6}\b",
    "PDB": r"\bPDB(?:\s+(?:ID|entry|code))?:?\s+([1-9][A-Za-z0-9]{3})\b",
    "EMDB": r"\bEMD-\d{4,5}\b",
    "EMPIAR": r"\bEMPIAR-\d{5}\b",
    "GEO": r"\bGS[EM]\d{3,}\b",
    "SRA/ENA": r"\b(?:SR[RPXS]|ER[RPXS]|DR[RPX])\d{6,}\b",
    "BioProject": r"\bPRJ(?:NA|EB|DB)\d+\b",
    "ArrayExpress": r"\bE-[A-Z]{4}-\d+\b",
    "MetaboLights": r"\bMTBLS\d+\b",
    "Zenodo": r"\b10\.5281/zenodo\.\d+\b",
    "figshare": r"\b10\.6084/m9\.figshare\.\d+(?:\.v\d+)?\b",
    "Dryad": r"\b10\.5061/dryad\.[a-z0-9]+\b",
    "OSF": r"\b10\.17605/OSF\.IO/[A-Z0-9]+\b",
    "Software Heritage": r"\bswh:1:[a-z]{3}:[0-9a-f]{40}\b",
}
# Identifiers that count as ARCHIVED code (a Git host URL does not: it can be
# rewritten or deleted after publication).
ARCHIVES = ("Zenodo", "figshare", "Dryad", "OSF", "Software Heritage")
PLACEHOLDERS = (r"X{5,}", r"(?i)currently private", r"\[AUTHOR ACTION",
                r"\bTBD\b", r"(?i)\bto be deposited\b")
SECTION = r"(?i)\b(?:data|code|software)\b[^\n]{0,40}?\bavailab"
HEADING = re.compile(r"(?m)^[ \t]*(?:=+[ \t]+(?P<h>[^\n]*)|#heading\([^\[\n]*\[(?P<hh>[^\]\n]*)\])")
RUNIN = re.compile(r"(?m)^[ \t]*\*(?P<r>[^*\n]{1,80})\*")
END = re.compile(r"#bibliography(?:x)?\(")


@dataclass(frozen=True)
class Finding:
    kind: str
    message: str


def settings(root: Path) -> dict:
    from project_hooks import load
    return load(root).availability


def _strip(src: str) -> str:
    from manuscript_sources import mask
    return mask(src)


def sections(src: str, title: str = SECTION) -> list[tuple[int, int]]:
    """(start, end) spans of every availability section in one source.

    A heading's section runs to the next heading (its bold run-ins, such as
    `*Data.*` and `*Code.*`, are part of it); a bold run-in's to the next
    heading or run-in. Either stops at the reference list.
    """
    heads = [(m.start(), m.group("h") or m.group("hh") or "") for m in HEADING.finditer(src)]
    runins = [(m.start(), m.group("r")) for m in RUNIN.finditer(src)]
    stops = [m.start() for m in END.finditer(src)] + [len(src)]
    rx = re.compile(title)
    spans = []
    for starts, bounds in ((heads, [s for s, _ in heads] + stops),
                           (runins, [s for s, _ in heads + runins] + stops)):
        for start, text in starts:
            if rx.search(text):
                spans.append((start, min(e for e in bounds if e > start)))
    spans.sort()
    merged: list[tuple[int, int]] = []
    for a, b in spans:  # a run-in inside a matching heading's section
        if merged and a < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def check(root: Path = ROOT, sources: dict[str, str] | None = None,
          config: dict | None = None) -> list[Finding]:
    config = settings(root) if config is None else config
    if not config.get("enabled", True):
        return []
    if sources is None:
        from manuscript_sources import source_files
        sources = source_files(root)
    if not sources:
        return []  # no manuscript here: nothing to hold to a statement
    title = SECTION
    if config.get("section"):
        title = f"(?:{SECTION})|(?:{config['section']})"
    patterns = {k: v for k, v in PATTERNS.items() if k not in config.get("disable", ())}
    for i, p in enumerate(config.get("patterns", ())):
        patterns[f"pattern {i + 1}"] = p
    compiled = {k: re.compile(v) for k, v in patterns.items()}

    statement, body, found_section = [], [], False
    findings: list[Finding] = []
    placeholder = [re.compile(p) for p in PLACEHOLDERS + tuple(config.get("placeholders", ()))]
    for name, raw in sources.items():
        src = _strip(raw)
        spans = sections(src, title)
        found_section |= bool(spans)
        rest, last = [], 0
        for a, b in spans:
            statement.append(src[a:b])
            rest.append(src[last:a])
            last = b
        rest.append(src[last:])
        body.append((name, "".join(rest)))
        for rx in placeholder:
            for m in rx.finditer(src):
                line = src.count("\n", 0, m.start()) + 1
                findings.append(Finding("placeholder",
                    f"{name}:{line}: placeholder {m.group(0)!r} left in the text"))
    text = "\n".join(statement)

    def ids(rx, s):
        return {(m.group(1) if rx.groups else m.group(0)) for m in rx.finditer(s)}

    used: dict[str, tuple[str, str]] = {}
    for name, src in body:
        for kind, rx in compiled.items():
            for acc in ids(rx, src):
                used.setdefault(acc.upper(), (kind, name))
    listed = {a.upper() for rx in compiled.values() for a in ids(rx, text)}
    for acc, (kind, name) in sorted(used.items()):
        if acc not in listed:
            findings.append(Finding("missing",
                f"{kind} {acc} is cited in {name} but not in the availability statement"))
    need_archive = config.get("require_code_archive", True)
    if (used or need_archive) and not found_section:
        findings.append(Finding("no-section",
            "no Data or Code Availability section (a heading or bold run-in "
            "naming data, code or software availability)"))
    elif need_archive and not any(ids(compiled[k], text) for k in ARCHIVES if k in compiled):
        findings.append(Finding("no-archive",
            "no archived code: give a Zenodo, figshare, Software Heritage, OSF "
            "or Dryad identifier in the availability statement (or set "
            "[availability] require_code_archive = false in project.toml)"))
    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        findings = check(args.root.resolve())
    except (OSError, ValueError, re.error) as exc:
        print(f"availability check failed: {exc}", file=sys.stderr)
        return 2
    for f in findings:
        print(f"AVAILABILITY: {f.message}")
    if not findings:
        print("availability: every cited accession is in the statement, and the code is archived")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
