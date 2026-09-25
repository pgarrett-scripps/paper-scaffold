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

from paths import ROOT  # the manuscript (tools/paths.py)

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

# A literal the author vouched for in place: `#lit("2.2")` renders as 2.2 and
# says "deliberate prose, not an unaccounted number". Resolved to its inner
# string like the stats helpers, and for the same reason: stripped, the number
# vanishes from the count and the narration; unresolved, the call text leaks
# into both. The value is a quoted string by contract (lit() panics otherwise),
# so the pattern needs only the direct-call form -- and the reflowed one, where
# typstyle has broken the call across lines.
#
# 5.0.0: an optional `unlike: "id"` (or `unlike: ("a", "b")`) names the stats
# the literal is NOT, which silences derivable-number at this one site for a
# collision with exactly those ids. `not:` would read better but is a Typst
# keyword and cannot be an argument name. Group 1 is the literal, group 2 the
# raw unlike argument (None without one); `lit_unlike()` parses it.
LIT = (r'#lit\(\s*"([^"]*)"\s*'
       r'(?:,\s*unlike\s*:\s*(\(\s*(?:"[^"]*"\s*,?\s*)*\)|"[^"]*")\s*)?,?\s*\)')


def lit_unlike(arg: str | None) -> tuple[str, ...]:
    """The ids named by a lit() call's `unlike:` argument, in order."""
    return tuple(re.findall(r'"([^"]*)"', arg or ""))


def resolve_lit(text: str) -> str:
    """Substitute `#lit("...")` with the literal it wraps."""
    return re.sub(LIT, lambda m: m.group(1), text)


# A note to self that cannot ship: `#todo("check this")` renders a marker in
# draft mode and panics the real build. STRIPPED here, never resolved -- a note
# is not prose, so it must not reach the word count, the readability score, or
# the narrator's mouth even while drafting.
TODO = r'#todo\(\s*"([^"]*)"\s*,?\s*\)'

# An interval read from stats.json (5.0.0): `#ci("id")` renders "lo–hi" with the
# entry's fmt, `#ci("id", level: true)` prefixes the coverage ("95% CI 1.2–3.4").
# Resolved like `#s`, for the same reason. Group 1 is the id, group 2 the level
# flag.
CI = r'#ci\(\s*"([^"]+)"\s*(?:,\s*level\s*:\s*(true|false)\s*)?,?\s*\)'


# Written by analysis/scripts/gen_stats.py, beside the generated SI tables.
STATS_JSON = ROOT / "stats.json"

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


# A generated figure or table pulled in by id: `fig("fig.x")` / `tbl("tbl.x")`
# from assets.typ. Dropped entirely, like the `#figure(...)` block and the bare
# `#table(` these normally sit inside -- an image is not words, and the id is a
# key rather than something to read aloud.
#
# Nearly always wrapped in a `#figure(...)` that is already stripped whole, so
# this only bites on a bare call in running prose. It went unhandled at first for
# exactly that reason, and the id leaked into the word count and the narration:
# "A sentence with a bare #fig("fig.example") call" came through verbatim.
#
# Optional leading # so it matches both the markup call and the code-mode one
# inside a larger expression. The argument list is matched non-greedily up to the
# first close paren, which is enough: the arguments are a quoted id and simple
# named values like `width: 70%`.
ASSET = r'#?(?:fig|tbl)\(\s*"[^"]*"[^()]*\)'

# The same call, but with the pieces captured, for a consumer that RESOLVES it
# rather than stripping it: (1) the leading `#`, or empty in code mode -- the
# replacement must re-emit it, or a markup-mode call resolves to literal prose;
# (2) the helper name, (3) the id, (4) any trailing arguments (`width: 70%`)
# that must survive the substitution. tools/resolve_typst.py uses this to turn
# fig("id", width: 70%) into a real image() call. It lives here, beside the
# stripping pattern, because this repository has fixed the same construct in
# two extractors separately three times; a second regex for the same syntax in
# another file is how the fourth happens.
#
# The lookbehind is a left word boundary: without it, a manuscript's own
# #subfig() helper -- or any identifier ending in fig/tbl, like config( --
# matches on its suffix, and the resolver either rejects a valid manuscript or
# silently rewrites a call that was never ours.
ASSET_CALL = re.compile(
    r'(?<![A-Za-z0-9_-])(#?)(fig|tbl)\(\s*"([^"]+)"((?:\s*,[^()]*)?)\s*\)')


