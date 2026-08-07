"""One look for every console report.

The word count, readability and density reports each build their table here, so
they stay visually consistent and a style decision is made once. Deliberately
restrained: thin rules, right-aligned numbers, no color except the accents that
carry meaning. Rich drops the styling automatically when output is piped, so CI
logs and `just paper | tee` stay plain, greppable text.
"""
from __future__ import annotations

import sys

from rich import box
from rich.console import Console
from rich.table import Table

# When output is piped (CI, tee, an agent reading it) rich assumes an 80-column
# terminal and truncates table cells to fit -- "numerals" becomes "nume…", which
# is worse than no styling at all. A real terminal reports its own width; for
# everything else the reports are allowed the width they need.
console = Console(highlight=False,
                  width=None if sys.stdout.isatty() else 200)


def table(title: str, caption: str | None = None) -> Table:
    return Table(
        title=title,
        title_justify="left",
        title_style="bold",
        caption=caption,
        caption_justify="left",
        caption_style="dim",
        box=box.SIMPLE_HEAD,
        header_style="dim",
        pad_edge=False,
    )
