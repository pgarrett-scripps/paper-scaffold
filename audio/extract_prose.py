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

from config import (  # noqa: F401  (re-exported for make_audiobook.py)
    MATH,
    PAPER_TYP,
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
    strip_balanced,
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
    return clean(_bracket_block(raw, m.end() - 1))


def extract_body(raw):
    """The prose between the BODY START / BODY END markers in paper.typ."""
    a, b = BODY_START.search(raw), BODY_END.search(raw)
    if not (a and b):
        sys.exit(
            "error: paper.typ is missing the `// >>> BODY START` / `// <<< BODY END` "
            "marker comments, so the narrator cannot tell prose from front/back matter."
        )
    return raw[a.end():b.start()]


# Tokens that reached clean() with no mapping in config.SYM. Collected rather
# than ignored: an unmapped token narrates as "sym arrow r", and the fixture test
# only pins the tokens the fixture happens to contain, so a manuscript can carry
# one the fixture never saw. main() reports these, so a missing mapping shows up
# at build time instead of on playback.
UNMAPPED: set[str] = set()


def clean(text):
    # 0a. Typst directives and line comments. A document's front matter can carry
    #     its own `#let` helpers, and the SI's overview chapter starts before the
    #     first heading, so without this the audiobook opens by reading source.
    text = re.sub(r"(?m)^\s*#(?:import|let|set|show)\b.*$", " ", text)
    text = re.sub(r"(?m)^\s*//.*$", " ", text)

    # 0. remove fenced code blocks and #raw(...) config dumps
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = strip_balanced(text, "#raw(")

    # 1. remove whole figure blocks (captions are not prose)
    text = strip_balanced(text, "#figure(")
    # A bare #table( in running prose, not wrapped in a #figure.
    text = strip_balanced(text, "#table(")
    # Same for a bare fig()/tbl() call: an image is not narration.
    text = re.sub(ASSET, " ", text)

    # 1a. generated numbers -> their value. Resolved, never stripped: a stripped
    #     call loses the figure from the spoken sentence, an unstripped one has
    #     the narrator read the lookup call aloud. Vouched literals unwrap the
    #     same way, for the same reason.
    text = resolve_stats(text)
    text = resolve_lit(text)
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

    # any leftover simple $...$ -> inner text without $
    text = re.sub(r"\$([^$]*)\$", lambda m: m.group(1), text)

    # 4. superscripts/subscripts helpers still around
    text = re.sub(r"#super\[([^\]]*)\]", r" to the \1", text)
    text = re.sub(r"#sub\[([^\]]*)\]", r"\1", text)

    # 5. cross-refs: #refn(<...>) and bare @label citations (labels may contain -)
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
    body = clean(body)

    parts = [spoken_title(), "Abstract.", abstract, body]
    OUT.write_text("\n\n".join(parts) + "\n")

    words = len((OUT.read_text()).split())
    print(f"wrote {OUT}  ({words} words, ~{words/150:.1f} min at 150 wpm)")
    report_unmapped()


if __name__ == "__main__":
    main()
