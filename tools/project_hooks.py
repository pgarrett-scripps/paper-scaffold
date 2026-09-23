"""Project-owned extension hooks, declared in project.toml.

The scaffold owns the justfile, tools/ and tests/; a paper that needs one
more gate stage, a Word touch-up or an extra source file used to get it by
editing those files, and every upgrade then had to merge the edit back in by
hand. project.toml is the paper's file instead: the scaffold reads it and
never writes it, and `just upgrade-plan` never offers to replace it.

Every hook is opt-in. With no project.toml, every function here returns the
empty answer and every recipe behaves exactly as it did before the file
existed. docs/hooks.md is the reference; this is the reader.

    uv run python tools/project_hooks.py show            # what is declared
    uv run python tools/project_hooks.py stages verify   # run one gate's stages
    uv run python tools/project_hooks.py bib-audit-args  # preflight's flags
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from document_project import keys, tomllib  # noqa: E402

FILE = "project.toml"
# Where each gate's project stages run:
#   verify     -- at the end of `just verify`, after the scaffold's stages
#   check      -- at the end of `just check` (so also inside verify)
#   preflight  -- at the end of `just preflight`, before its verdict
#   submission -- after the upload set, in `just submission` and `just all`
GATES = ("verify", "check", "preflight", "submission")
STAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.:/+-]*")


@dataclass(frozen=True)
class Stage:
    name: str
    run: str


@dataclass(frozen=True)
class Project:
    stages: dict[str, tuple[Stage, ...]] = field(
        default_factory=lambda: {g: () for g in GATES})
    bib_audit_require_complete: bool = True
    declared: bool = False


def _stages(value, where: str) -> tuple[Stage, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{where}: expected a list of {{name, run}} tables")
    out, seen = [], set()
    for i, item in enumerate(value):
        here = f"{where}[{i}]"
        keys(item, {"name", "run"}, here)
        name, run = item.get("name"), item.get("run")
        if not isinstance(name, str) or not STAGE_NAME.fullmatch(name):
            raise ValueError(f"{here}: name must be a short label, got {name!r}")
        if name in seen:
            raise ValueError(f"{here}: stage {name!r} is declared twice")
        if not isinstance(run, str) or not run.strip():
            raise ValueError(f"{here}: run must be a nonempty shell command")
        seen.add(name)
        out.append(Stage(name, run))
    return tuple(out)


def load(root: Path = ROOT) -> Project:
    """project.toml, validated; the empty Project when there is none.

    Unknown keys are an error, not ignored: a misspelt `[stages.verfiy]`
    that silently ran nothing would be a gate that never fails.
    """
    path = root / FILE
    if not path.is_file():
        return Project()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{FILE}: {exc}") from None
    keys(data, {"schema_version", "stages", "preflight"}, FILE)
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError(f"{FILE}: schema_version must be 1")

    stages = {g: () for g in GATES}
    table = data.get("stages", {})
    keys(table, set(GATES), f"{FILE} [stages]")
    for gate, value in table.items():
        stages[gate] = _stages(value, f"{FILE} stages.{gate}")

    preflight = data.get("preflight", {})
    keys(preflight, {"bib_audit_require_complete"}, f"{FILE} [preflight]")
    complete = preflight.get("bib_audit_require_complete", True)
    if not isinstance(complete, bool):
        raise ValueError(f"{FILE} [preflight]: bib_audit_require_complete must be true or false")

    return Project(stages=stages, bib_audit_require_complete=complete,
                   declared=True)


def run_stages(gate: str, root: Path = ROOT, project: Project | None = None) -> int:
    """Run one gate's project stages, every one even after a failure.

    Each prints under its own `=== name ===` header, the shape verify and
    preflight already use, so a failing project stage is named in the same
    place as a failing scaffold one. Nothing prints when nothing is declared.
    """
    project = project or load(root)
    rc = 0
    env = {**os.environ, "PAPER_ROOT": str(root)}
    for stage in project.stages[gate]:
        print(f"\n=== {stage.name} (project.toml) ===", flush=True)
        done = subprocess.run(["bash", "-c", stage.run], cwd=root, env=env)
        if done.returncode:
            print(f"project stage {stage.name!r} failed (exit {done.returncode}): {stage.run}")
            rc = 1
    return rc


def describe(project: Project) -> list[str]:
    if not project.declared:
        return [f"no {FILE}: no project hooks declared (see docs/hooks.md)"]
    lines = []
    for gate in GATES:
        for stage in project.stages[gate]:
            lines.append(f"stage      {gate:<10} {stage.name}: {stage.run}")
    if not project.bib_audit_require_complete:
        lines.append("preflight  bib-audit runs without --require-complete")
    return lines or [f"{FILE} declares no hooks"]


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="list the hooks project.toml declares")
    stages = sub.add_parser("stages", help="run one gate's project stages")
    stages.add_argument("gate", choices=GATES)
    sub.add_parser("bib-audit-args", help="the flags preflight passes bib-audit")
    args = parser.parse_args(argv)
    try:
        project = load(root)
    except (OSError, ValueError) as exc:
        if args.command == "stages":
            # Inside verify/preflight: name the failure where it is read.
            print(f"\n=== {FILE} ===", flush=True)
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.command == "show":
        print("\n".join(describe(project)))
        return 0
    if args.command == "bib-audit-args":
        print("--require-complete" if project.bib_audit_require_complete else "")
        return 0
    return run_stages(args.gate, root, project)


if __name__ == "__main__":
    raise SystemExit(main())
