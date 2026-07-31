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

HERE = Path(__file__).resolve().parent
PAPER = HERE / "paper.typ"
SI = HERE / "si-body.typ"

BODY_START = re.compile(r"(?m)^// >>> BODY START.*$")
BODY_END = re.compile(r"(?m)^// <<< BODY END.*$")

# Abbreviations whose trailing period must NOT end a sentence.
_ABBR = [
    "e.g.", "i.e.", "et al.", "vs.", "cf.", "Fig.", "Figs.", "Eq.", "Ref.",
    "Sec.", "approx.", "ca.", "no.", "Dr.", "Prof.", "sp.", "spp.", "al.",
    "min.", "Inc.", "Ltd.", "St.",
]


def _strip_balanced(text: str, opener: str) -> str:
    """Remove `opener` ... matching-close-paren blocks (e.g. #figure( ... ))."""
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
        m = re.match(r"\s*<[^>]+>", text[k:])  # swallow a trailing " <label>"
        if m:
            k += m.end()
        i = k
    return "".join(out)


def clean(text: str) -> str:
    """Strip Typst source down to exempt-free prose (math/code/figures dropped)."""
    # line comments and standalone directive lines (imports, lets, sets, shows)
    text = re.sub(r"(?m)^\s*//.*$", " ", text)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"(?m)^\s*#(?:import|let|set|show)\b.*$", " ", text)
    # block code and config dumps, then whole figures (caption + table + image)
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = _strip_balanced(text, "#raw(")
    text = _strip_balanced(text, "#figure(")
    # math: DROP entirely (exempt), including any leftover $...$
    text = re.sub(r"#sym\.[A-Za-z0-9.]+", " ", text)
    text = re.sub(r"\$[^$]*\$", " ", text)
    # cross-refs and citations. The \s* are load-bearing: typstyle breaks a long
    # line inside the call, leaving `#refn(\n  <sec:x>\n)`, and a one-line-only
    # pattern then leaks the bare `#refn(` and `)` into the prose as words.
    text = re.sub(r"#refn\(\s*<[^>]*>\s*,?\s*\)", " ", text)
    text = re.sub(r"\(@[^)]*\)", " ", text)         # (@fig:example) parentheticals
    text = re.sub(r"@[A-Za-z0-9:_-]+", " ", text)   # remaining @citekeys / @refs
    # links: #link("url")[shown] -> shown
    text = re.sub(r'#link\("[^"]*"\)\[([^\]]*)\]', r"\1", text)
    text = text.replace("`", "")                    # inline code -> bare word
    # strong/emph markup -> plain
    for _ in range(3):
        text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
        text = re.sub(r"(?<![A-Za-z0-9])_([^_\n]+)_(?![A-Za-z0-9])", r"\1", text)
    # generic inline wrappers #text(..)[x], #emph[x] -> x
    text = re.sub(r"#[a-z][a-z0-9.]*(?:\([^()]*\))?\s*\[", "[", text)
    text = text.replace("[", " ").replace("]", " ")
    text = re.sub(r"<[A-Za-z0-9:_-]+>", " ", text)  # stray labels
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
    t = text
    for ab in _ABBR:
        t = t.replace(ab, ab.replace(".", "\x00"))
    t = re.sub(r"(?<=\d)\.(?=\d)", "\x00", t)  # decimals: 0.15
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
    name_w = max(len(r[0]) for r in rows)
    print("Readability (prose only; same exemptions as the word count: no refs,")
    print("             figures/tables + captions, math, or block code)")
    print(f"  {'':<{name_w}}  {'words':>6}  {'w/sent':>6}  {'FK grade':>8}  "
          f"{'ease':>5}  {'fog':>5}")
    for name, m in rows:
        print(f"  {name:<{name_w}}  {m['words']:>6,}  {m['wps']:>6.1f}  "
              f"{m['fk']:>8.1f}  {m['ease']:>5.0f}  {m['fog']:>5.1f}")
    mt = rows[0][1]
    print(f"  Main text reads at ~grade {mt['fk']:.0f} ({_band(mt['fk'])}); "
          f"lower FK / higher ease = easier.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
