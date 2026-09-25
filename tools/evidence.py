"""The evidence manifest: which data a number came from, and what made it.

WHY THIS EXISTS. A generator used to open its data through a path written into
the script: `RESULTS = "benchmark/results/run_20260922"`. That constant is
the whole answer to "where do these numbers come from", and it answers badly.
Nothing records which release of the software produced the directory, so a
rerun under a new version silently mixes two versions in one table. Nothing
records the config the run read, so a result computed before a recalibration
keeps the old setting and is reported as current. A campaign swap means
editing every script that names the path. And an absolute path copied from a
shell works on exactly one machine.

`evidence.toml`, at the manuscript root, names each body of evidence once:

    [sets.orbitrap]
    path = "benchmark/results/orbitrap_2026-09"   # repo-relative
    software = { searchtool = "0.7.0" }           # name -> version or commit
    verify = "benchmark/results/orbitrap_2026-09/verification.json"
    inputs = ["config/search.toml"]               # what the run was configured by
    status = "frozen"                              # or "pending", "held-out"
    frozen_at = "2026-09-01"
    stats = ["bench.orbitrap.*"]                   # ids this set produces
    assets = ["fig.orbitrap-*"]

A generator asks for the set by name, `evidence("orbitrap")`, and gets its
path; a missing path, an unknown name or a path outside the repository fails
there, loudly. `record()` and `Stats.write()` then write, into each entry they
produce, the software versions of the sets behind it (the entry's `evidence`
field), which is what lets `just check-evidence` say that a number was built
by version 0.7.0 of a tool the manifest now says is 0.10.0, or that one table
mixes both, and lets `just impact TOOL@VER` list what a version change
touches. docs/evidence.md has the whole contract.

This module is imported by the analysis too (`paper sync` copies it to
analysis/scripts/_toolchain/), so it is stdlib-only and takes the manuscript
root as an argument rather than reading tools/paths.py.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover - the analysis env on 3.10
        tomllib = None  # type: ignore[assignment]

MANIFEST = "evidence.toml"
LOCK = "evidence.lock.json"
RUN_LOG = ".build-state/assets-run.json"
GRANDFATHERED = ".paper/grandfathered.json"

STATUSES = ("pending", "frozen", "held-out")
# A verification file's `status` that says the evidence was checked.
VERIFIED = ("verified", "complete", "completed", "ok", "passed", "pass")
LEVELS = ("off", "warn", "error")
CHECKS = {
    # A declared stats/asset input git does not hold. warn by default: data
    # often lives untracked on purpose; "error" makes a clone-reproducible
    # manuscript a gate.
    "untracked_inputs": "warn",
    # A version literal in the prose near a tool name that disagrees with
    # every version the manifest declares for that tool.
    "version_literals": "warn",
}
SET_KEYS = {"path", "files", "software", "commit", "verify", "status",
            "frozen_at", "first_scored_at", "inputs", "stats", "assets", "note"}
TOP_KEYS = {"sets", "allow_mixed", "checks"}

# Paths only one machine has: absolute POSIX homes and mounts, a Windows
# drive, a home-relative tilde. Matched inside free text (a verification
# file, a note) as well as against whole path fields.
HOST_PATH = re.compile(
    r"(?<![\w.:/])(?:/(?:home|Users|mnt|media|tmp|private|root|scratch|data|net|Volumes)/"
    r"|[A-Za-z]:\\|~/)")


class EvidenceError(ValueError):
    """evidence.toml is malformed, or a set cannot be used."""


@dataclass
class EvidenceSet:
    name: str
    path: str | None = None
    files: tuple[str, ...] = ()
    software: dict = field(default_factory=dict)
    commit: str | None = None
    verify: str | None = None
    status: str | None = None
    frozen_at: str | None = None
    first_scored_at: str | None = None
    inputs: tuple[str, ...] = ()
    stats: tuple[str, ...] = ()
    assets: tuple[str, ...] = ()
    note: str = ""

    @property
    def paths(self) -> tuple[str, ...]:
        """Every repo-relative path the set is made of."""
        return ((self.path,) if self.path else ()) + self.files

    def produced_by(self) -> dict:
        """What the entry records: the software, and the commit when declared."""
        out = dict(self.software)
        if self.commit:
            out["commit"] = self.commit
        return dict(sorted(out.items()))


@dataclass
class Manifest:
    sets: dict
    allow_mixed: tuple[str, ...] = ()
    checks: dict = field(default_factory=lambda: dict(CHECKS))

    def covering(self, id: str, kind: str) -> list[str]:
        """Sets whose `stats`/`assets` patterns name this id."""
        return sorted(n for n, s in self.sets.items()
                      if any(pattern_matches(p, id) for p in getattr(s, kind)))

    def containing(self, root: Path, rel: str) -> list[str]:
        """Sets whose path holds this repo-relative input."""
        target = _lexical(root, rel)
        out = []
        for name, s in self.sets.items():
            for p in s.paths:
                base = _lexical(root, p)
                if target == base or base in target.parents:
                    out.append(name)
                    break
        return sorted(out)

    def mixing_allowed(self, id: str) -> bool:
        return any(pattern_matches(p, id) for p in self.allow_mixed)


def pattern_matches(pattern: str, id: str) -> bool:
    """An exact id, or a prefix ending in `*` (the syntax stats.typ supports)."""
    if pattern.endswith("*"):
        return id.startswith(pattern[:-1])
    return id == pattern


def git_top(root: Path) -> Path:
    """The enclosing repository (the directory holding .git), else root."""
    here = Path(os.path.abspath(root))
    for d in (here, *here.parents):
        if (d / ".git").exists():
            return d
    return here


def _lexical(root: Path, rel: str) -> Path:
    return Path(os.path.normpath(Path(os.path.abspath(root)) / rel))


def path_problem(root: Path, rel: str) -> str | None:
    """Why a manifest path is not a repo-relative path, or None.

    LEXICAL, on purpose: a data directory is often a symlink into a data
    drive, and resolving it would call a perfectly portable in-repo path
    "outside the repository". `../` is allowed while it stays inside the git
    repository (a manuscript in paper/ reading ../benchmark/).
    """
    if not isinstance(rel, str) or not rel.strip():
        return "is empty"
    if rel.startswith("~") or os.path.isabs(rel) or re.match(r"[A-Za-z]:[\\/]", rel):
        return (f"{rel} is a host path; write it relative to the manuscript root "
                f"so the manifest works on another machine")
    top = git_top(root)
    lex = _lexical(root, rel)
    if lex != top and top not in lex.parents:
        return f"{rel} leaves the repository ({top.name}/)"
    return None


def _strings(name: str, key: str, value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise EvidenceError(f"{MANIFEST}: sets.{name}.{key} must be a string or "
                            f"a list of strings")
    return tuple(value)


def _date(name: str, key: str, value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):          # a TOML date
        return value.isoformat()
    if not isinstance(value, str):
        raise EvidenceError(f"{MANIFEST}: sets.{name}.{key} must be a date")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise EvidenceError(f"{MANIFEST}: sets.{name}.{key} = {value!r} is not "
                            f"an ISO date (2026-09-01 or 2026-09-01T12:00:00Z)") from None
    return value


def parse(doc: dict, root: Path) -> Manifest:
    """Validate a loaded evidence.toml strictly: an unknown key is an error."""
    unknown = set(doc) - TOP_KEYS
    if unknown:
        raise EvidenceError(f"{MANIFEST}: unknown top-level key(s) "
                            f"{', '.join(sorted(unknown))} (known: "
                            f"{', '.join(sorted(TOP_KEYS))})")
    checks = dict(CHECKS)
    raw_checks = doc.get("checks", {})
    if not isinstance(raw_checks, dict):
        raise EvidenceError(f"{MANIFEST}: [checks] must be a table")
    for key, level in raw_checks.items():
        if key not in CHECKS:
            raise EvidenceError(f"{MANIFEST}: [checks] has unknown key {key!r} "
                                f"(known: {', '.join(sorted(CHECKS))})")
        if level not in LEVELS:
            raise EvidenceError(f"{MANIFEST}: checks.{key} must be one of "
                                f"{', '.join(LEVELS)}")
        checks[key] = level
    sets = {}
    raw_sets = doc.get("sets", {})
    if not isinstance(raw_sets, dict):
        raise EvidenceError(f"{MANIFEST}: [sets] must be a table of named sets")
    for name, raw in raw_sets.items():
        if not isinstance(raw, dict):
            raise EvidenceError(f"{MANIFEST}: sets.{name} must be a table")
        bad = set(raw) - SET_KEYS
        if bad:
            raise EvidenceError(f"{MANIFEST}: sets.{name} has unknown key(s) "
                                f"{', '.join(sorted(bad))} (known: "
                                f"{', '.join(sorted(SET_KEYS))})")
        software = raw.get("software", {})
        if not isinstance(software, dict) or not all(
                isinstance(k, str) and isinstance(v, str) and v.strip()
                for k, v in software.items()):
            raise EvidenceError(f"{MANIFEST}: sets.{name}.software must map a "
                                f"tool name to a version or commit string")
        if "commit" in software:
            raise EvidenceError(f"{MANIFEST}: sets.{name}.software: `commit` is "
                                f"a set key, not a tool name")
        status = raw.get("status")
        if status is not None and status not in STATUSES:
            raise EvidenceError(f"{MANIFEST}: sets.{name}.status must be one of "
                                f"{', '.join(STATUSES)}")
        for key in ("path", "commit", "verify", "note"):
            if key in raw and not isinstance(raw[key], str):
                raise EvidenceError(f"{MANIFEST}: sets.{name}.{key} must be a string")
        s = EvidenceSet(
            name=name, path=raw.get("path"),
            files=_strings(name, "files", raw.get("files")),
            software=dict(software), commit=raw.get("commit"),
            verify=raw.get("verify"), status=status,
            frozen_at=_date(name, "frozen_at", raw.get("frozen_at")),
            first_scored_at=_date(name, "first_scored_at", raw.get("first_scored_at")),
            inputs=_strings(name, "inputs", raw.get("inputs")),
            stats=_strings(name, "stats", raw.get("stats")),
            assets=_strings(name, "assets", raw.get("assets")),
            note=raw.get("note", ""))
        if not s.paths:
            raise EvidenceError(f"{MANIFEST}: sets.{name} needs `path` or `files`")
        for p in (*s.paths, *s.inputs, *((s.verify,) if s.verify else ())):
            problem = path_problem(root, p)
            if problem:
                raise EvidenceError(f"{MANIFEST}: sets.{name}: {problem}")
        sets[name] = s
    allow = doc.get("allow_mixed", [])
    if not isinstance(allow, list) or not all(isinstance(a, str) for a in allow):
        raise EvidenceError(f"{MANIFEST}: allow_mixed must be a list of id patterns")
    return Manifest(sets=sets, allow_mixed=tuple(allow), checks=checks)


def load(root: Path) -> Manifest | None:
    """The manifest at root, or None when the paper declares none."""
    path = Path(root) / MANIFEST
    if not path.is_file():
        return None
    if tomllib is None:
        raise EvidenceError(f"{MANIFEST} needs Python 3.11+ (tomllib) or the "
                            f"tomli package in this environment")
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvidenceError(f"{MANIFEST}: {exc}") from None
    return parse(doc, Path(root))


# What this process resolved through evidence(): {name: produced_by}. Read by
# Stats.write() for the generator-level record.
USED: dict[str, dict] = {}


def resolve(root: Path, name: str, manifest: Manifest | None = None) -> Path:
    """The path of one set, checked. Raises EvidenceError, never returns a guess."""
    manifest = manifest if manifest is not None else load(root)
    if manifest is None:
        raise EvidenceError(f"evidence({name!r}): there is no {MANIFEST} at "
                            f"{root}; declare the set there first")
    if name not in manifest.sets:
        raise EvidenceError(f"evidence({name!r}): no such set in {MANIFEST} "
                            f"(declared: {', '.join(sorted(manifest.sets)) or 'none'})")
    s = manifest.sets[name]
    missing = [p for p in s.paths if not (Path(root) / p).exists()]
    if missing:
        state = " (the set is declared pending)" if s.status == "pending" else ""
        raise EvidenceError(f"evidence({name!r}): {', '.join(missing)} does not "
                            f"exist{state}. Fix the path in {MANIFEST}, or fetch "
                            f"the data before running the generator.")
    USED[name] = s.produced_by()
    return Path(root) / (s.path if s.path else s.files[0])


def attribution(manifest: Manifest | None, root: Path, id: str, kind: str,
                inputs=(), explicit=()) -> dict:
    """{set: produced_by} for one entry: the sets that name it by pattern,
    hold one of its declared inputs, or were passed explicitly."""
    if manifest is None:
        if explicit:
            raise EvidenceError(f"{id}: evidence={list(explicit)} but there is "
                                f"no {MANIFEST}")
        return {}
    names = set(manifest.covering(id, kind))
    for rel in inputs:
        names.update(manifest.containing(root, rel))
    for name in explicit:
        if name not in manifest.sets:
            raise EvidenceError(f"{id}: evidence={name!r} is not a set in {MANIFEST}")
        names.add(name)
    return {n: manifest.sets[n].produced_by() for n in sorted(names)}


def mixed(attrib: dict) -> dict:
    """{tool: [versions]} for every tool one entry saw at more than one version."""
    seen: dict[str, set] = {}
    for software in attrib.values():
        for tool, ver in software.items():
            if tool != "commit":
                seen.setdefault(tool, set()).add(ver)
    return {t: sorted(v) for t, v in sorted(seen.items()) if len(v) > 1}


def grandfathered(root: Path, key: str) -> set:
    """Ids `paper sync` recorded as predating a rule (hand entries with no source)."""
    path = Path(root) / GRANDFATHERED
    try:
        return set(json.loads(path.read_text()).get(key, []))
    except (OSError, ValueError, AttributeError):
        return set()


# ---- which generators the last `just assets` ran ---------------------------

@contextlib.contextmanager
def _locked(root: Path):
    lock = Path(root) / ".build-state" / "assets-run.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
    except ImportError:  # pragma: no cover - not POSIX
        yield
        return
    handle = os.open(lock, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_start(root: Path) -> str:
    """Open a run log for `just assets`; the token goes into PAPER_ASSETS_RUN."""
    import uuid
    token = uuid.uuid4().hex
    path = Path(root) / RUN_LOG
    with _locked(root):
        path.write_text(json.dumps({"token": token, "started": _now(),
                                    "complete": False, "ran": []}, indent=2) + "\n")
    return token


def run_note(root: Path, script: str) -> None:
    """Record that a generator executed, when a `just assets` run is open."""
    token = os.environ.get("PAPER_ASSETS_RUN")
    if not token:
        return
    path = Path(root) / RUN_LOG
    with _locked(root):
        try:
            log = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        if log.get("token") != token or script in log.get("ran", []):
            return
        log["ran"] = sorted({*log.get("ran", []), script})
        path.write_text(json.dumps(log, indent=2) + "\n")


def run_end(root: Path, token: str) -> None:
    path = Path(root) / RUN_LOG
    with _locked(root):
        try:
            log = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        if log.get("token") == token:
            log["complete"], log["ended"] = True, _now()
            path.write_text(json.dumps(log, indent=2) + "\n")


def last_run(root: Path) -> dict | None:
    try:
        log = json.loads((Path(root) / RUN_LOG).read_text())
    except (OSError, ValueError):
        return None
    return log if log.get("complete") else None


def main(argv: list[str]) -> int:
    """`paper tool evidence run-start|run-end TOKEN`: the assets recipe's log."""
    from paths import ROOT
    if argv[:1] == ["run-start"]:
        print(run_start(ROOT))
        return 0
    if argv[:1] == ["run-end"] and len(argv) == 2:
        run_end(ROOT, argv[1])
        return 0
    print("usage: evidence run-start | run-end TOKEN")
    return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
