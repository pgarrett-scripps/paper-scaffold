"""Shared provenance primitives: hashing, and what code a generator ran.

Both _stats.py and _assets.py need to answer "what produced this, and has any of
it changed since". They had separate copies of the hashing and the sys.modules
walk, which is how the two contracts drift apart.

WHY HASHES AND NOT JUST RE-RUNNING. Re-running a generator and diffing its output
is a stronger check -- it establishes the answer rather than fingerprinting the
inputs. It is also unaffordable: `just verify` is meant to rebuild nothing and be
cheap enough to run constantly, and a project whose analysis takes hours cannot
pay that on every invocation. So the hashes are the CHEAP GATE. They answer "is
it worth re-running" in milliseconds, and the expensive check is opt-in.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent.parent            # analysis/scripts/ -> analysis/ -> paper/

# The toolchain modules these helpers share with the checks (atomic_io,
# manifest_validation, hashcache, paths). The analysis environment does not
# install the toolchain package, so in a paper `paper sync` writes copies to
# _toolchain/ beside this file; the scaffold checkout reads its own tools/.
TOOLCHAIN = PAPER / "tools" if (PAPER / "tools" / "paths.py").is_file() else HERE / "_toolchain"
sys.path.insert(0, str(TOOLCHAIN))
# The checks compare with the same function, so recording and checking agree
# on what a root pyproject.toml / uv.lock hash covers (not its version line).
import hashcache  # noqa: E402
from hashcache import recorded_sha  # noqa: E402
import evidence as _evidence  # noqa: E402

# hashcache places its cache at the manuscript root it reads from the working
# directory (tools/paths.py); a generator runs from analysis/scripts/.
hashcache.CACHE = PAPER / ".hash-cache.json"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def caller_script() -> str:
    """Path of the running generator, relative to the manuscript root.

    Derived from __main__ rather than passed in, because a generator that had to
    name itself would eventually name itself wrongly after a rename.
    """
    main = sys.modules.get("__main__")
    p = getattr(main, "__file__", None)
    if not p:
        raise RuntimeError(
            "cannot tell which script is running (no __main__.__file__). Run the "
            "generator as a script, not from an interactive session.")
    return Path(p).resolve().relative_to(PAPER).as_posix()


def code_inputs() -> dict[str, str]:
    """Every module under analysis/ that is currently imported, hashed.

    sys.modules is a complete record of the code that ran, because an import is
    always Python-level. Transitive for free: a helper imported by a helper is in
    there without anyone naming it, which a hand-declared list forgets after the
    second refactor.

    analysis/.venv/ is excluded, and that exclusion is not cosmetic: the
    virtualenv lives INSIDE analysis/, so without it every site-package a
    generator imports counts as an input. The first version of this recorded 257
    inputs for one figure, nearly all PIL and matplotlib internals, and would have
    marked every figure stale on each dependency upgrade.

    _provenance.py and the two contract modules that import it are excluded too.
    They are the bookkeeping machinery: they cannot change a figure's pixels or a
    number's value, so recording them means the files guaranteed to be irrelevant
    to the output are also the ones guaranteed to invalidate everything. Editing a
    docstring here used to mark every asset in the manuscript stale.

    _toolchain/ (hashcache.BOOKKEEPING) is the same machinery, and `paper sync`
    rewrites it with a header naming the release: recorded, every pin move
    marked every figure and number stale (4.1.1).

    Hashed as recorded_sha() hashes them: a module `paper sync` wrote is
    hashed without the release in its GENERATED header, so a pin move alone
    changes no record, and an edit to its body still does (4.1.2).
    """
    skip = {"analysis/scripts/_provenance.py",
            "analysis/scripts/_assets.py",
            "analysis/scripts/_stats.py"}
    out: dict[str, str] = {}
    for name in ("analysis/pyproject.toml", "analysis/uv.lock"):
        path = PAPER / name
        if path.is_file():
            out[name] = sha(path)
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
        if ("/.venv/" in rel or "/__pycache__/" in rel or rel in skip
                or rel.startswith(hashcache.BOOKKEEPING)):
            continue
        out[rel] = recorded_sha(PAPER, rel)
    return out


def repo_relative(src) -> str:
    """A declared path as the manifests store it: relative to the manuscript root.

    LEXICAL first. A data directory is often a symlink into a data drive
    (analysis/data -> /mnt/data/run7), and resolving it would turn a portable
    in-repo path into a host path, or reject it as outside the repository.
    An absolute path inside the manuscript (or inside the repository, for a
    manuscript in paper/ that reads ../benchmark/) is stored relative, so the
    manifests never hold a path only one machine has. A path outside the
    repository is kept as given and named, since it cannot be made portable.
    """
    raw = Path(os.path.expanduser(str(src)))
    lex = Path(os.path.normpath(raw if raw.is_absolute() else PAPER / raw))
    try:
        return lex.relative_to(PAPER).as_posix()
    except ValueError:
        pass
    try:
        return lex.resolve().relative_to(PAPER.resolve()).as_posix()
    except (ValueError, OSError):
        pass
    top = _evidence.git_top(PAPER)
    if lex == top or top in lex.parents:
        return Path(os.path.relpath(lex, PAPER)).as_posix()
    print(f"  warn: declared input {src} is outside the repository; it is "
          f"recorded as a host path, which no other machine can verify")
    return str(src)


def declared_inputs(paths) -> dict[str, str]:
    """Hash data files a generator says it read. Paths are relative to the root.

    An absolute or `..` path is stored relative to the root (repo_relative),
    so the manifests hold no host paths.

    The root pyproject.toml and uv.lock are hashed without the project's own
    version line (tools/hashcache.py says why), so a scaffold upgrade that
    bumps it does not mark every figure and number stale; a file `paper sync`
    wrote (analysis/scripts/_stats.py, say) without the release in its header.
    """
    out: dict[str, str] = {}
    for src in paths:
        rel = repo_relative(src)
        p = PAPER / rel
        if not p.is_file():
            raise RuntimeError(
                f"declared input {src} does not exist. Paths are relative to the "
                f"manuscript root, not to analysis/.")
        out[rel] = recorded_sha(PAPER, rel)
    return out


def evidence(name: str) -> Path:
    """The path of an evidence set declared in evidence.toml, checked.

        from _assets import record, evidence
        runs = evidence("orbitrap")          # Path, or a loud EvidenceError

    Swapping a campaign is then one edit, in evidence.toml. The set's software
    versions are recorded into what this generator writes (docs/evidence.md).
    """
    return _evidence.resolve(PAPER, name)


def evidence_of(id: str, kind: str, inputs=(), explicit=()) -> dict:
    """{set: {tool: version}} for one entry; raises on a mixed-version entry."""
    if isinstance(explicit, str):
        explicit = (explicit,)
    manifest = _evidence.load(PAPER)
    found = _evidence.attribution(manifest, PAPER, id, kind, inputs, explicit)
    clash = _evidence.mixed(found)
    if clash and not manifest.mixing_allowed(id):
        detail = "; ".join(f"{t} {' and '.join(v)}" for t, v in clash.items())
        raise _evidence.EvidenceError(
            f"{id} mixes versions of one tool ({detail}) across evidence sets "
            f"{', '.join(found)}. Rebuild the older set, or list the id under "
            f"allow_mixed in evidence.toml if the comparison is the point.")
    return found


def note_run(script: str) -> None:
    """Tell the open `just assets` run log that this generator executed."""
    _evidence.run_note(PAPER, script)
