#!/usr/bin/env python3
"""Check where the numbers come from: the evidence manifest and the inputs.

`just check-evidence` (inside `just verify`) answers, reading files only:

- Is evidence.toml well formed, with repo-relative paths that exist? Is each
  set's verification file present, saying it passed, and unchanged since
  `just evidence-stamp`? Has a config the set was produced from changed
  since then (the run is older than its settings)? Has a frozen set's tree
  moved? Was a held-out set frozen before it was first scored?
- Was every stats and asset entry built from the software versions the
  manifest declares now, and does any single entry mix two versions of one
  tool?
- Is anything declared pending (an evidence set, or a `pending` block in
  stats.json / assets.json)? The paper compiles with a placeholder; this is
  the gate that fails.
- Are the inputs the generators declared held by git? Is any recorded as a
  host path? (Runs without evidence.toml too.)
- Does a version literal in the prose next to a tool's name disagree with
  every version the manifest declares for that tool?

`--strict` (preflight) makes a missing set path or verification file an
error. `--stamp [SET...]` records what the checks compare against
(evidence.lock.json). `--impact TOOL[@VER]` lists every set, number and
figure a version of a tool touches, and where the prose uses them.
docs/evidence.md has the contract.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from paths import ROOT  # the manuscript (tools/paths.py)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import evidence  # noqa: E402
import hashcache  # noqa: E402
from manifest_validation import load as load_manifest, ManifestError  # noqa: E402


class Finding:
    def __init__(self, level: str, id: str, msg: str) -> None:
        self.level, self.id, self.msg = level, id, msg

    def __str__(self) -> str:
        return f"  {self.level:<6} {self.id:<28} {self.msg}"


def _docs(root: Path) -> dict:
    out = {}
    for kind, name in (("stats", "stats.json"), ("assets", "assets.json")):
        path = root / name
        out[kind] = load_manifest(path, kind) if path.is_file() else {"values": {}}
    return out


def _lock(root: Path) -> dict:
    try:
        return json.loads((root / evidence.LOCK).read_text())
    except (OSError, ValueError):
        return {}


def _tree(root: Path, s: evidence.EvidenceSet) -> str | None:
    """A cheap fingerprint of a set's files: every relative path and size.

    Not a content hash: a frozen result directory can hold gigabytes, and the
    gate must stay cheap. It catches a file added, removed, truncated or
    rewritten to another length, which is how a frozen set usually moves.
    """
    h = hashlib.sha256()
    found = False
    for rel in s.paths:
        base = root / rel
        files = [base] if base.is_file() else sorted(
            f for f in base.rglob("*") if f.is_file()) if base.is_dir() else []
        for f in files:
            found = True
            h.update(f"{f.relative_to(root).as_posix()}\0{f.stat().st_size}\n".encode())
    return "tree:" + h.hexdigest() if found else None


def stamp(root: Path, names: list[str]) -> tuple[list[str], int]:
    """Record the verification file, inputs, software and tree of each set."""
    try:
        manifest = evidence.load(root)
    except evidence.EvidenceError as e:
        return [str(e)], 1
    if manifest is None:
        return [f"no {evidence.MANIFEST}: nothing to stamp"], 1
    unknown = sorted(set(names) - set(manifest.sets))
    if unknown:
        return [f"no such set: {', '.join(unknown)}"], 1
    lock = _lock(root)
    lines = []
    for name in names or sorted(manifest.sets):
        s = manifest.sets[name]
        entry = {"software": s.produced_by(),
                 "stamped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        for key, paths in (("verify", (s.verify,) if s.verify else ()), ("inputs", s.inputs)):
            hashes = {}
            for rel in paths:
                if not (root / rel).is_file():
                    return [f"{name}: {rel} does not exist, so it cannot be stamped"], 1
                hashes[rel] = hashcache.sha(root / rel)
            if hashes:
                entry[key] = hashes
        if s.status in ("frozen", "held-out"):
            tree = _tree(root, s)
            if tree:
                entry["tree"] = tree
        lock[name] = entry
        lines.append(f"  stamped {name}")
    lock = {k: v for k, v in sorted(lock.items()) if k in manifest.sets}
    (root / evidence.LOCK).write_text(json.dumps(lock, indent=2) + "\n")
    lines.append(f"  wrote {evidence.LOCK} ({len(lock)} set(s))")
    return lines, 0


def _sets(root: Path, manifest: evidence.Manifest, strict: bool) -> list[Finding]:
    out: list[Finding] = []
    lock = _lock(root)
    missing_level = "error" if strict else "warn"
    for name, s in sorted(manifest.sets.items()):
        subject = f"set {name}"
        if s.status == "pending":
            out.append(Finding("error", subject,
                "is declared pending: the paper shows placeholders, and the gate "
                "fails until the evidence is in and `status` is removed"))
        for rel in s.paths:
            if not (root / rel).exists() and s.status != "pending":
                out.append(Finding(missing_level, subject,
                    f"{rel} does not exist; generators reading it will fail"))
        if not s.software and not s.commit:
            out.append(Finding("warn", subject,
                "records no software or commit, so no version check can apply"))
        if s.status in ("frozen", "held-out") and not s.frozen_at:
            out.append(Finding("error", subject, f"is {s.status} but has no frozen_at"))
        if s.status == "held-out":
            if not s.first_scored_at:
                out.append(Finding("error", subject,
                    "is held-out but has no first_scored_at: record when it was "
                    "first scored, so a freeze after scoring is visible"))
            elif s.frozen_at and _when(s.frozen_at) > _when(s.first_scored_at):
                out.append(Finding("error", subject,
                    f"was frozen ({s.frozen_at}) after it was first scored "
                    f"({s.first_scored_at}): it is not held out"))
        stamped = lock.get(name)
        if s.verify:
            out += _verification(root, subject, s.verify, stamped, missing_level)
        if s.inputs and stamped is None:
            out.append(Finding("warn", subject,
                f"has inputs but was never stamped -- after checking the run: "
                f"just evidence-stamp {name}"))
        for rel in s.inputs:
            want = ((stamped or {}).get("inputs") or {}).get(rel)
            if not (root / rel).is_file():
                out.append(Finding("note", subject, f"input {rel} is not present"))
            elif want and hashcache.sha(root / rel) != want:
                out.append(Finding("error", subject,
                    f"{rel} changed after the set was stamped: the results were "
                    f"produced with the old setting. Re-run the set, or re-stamp "
                    f"if the change cannot affect it: just evidence-stamp {name}"))
            elif stamped is not None and not want:
                out.append(Finding("warn", subject,
                    f"input {rel} is not in the stamp: just evidence-stamp {name}"))
        if stamped and stamped.get("software") != s.produced_by():
            out.append(Finding("warn", subject,
                f"software in {evidence.MANIFEST} ({_fmt(s.produced_by())}) differs "
                f"from the stamp ({_fmt(stamped.get('software') or {})}): verify "
                f"the new run, then just evidence-stamp {name}"))
        if stamped and stamped.get("tree") and s.status in ("frozen", "held-out"):
            tree = _tree(root, s)
            if tree and tree != stamped["tree"]:
                out.append(Finding("error", subject,
                    f"is {s.status}, but its files changed since it was stamped "
                    f"({stamped.get('stamped_at')})"))
    return out


def _when(value: str) -> datetime:
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _fmt(software: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(software.items())) or "none"


def _verification(root, subject, rel, stamped, missing_level) -> list[Finding]:
    p = root / rel
    if not p.is_file():
        return [Finding(missing_level, subject, f"verification file {rel} does not exist")]
    out = []
    text = p.read_text(errors="replace")
    try:
        doc = json.loads(text)
    except ValueError:
        doc = None
    if isinstance(doc, dict) and "status" in doc:
        if str(doc["status"]).lower() not in evidence.VERIFIED:
            out.append(Finding("error", subject,
                f"{rel} says status {doc['status']!r}, not verified"))
    host = evidence.HOST_PATH.search(text)
    if host:
        snippet = text[host.start():host.start() + 40].split('"')[0]
        out.append(Finding("warn", subject,
            f"{rel} records a host path ({snippet}...); a reader on another "
            f"machine cannot follow it. Store paths relative to the repository"))
    want = ((stamped or {}).get("verify") or {}).get(rel)
    if stamped is None or not want:
        out.append(Finding("warn", subject,
            f"verification {rel} is not stamped: just evidence-stamp "
            f"{subject.split(' ', 1)[1]}"))
    elif hashcache.sha(p) != want:
        out.append(Finding("error", subject,
            f"{rel} changed since the set was stamped; re-check it, then "
            f"just evidence-stamp {subject.split(' ', 1)[1]}"))
    return out


def _entries(manifest: evidence.Manifest, docs: dict) -> list[Finding]:
    """Each entry's recorded versions against the manifest, and against itself."""
    out: list[Finding] = []
    for kind, doc in docs.items():
        for id, rec in sorted(doc["values"].items()):
            recorded = rec.get("evidence") or {}
            generated = (rec.get("origin") or {}).get("by") not in ("hand", "adopted", None)
            for name, software in sorted(recorded.items()):
                s = manifest.sets.get(name)
                if s is None:
                    out.append(Finding("error", id,
                        f"was built from evidence set {name!r}, which "
                        f"{evidence.MANIFEST} no longer declares -- run: just assets"))
                elif software != s.produced_by():
                    out.append(Finding("error", id,
                        f"was built from {name} with {_fmt(software)}; "
                        f"{evidence.MANIFEST} now says {_fmt(s.produced_by())} "
                        f"-- run: just assets"))
                elif s.status == "pending":
                    out.append(Finding("error", id, f"is built from pending set {name}"))
            clash = evidence.mixed(recorded)
            if clash:
                detail = "; ".join(f"{t} {' and '.join(v)}" for t, v in clash.items())
                if manifest.mixing_allowed(id):
                    out.append(Finding("note", id, f"mixes {detail} (allow_mixed)"))
                else:
                    out.append(Finding("error", id,
                        f"mixes versions of one tool: {detail}. Rebuild the older "
                        f"set, or list the id in allow_mixed if the comparison "
                        f"is the point"))
            covering = set(manifest.covering(id, kind))
            if generated and covering - set(recorded):
                out.append(Finding("warn", id,
                    f"is named by evidence set(s) {', '.join(sorted(covering - set(recorded)))} "
                    f"but was built before that was declared -- run: just assets"))
    for gen, sets in sorted((docs["stats"].get("evidence") or {}).items()):
        clash = evidence.mixed(sets)
        if clash:
            out.append(Finding("note", gen,
                f"resolved sets with different versions of "
                f"{', '.join(clash)}; each number records its own sets"))
        for name, software in sorted(sets.items()):
            s = manifest.sets.get(name)
            if s is not None and software != s.produced_by():
                out.append(Finding("warn", gen,
                    f"last read {name} at {_fmt(software)}; now "
                    f"{_fmt(s.produced_by())} -- run: just assets"))
    return out


