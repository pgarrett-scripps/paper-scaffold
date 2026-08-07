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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".hash-cache.json"

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
    """sha256 of the file, cached on (size, mtime_ns)."""
    global _dirty
    cache = _load()
    st = p.stat()
    key = str(p.resolve())
    hit = cache.get(key)
    if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        return hit[2]
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    digest = "sha256:" + h.hexdigest()
    cache[key] = [st.st_size, st.st_mtime_ns, digest]
    _dirty = True
    return digest
