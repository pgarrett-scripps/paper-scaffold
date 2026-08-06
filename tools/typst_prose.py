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

import json
import re
from pathlib import Path

# A number pulled from the analysis through the manuscript's `s` helper:
# `#s("effect.treated_fold")`. Tolerant of a reflow putting a break inside the
# call, like every other pattern here.
#
# These MUST be resolved rather than stripped. The word count and the narration
# read the SOURCE, not the compiled PDF, so a stripped call silently deletes a
# number from the count and a spoken sentence loses its figure, while an
# unstripped one leaks `#s("effect.treated_fold")` into both. Only substituting
# the real value leaves the extractors seeing what a reader sees.
STATS = r'#s\(\s*"([^"]+)"\s*,?\s*\)'

# The raw-value helper, `#n("cohort.total_n")`. Rarer in prose than `s`, because
# `n` exists for arithmetic and stats.typ says to prefer `s` for anything a
# reader sees -- but "rarer" is not "never", and an unhandled one leaked the call
# text verbatim into the word count and gave the narrator `#n("cohort.total_n")`
# to read aloud. Exactly the `#ref(` failure again, which reached 68 places.
#
# Resolves to the RAW value, not the display string, because that is what Typst
# renders for this helper. A `n()` nested inside a larger expression
# (`#calc.round(n("a") / n("b"), digits: 1)`) is a different and much bigger
# problem: the whole expression would have to be evaluated. This handles the
# direct call only.
STATS_N = r'#n\(\s*"([^"]+)"\s*,?\s*\)'

# Written by analysis/scripts/gen_stats.py, beside the generated SI tables.
# .parent.parent because this file lives in tools/; si/ is at the root.
STATS_JSON = Path(__file__).resolve().parent.parent / "si" / "stats.json"

# An explicit cross-reference call: Typst's own `#ref(<x>)` or a manuscript's
# `#refn(<x>)` helper. BOTH forms have to be here. `#ref(` is the more natural
# thing for an author to write, and a pattern that only knew the helper left a
# bare `#ref( )` in the word count, the reading-level score and the narration --
# in 68 places in the manuscript that found this, with the PDF correct throughout.
#
# The \s* are load-bearing for a different reason: typstyle breaks long lines
# INSIDE the call, so this can arrive as `#ref(\n  <tab:x>,\n)`. Matched without
# them, the leftover `)` closes the surrounding `(@...)` parenthetical early and
# the wrong span gets stripped.
REFN = r"#refn?\(\s*<[^>]*>\s*,?\s*\)"

# `#link("url")[shown text]` -> group 1 is the shown text. The url argument may
# sit on its own line after a reflow.
#
# The `[...]` is OPTIONAL, and that is the whole point. `#link("https://x")` with
# no body is valid Typst -- it renders the URL as its own visible text -- and it
# is what an author writes in a data-availability or code-availability
# statement, which is the one place a manuscript reliably has bare URLs. A
# pattern that demanded the bracket matched none of them, so the entire call
# survived into the word count and the narrator read the URL aloud, character by
# character. Exactly the `#ref(` failure, in the section every paper now has.
LINK = r'#link\(\s*"[^"]*"\s*,?\s*\)(?:\s*\[([^\]]*)\])?'


# A footnote call. Needs its own rule ahead of the generic `#name[` -> `[`
# stripper, which is deliberately gap-free so that `H#sub[2]O` stays "H2O" and an
# emphasis butted against a word does not gain a space it never had.
#
# A footnote is the opposite case: it attaches directly to the word it annotates
# ("the value was high#footnote[Measured in triplicate.]"), so the gap-free rule
# welded the note onto that word. The word count then saw "highMeasured" as one
# token and the narrator pronounced it as one.
#
# The note's text is KEPT, which is the behaviour this has always had. Whether a
# footnote should count toward a journal limit, or be read aloud at all, is a
# policy question and a separate one from this.
FOOTNOTE = r"#footnote\s*\["


