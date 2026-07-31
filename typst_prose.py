#!/usr/bin/env python3
"""Typst source-stripping primitives shared by the prose extractors.

readability.py and audio/extract_prose.py do different jobs: one drops math
because it is exempt from a reading-level score, the other verbalizes it so a
voice can read it aloud. Their pipelines are only about a quarter alike, so they
stay separate. But they must agree exactly on how to RECOGNIZE a construct, and
the four things below are where that matters.

They live here because keeping them in two places has already cost us. An
80-column reflow broke `#refn(<x>)`, `_two word emphasis_` and `#link(` across
lines, and each fix had to be made twice, in two files, correctly. Next time it
is one edit.

Everything here has to tolerate a line break in the middle, because `just fmt`
puts them there.
"""
from __future__ import annotations

import re

# A cross-reference through the manuscript's `refn` helper. The \s* are
# load-bearing: typstyle breaks long lines INSIDE the call, so this can arrive as
# `#refn(\n  <tab:x>,\n)`. Matched without them, the leftover `)` closes the
# surrounding `(@...)` parenthetical early and the wrong span gets stripped.
REFN = r"#refn\(\s*<[^>]*>\s*,?\s*\)"

# `#link("url")[shown text]` -> group 1 is the shown text. The url argument may
# sit on its own line after a reflow.
LINK = r'#link\(\s*"[^"]*"\s*,?\s*\)\s*\[([^\]]*)\]'


def markup(delim: str) -> str:
    """Pattern for one inline-markup pair (`*strong*`, `_emph_`), tolerant of the
    line break `just fmt` may have put inside it. Group 1 is the content.

    typstyle reflows prose to 80 columns and will happily break
    `_Saccharomyces cerevisiae_` across two lines. A `[^_\\n]+` body then stops
    matching, and the literal underscores survive into the word count and the
    narration.

    Allowing the newline is not enough on its own: it lets the pair span lines and
    match things that are not markup at all, such as a filename glob (`smooth_*`)
    or a subscript left behind by math (`"median"_"orig"`). So the delimiter must
    also sit where markup can sit -- not butted against an identifier character or
    a quote, and not against the whitespace inside the pair. That is what
    separates `_E. coli_`, which is real emphasis and legal directly after a `/`,
    from `smooth_*`, which is a glob.
    """
    d = re.escape(delim)
    body = rf"(?:[^{d}\n]|\n(?!\s*\n))+?"
    return rf'(?<![A-Za-z0-9_"]){d}(?!\s)({body})(?<!\s){d}(?![A-Za-z0-9_"])'


def strip_balanced(text: str, opener: str) -> str:
    """Remove `opener` ... matching-close-paren blocks (e.g. `#figure( ... )`),
    along with any `<label>` that trails the closing paren.

    Paren-matching rather than a regex, so it is indifferent to how the contents
    are wrapped and to nesting.
    """
    out, i = [], 0
    while i < len(text):
        j = text.find(opener, i)
        if j == -1:
            out.append(text[i:])
            break
        out.append(text[i:j])
        k = j + len(opener) - 1  # index of the '('
        depth = 0
        while k < len(text):
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
                if depth == 0:
                    k += 1
                    break
            k += 1
        m = re.match(r"\s*<[^>]+>", text[k:])
        if m:
            k += m.end()
        i = k
    return "".join(out)
