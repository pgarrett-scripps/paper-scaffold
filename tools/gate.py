#!/usr/bin/env python3
"""The agent workflow around `just verify`: one lock, one stamp, one hook.

    locked CMD...      run CMD holding the manuscript build lock, waiting for
                       another build (PAPER_BUILD_WAIT, default 900 s) instead
                       of failing, and checking free disk first. `just paper`
                       runs through this, so two sessions building the same
                       manuscript queue instead of colliding halfway.
    fingerprint        the hash of every non-ignored file in the manuscript
                       directory (tracked and untracked, as git sees them)
    stamp FP RC        after verify: record a pass for fingerprint FP when RC
                       is 0 and the tree has not moved since FP was taken;
                       remove any pass otherwise
    check-stamp        exit 0 when the recorded pass matches the tree now
    install-hook       write a git pre-commit hook that runs check-stamp

The pass stamp is .build-state/verify-pass.json. It is local state, never
committed: it says "verify passed on exactly these files, here". The
pre-commit hook is optional (`just install-hooks`); it checks the WORKING
TREE, so a commit of a partial staging after a clean verify still passes.
Bypass it once with `git commit --no-verify`.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from paths import ROOT  # the manuscript (tools/paths.py)

STAMP = Path(".build-state") / "verify-pass.json"
HOOK_MARK = "# paper-scaffold verify-stamp hook"
# Local state that never describes the manuscript, even in a directory whose
# .gitignore predates it.
SKIP_DIRS = {".git", ".build-state", ".edit-guard", ".review", ".venv", "__pycache__",
             "submission", "viz", ".paper"}
SKIP_FILES = {".hash-cache.json", "stats-rendered.json", "paper.resolved.typ"}


def _files(root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z", "-co", "--exclude-standard", "--", "."],
                             cwd=root, capture_output=True, check=True).stdout
        names = [n for n in out.decode().split("\0") if n]
    except (OSError, subprocess.CalledProcessError):
        names = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
    return sorted(n for n in names
                  if not set(Path(n).parts) & SKIP_DIRS and Path(n).name not in SKIP_FILES
                  and (root / n).is_file())


def fingerprint(root: Path = ROOT) -> str:
    """One hash over every non-ignored file's path and content."""
    import hashcache
    h = hashlib.sha256()
    for name in _files(root):
        h.update(name.encode() + b"\0")
        h.update(hashcache.sha(root / name).encode() + b"\0")
    return h.hexdigest()


def stamp(root: Path, fp: str, rc: int) -> int:
    path = root / STAMP
    if rc != 0:
        path.unlink(missing_ok=True)
        return 0
    now = fingerprint(root)
    if now != fp:
        path.unlink(missing_ok=True)
        print("note:    the files changed while verify ran; no pass recorded. Run it again.")
        return 0
    path.parent.mkdir(exist_ok=True)
    from atomic_io import write_text
    write_text(path, json.dumps({"schema_version": 1, "fingerprint": fp,
                                 "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                                indent=1) + "\n")
    return 0


def check_stamp(root: Path = ROOT) -> int:
    path = root / STAMP
    try:
        recorded = json.loads(path.read_text())["fingerprint"]
    except (OSError, ValueError, KeyError, TypeError):
        print(f"no verify pass recorded for {root.name}: run `just verify` "
              "(or `just gate`) before committing, or commit with --no-verify")
        return 1
    if recorded != fingerprint(root):
        print(f"{root.name} changed since `just verify` last passed: run it again "
              "(or `just gate`), or commit with --no-verify")
        return 1
    print("verify passed on exactly these files")
    return 0


def install_hook(root: Path = ROOT) -> int:
    try:
        hooks = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=root,
                               capture_output=True, text=True, check=True).stdout.strip()
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root,
                             capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        print("not a git repository: no hook to install")
        return 1
    hook = (root / hooks if not Path(hooks).is_absolute() else Path(hooks)) / "pre-commit"
    if hook.exists() and HOOK_MARK not in hook.read_text(errors="replace"):
        print(f"{hook} exists and is not this scaffold's: left untouched. Add a "
              f"call to `just -f {root}/justfile check-verify-stamp` to it by hand.")
        return 1
    rel = os.path.relpath(root, top)
    prefix = "" if rel == "." else rel.rstrip("/") + "/"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(f"""#!/bin/sh
{HOOK_MARK}: `just install-hooks` wrote this; delete it to opt out.
# Refuse a commit touching the manuscript unless `just verify` passed on the
# working tree as it is now. Bypass once: git commit --no-verify
git diff --cached --name-only | grep -q '^{prefix}' || exit 0
cd "$(git rev-parse --show-toplevel)/{prefix or '.'}" || exit 1
exec just check-verify-stamp
""")
    hook.chmod(0o755)
    print(f"installed {hook}: commits touching {prefix or 'this repository'} need a "
          "current verify pass")
    return 0


def locked(root: Path, command: list[str]) -> int:
    from build_state import HELD, build_lock
    try:
        wait = float(os.environ.get("PAPER_BUILD_WAIT", "900"))
    except ValueError:
        wait = 900.0
    owner = f"pid {os.getpid()}: {' '.join(command)} since {time.strftime('%H:%M:%S')}"
    try:
        with build_lock(root, wait=wait, owner=owner):
            env = dict(os.environ)
            env[HELD] = str((root / ".build-state" / "build.lock").resolve())
            return subprocess.run(command, cwd=root, env=env).returncode
    except ValueError as exc:
        print(f"build not started: {exc}", file=sys.stderr)
        return 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    root = ROOT
    if cmd == "fingerprint":
        print(fingerprint(root))
        return 0
    if cmd == "stamp" and len(rest) == 2:
        return stamp(root, rest[0], int(rest[1]))
    if cmd == "check-stamp":
        return check_stamp(root)
    if cmd == "install-hook":
        return install_hook(root)
    if cmd == "locked" and rest:
        return locked(root, rest[1:] if rest[0] == "--" else rest)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
