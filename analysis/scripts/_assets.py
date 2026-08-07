"""Declare the figures and tables the manuscript includes, by id.

WHY THIS EXISTS. A manifest that merely sits beside the files it describes rots:
nothing reads it, so nothing notices when it stops being true. This one is read
by the compile. The manuscript says

    #figure(fig("fig.example"), caption: [...]) <fig:example>

and `fig` resolves the id through assets.json, so an id that is not declared
fails the build the same way an undeclared `#s("id")` does. That is the whole
design: the ledger is load-bearing, not bookkeeping.

WHAT AN ENTRY RECORDS.

    path     where the file is, relative to the manuscript root
    kind     "figure" or "table" -- what the manuscript will wrap it in
    hash     sha256 of the output, so a hand-edit to a generated file is caught
    origin   { "by": the script that wrote it,
               "at": when the output last CHANGED. A regeneration that produces
                     byte-identical output keeps the old date, so the timestamp
                     says when the figure last actually moved. }
    inputs   { path: sha256 } for everything it was built from

INPUTS ARE PART DECLARED, PART AUTOMATIC. The generator script and every module
it imports from under analysis/ are recorded automatically, by walking
sys.modules -- imports are always Python-level, so that is exact. DATA files are
declared by hand with `inputs=[...]`, because the automatic equivalent is not:
an audit hook on `open` cannot see the reads that HDF5, parquet and most other
binary readers do from C, and would silently record an empty input set for
exactly the formats that matter. A missed input means a stale figure reported as
current, so this half stays explicit.

Undeclared data is not an error, but it IS reported. Nothing else can see it, and
nothing ever really could. The .assets-stamp hash that used to sit alongside this
caught some undeclared reads by accident, but it excluded analysis/data/ -- which
is where data lives -- so its coverage depended on where a file happened to sit
rather than on whether it mattered.

There is no way to enumerate a generator's inputs automatically and be right: an
audit hook misses C-level reads, a directory hash misses files outside it and
fires on files that changed nothing. So this does not pretend to. WHICH FILES ARE
WORTH TRACKING IS THE AUTHOR'S CALL, made explicitly in `inputs=[...]`, and the
note below makes the empty case visible rather than silent. An explicit partial
answer beats an implicit one that looks total.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from _provenance import PAPER, caller_script, code_inputs, declared_inputs, sha

OUT = PAPER / "assets.json"

ABOUT = ("Figures and tables the manuscript includes, referenced as "
         "#fig(\"<id>\") / #tbl(\"<id>\"). Written by the scripts in "
         "analysis/scripts/; see analysis/scripts/_assets.py.")

KINDS = ("figure", "table")


class AssetError(Exception):
    """A declared asset is not usable by the manuscript."""





def record(id: str, path: str, *, kind: str, inputs: list[str] = (),
           desc: str = "") -> None:
    """Declare one generated figure or table.

    `path`   relative to the manuscript root, e.g. "figures/cohort.png"
    `kind`   "figure" or "table"
    `inputs` data files this was built from, relative to the manuscript root.
             The generator and its imports are added automatically.
    """
    if kind not in KINDS:
        raise AssetError(f"{id!r}: kind must be one of {KINDS}, got {kind!r}")
    if not id or " " in id:
        raise AssetError(f"{id!r} is not a usable id (no spaces, not empty)")

    target = PAPER / path
    if not target.is_file():
        raise AssetError(
            f"{id!r} declares {path}, which does not exist. Write the file "
            f"first, then record it.")

    try:
        declared = declared_inputs(inputs)
    except RuntimeError as e:
        raise AssetError(f"{id!r}: {e}") from None

    # A generator that declared no data at all is the blind spot this contract
    # has: its output can go stale against data nothing here knows about, and no
    # check will say so. Reported at the point the omission is made rather than
    # left to be discovered from a wrong figure.
    if not declared:
        print(f"  note: {id} declares no data inputs, so a change to the data "
              f"behind it cannot be detected. Pass inputs=[...] if it reads any.")

    entry = {
        "path": Path(path).as_posix(),
        "kind": kind,
        "desc": desc,
        "hash": sha(target),
        "origin": {"by": caller_script()},
        "inputs": dict(sorted({**code_inputs(), **declared}.items())),
    }

    # Read-modify-write, one entry at a time. Safe because analysis/justfile runs
    # the generators SERIALLY -- if that ever becomes a parallel loop, this races
    # and each script needs to write its own fragment for the recipe to merge.
    doc = {"_about": ABOUT, "values": {}}
    if OUT.is_file():
        try:
            doc = json.loads(OUT.read_text())
            doc.setdefault("values", {})
        except json.JSONDecodeError as e:
            raise AssetError(
                f"assets.json is not valid JSON ({e}); fix or delete it") from None

    old = doc["values"].get(id, {})
    owner = old.get("origin", {}).get("by")
    if owner == "adopted":
        # Adoption is explicitly the provenance a script may replace: it means
        # "nothing can rebuild this", and a generator claiming the id has just
        # proven otherwise. The happy ending of a migration.
        print(f"  note: {id} was adopted; now generated by "
              f"{entry['origin']['by']}, which supersedes the adoption.")
    elif owner and owner != entry["origin"]["by"]:
        raise AssetError(
            f"{id!r} is already declared by {owner}, and {entry['origin']['by']} "
            f"declares it too. One id, one owner: rename one of them.")

    # `at` is when the OUTPUT last changed, not when the script last ran. A
    # regeneration that produces byte-identical output (seeded RNG, no embedded
    # timestamps) keeps the old date, so the field carries information.
    if old.get("hash") == entry["hash"] and old.get("origin", {}).get("at"):
        entry["origin"]["at"] = old["origin"]["at"]
    else:
        entry["origin"]["at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")

    doc["_about"] = ABOUT
    doc["values"][id] = entry
    OUT.write_text(json.dumps(
        {"_about": ABOUT, "values": dict(sorted(doc["values"].items()))},
        indent=2) + "\n")
