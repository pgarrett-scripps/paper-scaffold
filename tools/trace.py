"""Trace a declared statistic or asset to its uses, inputs, and current checks.

This command reads declarations and source files; it never runs analysis or
changes a declaration. JSON is a versioned interface for agents. Exit codes:
0 checked, 1 failed checks, 2 incomplete inspection or invalid request.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import check_assets
import check_stats
import check_evidence
import evidence as evidence_manifest
from manifest_validation import load
from manuscript_sources import usages
from typst_prose import display_of

from paths import ROOT  # the manuscript (tools/paths.py)


def inspect(id: str, root: Path = ROOT, kind: str | None = None) -> dict:
    documents = {k: load(root / name, k) if (root / name).is_file() else {"values": {}}
                 for k, name in (("stats", "stats.json"), ("assets", "assets.json"))}
    candidates = [k for k, doc in documents.items() if id in doc["values"]
                  and (kind is None or k == kind)]
    if len(candidates) != 1:
        raise ValueError(f"{id!r}: " + ("ambiguous; pass --kind stats or --kind assets"
                                       if candidates else "no matching declaration"))
    kind = candidates[0]
    doc = documents[kind]
    declaration = doc["values"][id]
    checks = []

    def add(rule, findings, command):
        for item in findings:
            status = "failed" if item.level == "error" else (
                "incomplete" if item.level in ("note", "incomplete") else "warning")
            checks.append({"rule": rule, "status": status, "subject": item.id,
                           "message": item.msg, "command": command})

    # Existing checks resolve paths through their module ROOT. Keep the override
    # local and reversible for scratch-tree inspection and test fixtures.
    old_stats, old_assets = check_stats.ROOT, check_assets.ROOT
    check_stats.ROOT = check_assets.ROOT = root
    try:
        if kind == "stats":
            add("stats.origin", check_stats._origin(id, declaration), None)
            add("stats.guard", check_stats._guard(id, declaration), None)
            add("stats.format", check_stats._display({id: declaration}), None)
            add("stats.checksum", check_stats._checksum({id: declaration}), "just assets")
            owner = (declaration.get("origin") or {}).get("by")
            inputs = (doc.get("sources") or {}).get(owner, {})
            add("stats.inputs", check_stats._sources({"sources": {owner or id: inputs}}),
                "just assets")
            if owner != "hand" and (not declaration.get("checksum") or not inputs):
                checks.append({"rule": "stats.provenance_missing", "status": "incomplete",
                               "subject": id, "message": "generated entry lacks checksum or source hashes",
                               "command": "just assets"})
            helpers = ("s", "n")
        else:
            add("assets.integrity", check_assets._entry(id, declaration),
                None if (declaration.get("origin") or {}).get("by") == "adopted" else "just assets")
            inputs = declaration.get("inputs", {})
            helpers = ("fig", "tbl")
    finally:
        check_stats.ROOT, check_assets.ROOT = old_stats, old_assets

    evidence = _evidence(root, id, kind, declaration, inputs, documents, add)

    uses = [u for u in usages(root) if u["id"] == id and u["helper"] in helpers]
    status = ("failed" if any(c["status"] == "failed" for c in checks) else
              "incomplete" if any(c["status"] == "incomplete" for c in checks) else "ok")
    commands = list(dict.fromkeys(c["command"] for c in checks if c["command"]))
    result = {"schema_version": 1, "id": id, "kind": kind, "status": status,
              "declaration": declaration, "inputs": inputs, "evidence": evidence, "uses": uses,
              "findings": checks, "suggested_commands": commands,
              "scope": {"rederived": False, "inputs": "declared inputs only",
                        "uses": "literal calls in entrypoints and slide decks, and literal Typst includes/imports",
                        "meaning": "checks establish consistency, not scientific correctness"}}
    if kind == "stats":
        try:
            result["display"] = display_of(declaration)
        except (TypeError, ValueError):
            result["display"] = None
    return result


def _evidence(root, id, kind, declaration, inputs, documents, add) -> dict:
    """The evidence sets behind one entry: the versions it was built from,
    what evidence.toml declares now, and the check-evidence findings for it."""
    try:
        manifest = evidence_manifest.load(root)
    except evidence_manifest.EvidenceError as exc:
        add("evidence.manifest", [check_evidence.Finding("error", id, str(exc))],
            None)
        return {}
    recorded = declaration.get("evidence") or {}
    names = set(recorded)
    if manifest is not None:
        names.update(manifest.covering(id, kind))
        for rel in inputs:
            names.update(manifest.containing(root, rel))
    out = {}
    for name in sorted(names):
        s = manifest.sets.get(name) if manifest else None
        out[name] = {"recorded": recorded.get(name),
                     "declared": s.produced_by() if s else None,
                     "paths": list(s.paths) if s else [],
                     "status": s.status if s else None,
                     "verify": s.verify if s else None}
    pending = {}
    for doc in documents.values():
        pending.update(doc.get("pending") or {})
    if manifest is not None:
        docs = {"stats": {"values": {}}, "assets": {"values": {}}}
        docs[kind] = {"values": {id: declaration}}
        found = [f for f in check_evidence._entries(manifest, docs) if f.id == id]
        add("evidence.versions", found, "just assets")
    from manifest_validation import pending_match
    reason = pending_match(pending, id)
    if reason:
        add("evidence.pending", [check_evidence.Finding(
            "error", id, f"declared pending: {reason}")], None)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("id")
    parser.add_argument("--json", action="store_true", help="emit one schema-versioned JSON object")
    parser.add_argument("--kind", choices=("stats", "assets"))
    args = parser.parse_args()
    try:
        result = inspect(args.id, kind=args.kind)
        code = {"ok": 0, "failed": 1, "incomplete": 2}[result["status"]]
    except (OSError, ValueError) as exc:
        result = {"schema_version": 1, "id": args.id, "status": "incomplete",
                  "findings": [{"rule": "trace.input", "status": "incomplete",
                                "message": str(exc), "command": None}]}
        code = 2
    result["exit_code"] = code
    if args.json:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    else:
        print(f"{args.id}: {result['status']}")
        if "declaration" in result:
            print(json.dumps(result["declaration"], ensure_ascii=False, indent=2))
            for use in result["uses"]:
                print(f"  {use['path']}:{use['line']}  {use['context']}")
            print("  scope: recorded consistency; analysis was not re-run")
        for item in result["findings"]:
            print(f"  {item['rule']}: {item['message']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
