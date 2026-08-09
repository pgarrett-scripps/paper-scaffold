#!/usr/bin/env python3
"""Readability metrics for the manuscript, computed from the Typst source.

Mirrors the exemptions of `wordcount.typ` (the project's definition of "what
counts toward the prose"): drops the title/author block, references and in-text
citations, whole figures/tables and their captions, images, math/equations, and
block code / config dumps; keeps body prose, section headings, and inline `code`.

Unlike audio/extract_prose.py (which *verbalizes* math for text-to-speech and so
would inflate word/syllable counts), math and #sym tokens are DROPPED here, since
they are exempt from a reading-level score.

Reports, per section (main text / SI / combined): prose words, sentences, average
words per sentence, Flesch-Kincaid grade, Flesch reading ease, and Gunning fog.
Uses `textstat` if installed (sharper syllables); otherwise a self-contained
estimate so `just paper` stays dependency-free.

Usage: python3 readability.py            (from the manuscript directory)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from typst_prose import (
    CITE,
    FOOTNOTE,
    strip_links,
    ASSET,
    REFN,
    markup as _markup,
    TODO,
    resolve_lit,
    resolve_stats,
    strip_balanced as _strip_balanced,
    unescape_unicode,
)

# The manuscript root, one level up: this file lives in tools/.
ROOT = Path(__file__).resolve().parent.parent
PAPER = ROOT / "paper.typ"
SI = ROOT / "si-body.typ"

BODY_START = re.compile(r"(?m)^// >>> BODY START.*$")
BODY_END = re.compile(r"(?m)^// <<< BODY END.*$")

# Abbreviations whose trailing period must NOT end a sentence.
_ABBR = [
    "e.g.", "i.e.", "et al.", "vs.", "cf.", "Fig.", "Figs.", "Eq.", "Ref.",
    "Sec.", "approx.", "ca.", "no.", "Dr.", "Prof.", "sp.", "spp.", "al.",
    "min.", "Inc.", "Ltd.", "St.",
]

# Matched only at a word boundary. These used to be masked with a plain substring
# replace, which made every word ending in "-al." ("removal.", "structural.")
# look like "et al." and weld the following sentence onto it. Sentences got
# longer, and words-per-sentence, Flesch-Kincaid and fog all reported the prose
# as denser than it is.
def _compile_abbr() -> re.Pattern:
    return re.compile(
        r"\b(?:%s)" % "|".join(
            re.escape(a) for a in sorted(_ABBR, key=len, reverse=True))
    )


_ABBR_RE = _compile_abbr()

# A heading is navigation, not prose. Left alone, the marker survived into the
# text and glued the title to the sentence after it, inventing long sentences
# that nobody wrote. It is replaced by a bare period rather than by its title: a
# hard sentence boundary that contributes no words, so a run of short headings
# cannot drag the words-per-sentence average down the way the gluing dragged it
# up. The narrator keeps headings; a reader needs to hear them. A readability
# score does not. The journal word count counts them separately.
_HEADING_RE = re.compile(r"(?m)^\s*=+\s+[^\n<]+?(?:\s*<[^>]+>)?\s*$")


def add_abbreviations(words) -> None:
    """Teach the sentence splitter project-specific abbreviations.

    A field has its own periods that do not end a sentence, and a splitter that
    does not know them reports the two halves as one long sentence and skews
    every words-per-sentence figure. Called from prose_check with whatever
    `[vocabulary.abbreviations]` lists.
    """
    global _ABBR_RE
    new = [w for w in words if w not in _ABBR]
    if not new:
        return
    _ABBR.extend(new)
    _ABBR_RE = _compile_abbr()


def protect_periods(text: str) -> str:
    """Mask the periods that do not end a sentence (abbreviations, decimals).

    Shared so the readability score and the long-sentence check agree on where a
    sentence ends. They had separate copies of this and had already drifted.
    """
    t = _ABBR_RE.sub(lambda m: m.group(0).replace(".", "\x00"), text)
    return re.sub(r"(?<=\d)\.(?=\d)", "\x00", t)


def clean(text: str, gap: str = " ") -> str:
    """Strip Typst source down to exempt-free prose (math/code/figures dropped).

    `gap` is what a removed construct leaves behind. The default, a space, is what
    you want for counting and scoring. Pass a sentinel when the caller then looks
    for adjacent duplicate words: `and $N_"human"$ and` collapses to a literal
    `and and` under a space, which is a repetition the author never wrote.
    """
    # headings -> a bare sentence boundary, before the markers are lost
    text = _HEADING_RE.sub("\n\n.\n\n", text)
    # line comments and standalone directive lines (imports, lets, sets, shows)
    text = re.sub(r"(?m)^\s*//.*$", gap, text)
    text = re.sub(r"/\*.*?\*/", gap, text, flags=re.S)
    text = re.sub(r"(?m)^\s*#(?:import|let|set|show)\b.*$", gap, text)
    # block code and config dumps, then whole figures (caption + table + image)
    text = re.sub(r"```.*?```", gap, text, flags=re.S)
    text = _strip_balanced(text, "#raw(", gap)
    text = _strip_balanced(text, "#figure(", gap)
    # A table written straight into the prose rather than wrapped in a
    # #figure. Legal, and excluded from a journal word count the same way.
    text = _strip_balanced(text, "#table(", gap)
    # A generated figure/table referenced by id, outside a #figure block.
    text = re.sub(ASSET, gap, text)
    # generated numbers -> their value. Resolved, never stripped: this text is
    # what gets counted and scored, and a reader sees the number, not the call.
    text = resolve_stats(text)
    # vouched literals -> the literal, for the same reason.
    text = resolve_lit(text)
    # notes to self are not prose: dropped whole, draft or not.
    text = re.sub(TODO, gap, text)
    # math: DROP entirely (exempt), including any leftover $...$
    text = re.sub(r"#sym\.[A-Za-z0-9.]+", gap, text)
    text = re.sub(r"\$[^$]*\$", gap, text)
    # cross-refs and citations. The \s* are load-bearing: typstyle breaks a long
    # line inside the call, leaving `#refn(\n  <sec:x>\n)`, and a one-line-only
    # pattern then leaks the bare `#refn(` and `)` into the prose as words.
    text = re.sub(REFN, gap, text)
    text = re.sub(r"\(@[^)]*\)", gap, text)         # (@fig:example) parentheticals
    text = re.sub(CITE, gap, text)                  # remaining @citekeys / @refs
    # links: #link("url")[shown] -> shown
    text = strip_links(text)
    # Inline code is unwrapped to a bare word, because a journal counts it as one.
    # Under a sentinel gap the caller is instead looking for adjacent duplicate
    # words, and an unwrapped `--proteome-k K` reads as a doubled "k K" the author
    # never wrote, so there the whole span goes.
    if gap == " ":
        text = text.replace("`", "")                # inline code -> bare word
    else:
        text = re.sub(r"`[^`]*`", gap, text)
    # strong/emph markup -> plain (see typst_prose.markup for why)
    for _ in range(3):
        text = re.sub(_markup("*"), r"\1", text)
        text = re.sub(_markup("_"), r"\1", text)
    # generic inline wrappers #text(..)[x], #emph[x] -> x
    # Before the gap-free rule below: a footnote attaches to the word it
    # annotates, so without a gap the note welds onto it.
    text = re.sub(FOOTNOTE, " [", text)
    text = re.sub(r"#[a-z][a-z0-9.]*(?:\([^()]*\))?\s*\[", "[", text)
    text = text.replace("[", " ").replace("]", " ")
    text = re.sub(r"<[A-Za-z0-9:_-]+>", gap, text)  # stray labels
    # Escapes: \u{2082} -> the character, so "log\u{2082}" counts as the one word
    # a reader sees rather than an opaque token. Before \_ and \@, since the
    # escape's own backslash would otherwise be ambiguous.
    text = unescape_unicode(text)
    text = text.replace(r"\@", "@").replace(r"\_", "_")
    return re.sub(r"\s+", " ", text).strip()


def slice_body(src: str) -> str:
    """The prose between the BODY START / BODY END markers in paper.typ."""
    a, b = BODY_START.search(src), BODY_END.search(src)
    if not (a and b):
        sys.exit(
            "error: paper.typ is missing the `// >>> BODY START` / `// <<< BODY END` "
            "marker comments, so the prose cannot be told from the front/back matter."
        )
    return src[a.end():b.start()]


def _syllables(word: str) -> int:
    w = word.lower()
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ie", "ee")) and n > 1:
        n -= 1
    return max(1, n)


def _sentences(text: str) -> int:
    t = protect_periods(text)
    parts = [s for s in re.split(r"[.!?]+(?:\s|$)", t) if len(s.split()) >= 2]
    return max(1, len(parts))


def metrics(text: str) -> dict:
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    W = len(words)
    if W == 0:
        return dict(words=0, sents=0, wps=0.0, fk=0.0, ease=0.0, fog=0.0)
    S = _sentences(text)
    try:
        import textstat  # sharper syllable model if available
        Sy = sum(textstat.syllable_count(w) for w in words)
    except Exception:
        Sy = sum(_syllables(w) for w in words)
    complex_words = sum(1 for w in words if _syllables(w) >= 3)
    wps, spw = W / S, Sy / W
    return dict(
        words=W, sents=S, wps=wps,
        fk=0.39 * wps + 11.8 * spw - 15.59,
        ease=206.835 - 1.015 * wps - 84.6 * spw,
        fog=0.4 * (wps + 100 * complex_words / W),
    )


def _band(fk: float) -> str:
    if fk < 10:
        return "general audience"
    if fk < 13:
        return "high-school / undergrad"
    if fk < 16:
        return "undergrad / early grad"
    return "graduate / specialist"


def main() -> int:
    main_txt = clean(slice_body(PAPER.read_text()))
    si_txt = clean(SI.read_text())
    combined = main_txt + "\n\n" + si_txt

    rows = [
        ("Main text", metrics(main_txt)),
        ("Supporting Information", metrics(si_txt)),
        ("Main + SI", metrics(combined)),
    ]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from report import console, table

    # No words column: it measured a slightly different text slice than the
    # journal count printed above it, and two disagreeing columns both named
    # "words" is worse than one.
    mt = rows[0][1]
    t = table("Readability",
              caption=f"main text ~grade {mt['fk']:.0f} "
                      f"({_band(mt['fk'])}); lower is easier")
    t.add_column()
    for col in ("w/sent", "FK grade", "ease", "fog"):
        t.add_column(col, justify="right")
    for name, m in rows:
        t.add_row(name, f"{m['wps']:.1f}", f"{m['fk']:.1f}",
                  f"{m['ease']:.0f}", f"{m['fog']:.1f}")
    console.print(t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
