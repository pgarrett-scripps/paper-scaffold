"""Where things are: the manuscript, and the toolchain's own files.

Until 4.0.0 every tool found the manuscript as `Path(__file__).parent.parent`,
because the tools sat in the manuscript's own `tools/`. They now also run from
an installed package (docs/package.md), where that expression names
site-packages. So the two questions are answered separately:

- ROOT is the manuscript: `$PAPER_ROOT` when set (the justfile exports it
  as its own directory, and `paper tool` sets it to the working directory
  otherwise), so a recipe always sees the manuscript root. Without it, tools
  running from a checkout find the manuscript as before, the directory above
  tools/, and tools running from the installed package use the working
  directory. `paper test` clears it, so a test's temporary manuscript is
  never mistaken for the one the suite was started from.
- DATA is the toolchain: the directory holding `tools/`, `journals/`, `word/`
  and `tests/`. In the scaffold checkout that is the repository (so ROOT and
  DATA coincide there, as they always did); in an installed wheel it is
  `paper_scaffold/data/`.

`locate()` is the one place a manuscript file may shadow a toolchain file: a
paper's own `word/paper-reference.docx` or `journals/<name>.toml` wins over
the package's copy.
"""
from __future__ import annotations

import os
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DATA = TOOLS.parent

# Paths a manuscript name may resolve to inside the toolchain when the
# manuscript has no file of its own there.
SHADOWED = ("tools/", "journals/", "word/")


# True when these tools are the installed package's (paper_scaffold/data/tools).
PACKAGED = DATA.name == "data" and DATA.parent.name == "paper_scaffold"


def manuscript_root() -> Path:
    env = os.environ.get("PAPER_ROOT")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve() if PACKAGED else DATA


ROOT = manuscript_root()


def locate(root: Path, name: str) -> Path:
    """`root/name`, or the toolchain's copy when the manuscript has none.

    Only names under SHADOWED fall back; anything else is the manuscript's
    and is returned as `root/name` whether or not it exists.
    """
    path = root / name
    if path.exists() or not name.startswith(SHADOWED):
        return path
    packaged = DATA / name
    return packaged if packaged.exists() else path


def tool(name: str) -> Path:
    """A file among the tools, by name (`render_stats.py`)."""
    return TOOLS / name


def version() -> str:
    """The toolchain release these tools belong to.

    A checkout's pyproject.toml is the truth there (whatever else the running
    interpreter has installed); an installed wheel has none and asks the
    distribution metadata.
    """
    import re
    py = DATA / "pyproject.toml"
    if not PACKAGED and py.is_file():
        m = re.search(r'^version = "([^"]+)"', py.read_text(), re.MULTILINE)
        if m:
            return m.group(1)
    try:
        from importlib.metadata import version as dist_version
        return dist_version("paper-scaffold")
    except Exception:  # a captured copy with no metadata
        return "unknown"
