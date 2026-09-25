"""The `paper` console script (docs/package.md).

    paper tool NAME [ARGS...]   run tools/NAME(.py) from the package, in-process
    paper test [--update|--docx] the extractor fixture check (the full suite in
                                the scaffold checkout)
    paper sync [--check]        write / check the generated files and the lock
    paper upgrade-notes         HISTORY Upgrade: lines since the lock's release
    paper version               installed release, the pin, the lock
    paper path [NAME]           where the package's data (or one file) is
    paper migrate --project P   move a 3.x paper onto the package
"""
from __future__ import annotations

import argparse
import os
import runpy
import subprocess
import sys
from pathlib import Path

from . import data_dir, tools_dir, use_tools, version


def run_tool(name: str, args: list[str]) -> int:
    tools = tools_dir()
    path = tools / name
    if not path.is_file():
        path = tools / f"{name}.py"
    if not path.is_file() or path.parent != tools:
        known = sorted(p.stem for p in tools.glob("*.py") if not p.stem.startswith("_"))
        print(f"paper tool: no tool {name!r}; one of: {', '.join(known)}",
              file=sys.stderr)
        return 2
    # The manuscript is where the command runs (tools/paths.py). `just` exports
    # PAPER_ROOT as the justfile's directory; keep it when set.
    os.environ.setdefault("PAPER_ROOT", str(Path.cwd().resolve()))
    if path.suffix == ".sh":
        os.execvp("bash", ["bash", str(path), *args])
    # Exactly what `python tools/NAME.py ARGS` did: the script's directory
    # first on sys.path, run as __main__.
    sys.argv = [str(path), *args]
    sys.path.insert(0, str(tools))
    runpy.run_path(str(path), run_name="__main__")
    return 0


def is_checkout() -> bool:
    return (data_dir() / "scripts" / "new-paper.sh").is_file()


def run_tests(update: bool, docx: bool) -> int:
    data, checkout = data_dir(), is_checkout()
    tests = data / "tests"
    if (update or docx) and not checkout:
        print("paper test: --update and --docx test the toolchain itself; run "
              "them in the scaffold checkout", file=sys.stderr)
        return 2
    py = sys.executable
    # A test builds its own temporary manuscripts; the caller's $PAPER_ROOT
    # (exported by `just test`) must not point their tools back here.
    env = {k: v for k, v in os.environ.items() if k != "PAPER_ROOT"}
    if docx:
        cmds = [[py, "-m", "unittest", "discover", "-s", str(tests), "-p", p]
                for p in ("test_document_docx.py", "test_paper_word.py")]
    else:
        cmds = [[py, str(tests / "run.py")]
                + (["--update"] if update else [])
                + ([] if checkout else ["--fixture-only"])]
        if checkout and not update:
            cmds += [[py, "-m", "unittest", "discover", "-s", str(tests), "-p", p]
                     for p in ("test_export_text.py", "test_word_audit.py",
                               "test_wordcount.py")]
    for cmd in cmds:
        rc = subprocess.run(cmd, env=env).returncode
        if rc:
            return rc
    return 0


def show_version(root: Path) -> int:
    from . import sync as sync_mod
    print(f"paper-scaffold {version()}")
    if sync_mod.is_scaffold_checkout(root):
        print("  source  this checkout (editable)")
        return 0
    print(f"  pin     {sync_mod.read_pin(root) or 'none in pyproject.toml'}")
    try:
        lock = sync_mod.read_lock(root)
    except sync_mod.SyncError as e:
        print(f"  lock    {e}")
        return 1
    if lock is None:
        print("  lock    none (run: uv run paper sync)")
    else:
        v = lock.get("scaffold", {}).get("version")
        note = "" if v == version() else "  <- differs: run uv run paper sync"
        print(f"  lock    written by {v}{note}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["tool"]:
        if len(argv) < 2:
            print("usage: paper tool NAME [ARGS...]", file=sys.stderr)
            return 2
        return run_tool(argv[1], argv[2:])
    if argv[:1] == ["port-diff"]:
        return run_tool("port", ["diff", *argv[1:]])
    if argv[:1] == ["upgrade-notes"]:
        use_tools()
        import upgrade_plan
        return upgrade_plan.main(argv[1:])

    ap = argparse.ArgumentParser(prog="paper", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tool", help="run a tool from the package")
    sub.add_parser("upgrade-notes", help="HISTORY Upgrade: lines since the lock")
    sub.add_parser("port-diff", help="a ported part's upstream stats.json, "
                                     "recorded commit vs HEAD (docs/multi-document.md)")
    t = sub.add_parser("test", help="the extractor fixture check")
    t.add_argument("--update", action="store_true")
    t.add_argument("--docx", action="store_true")
    s = sub.add_parser("sync", help="write or check the generated files")
    s.add_argument("--check", action="store_true")
    s.add_argument("--force", action="store_true",
                   help="overwrite generated files even when edited")
    s.add_argument("--root", default=None, help="the paper (default: here)")
    v = sub.add_parser("version", help="installed release, pin and lock")
    v.add_argument("--root", default=None)
    p = sub.add_parser("path", help="the package's data directory, or one file in it")
    p.add_argument("name", nargs="?")
    m = sub.add_parser("migrate", help="move a 3.x paper onto the package")
    m.add_argument("--project", required=True)
    m.add_argument("--scaffold", default=None,
                   help="a scaffold clone with the release tags")
    m.add_argument("--from", dest="base", default=None,
                   help="the paper's release (default: pyproject's version)")
    m.add_argument("--pin", default=None, help="the dependency line to write")
    m.add_argument("--dry-run", action="store_true")
    m.add_argument("--no-install", action="store_true",
                   help="skip uv lock / uv sync; sync from this environment")
    a = ap.parse_args(argv)

    here = Path.cwd().resolve()
    if a.cmd == "test":
        return run_tests(a.update, a.docx)
    if a.cmd == "sync":
        from .sync import main_sync
        root = Path(a.root).expanduser().resolve() if a.root else here
        return main_sync(root, a.check, a.force)
    if a.cmd == "version":
        return show_version(Path(a.root).resolve() if a.root else here)
    if a.cmd == "path":
        if not a.name:
            print(data_dir())
            return 0
        use_tools()
        from paths import locate
        print(locate(here, a.name))
        return 0
    if a.cmd == "migrate":
        from .migrate import main as migrate_main
        return migrate_main(Path(a.project).expanduser(),
                            Path(a.scaffold).expanduser() if a.scaffold else None,
                            a.base, a.pin, a.dry_run, not a.no_install)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
