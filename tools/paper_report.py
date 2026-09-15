"""Run independent manuscript reports together, displaying them in order."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def main(root: Path = ROOT) -> int:
    # Capture each report so concurrent processes cannot interleave tables.
    # Both must finish before returning, including when either one fails.
    commands = (
        ["bash", str(root / "tools/wordcount.sh")],
        [sys.executable, str(root / "tools/readability.py")],
    )
    env = os.environ.copy()
    if sys.stdout.isatty():
        # Capturing output must not turn the interactive Rich tables into
        # unstyled, 200-column piped reports.
        env["FORCE_COLOR"] = "1"
        env["PAPER_REPORT_COLUMNS"] = str(os.get_terminal_size().columns)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(subprocess.run, command, cwd=root,
                            capture_output=True, text=True, env=env)
                for command in commands]
        results = [job.result() for job in jobs]
    for index, result in enumerate(results):
        if index:
            print()
        print(result.stdout, end="", flush=True)
        print(result.stderr, end="", file=sys.stderr, flush=True)
        if result.returncode:
            return result.returncode
    print("  density and per-section outliers: just density")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
