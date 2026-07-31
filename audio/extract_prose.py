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

BODY_START = re.compile(r"(?m)^// >>> BODY START.*$")
BODY_END = re.compile(r"(?m)^// <<< BODY END.*$")


def strip_balanced(text, opener):
    """Remove `opener` ... matching-close-paren blocks (e.g. #figure( ... ))."""
    out = []
    i = 0
    while i < len(text):
        j = text.find(opener, i)
        if j == -1:
            out.append(text[i:])
            break
        out.append(text[i:j])
        # find the matching close paren starting at the '(' in opener
        k = j + len(opener) - 1  # index of '('
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
        # also swallow a trailing " <label>" anchor if present
        m = re.match(r"\s*<[^>]+>", text[k:])
        if m:
            k += m.end()
        i = k
    return "".join(out)


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


def clean(text):
    # 0. remove fenced code blocks and #raw(...) config dumps
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = strip_balanced(text, "#raw(")

    # 1. remove whole figure blocks (captions are not prose)
    text = strip_balanced(text, "#figure(")

    # 2. display equations are dropped rather than read; a block of notation read
    #    aloud is noise, and the surrounding prose always restates it in words.
    text = re.sub(r"(?m)^\s*\$ .*? \$\s*$", " ", text, flags=re.S)

    # 3. math and symbol tokens (do multi-char keys first)
    for k in sorted(MATH, key=len, reverse=True):
        text = text.replace(k, MATH[k])
    for k in sorted(SYM, key=len, reverse=True):
        text = text.replace(k, SYM[k])
    # any leftover simple $...$ -> inner text without $
    text = re.sub(r"\$([^$]*)\$", lambda m: m.group(1), text)

    # 4. superscripts/subscripts helpers still around
    text = re.sub(r"#super\[([^\]]*)\]", r" to the \1", text)
    text = re.sub(r"#sub\[([^\]]*)\]", r"\1", text)

    # 5. cross-refs: #refn(<...>) and bare @label citations (labels may contain -)
    #    The \s* are load-bearing: typstyle breaks a long line inside the call,
    #    leaving `#refn(\n  <sec:x>\n)`, and a one-line-only pattern then leaves
    #    a bare `#refn(` behind for the voice to read aloud as "refn".
    text = re.sub(r"#refn\(\s*<[^>]*>\s*,?\s*\)", "", text)
    text = re.sub(r"\(@[^)]*\)", "", text)              # (@fig:x) parenthetical refs
    text = re.sub(r"@[A-Za-z0-9:_-]+", "", text)        # remaining @citekeys / @refs

    # 6. links: #link("url")[shown text] -> shown text
    text = re.sub(r'#link\("[^"]*"\)\[([^\]]*)\]', r"\1", text)

    # 7. inline code -> the bare word, with spaces kept. Stripping the backticks
    #    alone glues the term to the preceding word, which the voice then runs
    #    together ("resulting.d").
    text = re.sub(r"`([^`]*)`", r" \1 ", text)

    # 8. strong *...* and emphasis _..._ -> plain (do a couple of passes)
    for _ in range(3):
        text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
        text = re.sub(r"(?<![A-Za-z0-9])_([^_\n]+)_(?![A-Za-z0-9])", r"\1", text)

    # 8b. generic inline content wrappers: #text(size: 9pt)[x], #emph[x],
    #     #block(..)[x] -> keep x, drop the marker and its content brackets
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


if __name__ == "__main__":
    main()
