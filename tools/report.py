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


SEVERITY_STYLE = {
    "error": "bold red",
    "ERROR": "bold red",
    "warn": "yellow",
    "note": "dim",
}


def findings(rows) -> None:
    """Print findings as a table: (severity, subject, message) triples.

    Everything goes through Text, never markup: finding messages legitimately
    contain brackets ("outside its declared range [500, inf]"), and rich would
    read those as style tags and silently swallow them.
    """
    from rich.text import Text
    if not rows:
        return
    t = Table(box=box.SIMPLE_HEAD, show_header=False, pad_edge=False)
    t.add_column(no_wrap=True)                       # severity
    t.add_column(style="bold", overflow="fold")      # subject
    t.add_column()                                   # message; wraps
    for sev, subject, msg in rows:
        t.add_row(Text(sev, style=SEVERITY_STYLE.get(sev, "")),
                  Text(str(subject)), msg if isinstance(msg, Text) else Text(str(msg)))
    console.print(t)
