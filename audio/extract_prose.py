#!/usr/bin/env python3
"""Extract narratable prose from the manuscript for text-to-speech.

Pulls the abstract (from config.typ) plus the prose body (from paper.typ, between
the BODY START / BODY END markers), drops figure and code blocks, and rewrites
Typst markup, citations, math, and #sym.* tokens into plain readable English.
Output is one clean .txt file.

Project-specific pronunciations and math readings live in config.py, not here.
"""
import re
import sys
from pathlib import Path

import config
from config import (  # noqa: F401  (re-exported for make_audiobook.py)
    MATH,
    PAPER_TYP,
    SI_TYP,
    SYM,
    CONFIG_TYP,
    speakable,
    spoken_title,
)

OUT = Path(__file__).resolve().parent / "paper_prose.txt"

# The shared Typst-recognition primitives live one level up, beside the
# manuscript. strip_balanced is re-exported because make_audiobook.py imports it
# from here.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import readability  # noqa: E402
import resolve_typst  # noqa: E402
from resolve_typst import SUPPLEMENT  # noqa: E402
import typst_prose  # noqa: E402
from typst_prose import (  # noqa: E402
    CITE,
    FOOTNOTE,
    TODO,
    resolve_lit,
    strip_links,
    unescape_unicode,
    ASSET,
    REFN,
    markup as _markup,
    resolve_stats,
    BIBLIOGRAPHY_CALLS,
    strip_balanced,
    strip_directives,
)

BODY_START = re.compile(r"(?m)^// >>> BODY START.*$")
BODY_END = re.compile(r"(?m)^// <<< BODY END.*$")


