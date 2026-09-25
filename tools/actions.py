#!/usr/bin/env python3
"""Write the review action ledger, reviews/ACTIONS.md, safely.

tools/check_actions.py reads and validates the ledger; this changes it. Two
sessions reviewing at once used to pick the same "next id" from the table and
append two different A-0012 rows, and a row closed by hand often named a hash
from before a rebase. So:

    add        append one row under a lock, with the next free id. The id comes
               from .build-state/actions-next-id as well as the table, so an id
               reserved by another session is never handed out twice.
    reserve N  hand out N ids without writing rows (review-all merges several
               findings files and writes the rows itself)
    close      read `Closes: A-0012` trailers from the git history and mark each
               named open row done with that commit's short hash (replacing an
               `uncommitted: <note>`); a row already closed with another hash
               is reported, never rewritten

check_actions.py then holds a done row's hash to the commit carrying its
Closes: trailer (tools/check_actions.py verify_hashes).

    just actions-add major "reviews/2026-09-25-claim-audit.md#row 3" "summary" "/paper:copy-edit"
    just actions-reserve 5
    just close-actions
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from paths import ROOT  # the manuscript (tools/paths.py)
import check_actions as ca

TRAILER = re.compile(r"(?mi)^Closes:[ \t]*(A-\d{4,}(?:[ \t]*,[ \t]*A-\d{4,})*)[ \t]*$")
HASH = re.compile(r"^([0-9a-f]{7,40})\b")


def _state(ledger: Path) -> Path:
    # The ledger lives at <root>/reviews/ACTIONS.md; its lock beside the build's.
    return ledger.parent.parent / ".build-state"


@contextmanager
def ledger_lock(ledger: Path, wait: float = 60.0):
    folder = _state(ledger)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "actions.lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            lock = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)  # noqa: E731
            unlock = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)  # noqa: E731
        else:
            import fcntl
            lock = lambda: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)  # noqa: E731
            unlock = lambda: fcntl.flock(stream, fcntl.LOCK_UN)  # noqa: E731
        deadline = time.monotonic() + wait
        while True:
            try:
                lock()
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise ValueError("another session is writing reviews/ACTIONS.md") from None
                time.sleep(0.2)
        try:
            yield
        finally:
            unlock()


def _load(ledger: Path) -> tuple[str, list[dict]]:
    if not ledger.is_file():
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(ca.TEMPLATE.read_text())
    text = ledger.read_text()
    rows, errors = ca.parse(text)
    if errors:
        raise ValueError("reviews/ACTIONS.md is malformed; fix it first "
                         f"(just check-actions): {errors[0]}")
    return text, rows


def allocate(ledger: Path, rows: list[dict], n: int) -> list[str]:
    """n fresh ids past both the table and the next-id file; the file moves on."""
    counter = _state(ledger) / "actions-next-id"
    try:
        floor = int(counter.read_text().strip())
    except (OSError, ValueError):
        floor = 1
    table = int(ca.next_id(rows)[2:])
    first = max(floor, table)
    counter.write_text(f"{first + n}\n")
    return [f"A-{i:04d}" for i in range(first, first + n)]


def _cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|")


def _insert(text: str, rows: list[dict], lines_to_add: list[str]) -> str:
    lines = text.splitlines()
    if rows:
        at = int(rows[-1]["line"])           # after the last row (1-based -> index)
    else:
        header = next(i for i, line in enumerate(lines)
                      if tuple(c.lower() for c in ca.split_row(line)) == ca.COLUMNS)
        at = header + 2
    lines[at:at] = lines_to_add
    return "\n".join(lines) + "\n"


def add(ledger: Path, severity: str, source: str, summary: str, fix: str) -> str:
    if severity not in ca.SEVERITIES:
        raise ValueError(f"severity must be one of {', '.join(ca.SEVERITIES)}")
    for name, value in (("source", source), ("summary", summary), ("fix", fix)):
        if not value.strip():
            raise ValueError(f"{name} must not be empty")
    with ledger_lock(ledger):
        text, rows = _load(ledger)
        rid = allocate(ledger, rows, 1)[0]
        row = f"| {rid} | {severity} | open | {_cell(source)} | {_cell(summary)} | {_cell(fix)} | |"
        ledger.write_text(_insert(text, rows, [row]))
    return rid


def reserve(ledger: Path, n: int) -> list[str]:
    if n < 1:
        raise ValueError("reserve at least one id")
    with ledger_lock(ledger):
        _, rows = _load(ledger)
        return allocate(ledger, rows, n)


def trailers(root: Path) -> dict[str, list[str]]:
    """{id: [full hashes of commits whose message carries Closes: id]}, newest first."""
    try:
        out = subprocess.run(
            ["git", "log", "-E", "-i", "--grep=^Closes:", "--format=%H%x1f%B%x1e"],
            cwd=root, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    found: dict[str, list[str]] = {}
    for record in out.split("\x1e"):
        if "\x1f" not in record:
            continue
        sha, body = record.strip().split("\x1f", 1)
        for m in TRAILER.finditer(body):
            for rid in re.split(r"[ \t]*,[ \t]*", m.group(1)):
                found.setdefault(rid.upper(), []).append(sha)
    return found


def close(ledger: Path, root: Path) -> tuple[list[str], list[str]]:
    """Close rows named by Closes: trailers. Returns (closed lines, notes)."""
    found = trailers(root)
    closed, notes = [], []
    with ledger_lock(ledger):
        if not ledger.is_file():
            return [], ["no reviews/ACTIONS.md: nothing to close"]
        text, rows = _load(ledger)
        lines = text.splitlines()
        for row in rows:
            shas = found.get(row["id"])
            if not shas:
                continue
            short = shas[0][:10]
            recorded = HASH.match(row["closed"])
            if row["status"] == "done" and recorded:
                if not any(s.startswith(recorded.group(1)) for s in shas):
                    notes.append(f"{row['id']} is closed as {recorded.group(1)} but "
                                 f"{short} carries Closes: {row['id']}; left as is")
                continue
            if row["status"] == "wontfix":
                notes.append(f"{row['id']} is wontfix but {short} says it closes it; left as is")
                continue
            cells = [row[c] for c in ca.COLUMNS]
            cells[2], cells[6] = "done", short
            lines[int(row["line"]) - 1] = "| " + " | ".join(
                c.replace("|", "\\|") for c in cells) + " |"
            closed.append(f"{row['id']} done in {short}")
        if closed:
            ledger.write_text("\n".join(lines) + "\n")
    return closed, notes


def verify_hashes(rows: list[dict], root: Path) -> tuple[list[str], list[str]]:
    """(errors, warnings) for done rows whose hash disagrees with the history.

    An error: the row names hash X but the commit carrying `Closes: <id>` is
    another. A warning: the hash names no commit here (a rebase rewrote it,
    or it was typed wrong); `uncommitted:` and reasons are not hashes.
    """
    hashed = [(r, m.group(1)) for r in rows if r["status"] == "done"
              and (m := HASH.match(r["closed"]))]
    if not hashed:
        return [], []
    try:
        if subprocess.run(["git", "rev-parse", "--git-dir"], cwd=root,
                          capture_output=True).returncode != 0:
            return [], []                               # not a repository
    except OSError:
        return [], []                                   # no git
    found = trailers(root)
    errors, warnings = [], []
    for row, sha in hashed:
        shas = found.get(row["id"], [])
        if shas and not any(s.startswith(sha) for s in shas):
            errors.append(f"line {row['line']}: {row['id']} is closed as {sha}, but "
                          f"{shas[0][:10]} carries Closes: {row['id']} (fix `closed`, "
                          "or run just close-actions)")
            continue
        try:
            ok = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=root,
                                capture_output=True).returncode == 0
        except OSError:
            return errors, warnings                     # no git: nothing to verify
        if not ok:
            warnings.append(f"line {row['line']}: {row['id']} is closed as {sha}, "
                            "which names no commit in this repository")
    return errors, warnings


def main(argv=None, ledger: Path | None = None, root: Path | None = None) -> int:
    ledger = ledger or ca.LEDGER
    root = root or ROOT
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    a = sub.add_parser("add", help="append one open row with the next free id")
    a.add_argument("severity", choices=ca.SEVERITIES)
    a.add_argument("source")
    a.add_argument("summary")
    a.add_argument("fix")
    r = sub.add_parser("reserve", help="hand out N ids without writing rows")
    r.add_argument("n", type=int)
    sub.add_parser("close", help="close rows from Closes: trailers in the git history")
    args = ap.parse_args(argv)
    try:
        if args.command == "add":
            print(add(ledger, args.severity, args.source, args.summary, args.fix))
        elif args.command == "reserve":
            print("\n".join(reserve(ledger, args.n)))
        else:
            closed, notes = close(ledger, root)
            for line in closed + [f"note: {n}" for n in notes]:
                print(line)
            if not closed:
                print("no open row is named by a Closes: trailer")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