def display_of(rec: dict) -> str:
    """The string a reader sees, from a stats.json entry's `value` and `fmt`.

    THE ONLY FORMATTER IN THE PIPELINE. stats.json stores no rendered string:
    tools/render_stats.py calls this to build the file Typst reads, and the
    extractors call it to resolve `#s("id")` while reading the source. One
    implementation, so the PDF, the word count and the narration cannot disagree
    about what a number looks like.

    It is Python's formatter rather than Typst's on purpose. Typst has no
    format-spec at all, and its str() rounds floats where Python's does not, so
    doing this in the document would mean reimplementing the spec in a language
    that cannot express it.
    """
    v, fmt = rec.get("value"), rec.get("fmt", "")
    if fmt:
        return format(v, fmt)
    # A count computed as a float (a pandas sum, a mean of integers) has no
    # business printing as "14.0": with no fmt, a whole float prints as one.
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    return str(v)


def intervals_of(values: dict) -> dict:
    """Every interval `#ci("id")` can read, keyed by id.

    An entry's own lo/hi (written by Stats.add) come first. Failing that, a
    pair of sibling ids, `id.lo`/`id.hi` or `id_lo`/`id_hi`, which is how
    manuscripts declared intervals before the fields existed; those keep
    working, each end rendered with its own fmt. Level is a fraction (0.95).
    """
    out: dict[str, dict] = {}
    for id, rec in values.items():
        if not isinstance(rec, dict):
            continue
        for sep in (".", "_"):
            if id.endswith(sep + "lo") and id[:-3] + sep + "hi" in values:
                base, hi = id[:-3], values[id[:-3] + sep + "hi"]
                out.setdefault(base, {"lo": display_of(rec), "hi": display_of(hi),
                                      "level": None})
    for id, rec in values.items():
        if isinstance(rec, dict) and "lo" in rec and "hi" in rec:
            fmt = rec.get("fmt", "")
            out[id] = {"lo": display_of({"value": rec["lo"], "fmt": fmt}),
                       "hi": display_of({"value": rec["hi"], "fmt": fmt}),
                       "level": rec.get("level")}
    for rec in out.values():
        rec["display"] = f"{rec['lo']}\u2013{rec['hi']}"
        level = rec["level"]
        rec["with_level"] = (f"{level * 100:g}% CI {rec['display']}"
                             if level is not None else rec["display"])
    return out


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
    """Substitute `#s("id")` and `#n("id")` with their values from stats.json.

    `s` resolves to the display string (already rounded by the analysis), `n` to
    the raw value, matching what Typst renders for each.

    A no-op when the text contains neither call, so a manuscript that does not
    use the mechanism (and has no stats.json) still extracts. When it IS used,
    both a missing file and an unknown id raise: the same failure Typst gives at
    compile time, rather than a number quietly vanishing from the word count.
    """
    if not any(re.search(p, text) for p in (STATS, STATS_N, CI)):
        return text
    p = path or STATS_JSON
    if not p.is_file():
        raise SystemExit(
            f'error: prose uses #s("...") or #n("...") but {p} is missing; '
            f"regenerate it with `just assets`")
    doc = json.loads(p.read_text())
    values = doc.get("values", {})
    from manifest_validation import pending_match

    def repl(field: str):
        def sub(m: re.Match) -> str:
            id = m.group(1)
            # Declared pending (docs/evidence.md): the placeholder the PDF shows.
            if field == "display" and pending_match(doc.get("pending") or {}, id) is not None:
                return f"[pending: {id}]"
            if id not in values:
                raise SystemExit(
                    f"error: {p.name} has no value '{id}'; declare it in "
                    f"analysis/scripts/gen_stats.py, or fix the id in the prose")
            rec = values[id]
            # stats.json stores no rendered string; it is computed here by the
            # same function that builds the file Typst reads, so the extractors
            # and the PDF cannot disagree.
            if field == "display":
                return display_of(rec)
            return str(rec.get(field, ""))
        return sub

    text = re.sub(STATS, repl("display"), text)
    text = re.sub(STATS_N, repl("value"), text)
    if re.search(CI, text):
        intervals = intervals_of(values)

        def interval(m: re.Match) -> str:
            if m.group(1) not in intervals:
                raise SystemExit(
                    f"error: {p.name} has no interval for '{m.group(1)}': give it "
                    f"lo/hi in Stats.add(), or declare {m.group(1)}.lo and .hi")
            rec = intervals[m.group(1)]
            return rec["with_level"] if m.group(2) == "true" else rec["display"]
        text = re.sub(CI, interval, text)
    return text


# Supplementary data files, numbered by config.typ's `paper-data-files`
# (assets.typ: dfile). Group 1 is the `#` (absent in code mode), group 2 the
# variant, group 3 the id. The lookbehind keeps a project's own `mydfile(`
# from matching.
DFILE = r'(?<![\w-])(#?)dfile(-short|-number)?\(\s*"([^"]+)"\s*,?\s*\)'
DFILE_COUNT = r"(?<![\w-])(#?)dfile-count\(\s*\)"

