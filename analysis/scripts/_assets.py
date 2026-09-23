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
    print    for a figure: the size it will print at, and the smallest type
             on it. See PRINT GEOMETRY below.

PRINT GEOMETRY. A journal's figure rules are about the printed article, not the
file: a column width in inches and a floor on type size in points. Neither is
visible in the manuscript source, and both are easy to break by editing a
`figsize` in a script nobody reads next to the paper. So the generator records
them. `width_in`/`height_in`/`dpi` come from the written raster's pixel size and
dpi -- what production will actually receive, after any `bbox_inches="tight"`
crop. `min_pt` is measured by walking the figure's visible text artists, which
is exact where grepping the script for `fontsize=` misses rcParams defaults and
tick labels. Pass `fig=` to get it; without it the entry records no type size
rather than guessing. A figure that is not a matplotlib canvas has no artists
to walk and may pass `min_pt=` instead: the generator's own claim, weaker, and
still better than silence.

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

import contextlib
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from _provenance import PAPER, caller_script, code_inputs, declared_inputs, sha

from atomic_io import write_text
from manifest_validation import validate, ManifestError

OUT = PAPER / "assets.json"

ABOUT = ("Figures and tables the manuscript includes, referenced as "
         "#fig(\"<id>\") / #tbl(\"<id>\"). Written by the scripts in "
         "analysis/scripts/; see analysis/scripts/_assets.py.")

KINDS = ("figure", "table")


class AssetError(Exception):
    """A declared asset is not usable by the manuscript."""


@contextlib.contextmanager
def _exclusive():
    """Serialize the read-modify-write of assets.json across generators.

    Generators run serially from analysis/justfile, but nothing stops a project
    running them in parallel (a `&`-and-`wait` loop, make -j, Snakemake), and
    then two can each read the file, add their own entry, and write back a copy
    missing the other's. An advisory lock is enough: every writer is a local
    process and the critical section is a few milliseconds of JSON. The lock
    file sits in .build-state/ (local, untracked) rather than beside
    assets.json, and is separate from it so it survives the atomic replace
    write_text() does.
    """
    lock = PAPER / ".build-state" / "assets.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(lock, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)


def _print_geometry(target: Path, fig, min_pt) -> dict:
    """The printed size of a figure file, and the smallest type on it.

    Geometry is read back from the written file rather than from
    `fig.get_size_inches()`, because `bbox_inches="tight"` crops the canvas
    after the figure is sized: the file is the only honest answer.
    """
    out: dict = {}
    try:
        from PIL import Image
        with Image.open(target) as im:
            dpi = im.info.get("dpi", (None,))[0]
            if dpi:
                out["width_in"] = round(im.width / dpi, 3)
                out["height_in"] = round(im.height / dpi, 3)
                out["dpi"] = round(float(dpi))
    except Exception:
        pass  # no Pillow, not a raster, or unreadable: size goes unrecorded

    if fig is not None:
        from matplotlib.text import Text
        sizes = [t.get_fontsize() for t in fig.findobj(Text)
                 if t.get_visible() and t.get_text().strip()]
        if sizes:
            out["min_pt"] = round(min(sizes), 2)
    elif min_pt is not None:
        out["min_pt"] = round(float(min_pt), 2)
    return out


def record(id: str, path: str, *, kind: str, inputs: list[str] = (),
           desc: str = "", fig=None, min_pt: float | None = None) -> None:
    """Declare one generated figure or table.

    `path`   relative to the manuscript root, e.g. "figures/cohort.png"
    `kind`   "figure" or "table"
    `inputs` data files this was built from, relative to the manuscript root.
             The generator and its imports are added automatically.
    `fig`    the matplotlib Figure just saved. Optional, for a figure only:
             it lets the smallest type size be measured rather than guessed.
    `min_pt` the smallest type size on a figure no matplotlib Figure drew,
             stated by the generator. Ignored when `fig` is given.
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
    if kind == "figure":
        geometry = _print_geometry(target, fig, min_pt)
        if geometry:
            entry["print"] = geometry

    # Read-modify-write, one entry at a time, under an exclusive lock so
    # generators run in parallel cannot drop each other's entries.
    with _exclusive():
        _merge(id, entry)


def _merge(id: str, entry: dict) -> None:
    """Add one entry to assets.json. The caller holds the lock."""
    doc = {"_about": ABOUT, "values": {}}
    if OUT.is_file():
        try:
            doc = json.loads(OUT.read_text())
        except json.JSONDecodeError as e:
            raise AssetError(
                f"assets.json is not valid JSON ({e}); fix or delete it") from None

    try:
        validate(doc, "assets")
    except ManifestError as exc:
        raise AssetError(str(exc)) from None
    old = doc["values"].get(id, {})
    owner = (old.get("origin") or {}).get("by")
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
    if old.get("hash") == entry["hash"] and (old.get("origin") or {}).get("at"):
        entry["origin"]["at"] = old["origin"]["at"]
    else:
        entry["origin"]["at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")

    doc["_about"] = ABOUT
    doc["values"][id] = entry
    write_text(OUT, json.dumps(
        {"_about": ABOUT, "values": dict(sorted(doc["values"].items()))},
        indent=2) + "\n")
