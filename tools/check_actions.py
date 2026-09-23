#!/usr/bin/env python3
"""Validate the review action ledger, reviews/ACTIONS.md, and count what is open.

WHY THIS EXISTS. Each review skill writes a dated findings file under reviews/,
and nothing used to record which of those findings had since been fixed. The
next review raised them again, and an editing agent had no list of what was
still outstanding. The ledger is that list: one markdown table, appended to by
the review skills and closed by the editing skills. It is hand-editable on
purpose, so this checks that the edits left it parseable.

What it checks: the table header is present exactly once with the fixed
columns, every row has seven cells, ids are `A-` plus digits and unique,
severity and status take their allowed values, and every done or wontfix row
says in `closed` how (a commit hash, `uncommitted: <note>`, or a reason).

What it does not do: fail on open work. Open blockers print a WARNING line and
the exit status stays 0; a ledger with open items is a manuscript with work
left, not a broken one. A missing ledger is a silent pass, because a paper that
has never been reviewed has nothing to track.

Usage:
    just check-actions             # validate; print open counts and the next id
    just check-actions --open      # also list the open rows, blockers first
    just check-actions --init      # create reviews/ACTIONS.md from the template

Exit status: 0 valid or absent, 1 malformed, 2 --init refused.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "reviews" / "ACTIONS.md"
TEMPLATE = ROOT / "tools" / "actions-template.md"

COLUMNS = ("id", "severity", "status", "source", "summary", "fix", "closed")
SEVERITIES = ("blocker", "major", "minor")
STATUSES = ("open", "done", "wontfix")
ID_RE = re.compile(r"^A-(\d{4,})$")
SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")


def split_row(line: str) -> list[str]:
    """The cells of one markdown table line. `\\|` is a literal pipe."""
    body = line.strip()
    body = body.removeprefix("|")
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", body)]


def parse(text: str) -> tuple[list[dict[str, str]], list[str]]:
    """Rows of the ledger table and every format error, with line numbers."""
    lines = text.splitlines()
    headers = [i for i, line in enumerate(lines)
               if line.lstrip().startswith("|")
               and tuple(c.lower() for c in split_row(line)) == COLUMNS]
    if not headers:
        return [], ["no ledger table: expected the header row | "
                    + " | ".join(COLUMNS) + " |"]
    if len(headers) > 1:
        return [], [f"line {i + 1}: a second ledger header; keep one table"
                    for i in headers[1:]]

    start = headers[0] + 1
    if start >= len(lines) or not all(SEPARATOR_RE.match(c) for c in split_row(lines[start])):
        return [], [f"line {start + 1}: expected the |---|---| separator under the header"]

    rows: list[dict[str, str]] = []
    errors: list[str] = []
    seen: dict[str, int] = {}
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not line.lstrip().startswith("|"):
            break                              # the table ends at the first non-row
        n = i + 1
        cells = split_row(line)
        if len(cells) != len(COLUMNS):
            errors.append(f"line {n}: {len(cells)} cells, expected {len(COLUMNS)} "
                          "(a pipe inside a cell is written \\|)")
            continue
        row = dict(zip(COLUMNS, cells))
        row["line"] = str(n)
        rid = row["id"]
        if not ID_RE.match(rid):
            errors.append(f"line {n}: id {rid!r} is not A- plus four or more digits")
        elif rid in seen:
            errors.append(f"line {n}: id {rid} already used on line {seen[rid]}")
        else:
            seen[rid] = n
        if row["severity"] not in SEVERITIES:
            errors.append(f"line {n}: severity {row['severity']!r} is not one of "
                          + ", ".join(SEVERITIES))
        if row["status"] not in STATUSES:
            errors.append(f"line {n}: status {row['status']!r} is not one of "
                          + ", ".join(STATUSES))
        for col in ("source", "summary", "fix"):
            if not row[col]:
                errors.append(f"line {n}: {rid or 'row'} has an empty {col}")
        if row["status"] in ("done", "wontfix") and not row["closed"]:
            errors.append(f"line {n}: {rid} is {row['status']} but `closed` is empty "
                          "(a commit hash, `uncommitted: <note>`, or a reason)")
        rows.append(row)
    return rows, errors


def next_id(rows: list[dict[str, str]]) -> str:
    nums = [int(m.group(1)) for r in rows if (m := ID_RE.match(r["id"]))]
    return f"A-{(max(nums) + 1 if nums else 1):04d}"


def summarize(rows: list[dict[str, str]]) -> list[str]:
    open_rows = [r for r in rows if r["status"] == "open"]
    by_sev = {s: sum(r["severity"] == s for r in open_rows) for s in SEVERITIES}
    done = sum(r["status"] == "done" for r in rows)
    wontfix = sum(r["status"] == "wontfix" for r in rows)
    out = [f"actions: {len(open_rows)} open ("
           + ", ".join(f"{by_sev[s]} {s}" for s in SEVERITIES)
           + f"), {done} done, {wontfix} wontfix; next id {next_id(rows)}"]
    blockers = [r["id"] for r in open_rows if r["severity"] == "blocker"]
    if blockers:
        out.append(f"WARNING: {len(blockers)} open blocker(s) in reviews/ACTIONS.md: "
                   + ", ".join(blockers))
    return out


def list_open(rows: list[dict[str, str]]) -> list[str]:
    order = {s: i for i, s in enumerate(SEVERITIES)}
    open_rows = sorted((r for r in rows if r["status"] == "open"),
                       key=lambda r: (order.get(r["severity"], 9), r["id"]))
    return [f"  {r['id']}  {r['severity']:<7}  {r['fix']:<24}  {r['summary']}"
            for r in open_rows]


def main(argv: list[str] | None = None, ledger: Path = LEDGER,
         template: Path = TEMPLATE) -> int:
    ap = argparse.ArgumentParser(description="Validate reviews/ACTIONS.md.")
    ap.add_argument("--open", action="store_true", help="list the open rows")
    ap.add_argument("--init", action="store_true",
                    help="create the ledger from the template if it is missing")
    args = ap.parse_args(argv)

    if args.init:
        if ledger.exists():
            print(f"{ledger} already exists; left untouched", file=sys.stderr)
            return 2
        if not template.is_file():
            print(f"template {template} is missing", file=sys.stderr)
            return 2
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(template.read_text())
        print(f"created {ledger} from the template")
        return 0

    if not ledger.is_file():
        return 0                               # never reviewed: nothing to track

    rows, errors = parse(ledger.read_text())
    if errors:
        print(f"reviews/ACTIONS.md is malformed ({len(errors)} problem(s)):")
        for e in errors:
            print(f"  {e}")
        return 1
    for line in summarize(rows):
        print(line)
    if args.open:
        for line in list_open(rows):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
