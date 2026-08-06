#!/usr/bin/env python3
"""Pictures OF the manuscript, for revising it. Not pictures IN it.

Everything here is a diagnostic: it answers a question about the draft that a
single number cannot. `just readability` says the mean sentence is 22 words,
which does not tell you whether that is a uniform 22 or a calm 15 with a tail of
monsters. The histogram does, and the tail is what you actually go and fix.

Output goes to viz/, NOT figures/. figures/ holds the manuscript's own figures
and is checked for orphans, so a diagnostic written there would be reported as
a generated asset nothing cites. viz/ is gitignored and disposable.

    just viz          # rebuild all of them

Inputs are the same cleaned prose the word count and readability report use, so
citations, math, code and captions are already out of the way.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt        # noqa: E402

import density                          # noqa: E402  (the section splitter)
import prose_check                      # noqa: E402  (COMMON, the bib reader)
import readability                      # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "viz"

# Determinism, so a rebuild with no edits produces the same bytes and does not
# look like a change. Same reason the figure generators seed their RNG.
PNG = {"dpi": 200, "bbox_inches": "tight", "metadata": {"Software": None}}
INK = "#2563eb"
MUTED = "#94a3b8"

# Words too ordinary to be interesting in a frequency ranking. COMMON is the
# list the repetition check already uses; the rest are the connective tissue of
# academic prose specifically, which would otherwise fill the top ten of every
# paper ever written.
STOP = prose_check.COMMON | set("""
we our us their its it this that these those there here
using used use uses than then thus also however therefore although while
each per both same other another such only just even still yet
been being was were are is be has have had having does did do
between within across after before above below during through
first second third one two three four five
figure figures table tables section sections supporting information
shows show shown showed observed observe found find seen see given give
respectively approximately about across less more most least high higher
low lower large larger small smaller same different
""".split())


def prose() -> tuple[str, str]:
    """(main text, SI) as cleaned prose."""
    main = readability.clean(
        readability.slice_body((HERE / "paper.typ").read_text()))
    si_path = HERE / "si-body.typ"
    si = readability.clean(si_path.read_text()) if si_path.is_file() else ""
    return main, si


def _save(fig, name: str) -> None:
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / name, **PNG)
    plt.close(fig)
    print(f"  viz/{name}")


def _bare(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


# --- 1. sentence lengths ---------------------------------------------------

def sentence_lengths(main: str, si: str) -> None:
    """Where the long sentences actually are.

    A mean hides the shape. This shows the tail, which is the part worth
    rewriting, and marks the limit prose-check enforces so the two agree.
    """
    lens = [len(s.split()) for s in prose_check.sentences(main + " " + si)]
    if not lens:
        return
    limit = prose_check.load_config(HERE).limit("max-sentence-words")
    over = [n for n in lens if n > limit]

    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.hist(lens, bins=range(0, max(lens) + 3, 2), color=INK, alpha=0.85)
    ax.axvline(limit, color="#dc2626", lw=1.4, ls="--",
               label=f"prose-check limit ({limit}): {len(over)} over")
    med = sorted(lens)[len(lens) // 2]
    ax.axvline(med, color=MUTED, lw=1.4, label=f"median {med}")
    ax.set_xlabel("words in a sentence")
    ax.set_ylabel("sentences")
    ax.set_title(f"Sentence length ({len(lens)} sentences)")
    ax.legend(frameon=False, fontsize=9)
    _bare(ax)
    _save(fig, "sentence_lengths.png")


# --- 2. section word budget ------------------------------------------------

def section_budget(main: str, si: str) -> None:
    """Which section is eating the word count.

    Ordered as written, not sorted by size: a paper is read in order, and the
    question is usually "is Methods swallowing the paper", which needs position.
    """
    rows = []
    for label, body in (("", main), ("SI: ", si)):
        for head, text in density.sections(body):
            n = len(re.findall(r"[A-Za-z][A-Za-z'-]*", text))
            if n:
                rows.append((label + head, n))
    if not rows:
        return

    fig, ax = plt.subplots(figsize=(7, max(2.5, 0.32 * len(rows))))
    names = [r[0][:44] for r in rows][::-1]
    vals = [r[1] for r in rows][::-1]
    colors = [MUTED if n.startswith("SI: ") else INK for n in names]
    ax.barh(names, vals, color=colors)
    for i, v in enumerate(vals):
        ax.text(v + max(vals) * 0.01, i, str(v), va="center", fontsize=8)
    ax.set_xlabel("words")
    ax.set_title(f"Words per section  (main {sum(v for n, v in zip(names, vals) if not n.startswith('SI: '))}, "
                 f"SI {sum(v for n, v in zip(names, vals) if n.startswith('SI: '))})")
    ax.tick_params(axis="y", labelsize=8)
    _bare(ax)
    _save(fig, "section_budget.png")


# --- 3. word frequency -----------------------------------------------------

def word_counts(main: str, si: str) -> Counter:
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", (main + " " + si).lower())
    return Counter(w for w in words if w not in STOP and not w.endswith("'s"))


def top_words(counts: Counter, n: int = 25) -> None:
    """The words this paper leans on.

    Stopwords removed, so what is left is vocabulary you chose. The use is
    spotting a term repeated where a pronoun or a shorter form would read
    better, which the per-sentence repetition rule cannot see across a section.
    """
    top = counts.most_common(n)
    if not top:
        return
    fig, ax = plt.subplots(figsize=(7, max(2.5, 0.28 * len(top))))
    names = [w for w, _ in top][::-1]
    vals = [c for _, c in top][::-1]
    ax.barh(names, vals, color=INK)
    for i, v in enumerate(vals):
        ax.text(v + max(vals) * 0.01, i, str(v), va="center", fontsize=8)
    ax.set_xlabel("occurrences")
    ax.set_title(f"Most-used content words (top {len(top)}, stopwords removed)")
    ax.tick_params(axis="y", labelsize=9)
    _bare(ax)
    _save(fig, "top_words.png")


def word_cloud(counts: Counter) -> None:
    """The same counts, arranged for looking at rather than reading off.

    Kept because it is enjoyable and it does make an unbalanced vocabulary
    obvious at a glance. It is not a measurement: area encodes frequency only
    loosely and the layout is arbitrary, so read top_words.png for anything you
    intend to act on.
    """
    try:
        from wordcloud import WordCloud
    except ImportError:
        print("  (wordcloud not installed, skipping word_cloud.png)")
        return
    if not counts:
        return
    wc = WordCloud(width=1600, height=900, background_color="white",
                   colormap="viridis", prefer_horizontal=0.9,
                   random_state=0)          # fixed, so the layout is stable
    wc.generate_from_frequencies(dict(counts))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    _save(fig, "word_cloud.png")


# --- 4. citation years -----------------------------------------------------

def citation_years() -> None:
    """How old the literature is.

    A review skewed a decade back is something reviewers notice and authors
    cannot see from the .bib. Recent years are highlighted so the balance reads
    at a glance.
    """
    bibs = sorted(HERE.glob("*.bib"))
    entries = [e for b in bibs for e in prose_check._bib_entries(b)]
    years = []
    for e in entries:
        m = re.search(r"\d{4}", e.get("year", ""))
        if m:
            years.append(int(m.group(0)))
    if not years:
        return

    newest = max(years)
    fig, ax = plt.subplots(figsize=(7, 3))
    lo, hi = min(years), newest
    bins = range(lo, hi + 2)
    counts = Counter(years)
    colors = [INK if y >= newest - 4 else MUTED for y in bins]
    ax.bar(list(bins), [counts.get(y, 0) for y in bins], color=colors)
    recent = sum(c for y, c in counts.items() if y >= newest - 4)
    ax.set_xlabel("year of publication")
    ax.set_ylabel("references")
    ax.set_title(f"Citation ages ({len(years)} dated references, "
                 f"{recent} from the last 5 years)")
    _bare(ax)
    _save(fig, "citation_years.png")


def main() -> int:
    main_text, si = prose()
    if not main_text.strip():
        print("no prose found in paper.typ", file=sys.stderr)
        return 1
    print("writing diagnostics to viz/ (not figures/ -- these are not manuscript figures)")
    sentence_lengths(main_text, si)
    section_budget(main_text, si)
    counts = word_counts(main_text, si)
    top_words(counts)
    word_cloud(counts)
    citation_years()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