# The registry as Typst evaluates it, cached per process. Tests assign a dict
# here to avoid the compile.
DATA_FILES: dict | None = None
_DATA_FILES_PROBE = (
    '#import "/config.typ" as _cfg\n'
    "#let _c = dictionary(_cfg)\n"
    '#metadata((files: _c.at("paper-data-files", default: ()),'
    ' name: _c.at("paper-data-file-name", default: "Supplementary Data File"),'
    ' short: _c.at("paper-data-file-short", default: "File"))) <data-files>\n'
)


def data_file_registry(root: Path | None = None) -> dict:
    """config.typ's data-file list and words, read by Typst itself.

    Asking Typst rather than parsing config.typ means the list may be built
    any way Typst allows, and the defaults are the ones assets.typ applies.
    Called only when the prose uses a dfile call, so a manuscript without data
    files never pays for the query. `root` (tests) reads another manuscript,
    uncached.
    """
    global DATA_FILES
    if root is not None or DATA_FILES is None:
        import subprocess
        cache = root is None
        root = root or ROOT
        try:
            proc = subprocess.run(
                ["typst", "query", "--root", str(root), "-", "<data-files>",
                 "--field", "value", "--one"],
                input=_DATA_FILES_PROBE, capture_output=True, text=True,
                cwd=root)
        except FileNotFoundError:
            raise SystemExit("error: the prose uses dfile() but typst is not "
                             "on PATH to read paper-data-files from config.typ")
        if proc.returncode:
            raise SystemExit("error: could not read paper-data-files from "
                             f"config.typ: {proc.stderr.strip()}")
        reg = json.loads(proc.stdout)
        if not cache:
            return reg
        DATA_FILES = reg
    return DATA_FILES


def resolve_data_files(text: str, code_wrap: bool = False) -> str:
    """Substitute `#dfile("id")`, `#dfile-short("id")`, `#dfile-number("id")`
    and `#dfile-count()` with what the PDF prints for them.

    A no-op without such a call. An id missing from `paper-data-files` raises,
    as the compile does. With `code_wrap`, a code-mode call (no `#`) becomes a
    content block `[...]`, so the resolved Typst stays valid.
    """
    if not re.search(DFILE, text) and not re.search(DFILE_COUNT, text):
        return text
    reg = data_file_registry()
    files = list(reg.get("files", []))

    def out(hash_: str, words: str) -> str:
        return f"[{words}]" if code_wrap and not hash_ else words

    def sub(m: re.Match) -> str:
        hash_, variant, id = m.groups()
        if id not in files:
            raise SystemExit(
                f"error: '{id}' is not in paper-data-files in config.typ; add "
                "it there, in the order the files are supplied")
        n = files.index(id) + 1
        if variant == "-number":
            return out(hash_, str(n))
        word = reg["short"] if variant == "-short" else reg["name"]
        return out(hash_, f"{word} {n}")

    text = re.sub(DFILE, sub, text)
    return re.sub(DFILE_COUNT, lambda m: out(m.group(1), str(len(files))), text)


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


# The reference lists, in both forms this scaffold produces: Typst's own
# #bibliography for the main text, and Alexandria's #bibliographyx for the
# Supporting Information's separate list (Typst allows only one native call
# per document). Neither is prose: a reference list is exempt from a journal
# word count, scores nothing readable, and must not be read aloud.
#
# The main call sits outside the BODY markers and so was never seen here. The
# SI's sits INSIDE si-body.typ, which is counted and narrated whole, and the
# first version of it reached all three consumers verbatim -- the narrator
# read out `#bibliographyx("references.bib", prefix: "si-"...)`. Stripped
# with the same balanced-paren pass as #figure(, so a reflowed call with its
# arguments on five lines goes too.
BIBLIOGRAPHY_CALLS = ("#bibliography(", "#bibliographyx(")


DIRECTIVE = re.compile(r"^\s*#(import|let|set|show)\b")


def strip_directives(text: str, gap: str = "") -> str:
    """Remove standalone directive lines: #import, #let, #set, #show.

    A directive that typstyle broke across lines -- `#show raw: it => text(`
    with its arguments on the lines below -- is one statement, so the strip
    follows unbalanced brackets to the line that closes it. The old
    single-line regex removed the opening line and left the continuation
    lines behind as prose, which leaked a table's `#show` rule into the Word
    export and into the word count. Strings are skipped when counting.
    Every removed line becomes `gap`, so line structure is preserved.
    """
    out = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if not DIRECTIVE.match(lines[i]):
            out.append(lines[i])
            i += 1
            continue
        depth = _bracket_depth(lines[i])
        out.append(gap)
        while depth > 0 and i + 1 < len(lines):
            i += 1
            depth += _bracket_depth(lines[i])
            out.append(gap)
        i += 1
    return "\n".join(out)


def _bracket_depth(line: str) -> int:
    """Net bracket depth of one line, ignoring bracket characters in strings."""
    depth, in_str, esc = 0, False, False
    for ch in line:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
    return depth


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
