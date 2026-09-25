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
    cfg = load_config(project.root)
    readability.add_abbreviations(sorted(cfg.vocabulary("abbreviations", set())))
    return report(findings(project, document, cfg), cfg, show_suppressed=False,
                  strict=strict)


def covering(project: Project) -> list[Document]:
    """The fewest documents, default first, that between them hold every part.

    `just prose-check` on a multi-document project checks each part once, in
    the context of a document that really contains it, so a part shared by
    the whole thesis and its chapter PDF is not reported twice.
    """
    order = sorted(project.documents.values(), key=lambda d: d.id != project.default)
    chosen, seen = [], set()
    for doc in order:
        if set(doc.parts) - seen:
            chosen.append(doc)
            seen |= set(doc.parts)
    return chosen


def findings(project: Project, document: Document, cfg) -> list[Finding]:
    """Every prose and chapter-bibliography finding for one document."""
    sources = project.sources(document)
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
        findings += pc.claim_rules.claim_findings(targets, project.root / "stats.json")
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
        findings += routing(project, document)
    finally:
        typst_prose.STATS_JSON = saved
    return findings


def routing(project: Project, document: Document) -> list[Finding]:
    """`misrouted-citation` for chapter bibliographies (the SI rule, per part).

    Alexandria routes a citation to a chapter's list by its prefix. `@pep-x`
    written in the UNO chapter compiles in the whole thesis and prints in the
    peptacular chapter's references, where a reader of UNO never looks; a
    bare `@x` whose entry is in the chapter's own file misses that list. Only
    a key the named bibliography really holds is reported, so a figure label
    that happens to share a prefix is never flagged.
    """
    lists = {name: part for name, part in project.parts.items()
             if part.bibliography and part.citation_prefix}
    keys: dict[str, set[str]] = {}
    for name, part in lists.items():
        try:
            keys[name] = {e["_key"] for e in pc._bib_entries(project.root / part.bibliography)}
        except (OSError, ValueError):
            keys[name] = set()          # check_bibliography reports the parse
    out = []
    for name in document.parts:
        part = lists.get(name)
        if part is None:
            continue
        src = project.prose(part)
        code = mask(src, strings=True)
        for m in re.finditer(r"(?<![\w\\:./-])" + typst_prose.CITE, mask(src)):
            if not code[m.start():m.start() + 1].strip():
                continue                # inside a string, not a citation
            key = m.group(0)[1:]
            if key.startswith(part.citation_prefix):
                continue
            other = next((o for o, p in lists.items() if o != name
                          and key.startswith(p.citation_prefix)
                          and key[len(p.citation_prefix):] in keys[o]), None)
            if other is not None:
                bare = key[len(lists[other].citation_prefix):]
                message = (f"@{key} in part {name} prints in part {other}'s "
                           f"reference list ({lists[other].bibliography}), not "
                           f"this chapter's; add the entry to {part.bibliography} "
                           f"and write @{part.citation_prefix}{bare}")
            elif key in keys[name]:
                message = (f"@{key} in part {name} has no "
                           f"{part.citation_prefix!r} prefix, so it misses the "
                           f"chapter's reference list; write "
                           f"@{part.citation_prefix}{key}")
            else:
                continue
            out.append(Finding("misrouted-citation", "error", message,
                               subject=key, where=part.source))
    return out
