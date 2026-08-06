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
    origin   { "by": the script that wrote it }
    inputs   { path: sha256 } for everything it was built from

INPUTS ARE PART DECLARED, PART AUTOMATIC. The generator script and every module
it imports from under analysis/ are recorded automatically, by walking
sys.modules -- imports are always Python-level, so that is exact. DATA files are
declared by hand with `inputs=[...]`, because the automatic equivalent is not:
an audit hook on `open` cannot see the reads that HDF5, parquet and most other
binary readers do from C, and would silently record an empty input set for
exactly the formats that matter. A missed input means a stale figure reported as
current, so this half stays explicit.

Undeclared data is not an error. `.assets-stamp` still hashes all of analysis/
and still fails closed, so a generator edited without a re-run is caught whether
or not it declared anything.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent.parent            # analysis/scripts/ -> analysis/ -> paper/
ANALYSIS = PAPER / "analysis"
OUT = PAPER / "assets.json"

ABOUT = ("Figures and tables the manuscript includes, referenced as "
         "#fig(\"<id>\") / #tbl(\"<id>\"). Written by the scripts in "
         "analysis/scripts/; see analysis/scripts/_assets.py.")

KINDS = ("figure", "table")


class AssetError(Exception):
    """A declared asset is not usable by the manuscript."""


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _caller_script() -> str:
    main = sys.modules.get("__main__")
    p = getattr(main, "__file__", None)
    if not p:
        raise AssetError(
            "cannot tell which script is writing assets.json. Run the generator "
            "as a script, not from an interactive session.")
    return Path(p).resolve().relative_to(PAPER).as_posix()


def _code_inputs() -> dict[str, str]:
    """Every module under analysis/ that is currently imported.

    Reliable in a way the data half is not: an import is always Python-level, so
    sys.modules is a complete record of the code that ran. Catches the shared
    helper a generator imports, which a hand-declared list forgets after the
    second refactor.

    analysis/.venv/ is excluded, and that exclusion is not cosmetic: the
    virtualenv lives INSIDE analysis/, so without it every site-package a
    generator imports is recorded as an input. The first run of this recorded 257
    inputs for one figure, nearly all of them PIL and matplotlib internals, which
    would then have marked the figure stale on every dependency upgrade.
    """
    out: dict[str, str] = {}
    for mod in list(sys.modules.values()):
        f = getattr(mod, "__file__", None)
        if not f:
            continue
        p = Path(f).resolve()
        try:
            rel = p.relative_to(PAPER).as_posix()
        except ValueError:
            continue                              # stdlib, or outside the paper
        if not rel.startswith("analysis/") or not p.is_file():
            continue
        if "/.venv/" in rel or "/__pycache__/" in rel:
            continue
        out[rel] = _sha(p)
    return out


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

    declared: dict[str, str] = {}
    for src in inputs:
        p = PAPER / src
        if not p.is_file():
            raise AssetError(
                f"{id!r} declares input {src}, which does not exist. Paths are "
                f"relative to the manuscript root, not to analysis/.")
        declared[Path(src).as_posix()] = _sha(p)

    entry = {
        "path": Path(path).as_posix(),
        "kind": kind,
        "desc": desc,
        "hash": _sha(target),
        "origin": {"by": _caller_script()},
        "inputs": dict(sorted({**_code_inputs(), **declared}.items())),
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

    owner = doc["values"].get(id, {}).get("origin", {}).get("by")
    if owner and owner != entry["origin"]["by"]:
        raise AssetError(
            f"{id!r} is already declared by {owner}, and {entry['origin']['by']} "
            f"declares it too. One id, one owner: rename one of them.")

    doc["_about"] = ABOUT
    doc["values"][id] = entry
    OUT.write_text(json.dumps(
        {"_about": ABOUT, "values": dict(sorted(doc["values"].items()))},
        indent=2) + "\n")
