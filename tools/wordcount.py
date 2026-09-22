#!/usr/bin/env python3
"""Journal word counts and optional section-scoped word limits.

Typst/wordometer owns counting. This module selects disjoint counted sections
and checks inclusive bounds; it never tokenizes manuscript prose itself.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

from document_project import keys, tomllib

ROOT = Path(__file__).resolve().parent.parent
CONFIG = "word-limits.toml"
REGIONS = ("abstract", "main", "si")


def load_checks(root: Path) -> list[dict]:
    path = root / CONFIG
    if not path.exists():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    keys(data, {"schema_version", "checks"}, CONFIG)
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError(f"{CONFIG}: schema_version must be 1")
    checks = data.get("checks", [])
    if not isinstance(checks, list):
        raise ValueError(f"{CONFIG}: checks must use [[checks]] tables")
    names = set()
    for spec in checks:
        keys(spec, {"name", "include", "exclude", "min", "max"}, "word check")
        name = spec.get("name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("word checks need distinct, nonempty names")
        names.add(name)
        for field in ("include", "exclude"):
            values = spec.get(field, [] if field == "exclude" else None)
            if (not isinstance(values, list) or (field == "include" and not values)
                    or any(not isinstance(v, str) or not v or v.endswith("/")
                           for v in values) or len(set(values)) != len(values)):
                raise ValueError(f"{name}: {field} must contain unique section paths"
                                 + (" (at least one)" if field == "include" else ""))
            spec[field] = values
        for bound in ("min", "max"):
            if bound in spec and (type(spec[bound]) is not int or spec[bound] < 0):
                raise ValueError(f"{name}: {bound} must be a nonnegative integer")
        if "min" in spec and "max" in spec and spec["min"] > spec["max"]:
            raise ValueError(f"{name}: min must not exceed max")
    return checks


def contains(parent: str, child: str) -> bool:
    return child == parent or child.startswith(parent + "/")


def evaluate(checks: list[dict], sections: list[dict]) -> list[dict]:
    headings = Counter(row["id"] for row in sections if row["heading"])
    known = set(REGIONS) | set(headings)
    results = []
    for spec in checks:
        for selector in spec["include"] + spec["exclude"]:
            if selector not in known:
                raise ValueError(f"{spec['name']}: unknown section {selector!r}; "
                                 "run just wordcount --sections")
            if headings[selector] > 1:
                raise ValueError(f"{spec['name']}: ambiguous section {selector!r}; "
                                 "use distinct heading paths")
        included = {i for i, row in enumerate(sections)
                    if any(contains(s, row["id"]) for s in spec["include"])}
        for selector in spec["exclude"]:
            if not any(contains(selector, sections[i]["id"]) for i in included):
                raise ValueError(f"{spec['name']}: excluded section {selector!r} "
                                 "is outside the included scope")
        selected = [row for i, row in enumerate(sections) if i in included
                    and not any(contains(s, row["id"]) for s in spec["exclude"])]
        words = sum(row["words"] for row in selected)
        low, high = spec.get("min"), spec.get("max")
        status = ("below-min" if low is not None and words < low else
                  "above-max" if high is not None and words > high else
                  "ok" if low is not None or high is not None else "unbounded")
        results.append({**spec, "words": words, "status": status,
                        "selected_sections": [row["id"] for row in selected]})
    return results


def current_stats(root: Path) -> None:
    """A read-only check must not silently count an old formatted statistic."""
    if not (root / "stats.json").is_file():
        return
    from manifest_validation import load
    from typst_prose import display_of
    values = load(root / "stats.json", "stats")["values"]
    expected = {key: {"display": display_of(rec), "value": rec["value"]}
                for key, rec in values.items()}
    path = root / "stats-rendered.json"
    if not path.is_file() or json.loads(path.read_text()).get("values") != expected:
        raise ValueError("formatted statistics are missing or stale; run just render-stats")


def counts(root: Path) -> dict:
    current_stats(root)
    result = subprocess.run(
        ["typst", "query", "--root", str(root), "wordcount.typ", "<wc>",
         "--field", "value", "--one"], cwd=root,
        capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Typst word count failed")
    data = json.loads(result.stdout)
    if "sections" not in data:
        raise ValueError("wordcount.typ needs the section inventory; update it together "
                         "with wordcount-sections.typ and tools/wordcount.py")
    return data


def print_checks(rows: list[dict]) -> None:
    for row in rows:
        limits = ", ".join(f"{key} {row[key]:,}" for key in ("min", "max") if key in row)
        message = {"ok": "OK", "unbounded": "no limits", "below-min": "BELOW MIN",
                   "above-max": "ABOVE MAX"}[row["status"]]
        print(f"  {row['name']}: {row['words']:,} words; {limits or 'unbounded'}; {message}")
        print("    include: " + ", ".join(row["include"])
              + ("; exclude: " + ", ".join(row["exclude"]) if row["exclude"] else ""))
        if row.get("note"):
            print(f"    note: {row['note']}")


def print_counts(data: dict) -> None:
    from report import console, table
    t = table("Journal word count", caption="excludes refs, floats, captions, math, block code")
    t.add_column()
    t.add_column("words", justify="right")
    t.add_column("chars", justify="right")
    for region, label in (("abstract", "Abstract (own limit; not in total)"),
                          ("main", "Main text"), ("si", "Supporting Information"),
                          ("total", "Total (main + SI)")):
        t.add_row(label, f"{data[region + '_words']:,}", f"{data[region + '_chars']:,}")
    console.print(t)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--sections", action="store_true", help="list selectable section paths")
    parser.add_argument("--json", action="store_true", help="print counts, scopes and status as JSON")
    parser.add_argument("--check", action="store_true", help="exit nonzero for violated limits")
    args = parser.parse_args(argv)
    try:
        if args.check and args.sections:
            raise ValueError("--sections lists paths; use it separately from --check")
        root = args.root.resolve()
        # The selected journal profile's limits join the project's own, so one
        # table answers "am I within limits" whoever set them.
        from journal import word_checks
        checks = load_checks(root) + word_checks(root)
        if args.check and not checks:
            data = {"checks": [], "status": "unconfigured"}
        else:
            data = counts(root)
            # Inventory remains available to repair an outdated section selector.
            data["checks"] = [] if args.sections else evaluate(checks, data["sections"])
            data["status"] = ("failed" if any(r["status"] in ("below-min", "above-max")
                                              for r in data["checks"]) else "ok")
        data["schema_version"] = 1
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        elif data["status"] == "unconfigured":
            print(f"Word limits: no checks configured in {CONFIG}.")
        elif args.sections:
            print("Selectable sections (words include subsections):")
            for row in data["sections"]:
                if row["id"] in REGIONS or row["heading"]:
                    total = sum(s["words"] for s in data["sections"] if contains(row["id"], s["id"]))
                    print(f"  {row['id']}: {total:,}")
        else:
            if not args.check:
                print_counts(data)
            if data["checks"]:
                print("Configured word checks (inclusive bounds):")
                print_checks(data["checks"])
        return int(args.check and data["status"] == "failed")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if args.json:
            print(json.dumps({"schema_version": 1, "status": "incomplete", "error": str(exc)}))
        else:
            print(f"Word count incomplete: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
