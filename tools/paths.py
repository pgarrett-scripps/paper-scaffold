"""Where things are: the manuscript, and the toolchain's own files.

Until 4.0.0 every tool found the manuscript as `Path(__file__).parent.parent`,
because the tools sat in the manuscript's own `tools/`. They now also run from
an installed package (docs/package.md), where that expression names
site-packages. So the two questions are answered separately:

- ROOT is the manuscript. Tools running from a checkout (the scaffold
  repository, a captured manuscript under .build-state/) find it as before:
  the directory above tools/. Tools running from the installed package use
  `$PAPER_ROOT` if set, else the working directory; `just` runs every recipe
  from the justfile's directory and `paper tool` sets `$PAPER_ROOT`, so a
  recipe always sees the manuscript root.
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
    if not PACKAGED:
        return DATA
    env = os.environ.get("PAPER_ROOT")
    return Path(env).resolve() if env else Path.cwd().resolve()


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
