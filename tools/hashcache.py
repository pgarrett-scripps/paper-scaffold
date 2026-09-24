"""Content hashes with a stat-keyed cache, for the checks that run constantly.

WHY THIS EXISTS. `just verify` re-hashes every declared input and every pinned
file on every run. On the scaffold that is a CSV and costs nothing; on a real
project a declared input can be a multi-gigabyte HDF5, and hashing it on every
verify makes the constant gate cost seconds to minutes -- the same
scale-blindness the 3.2.0 re-derivation flaw had, one layer down.

THE CACHE IS A SHORTCUT, NOT AN AUTHORITY. A file's (size, mtime_ns) is the
KEY; the sha256 is still the recorded truth everywhere. Any change to either
stat re-hashes the content, so the only way to a stale answer is content that
changed while size and nanosecond mtime both stayed identical -- which no edit,
copy, checkout or download does. This is the trick every build system uses, and
it does not contradict "hashes, not dates": dates here only decide when to
recompute the hash, never stand in for it.

The cache file is local build state, like .build-stamp: gitignored, safe to
delete at any time (the next run just re-hashes everything), and never a
substitute for the hashes recorded in stats.json / assets.json.

Recording paths (`just pin`, the generators) deliberately do NOT use this:
they run rarely, and the moment a hash becomes the recorded truth it should be
computed from the bytes, not looked up.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import re
import time
from pathlib import Path

from paths import ROOT  # the manuscript (tools/paths.py)
CACHE = ROOT / ".hash-cache.json"

# A cached digest is trusted only for a file last modified longer ago than
# this. Two same-size writes inside the filesystem's timestamp granularity share
# an mtime_ns, and a freshly written file is exactly when that happens: the
# classic racy-clean window, which build tools re-check for the same reason.
RACY_NS = 2_000_000_000

_cache: dict[str, list] | None = None
_dirty = False


def _load() -> dict[str, list]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE.read_text())
            if not isinstance(_cache, dict):
                _cache = {}
        except (OSError, json.JSONDecodeError):
            _cache = {}
        atexit.register(_save)
    return _cache


def _save() -> None:
    if _dirty and _cache is not None:
        try:
            CACHE.write_text(json.dumps(_cache))
        except OSError:
            pass                      # a read-only tree still gets its answer


def sha(p: Path) -> str:
    """sha256 of the file, cached on (size, mtime_ns).

    A hit is only served, and a digest only stored, for a file older than
    RACY_NS; a younger one is hashed from its bytes every time, since its
    (size, mtime) cannot yet tell two writes apart.
    """
    global _dirty
    cache = _load()
    st = p.stat()
    key = str(p.resolve())
    hit = cache.get(key)
    racy = time.time_ns() - st.st_mtime_ns < RACY_NS
    if hit and not racy and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        return hit[2]
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    digest = "sha256:" + h.hexdigest()
    # Not stored while racy either: a same-size write later in the same tick
    # would leave this digest filed under the new bytes' (size, mtime), and it
    # would be served once the file ages out of the window.
    if not racy:
        cache[key] = [st.st_size, st.st_mtime_ns, digest]
        _dirty = True
    return digest


# ------------------------------------------------- toolchain manifests ---
# The ROOT pyproject.toml and uv.lock describe the paper toolchain, and their
# `version` line is the scaffold version, bumped on every upgrade. A generator
# that declares either as an input (cascade/paper does: its analysis runs in
# the root environment) then read as stale on every bump, figures and numbers
# alike, though no dependency moved and `just assets` could only re-record the
# same outputs. So for those two files the recorded hash is of the content
# with the project's own version line removed; every other line (every
# dependency and every locked version) still counts. analysis/pyproject.toml
# and analysis/uv.lock are the analysis environment and are hashed whole.
# A hash recorded before this (of the raw bytes) is still accepted while the
# file is unchanged, so upgrading marks nothing stale.
#
# 4.1.1: from 4.0.0 a paper's own version is a constant "0.0.0" and the
# release moves in the paper-scaffold pin instead: the dependency string in
# pyproject.toml, and in uv.lock the root package's requires-dist entry and
# the paper-scaffold [[package]] block (its version, git commit and
# dependency list). Those are removed too, so moving the pin alone marks
# nothing stale. What the toolchain pulls in is still counted: every other
# locked package keeps its block, and a changed dependency moves its version
# there. A hash of the 4.0.0 form (version line only) is still accepted while
# the file is unchanged; the first pin move after it reads stale once, since
# the old pin cannot be recovered from a hash (HISTORY.md 4.1.1).
TOOLCHAIN = ("pyproject.toml", "uv.lock")

# Written by `paper sync` with a header naming the release, so every pin move
# rewrites them. They are the provenance machinery (hashing, paths), like
# _provenance.py, which is never recorded: they cannot change a figure or a
# number. _provenance.code_inputs() does not record them, and a record made
# before 4.1.1 that holds them is not stale because of them.
BOOKKEEPING = "analysis/scripts/_toolchain/"

_PROJECT_VERSION = re.compile(r'(?m)^version\s*=\s*"[^"\n]*"[ \t]*\n?')
_SCAFFOLD_PIN = re.compile(r'"paper-scaffold\s*@[^"\n]*"')
_SCAFFOLD_SOURCE = re.compile(r'(?m)^paper-scaffold\s*=\s*\{[^\n]*\}[ \t]*$')
_SCAFFOLD_REQUIRES = re.compile(r'\{ name = "paper-scaffold",[^}\n]*\}')


def _without_own_version(name: str, text: str) -> str:
    if name == "pyproject.toml":
        # Only the [project] table's version, not a tool's.
        head = re.search(r"(?m)^\[project\][ \t]*$", text)
        if not head:
            return text
        end = re.compile(r"(?m)^\[").search(text, head.end())
        stop = end.start() if end else len(text)
        return text[:head.end()] + _PROJECT_VERSION.sub("", text[head.end():stop], 1) \
            + text[stop:]
    # uv.lock: the one [[package]] whose source is the project itself.
    blocks = re.split(r"(?m)^(?=\[\[package\]\]$)", text)
    return "".join(_PROJECT_VERSION.sub("", b, 1)
                   if re.search(r'(?m)^source = \{ (?:virtual|editable) = "\." \}', b)
                   else b for b in blocks)


def _without_release(name: str, text: str) -> str:
    """The recorded form: own version and the paper-scaffold pin removed."""
    text = _without_own_version(name, text)
    if name == "pyproject.toml":
        text = _SCAFFOLD_PIN.sub('"paper-scaffold"', text)
        return _SCAFFOLD_SOURCE.sub("paper-scaffold = {}", text)
    blocks = re.split(r"(?m)^(?=\[\[package\]\]$)", text)
    # The installed toolchain's block, not the scaffold checkout's own
    # (editable ".") one, whose dependency list is the toolchain itself.
    text = "".join(b for b in blocks
                   if not (re.search(r'(?m)^name = "paper-scaffold"$', b)
                           and not re.search(r'(?m)^source = \{ (?:virtual|editable) = "\." \}', b)))
    return _SCAFFOLD_REQUIRES.sub('{ name = "paper-scaffold" }', text)


def toolchain_file(rel: str) -> bool:
    """Whether a root-relative input path is a root toolchain manifest."""
    return Path(rel).as_posix() in TOOLCHAIN


def recorded_sha(root: Path, rel: str) -> str:
    """The hash a generator records for input `rel` (uncached, from the bytes)."""
    path = root / rel
    if not toolchain_file(rel):
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return "sha256:" + h.hexdigest()
    text = _without_release(Path(rel).name, path.read_text(encoding="utf-8"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def input_current(root: Path, rel: str, want: str) -> bool:
    """Whether input `rel` still matches its recorded hash `want`."""
    if Path(rel).as_posix().startswith(BOOKKEEPING):
        return True
    path = root / rel
    if sha(path) == want:
        return True
    if not toolchain_file(rel):
        return False
    text = path.read_text(encoding="utf-8")
    name = Path(rel).name
    return want in (_sha_text(_without_release(name, text)),
                    _sha_text(_without_own_version(name, text)))