def _bracket_block(text, start):
    """Return the contents of the `[...]` block whose opening bracket is at `start`."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return text[start + 1:]


def extract_abstract():
    """The cleaned abstract, read from `#let paper-abstract = [...]` in config.typ."""
    raw = CONFIG_TYP.read_text()
    m = re.search(r"#let\s+paper-abstract\s*=\s*\[", raw)
    if not m:
        sys.exit(f"error: could not find `#let paper-abstract = [...]` in {CONFIG_TYP}")
    return clean(_bracket_block(raw, m.end() - 1), crossrefs())


def extract_body(raw):
    """The prose between the BODY START / BODY END markers in paper.typ."""
    a, b = BODY_START.search(raw), BODY_END.search(raw)
    if not (a and b):
        sys.exit(
            "error: paper.typ is missing the `// >>> BODY START` / `// <<< BODY END` "
            "marker comments, so the narrator cannot tell prose from front/back matter."
        )
    return raw[a.end():b.start()]


# Typst math word tokens -> spoken words, inside a $...$ span that config.MATH
# does not list. Matched as whole words, longest first ("gt.eq" before "gt").
# config.MATH_WORDS extends or overrides these; a config.py written before it
# existed simply gets the defaults.
MATH_WORDS: dict[str, str] = {
    "plus.minus": " plus or minus ",
    "minus.plus": " minus or plus ",
    "arrow.r": " to ",
    "arrow.l": " from ",
    "tilde.op": " approximately ",
    "gt.eq": " greater than or equal to ",
    "lt.eq": " less than or equal to ",
    "eq.not": " not equal to ",
    "approx": " approximately ",
    "prop": " proportional to ",
    "times": " times ",
    "dot.c": " times ",
    "sqrt": " the square root of ",
    "infinity": " infinity ",
    "dots": " ",
    "gt": " greater than ",
    "lt": " less than ",
    **getattr(config, "MATH_WORDS", {}),
}

# Bare Unicode operators the voice skips or mangles ("0.4 ± 0.1", "8×"),
# including the ones unescape_unicode() just made out of \u{...} escapes.
# config.UNICODE_SPEAK extends or overrides these. An en dash is only a range
# between two numbers, so that one is a rule in clean(), not an entry here.
UNICODE_SPEAK: dict[str, str] = {
    "\u2212": " minus ",       # true minus sign
    "\u00d7": " times ",
    "\u00b1": " plus or minus ",
    "\u2248": " approximately ",
    "\u2264": " less than or equal to ",
    "\u2265": " greater than or equal to ",
    "\u2192": " to ",
    "\u0394": " delta ",
    **{chr(0x2080 + d): f" {w} " for d, w in enumerate(
        "zero one two three four five six seven eight nine".split())},
    **getattr(config, "UNICODE_SPEAK", {}),
}


def speak_math(s):
    """The inside of a $...$ span that config.MATH does not list, in words.

    A literal MATH entry reads an equation the way the author would, and still
    wins. This is the fallback for everything else, which before was read as
    raw notation with the dollar signs stripped ("t_obs <= t_max"). A paper
    with many inline equations (koth carries about 170) cannot keep a literal
    map in step with the prose, and a threshold whose digits come from
    stats.json ("$T = #s(..)$") cannot be listed at all: "$T = 84$" was
    "$T = 86$" before a recalibration (dnoise). The grammar is structural --
    quotes, |x|, superscripts, subscripts, comparisons -- over the vocabulary
    in MATH_WORDS, so an unanticipated span degrades into roughly-right English
    rather than into notation.
    """
    s = s.replace('"/"', "/")                          # m"/"z -> m/z
    s = re.sub(r'"([^"]*)"', r"\1", s)                  # t_"obs" -> t_obs
    s = re.sub(r"\|([^|]*)\|", r" the absolute value of \1 ", s)
    s = re.sub(r"\^\(([^)]*)\)", r" to the \1 ", s)
    s = re.sub(r"\^(-?[0-9A-Za-z]+)", r" to the \1 ", s)
    s = re.sub(r"_\(([^)]*)\)", r" \1 ", s)
    s = re.sub(r"_([0-9A-Za-z]+)", r" \1 ", s)
    # A digit-letter transition is a boundary too, so "4sigma" -> "4 sigma".
    for k in sorted(MATH_WORDS, key=len, reverse=True):
        s = re.sub(rf"(?<![A-Za-z]){re.escape(k)}(?![A-Za-z])", MATH_WORDS[k], s)
    s = s.replace("..=", " to ").replace("...", " ").replace("..", " to ")
    for sym, word in ((">=", "greater than or equal to"), ("<=", "less than or equal to"),
                      ("!=", "not equal to"), (">", "greater than"), ("<", "less than"),
                      ("=", "equals"), ("-", "minus"), ("+", "plus")):
        s = s.replace(sym, f" {word} ")
    s = re.sub(r"[{}\[\]]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return f" {s} "       # padded so it never glues to the next word (11$times$)


# Tokens that reached clean() with no mapping in config.SYM. Collected rather
# than ignored: an unmapped token narrates as "sym arrow r", and the fixture test
# only pins the tokens the fixture happens to contain, so a manuscript can carry
# one the fixture never saw. main() reports these, so a missing mapping shows up
# at build time instead of on playback.
UNMAPPED: set[str] = set()

_FLOAT_REF = re.compile(
    r"#refn?\(\s*<((?:fig|tbl|tab|eq|sec):[A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*)>"
    r"\s*(,\s*supplement:\s*none\s*)?,?\s*\)"
    r"|@((?:fig|tbl|tab|eq|sec):[A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*)(?:\[([^\[\]\n]*)\])?")


def speak_crossrefs(text, refs):
    """`@tbl:x` -> "Table S1", the words the PDF prints there.

    Dropping them, as clean() once did, narrated "as seen in" and moved on:
    the sentence lost the very thing it pointed at. `refs` maps a label to
    its printed number (resolve_typst.label_numbers, the Word export's own
    count). A label it lacks is left for clean() to drop as before.
    """
    def repl(m):
        if m[1]:
            label, bare = m[1], bool(m[2]) or m[0].startswith("#refn")
            shown = None
        else:
            label, bare, shown = m[3], m[4] is not None, (m[4] or "").strip()
        if label not in refs:
            return m[0]
        num = refs[label]
        if shown:
            return f"{shown} {num}"
        return num if bare else f"{SUPPLEMENT[label.split(':', 1)[0]]} {num}"
    return _FLOAT_REF.sub(repl, text)


_CROSSREFS = None


def crossrefs():
    """The printed number of every labeled float and heading, main text then
    SI, counted exactly as the Word export counts them. Cached: both
    audiobooks and the abstract share one count."""
    global _CROSSREFS
    if _CROSSREFS is None:
        body = readability.slice_body(PAPER_TYP.read_text())
        if SI_TYP.is_file():
            body += "\n\n" + resolve_typst._SI_MARK + "\n" + SI_TYP.read_text()
        try:
            _CROSSREFS = resolve_typst.label_numbers(body)
        except resolve_typst.ResolveError:
            _CROSSREFS = {}
    return _CROSSREFS


# Calls whose result is layout or document state, never words: a counter reset
# before the SI's tables, `#context` reading a page number, spacing and breaks.
# A line that STARTS with one is code, and before this the voice read it out
# ("hash counter figure dot where kind table dot update zero").
CODE_CALLS = ("counter", "state", "context", "pagebreak", "colbreak", "v", "h",
              "place", "metadata", "layout")
_CODE_START = re.compile(
    r"(?m)^[ \t]*#(?:" + "|".join(CODE_CALLS) + r")(?![\w-])")
_IDENT = re.compile(r"[A-Za-z_][\w-]*")


def _balanced_end(text, i):
    """Index just past the bracket group opening at text[i], strings skipped."""
    depth, in_str, esc = 0, False, False
    for k in range(i, len(text)):
        ch = text[k]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                return k + 1
    return len(text)


def _expr_end(text, i):
    """End of the code expression starting at text[i]: an identifier, then any
    chain of `(...)`, `[...]`, `{...}` groups and `.method` accesses. `context`
    takes the expression after it, so `#context counter(page).display()` goes
    as one unit. A bare group (`#context { ... }`) is an expression too."""
    m = _IDENT.match(text, i)
    if m:
        i = m.end()
        if m[0] == "context":
            j = i
            while j < len(text) and text[j] in " \t":
                j += 1
            if j < len(text) and (text[j] in "([{" or _IDENT.match(text, j)):
                return _expr_end(text, j)
            return i
    elif i < len(text) and text[i] in "([{":
        i = _balanced_end(text, i)
    while i < len(text):
        if text[i] in "([{":
            i = _balanced_end(text, i)
        elif text[i] == "." and _IDENT.match(text, i + 1):
            i = _IDENT.match(text, i + 1).end()
        else:
            break
    return i


def strip_code_lines(text):
    """Drop a layout or state call (CODE_CALLS) that starts a line, however
    many lines its brackets span. Newlines inside it are kept, so paragraph
    breaks around it survive; prose after it on the same line is kept too."""
    out, pos = [], 0
    for m in _CODE_START.finditer(text):
        if m.start() < pos:
            continue            # inside an expression already removed
        end = _expr_end(text, m.end() - len(m[0].lstrip(" \t#")))
        out.append(text[pos:m.start()])
        out.append(" " + "\n" * text.count("\n", m.start(), end))
        pos = end
    out.append(text[pos:])
    return "".join(out)


def clean(text, refs=None):
    # 0a. Typst directives and line comments. A document's front matter can carry
    #     its own `#let` helpers, and the SI's overview chapter starts before the
    #     first heading, so without this the audiobook opens by reading source.
    #     Layout and state calls on their own line (a counter reset, #context,
    #     #pagebreak(), #v(1em)) are code for the same reason.
    text = strip_directives(text, " ")
    text = strip_code_lines(text)
    text = re.sub(r"(?m)^\s*//.*$", " ", text)

    # 0. remove fenced code blocks and #raw(...) config dumps
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = strip_balanced(text, "#raw(")

    # 1. remove whole figure blocks (captions are not prose)
    text = strip_balanced(text, "#figure(")
    # A bare #table( in running prose, not wrapped in a #figure.
    text = strip_balanced(text, "#table(")
    # The SI sets its own reference list, in the file this narrates whole.
    for call in BIBLIOGRAPHY_CALLS:
        text = strip_balanced(text, call)
    # Same for a bare fig()/tbl() call: an image is not narration.
    text = re.sub(ASSET, " ", text)

    # 1a. generated numbers -> their value. Resolved, never stripped: a stripped
    #     call loses the figure from the spoken sentence, an unstripped one has
    #     the narrator read the lookup call aloud. Vouched literals unwrap the
    #     same way, for the same reason.
    text = resolve_stats(text)
    text = resolve_lit(text)
    # data files -> "Supplementary Data File 2", as the PDF prints them.
    text = typst_prose.resolve_data_files(text)
    # a note to self is not narration
    text = re.sub(TODO, " ", text)

    # 1b. An explicitly signed number, which `fmt="+.2f"` in gen_stats.py is
    #     meant to produce, reaches the voice as a bare "+". Spell it, or a
    #     stated increase narrates as an unsigned figure and the sentence loses
    #     the very thing the sign was carrying.
    #     The `+` in the lookbehind is load-bearing: without it `C++11` narrates
    #     as "C plus 11".
    text = re.sub(r"(?<![\w.+])\+(?=\d)", "plus ", text)

    # 2. display equations are dropped rather than read; a block of notation read
    #    aloud is noise, and the surrounding prose always restates it in words.
    text = re.sub(r"(?m)^\s*\$ .*? \$\s*$", " ", text, flags=re.S)

    # 2b. `\u{2082}` -> the character it names, BEFORE the symbol maps, so a
    #     subscript written as an escape gets the same spoken form as one typed
    #     directly. Without this the voice read "log u 2082" -- the fix landed
    #     in the shared layer (typst_prose) for the word count and was never
    #     wired in here, and the golden file blessed the broken narration.
    text = unescape_unicode(text)
    text = re.sub(r"(?<=\d)\s*\u2013\s*(?=\d)", " to ", text)     # 3\u20135 is a range
    for k in sorted(UNICODE_SPEAK, key=len, reverse=True):
        text = text.replace(k, UNICODE_SPEAK[k])

    # 3. math and symbol tokens (do multi-char keys first)
    for k in sorted(MATH, key=len, reverse=True):
        text = text.replace(k, MATH[k])
    for k in sorted(SYM, key=len, reverse=True):
        text = text.replace(k, SYM[k])
    # Anything still spelled #sym.* has no mapping. Drop it and remember it:
    # silence narrates better than "sym arrow r", and UNMAPPED makes the
    # omission visible at build time.
    for m in re.finditer(r"#sym\.[A-Za-z0-9.]+", text):
        UNMAPPED.add(m.group(0))
    text = re.sub(r"#sym\.[A-Za-z0-9.]+", " ", text)

    # any $...$ config.MATH did not list -> spoken structurally
    text = re.sub(r"\$([^$]*)\$", lambda m: speak_math(m.group(1)), text)

    # 4. superscripts/subscripts helpers still around
    text = re.sub(r"#super\[([^\]]*)\]", r" to the \1", text)
    text = re.sub(r"#sub\[([^\]]*)\]", r"\1", text)

    # 5. cross-refs: a known float or heading label is spoken as the PDF prints
    #    it; what is left (citations, unknown labels) is dropped.
    if refs:
        text = speak_crossrefs(text, refs)
    text = re.sub(REFN, "", text)
    text = re.sub(r"\(@[^)]*\)", "", text)              # (@fig:x) parenthetical refs
    text = re.sub(CITE, "", text)                       # remaining @citekeys / @refs

    # 6. links: #link("url")[shown text] -> shown text
    text = strip_links(text)

    # 7. inline code -> the bare word, with spaces kept. Stripping the backticks
    #    alone glues the term to the preceding word, which the voice then runs
    #    together ("resulting.d").
    text = re.sub(r"`([^`]*)`", r" \1 ", text)

    # 8. strong *...* and emphasis _..._ -> plain (do a couple of passes).
    #    See typst_prose.markup() for why this is not just [^*\n]+.
    for _ in range(3):
        text = re.sub(_markup("*"), r"\1", text)
        text = re.sub(_markup("_"), r"\1", text)

    # 8b. generic inline content wrappers: #text(size: 9pt)[x], #emph[x],
    #     #block(..)[x] -> keep x, drop the marker and its content brackets
    # Before the gap-free rule below: a footnote attaches to the word it
    # annotates, so without a gap the note welds onto it.
    text = re.sub(FOOTNOTE, " [", text)
    text = re.sub(r"#[a-z][a-z0-9.]*(?:\([^()]*\))?\s*\[", "[", text)
    text = text.replace("[", "").replace("]", "")

    # 9. escaped chars, leftover anchors, and Typst line comments
    text = text.replace(r"\@", "@").replace(r"\_", "_")
    text = re.sub(r"<[A-Za-z0-9:_-]+>", "", text)
    text = re.sub(r"(?m)^\s*//.*$", "", text)

    # 10. project pronunciation fixes
    text = speakable(text)

    # 11. tidy spacing left by removed citations: " ," -> ",", " ." -> ".",
    #     "( " -> "(", " )" -> ")", and empty "()" parentheticals.
    #     Only when the mark actually ends a word -- otherwise a term that starts
    #     with a dot (".docx", ".gitignore") gets welded onto the word before it
    #     and the voice reads "opens the.docx" as one run-on token.
    text = re.sub(r"\s+([,.;:%])(?=[\s)\]]|$)", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\(\s*\)", "", text)
    # A stripped cross-reference can leave the conjunction that joined it:
    #   "in Tables #refn(<a>) and #refn(<b>))" -> "in Tables and)"
    # Drop a coordinator left dangling against punctuation.
    text = re.sub(r"\s+\b(?:and|or)\b\s*(?=[)\].,;:])", "", text)
    text = re.sub(r"([;,:])\1+", r"\1", text)     # ";;" (removed mid-sentence ref)
    text = re.sub(r"[;,]\s*([.)])", r"\1", text)  # "; ." / ", )" -> "." / ")"

    # 12. collapse whitespace inside paragraphs but keep blank lines
    paras = re.split(r"\n\s*\n", text)
    cleaned = []
    for p in paras:
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            cleaned.append(p)
    return "\n\n".join(cleaned)


def report_unmapped():
    """Print any #sym.* token clean() dropped for want of a mapping.

    Called by both entry points. UNMAPPED exists to make a missing mapping
    visible at build time rather than on playback, which it only does if
    something actually prints it.
    """
    if not UNMAPPED:
        return
    print(f"note: {len(UNMAPPED)} unmapped symbol token(s) dropped rather than "
          f"narrated: {', '.join(sorted(UNMAPPED))}")
    print("      add them to SYM in audio/config.py to have them spoken.")


def main():
    raw = PAPER_TYP.read_text()

    abstract = extract_abstract()
    if not abstract:
        sys.exit("error: the abstract in config.typ is empty")

    body = extract_body(raw)

    # turn headings into spoken lines with a trailing period for a pause
    def heading_repl(m):
        title = m.group(2).strip()
        return f"\n\n{title}.\n\n"

    body = re.sub(r"(?m)^(=+)\s+([^\n<]+?)(?:\s*<[^>]+>)?\s*$", heading_repl, body)
    body = clean(body, crossrefs())

    parts = [spoken_title(), "Abstract.", abstract, body]
    OUT.write_text("\n\n".join(parts) + "\n")

    words = len((OUT.read_text()).split())
    print(f"wrote {OUT}  ({words} words, ~{words/150:.1f} min at 150 wpm)")
    report_unmapped()


if __name__ == "__main__":
    main()
