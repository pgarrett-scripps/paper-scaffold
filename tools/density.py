#!/usr/bin/env python3
"""Density metrics for the manuscript: the things that make prose hard to read
which a reading-level score does not see.

Flesch-Kincaid only knows about word length and sentence length. It is blind to a
sentence carrying nine numerals, or three nested parentheticals, or an acronym
every eight words. Those are what actually make a Results section unreadable, and
they are all cheap to count.

HOW TO READ THE OUTPUT. Not against an absolute threshold. There is no published
"numerals per thousand words" limit for scientific prose and anyone quoting one is
guessing. What is meaningful is a section that departs from the rest of your own
paper: if Methods runs at three times the manuscript's median parenthetical rate,
that is a real signal, and it is one you can act on. So the second table flags
outliers against the paper's own median, not against a number invented here.

Usage: python3 density.py            (from the manuscript directory)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import readability

# The manuscript root, one level up: this file lives in tools/.
from paths import ROOT  # the manuscript (tools/paths.py)

# A section that exceeds the manuscript's own median by this factor is flagged.
OUTLIER_FACTOR = 1.6
# Sections shorter than this are too small for a rate to mean anything.
MIN_SECTION_WORDS = 120

NOMINAL = re.compile(
    r"\b\w{5,}(?:tion|sion|ment|ance|ence|ity|ness|ism)s?\b", re.I)
PASSIVE = re.compile(
    r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ed|\w+en)\b", re.I)
HEDGE = re.compile(
    r"\b(?:may|might|could|would|appears?|seems?|suggests?|likely|possibly|"
    r"potentially|presumably|apparently|relatively|somewhat)\b", re.I)
# Concessions and contrasts. Not a fault one at a time; a paragraph where
# every claim carries a "however" or an "although" is hard to follow, and
# this is how a section of them shows up.
CONCESSIVE = re.compile(
    r"\b(?:however|although|though|whereas|despite|nevertheless|nonetheless|"
    r"albeit|but|while)\b", re.I)
ACRONYM = re.compile(r"\b[A-Z]{2,}[0-9]*\b")
NUMERAL = re.compile(r"\b\d[\d.,/-]*\b")
SYMBOL = re.compile(r"[%±×÷≤≥<>=~µ°]")
# A sentence carrying this many numerals is counted as number-heavy. A
# prompt to reread, not a limit: a sentence comparing two conditions on two
# metrics legitimately carries four.
HEAVY_NUMERALS = 4
# How many of the most number-dense sentences to print.
TOP_SENTENCES = 8


def sentences(text: str) -> list[str]:
    """Split cleaned prose at sentence ends, keeping decimals and "e.g." whole."""
    masked = readability.protect_periods(text)
    parts = re.split(r"(?<=[.!?])\s+", masked)
    return [p.replace("\x00", ".") for p in parts if len(p.split()) >= 2]


def sections(body: str) -> list[tuple[str, str]]:
    """Split the prose into (heading, text) at `=` / `==` headings."""
    marks = list(re.finditer(r"(?m)^(={1,3})\s+([^\n<]+?)(?:\s*<[^>]+>)?\s*$", body))
    if not marks:
        return [("(whole document)", body)]
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        out.append((m.group(2).strip(), body[m.end():end]))
    return out


def metrics(text: str) -> dict[str, float]:
    """Per-1,000-word rates, plus mean words per sentence."""
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    n = len(words)
    if n == 0:
        return {}
    sents = sentences(text)
    heavy = sum(1 for s in sents if len(NUMERAL.findall(s)) >= HEAVY_NUMERALS)
    per_k = lambda c: 1000.0 * c / n  # noqa: E731

    # Parentheses: count pairs, and how much text sits inside them. A long
    # parenthetical is worse than a short one, so both are reported.
    parens = re.findall(r"\(([^()]*)\)", text)
    inside = sum(len(p.split()) for p in parens)

    return {
        "words": n,
        "w/sent": n / max(1, len(sents)),
        "numerals": per_k(len(NUMERAL.findall(text))),
        "parens": per_k(len(parens)),
        "in-paren%": 100.0 * inside / n,
        "acronyms": per_k(len(ACRONYM.findall(text))),
        "nominal.": per_k(len(NOMINAL.findall(text))),
        "passive": per_k(len(PASSIVE.findall(text))),
        "hedges": per_k(len(HEDGE.findall(text))),
        "concess.": per_k(len(CONCESSIVE.findall(text))),
        f"{HEAVY_NUMERALS}+num%": 100.0 * heavy / max(1, len(sents)),
    }


COLS = ["w/sent", "numerals", f"{HEAVY_NUMERALS}+num%", "parens", "in-paren%",
        "acronyms", "nominal.", "passive", "hedges", "concess."]


def median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def main() -> int:
    paper = readability.slice_body((ROOT / "paper.typ").read_text())
    si = (ROOT / "si-body.typ").read_text()

    rows: list[tuple[str, dict]] = []
    for label, src in (("Main text", paper), ("Supporting Info", si)):
        m = metrics(readability.clean(src))
        if m:
            rows.append((label, m))

    if not rows:
        print("  no prose to measure")
        return 0

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from report import console, table

    t = table("Density, per 1,000 words",
              caption="what a reading-level score does not see")
    t.add_column()
    t.add_column("words", justify="right")
    for c in COLS:
        t.add_column(c, justify="right")
    for label, m in rows:
        t.add_row(label, f"{m['words']:,}",
                  *(f"{m[c]:.1f}" for c in COLS))
    console.print(t)

    # --- per-section outliers, judged against this paper's own median ---
    secs = []
    for scope, src in (("", paper), ("SI ", si)):
        for name, text in sections(src):
            m = metrics(readability.clean(text))
            if m and m["words"] >= MIN_SECTION_WORDS:
                secs.append((scope + name, m))

    if len(secs) < 3:
        print("\n  (too few substantial sections to compare against each other)")
        return 0

    meds = {c: median([m[c] for _, m in secs]) for c in COLS}
    # Full names, never truncated. The old fixed 34-column cut turned
    # "Implementation and format compatibility" into a string that had to be
    # guessed at -- in a report whose whole job is to name a section.
    flagged = []
    for name, m in secs:
        flags = [f"{c} [bold]{m[c]:.0f}[/] (median {meds[c]:.0f})"
                 for c in COLS if meds[c] > 0 and m[c] > OUTLIER_FACTOR * meds[c]]
        if flags:
            flagged.append((name, flags))

    console.print()
    t = table(f"Section outliers, > {OUTLIER_FACTOR}x this paper's own median",
              caption="heuristics, not limits: a high rate is a prompt to "
                      "reread the section, not a defect. See STYLE.md.")
    t.add_column("section")
    t.add_column("departs from the rest of the paper")
    if flagged:
        for name, flags in flagged:
            t.add_row(name, "\n".join(flags))
    else:
        t.add_row("[dim]none[/]",
                  "[dim]every section sits close to the manuscript's norms[/]")
    console.print(t)

    # --- the sentences carrying the most numbers, where a rewrite starts ---
    ranked = []
    for scope, src in (("", paper), ("SI ", si)):
        for name, text in sections(src):
            for sent in sentences(readability.clean(text)):
                k = len(NUMERAL.findall(sent))
                if k >= HEAVY_NUMERALS:
                    ranked.append((k, scope + name, sent))
    ranked.sort(key=lambda r: -r[0])
    if ranked:
        console.print()
        t = table(f"Most number-dense sentences ({len(ranked)} carry "
                  f"{HEAVY_NUMERALS} or more numerals)",
                  caption="some need every number; ask which ones the "
                          "sentence's point rests on")
        t.add_column("n", justify="right")
        t.add_column("section")
        t.add_column("sentence")
        for k, name, sent in ranked[:TOP_SENTENCES]:
            short = sent if len(sent) <= 160 else sent[:157] + "..."
            t.add_row(str(k), name, short)
        console.print(t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
