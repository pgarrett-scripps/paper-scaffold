"""The paper-scaffold toolchain as an installed package (docs/package.md).

The package code is small: the `paper` console script, `paper sync` and
`paper migrate`. Everything a paper runs or reads (tools/, tests/, journals/,
word/, docs/, the justfile and the generated Typst and Python helpers) is
package data under `data/`, laid out as in the scaffold repository.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def data_dir() -> Path:
    """`paper_scaffold/data/` in a wheel; the repository in an editable install."""
    packaged = HERE / "data"
    return packaged if packaged.is_dir() else HERE.parent.parent


def tools_dir() -> Path:
    return data_dir() / "tools"


def use_tools() -> None:
    """Put the toolchain's tools/ first on sys.path (they import each other)."""
    tools = str(tools_dir())
    if tools not in sys.path:
        sys.path.insert(0, tools)


def version() -> str:
    use_tools()
    import paths
    return paths.version()