def strip_links(text: str) -> str:
    """Replace every `#link(...)` with its shown text, or nothing if it has none.

    A bare link is dropped rather than replaced by its URL: a URL is not words a
    journal counts, and it is certainly not a sentence anyone wants read out. The
    same reasoning already governs the `[shown text]` form, whose URL is
    discarded.

    A function rather than `re.sub(LINK, r"\\1", ...)` at each call site, because
    the optional group is None for a bare link and a `\\1` backreference raises on
    it. Shared for the reason everything else here is: the two extractors have
    already been fixed separately, three times.
    """
    return re.sub(LINK, lambda m: m.group(1) or "", text)

# A bare citation key or cross-reference: @smith2020, @fig:x, @sec:methods.
#
# The colon is matched only when an identifier follows it. A plain `[A-Za-z0-9:_-]+`
# class also swallows a colon that is punctuation rather than part of the key, so
# `@smith2020: the counts` lost the colon that introduced the clause. Typst's own
# parser stops at the same place.
CITE = r"@[A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*"


# A Typst Unicode escape, `\u{2082}`. A manuscript writing subscripts that way
# (log\u{2082} ratios) otherwise has the escape reach the prose verbatim: the word
# counter counts "log\u{2082}" as one opaque token and the narrator reads it aloud
# as "log u 2082". Resolving it to the character it denotes is what both consumers
# want, and it lets the narrator's spoken-Unicode map handle the result like any
# other symbol.
UNICODE_ESCAPE = re.compile(r"\\u\{([0-9A-Fa-f]{1,6})\}")


def unescape_unicode(text: str) -> str:
    """Resolve Typst `\\u{XXXX}` escapes to the characters they denote."""
    def sub(m: "re.Match[str]") -> str:
        try:
            return chr(int(m.group(1), 16))
        except (ValueError, OverflowError):
            return m.group(0)
    return UNICODE_ESCAPE.sub(sub, text)


def resolve_stats(text: str, path: Path | None = None) -> str:
    """Substitute `#s("id")` and `#n("id")` with their values from si/stats.json.

    `s` resolves to the display string (already rounded by the analysis), `n` to
    the raw value, matching what Typst renders for each.

    A no-op when the text contains neither call, so a manuscript that does not
    use the mechanism (and has no stats.json) still extracts. When it IS used,
    both a missing file and an unknown id raise: the same failure Typst gives at
    compile time, rather than a number quietly vanishing from the word count.
    """
    if not re.search(STATS, text) and not re.search(STATS_N, text):
        return text
    p = path or STATS_JSON
    if not p.is_file():
        raise SystemExit(
            f'error: prose uses #s("...") or #n("...") but {p} is missing; '
            f"regenerate it with `just assets`")
    values = json.loads(p.read_text()).get("values", {})

    def repl(field: str):
        def sub(m: re.Match) -> str:
            id = m.group(1)
            if id not in values:
                raise SystemExit(
                    f"error: {p.name} has no value '{id}'; declare it in "
                    f"analysis/scripts/gen_stats.py, or fix the id in the prose")
            return str(values[id].get(field, ""))
        return sub

    text = re.sub(STATS, repl("display"), text)
    return re.sub(STATS_N, repl("value"), text)


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


def strip_balanced(text: str, opener: str, gap: str = "") -> str:
    """Remove `opener` ... matching-close-paren blocks (e.g. `#figure( ... )`),
    along with any `<label>` that trails the closing paren.

    Paren-matching rather than a regex, so it is indifferent to how the contents
    are wrapped and to nesting.

    `gap` is what replaces the removed block. Callers that go on to look for
    adjacent duplicate words pass a sentinel, so that deleting something from
    between two identical words does not fabricate a repetition.
    """
    out, i = [], 0
    while i < len(text):
        j = text.find(opener, i)
        if j == -1:
            out.append(text[i:])
            break
        out.append(text[i:j])
        out.append(gap)
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