def _pending(manifest: evidence.Manifest | None, docs: dict) -> list[Finding]:
    out: list[Finding] = []
    for kind, doc in docs.items():
        for key, reason in sorted((doc.get("pending") or {}).items()):
            out.append(Finding("error", key,
                f"is declared pending in {kind}.json ({reason}); the paper shows "
                f"a placeholder until the entry is removed"))
    if manifest is not None:
        for name, s in sorted(manifest.sets.items()):
            if s.status == "pending" and (s.stats or s.assets):
                patterns = ", ".join((*s.stats, *s.assets))
                out.append(Finding("note", f"set {name}",
                    f"pending set covers {patterns}; to show placeholders in "
                    f"the PDF, list them under `pending` in stats.json / assets.json"))
    return out


def _git_status(root: Path, paths: list[str]) -> tuple[set, set] | None:
    """(tracked, ignored) among paths, or None outside a git work tree."""
    if not paths:
        return set(), set()
    try:
        tracked = subprocess.run(["git", "ls-files", "-z", "--", *paths], cwd=root,
                                 capture_output=True, text=True, check=True).stdout
        ignored = subprocess.run(["git", "check-ignore", "--no-index", "--stdin"],
                                 cwd=root, input="\n".join(paths),
                                 capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return set(filter(None, tracked.split("\0"))), set(ignored.split())


def _inputs(root: Path, manifest: evidence.Manifest | None, docs: dict) -> list[Finding]:
    """Declared inputs git does not hold, and inputs recorded as host paths."""
    level = (manifest.checks if manifest else evidence.CHECKS)["untracked_inputs"]
    by_owner: dict[str, set] = {}
    for owner, inputs in (docs["stats"].get("sources") or {}).items():
        by_owner.setdefault(owner, set()).update(inputs)
    for id, rec in docs["assets"]["values"].items():
        owner = (rec.get("origin") or {}).get("by") or id
        by_owner.setdefault(owner, set()).update(rec.get("inputs") or {})
    out: list[Finding] = []
    host = {o: sorted(p for p in paths if p.startswith(("/", "~")) or re.match(r"[A-Za-z]:[\\/]", p))
            for o, paths in by_owner.items()}
    for owner, paths in sorted(host.items()):
        if paths:
            out.append(Finding("warn", owner,
                f"{len(paths)} input(s) recorded as host paths (e.g. {paths[0]}); "
                f"`just assets` now stores them relative to the manuscript"))
    if level == "off":
        return out
    candidates = sorted({p for o, ps in by_owner.items() for p in ps} - {p for ps in host.values() for p in ps})
    if manifest is not None:
        candidates = [p for p in candidates if not manifest.containing(root, p)]
    status = _git_status(root, candidates)
    if status is None:
        return out
    tracked, ignored = status
    for owner, paths in sorted(by_owner.items()):
        loose = sorted(p for p in paths if p in candidates and p not in tracked)
        if not loose:
            continue
        gone = [p for p in loose if p in ignored]
        example = ", ".join(loose[:2]) + (" ..." if len(loose) > 2 else "")
        out.append(Finding(level, owner,
            f"{len(loose)} declared input(s) not tracked by git"
            + (f" ({len(gone)} gitignored)" if gone else "")
            + f": {example}. A clone cannot re-check or rebuild from them: "
            f"commit them, or declare the data in {evidence.MANIFEST}"))
    return out


VERSION = re.compile(r'(?:lit\(\s*")?\bv?(\d+\.\d+\.\d+(?:[-+.][\w.]+)?)\b')


def _literals(root: Path, manifest: evidence.Manifest) -> list[Finding]:
    """Version literals in the prose that no set declares for the tool beside them."""
    level = manifest.checks["version_literals"]
    if level == "off":
        return []
    versions: dict[str, set] = {}
    for s in manifest.sets.values():
        for tool, ver in s.software.items():
            versions.setdefault(tool, set()).add(ver.lstrip("v"))
    if not versions:
        return []
    from manuscript_sources import source_files
    try:
        sources = source_files(root)
    except (OSError, ValueError):
        return []
    out: list[Finding] = []
    for path, src in sorted(sources.items()):
        for n, line in enumerate(src.splitlines(), 1):
            if line.lstrip().startswith("//"):
                continue
            for tool, known in versions.items():
                if not re.search(rf"(?<![\w-]){re.escape(tool)}(?![\w-])", line, re.I):
                    continue
                for m in VERSION.finditer(line):
                    if m.group(1) not in known:
                        out.append(Finding(level, f"{path}:{n}",
                            f"says {tool} {m.group(1)}, but {evidence.MANIFEST} "
                            f"declares {', '.join(sorted(known))}"))
    return out


def impact(root: Path, spec: str) -> tuple[list[str], int]:
    """Everything a version of a tool touches: sets, entries, and prose uses."""
    tool, _, ver = spec.partition("@")
    try:
        manifest = evidence.load(root)
        docs = _docs(root)
    except (evidence.EvidenceError, ManifestError) as e:
        return [str(e)], 1

    def hit(software: dict) -> bool:
        return tool in software and (not ver or software[tool].lstrip("v") == ver.lstrip("v"))

    sets = sorted(n for n, s in (manifest.sets.items() if manifest else ())
                  if hit(s.produced_by()))
    touched: dict[str, str] = {}
    for kind, doc in docs.items():
        for id, rec in doc["values"].items():
            why = [n for n, sw in (rec.get("evidence") or {}).items() if hit(sw)]
            if manifest:
                why += [n for n in manifest.covering(id, kind) if n in sets]
            if why:
                touched[id] = f"{kind[:-1] if kind == 'assets' else 'stat'} via {', '.join(sorted(set(why)))}"
    gens = sorted(g for g, sw in (docs["stats"].get("evidence") or {}).items()
                  if any(hit(v) for v in sw.values()))
    lines = [f"{spec}: {len(sets)} evidence set(s), {len(touched)} declared value(s)/asset(s)"]
    lines += [f"  set     {n}  ({manifest.sets[n].paths[0]})" for n in sets]
    lines += [f"  gen     {g}  (read a matching set)" for g in gens]
    from manuscript_sources import usages
    uses: dict[str, list] = {}
    for u in usages(root):
        uses.setdefault(u["id"], []).append(u)
    for id, why in sorted(touched.items()):
        lines.append(f"  {why.split(' ')[0]:<7} {id}  ({why.split(' ', 1)[1]})")
        for u in uses.get(id, []):
            lines.append(f"            {u['path']}:{u['line']}  {u['context'][:90]}")
    return lines, 0


def check(root: Path, strict: bool = False) -> list[Finding]:
    try:
        docs = _docs(root)
    except ManifestError as e:
        return [Finding("error", "manifests", str(e))]
    try:
        manifest = evidence.load(root)
    except evidence.EvidenceError as e:
        return [Finding("error", evidence.MANIFEST, str(e))]
    found: list[Finding] = []
    if manifest is not None:
        found += _sets(root, manifest, strict)
        found += _entries(manifest, docs)
        found += _literals(root, manifest)
    found += _pending(manifest, docs)
    found += _inputs(root, manifest, docs)
    return found


def main(argv: list[str]) -> int:
    if argv[:1] == ["--stamp"]:
        lines, rc = stamp(ROOT, argv[1:])
        print("\n".join(lines))
        return rc
    if argv[:1] == ["--impact"]:
        if len(argv) != 2:
            print("usage: just impact TOOL[@VERSION]")
            return 2
        lines, rc = impact(ROOT, argv[1])
        print("\n".join(lines))
        return rc
    found = check(ROOT, strict="--strict" in argv)
    from report import findings
    findings([(f.level, f.id, f.msg) for f in found])
    errors = sum(f.level == "error" for f in found)
    try:
        manifest = evidence.load(ROOT)
    except evidence.EvidenceError:
        manifest = None
    sets = len(manifest.sets) if manifest else 0
    print(f"  {sets} evidence set(s)" if (ROOT / evidence.MANIFEST).is_file()
          else f"  no {evidence.MANIFEST}: inputs and pending checks only",
          end="")
    print(f", {errors} error(s)" if errors else ", no errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
