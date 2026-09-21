#!/usr/bin/env python3
"""Optional source-based vocabulary review. Never predicts AI authorship.

Shares the manuscript's prose cleaner; literal includes are expanded, imports
are not evaluated. Counts exact case-insensitive tokens, not word families.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from document_project import body_span, keys, load_project, tomllib
from manuscript_sources import mask, matches
import readability
import typst_prose

ROOT = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r"\b[^\W\d_]+(?:[-'’][^\W\d_]+)*\b")
INCLUDE = re.compile(r'#include\s+"([^"\n]+)"')


def load_manifest(path: Path) -> dict:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    keys(data, {"schema_version", "words", "source", "extensions", "allow"},
         str(path))
    if type(data.get("schema_version")) is not int or data["schema_version"] != 2:
        raise ValueError("word watchlist: schema_version must be 2 (counts only; no limits)")
    def validate_group(group):
        words = group.get("words")
        if (not isinstance(words, list) or not words
                or any(not isinstance(w, str) or not re.fullmatch(r"[a-z]+", w)
                       for w in words) or len(set(words)) != len(words)):
            raise ValueError("word watchlist: words must be unique lowercase words")
        source = group.get("source", {})
        if not isinstance(source, dict):
            raise ValueError("word watchlist: source must be a table")
        kind = source.get("kind", "research")
        if kind not in ("research", "editorial"):
            raise ValueError("word watchlist: source.kind must be research or editorial")
        required = ("citation", "location", "note") if kind == "editorial" else (
            "citation", "url", "location")
        if not all(
                isinstance(source.get(k), str) and source[k].strip()
                for k in required):
            raise ValueError(f"word watchlist: {kind} source needs {', '.join(required)}")

    validate_group(data)
    words = list(data["words"])
    word_sources = dict.fromkeys(words, "primary")
    extensions = data.setdefault("extensions", [])
    if not isinstance(extensions, list):
        raise ValueError("word watchlist: extensions must be an array of tables")
    ids = {"primary"}
    for group in extensions:
        keys(group, {"id", "words", "source"}, "extension")
        name = group.get("id")
        if (not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", name)
                or name in ids):
            raise ValueError("word watchlist: extension ids must be unique lowercase IDs")
        validate_group(group)
        if set(group["words"]) & set(words):
            raise ValueError("word watchlist: words must be unique across groups")
        ids.add(name)
        words.extend(group["words"])
        word_sources.update(dict.fromkeys(group["words"], name))
    data["words"] = words
    data["word_sources"] = word_sources
    allow = data.setdefault("allow", {})
    if not isinstance(allow, dict) or any(
            w not in words or not isinstance(reason, str) or not reason.strip()
            for w, reason in allow.items()):
        raise ValueError("allow must map watched words to nonempty reasons")
    return data


def expand(src: str, path: Path, root: Path, stack=()) -> str:
    """Expand literal includes, rejecting missing, cyclic or dynamic sources."""
    path = path.resolve()
    if path in stack:
        raise ValueError(f"cyclic prose include: {path}")
    src = mask(src)  # Removes comments and raw code, preserving line breaks.
    calls = matches(INCLUDE, src)
    rest = list(mask(src, strings=True))
    for m in calls:
        rest[m.start():m.end()] = " " * (m.end() - m.start())
    if re.search(r"#include\b", "".join(rest)):
        raise ValueError(f"{path}: dynamic prose includes are unsupported")
    for m in reversed(calls):
        target = (root / m[1].lstrip("/") if m[1].startswith("/")
                  else path.parent / m[1]).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"prose include outside project: {m[1]}")
        body = expand(target.read_text(encoding="utf-8"), target, root, (*stack, path))
        src = src[:m.start()] + body + src[m.end():]
    return src


def abstract(root: Path) -> str:
    path = root / "config.typ"
    src = mask(path.read_text(encoding="utf-8"))
    visible = mask(src, strings=True)
    m = re.search(r"#let\s+paper-abstract\s*=\s*\[", visible)
    if not m:
        raise ValueError("config.typ: expected a literal paper-abstract = [...] block")
    depth = 1
    for i in range(m.end(), len(visible)):
        if i and visible[i - 1] == "\\":
            continue
        depth += (visible[i] == "[") - (visible[i] == "]")
        if depth == 0:
            return expand(src[m.end():i], path, root)
    raise ValueError("config.typ: unclosed paper-abstract block")


def sources(root: Path, document: str | None) -> dict[str, str]:
    if document or (root / "manuscript.toml").exists():
        project = load_project(root)
        result = {}
        for doc in project.select(document):
            project.sources(doc)
            for name in doc.parts:
                part = project.parts[name]
                result[f"{doc.id}/{name}"] = project.prose(part)
        return result
    path = root / "paper.typ"
    src = path.read_text(encoding="utf-8")
    start, end = body_span(src, "paper.typ")
    result = {"Abstract": abstract(root),
              "Main text": expand(src[start:end], path, root)}
    si = root / "si-body.typ"
    if si.exists():
        result["SI"] = expand(si.read_text(encoding="utf-8"), si, root)
    return result


def prose_tokens(src: str) -> list[str]:
    """Count cleaned prose without depending on paragraph boundaries."""
    src = mask(src)
    for opener in ("#figure(", "#table(", "#raw(",
                   *typst_prose.BIBLIOGRAPHY_CALLS):
        src = typst_prose.strip_balanced(src, opener, " ")
    return TOKEN.findall(readability.clean(src).lower())


def audit(document: str, src: str | dict[str, str], manifest: dict) -> dict:
    parts = {document: src} if isinstance(src, str) else src
    counts = Counter(w for text in parts.values() for w in prose_tokens(text))
    rows = []
    for word in manifest["words"]:
        if counts[word]:
            rows.append({"word": word, "source": manifest["word_sources"][word],
                         "count": counts[word], "exception": manifest["allow"].get(word)})
    rows.sort(key=lambda r: (-r["count"], r["word"]))
    return {"document": document, "prose_words": sum(counts.values()),
            "flagged_occurrences": sum(r["count"] for r in rows if not r["exception"]),
            "distinct_flagged_words": sum(not r["exception"] for r in rows),
            "allowed_occurrences": sum(r["count"] for r in rows if r["exception"]),
            "matches": rows}


def documents(root: Path, document: str | None) -> dict[str, dict[str, str]]:
    """Combine parts within each target; never add alternative exports together."""
    parts = sources(root, document)
    if not document and not (root / "manuscript.toml").exists():
        return {"Manuscript (abstract + main text + SI)": parts}
    grouped = {}
    for name, src in parts.items():
        target, part = name.split("/", 1)
        grouped.setdefault(target, {})[part] = src
    return grouped


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "word-watchlist.toml")
    parser.add_argument("--document", help="named manuscript.toml target (or all)")
    parser.add_argument("--json", action="store_true", help="print counts and source metadata as JSON")
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        rows = [audit(name, parts, manifest)
                for name, parts in documents(ROOT, args.document).items()]
    except (OSError, ValueError) as exc:
        print(f"word-audit: {exc}", file=sys.stderr)
        return 1
    report = {"schema_version": 2, "source": manifest["source"],
              "extensions": manifest["extensions"], "allow": manifest["allow"],
              "documents": rows}
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    print(f"Word audit: {len(manifest['words'])} watched word forms.")
    for row in rows:
        print(f"\n{row['document']}")
        print(f"  Flagged word occurrences: {row['flagged_occurrences']} "
              f"({row['distinct_flagged_words']} distinct words)")
        for match in row["matches"]:
            suffix = f" (allowed: {match['exception']})" if match["exception"] else ""
            print(f"  {match['word']}: {match['count']}{suffix}")
        if row["allowed_occurrences"]:
            print(f"  Allowed occurrences excluded from total: {row['allowed_occurrences']}")
    print("\nCounts for editorial review, not an AI detector or a pass/fail score.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
