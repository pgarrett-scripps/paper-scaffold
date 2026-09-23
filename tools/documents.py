#!/usr/bin/env python3
"""Build/check named PDF documents from manuscript.toml (opt-in chapter support)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from document_project import load_project
import document_build

from paths import ROOT, tool  # the manuscript (tools/paths.py)


def print_metrics(data: dict):
    for row in data["parts"] if len(data["parts"]) > 1 else ():
        r = row["readability"]
        print(f"  {row['id']}: {row['words']:,} words; FK {r['fk']:.1f}, "
              f"ease {r['ease']:.1f}, fog {r['fog']:.1f}")
    r = data["readability"]
    print(f"{data['document']}: {data['words']:,} words; FK {r['fk']:.1f}, "
          f"ease {r['ease']:.1f}, fog {r['fog']:.1f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list", "build", "check", "metrics", "prose", "verify"))
    parser.add_argument("document", nargs="?")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", help="structured list, metrics or staleness")
    parser.add_argument("--strict", action="store_true", help="treat prose warnings as errors")
    args = parser.parse_args()
    try:
        project = load_project(args.root)
        if args.json and args.command not in ("list", "check", "metrics"):
            raise ValueError("--json supports list, check and metrics")
        selected = project.select("all" if args.command == "list" else args.document)
        rows, rc = [], 0
        if args.command == "verify":
            # Declarations are project-wide: changing a shared result can affect
            # multiple chapters. Use the same recorded-provenance checks as paper.
            for manifest, checker in (("stats.json", "check_stats.py"),
                                      ("assets.json", "check_assets.py")):
                if (project.root / manifest).is_file():
                    result = subprocess.run([sys.executable, str(tool(checker))],
                                            cwd=project.root)
                    rc = max(rc, int(result.returncode != 0))
        for doc in selected:
            if args.command == "list":
                rows.append(vars(doc))
                if not args.json:
                    print(f"{doc.id}: {doc.entrypoint} -> {doc.output}")
            elif args.command in ("build", "metrics"):
                data = (document_build.build(project, doc) if args.command == "build"
                        else document_build.saved_metrics(project, doc))
                rows.append(data)
                if not args.json:
                    print_metrics(data)
            else:
                if args.command in ("prose", "verify"):
                    from document_check import check
                    print(f"{doc.id}: prose and chapter bibliographies")
                    rc = max(rc, check(project, doc, strict=args.strict))
                if args.command in ("check", "verify"):
                    status = document_build.status(project, doc)
                    rows.append({"document": doc.id, "output": doc.output, "status": status})
                    if not args.json:
                        print(f"{doc.id}: {status}" + ("" if status == "current" else
                              f"; rebuild with just document {doc.id}"))
                    rc = max(rc, int(status != "current"))
        if args.json:
            print(json.dumps(rows, indent=2))
        return rc
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f"document operation incomplete: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
