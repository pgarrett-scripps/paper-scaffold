"""Run existing prose rules over declared parts, with chapter bibliographies."""
from __future__ import annotations

from dataclasses import replace
import re

from document_project import Project, Document
from manuscript_sources import mask
import prose_check as pc
from prose_rules import Finding, load_config, report
import readability
import typst_prose


def check(project: Project, document: Document, *, strict=False) -> int:
    sources = project.sources(document)
    cfg = load_config(project.root)
    readability.add_abbreviations(sorted(cfg.vocabulary("abbreviations", set())))
    targets = {project.parts[p].source: project.prose(project.parts[p]) for p in document.parts}
    saved = typst_prose.STATS_JSON
    typst_prose.STATS_JSON = project.root / "stats.json"
    findings = []
    try:
        for path, src in targets.items():
            findings += pc.check(path, readability.clean(src),
                                 readability.clean(pc.no_code(src)),
                                 readability.clean(src, gap=pc.GAP), cfg)
        findings += pc.check_structure(targets)
        findings += pc.check_derivable_numbers(targets, stats_path=project.root / "stats.json")
        findings += pc.check_unaccounted_numbers(targets, stats_path=project.root / "stats.json")
        findings += pc.check_bypassed_assets(targets, assets_path=project.root / "assets.json")
        findings += pc.check_todos(targets)
        if cfg.runs("list-in-prose") or cfg.runs("bold-in-prose"):
            findings += pc.check_house_style(targets)
        # Legacy chapter drafts use visible [TODO: ...] rather than todo().
        for path, src in targets.items():
            for m in re.finditer(r"\[TODO[^\]\n]*", mask(src)):
                findings.append(Finding("unresolved-todo", "warn", m[0], where=path))
        # Citation prefixes are identities, not part of the BibTeX key. Keep
        # independent chapter bibliographies separate even when keys coincide.
        visible = "\n".join(mask(src) for src in sources.values())
        citations = set(re.findall(r"@([A-Za-z0-9_:-]+)", visible))
        for name in document.parts:
            part = project.parts[name]
            if part.bibliography is None:
                continue
            cited = {key[len(part.citation_prefix):] for key in citations
                     if key.startswith(part.citation_prefix)}
            rows = pc.check_bibliography(project.root, cfg,
                        bib_paths=[project.root / part.bibliography], cited_keys=cited)
            findings += [replace(row, where=part.bibliography) for row in rows]
    finally:
        typst_prose.STATS_JSON = saved
    return report(findings, cfg, show_suppressed=False, strict=strict)
