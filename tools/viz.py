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

# The manuscript root, one level up: this file lives in tools/.
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "viz"

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
        readability.slice_body((ROOT / "paper.typ").read_text()))
    si_path = ROOT / "si-body.typ"
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
    limit = prose_check.load_config(ROOT).limit("max-sentence-words")
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

def section_budget(main_src: str, si_src: str) -> None:
    """Which section is eating the word count.

    Ordered as written, not sorted by size: a paper is read in order, and the
    question is usually "is Methods swallowing the paper", which needs position.

    Takes the RAW source: cleaning first would remove the headings this splits
    on and collapse the whole document into one bar.
    """
    rows = []
    for label, body in (("", main_src), ("SI: ", si_src)):
        for head, raw in density.sections(body):
            n = len(re.findall(r"[A-Za-z][A-Za-z'-]*", readability.clean(raw)))
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
    bibs = sorted(ROOT.glob("*.bib"))
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


# --- 5. readability and density by section ---------------------------------

def _section_rows(main_src: str, si_src: str) -> list[dict]:
    """Per-section metrics, shared by the two plots and the JSON report.

    Splits the RAW source and cleans each section, in that order, the way
    density.py does. Cleaning first destroys the headings: readability.clean
    replaces a heading with a bare sentence boundary, so the splitter finds none
    and reports the whole document as one section.
    """
    rows = []
    for part, body in (("main", main_src), ("SI", si_src)):
        for head, raw in density.sections(body):
            text = readability.clean(raw)
            m = readability.metrics(text)
            d = density.metrics(text)
            if not m or m["words"] < density.MIN_SECTION_WORDS:
                continue
            rows.append({
                "section": head, "part": part, "words": m["words"],
                "fk_grade": round(m["fk"], 1), "reading_ease": round(m["ease"], 1),
                "words_per_sentence": round(m["wps"], 1),
                "passive_per_1k": round(d.get("passive", 0.0), 1),
                "hedges_per_1k": round(d.get("hedges", 0.0), 1),
                "nominalizations_per_1k": round(d.get("nominal.", 0.0), 1),
            })
    return rows


def readability_by_section(rows: list[dict]) -> None:
    """Which section is harder than the rest of the paper.

    A whole-document grade is an average, and the average is never the problem.
    Methods usually spikes, and that spike is what a reader hits first.
    """
    if not rows:
        return
    med = sorted(r["fk_grade"] for r in rows)[len(rows) // 2]
    fig, ax = plt.subplots(figsize=(7, max(2.5, 0.34 * len(rows))))
    names = [f"{r['section'][:38]}{'  (SI)' if r['part'] == 'SI' else ''}"
             for r in rows][::-1]
    vals = [r["fk_grade"] for r in rows][::-1]
    ax.barh(names, vals,
            color=["#dc2626" if v > med + 2 else INK for v in vals])
    ax.axvline(med, color=MUTED, lw=1.4, label=f"paper median {med}")
    for i, v in enumerate(vals):
        ax.text(v + 0.1, i, f"{v}", va="center", fontsize=8)
    ax.set_xlabel("Flesch-Kincaid grade")
    ax.set_title("Reading level by section (red = 2+ grades above the median)")
    ax.tick_params(axis="y", labelsize=8)
    ax.legend(frameon=False, fontsize=9)
    _bare(ax)
    _save(fig, "readability_by_section.png")


def style_density(rows: list[dict]) -> None:
    """Passive voice, hedging and nominalizations, per section.

    Three things a reading-level score is blind to and that make scientific
    prose heavy. Shown together because they travel together: the section that
    hedges most is usually the one hiding behind the passive.
    """
    if not rows:
        return
    keys = [("passive_per_1k", "passive"), ("hedges_per_1k", "hedges"),
            ("nominalizations_per_1k", "nominalizations")]
    fig, ax = plt.subplots(figsize=(7.5, max(2.8, 0.42 * len(rows))))
    names = [f"{r['section'][:34]}{'  (SI)' if r['part'] == 'SI' else ''}"
             for r in rows][::-1]
    y = range(len(names))
    h = 0.26
    for i, (key, label) in enumerate(keys):
        vals = [r[key] for r in rows][::-1]
        ax.barh([v + (i - 1) * h for v in y], vals, height=h, label=label)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel("per 1,000 words")
    ax.set_title("Style density by section")
    ax.legend(frameon=False, fontsize=9)
    _bare(ax)
    _save(fig, "style_density.png")


# --- 6. where each figure and table is cited -------------------------------

def _float_map(main_src: str, si_src: str) -> list[dict]:
    """Every float, and where in the document it is referenced.

    Positions are fractions of the whole text, so the picture is "cited early
    and never again" versus "carried through the argument", which is the thing
    worth seeing.
    """
    joined = main_src + "\n" + si_src
    total = max(1, len(joined))
    labels = {}
    for m in prose_check.DEFINITION.finditer(joined):
        labels.setdefault(m.group(1), m.start() / total)

    out = []
    for label, defined_at in labels.items():
        sites = [m.start() / total
                 for m in re.finditer(rf"@{re.escape(label)}\b", joined)]
        sites += [m.start() / total for m in re.finditer(
            rf"#refn?\(\s*<{re.escape(label)}>", joined)]
        kind = {"fig": "figure", "tbl": "table", "tab": "table",
                "eq": "equation"}.get(label.split(":")[0], "float")
        out.append({"label": label, "kind": kind, "defined_at": round(defined_at, 3),
                    "citations": len(sites),
                    "positions": [round(p, 3) for p in sorted(sites)]})
    return sorted(out, key=lambda r: r["defined_at"])


def float_map(rows: list[dict]) -> None:
    """A strip per float showing every place it is referenced.

    Reveals two things nothing else does: a figure cited once in passing and
    then abandoned, and a cluster of floats all cited in one paragraph, which
    usually means the argument is carrying them rather than the reverse.
    """
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(7.5, max(2.4, 0.3 * len(rows))))
    for i, r in enumerate(rows[::-1]):
        y = i
        ax.plot([0, 1], [y, y], color="#e2e8f0", lw=1, zorder=1)
        ax.scatter([r["defined_at"]], [y], marker="|", s=90, color=MUTED,
                   zorder=2)
        if r["positions"]:
            ax.scatter(r["positions"], [y] * len(r["positions"]), s=26,
                       color=INK if r["citations"] > 1 else "#dc2626", zorder=3)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"{r['label']}  ({r['citations']}x)"
                        for r in rows[::-1]], fontsize=8)
    ax.set_xlabel("position in the document")
    ax.set_xlim(-0.02, 1.02)
    ax.set_title("Where each figure and table is cited "
                 "(grey = defined, red = cited once)")
    _bare(ax)
    _save(fig, "float_map.png")


# --- 7. who the bibliography cites -----------------------------------------

AUTHOR_NAME = re.compile(r'name:\s*"([^"]+)"')


def _own_surnames() -> set[str]:
    """Surnames from config.typ, for the self-citation share.

    Parsed with the same regex audio/config.py uses rather than imported from
    it, because audio/ is optional and deleting it must not take this with it.
    """
    cfg = ROOT / "config.typ"
    if not cfg.is_file():
        return set()
    out = set()
    for name in AUTHOR_NAME.findall(cfg.read_text()):
        parts = [p for p in name.replace(",", " ").split() if len(p) > 1]
        if parts:
            out.add(parts[-1].lower())
    return out


def _bib_authors() -> tuple[list[dict], set[str]]:
    entries = [e for b in sorted(ROOT.glob("*.bib"))
               for e in prose_check._bib_entries(b)]
    return entries, _own_surnames()


def _surnames(author_field: str) -> list[str]:
    """Surnames out of a BibTeX author field, both orderings."""
    out = []
    for chunk in re.split(r"\s+and\s+", author_field):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "," in chunk:                       # "Lovelace, Ada"
            out.append(chunk.split(",")[0].strip().lower())
        else:                                  # "Ada Lovelace"
            parts = chunk.split()
            if parts:
                out.append(parts[-1].strip().lower())
    return [s for s in out if len(s) > 1]


def citation_authors(entries: list[dict], mine: set[str]) -> dict:
    """Who this bibliography cites, and how much of it is us.

    Self-citation is normal and expected; an unexamined share of it is what
    reviewers comment on. The number is not visible from the .bib while writing.
    """
    counts, self_cited = Counter(), 0
    for e in entries:
        names = _surnames(e.get("author", ""))
        counts.update(names)
        if mine & set(names):
            self_cited += 1
    stats = {
        "entries": len(entries),
        "self_cited": self_cited,
        "self_share": round(100.0 * self_cited / max(1, len(entries)), 1),
        "own_surnames": sorted(mine),
        "top_authors": counts.most_common(15),
    }
    if not counts:
        return stats

    top = counts.most_common(15)
    fig, ax = plt.subplots(figsize=(7, max(2.5, 0.28 * len(top))))
    names = [n.title() for n, _ in top][::-1]
    vals = [c for _, c in top][::-1]
    ax.barh(names, vals,
            color=["#dc2626" if n.lower() in mine else INK for n in names])
    for i, v in enumerate(vals):
        ax.text(v + 0.05, i, str(v), va="center", fontsize=8)
    ax.set_xlabel("references")
    ax.set_title(f"Most-cited authors  (red = an author of this paper; "
                 f"{self_cited}/{len(entries)} refs = {stats['self_share']}% self-cited)")
    ax.tick_params(axis="y", labelsize=9)
    _bare(ax)
    _save(fig, "citation_authors.png")
    return stats


# --- the machine-readable half ---------------------------------------------

def write_report(main: str, si: str, rows: list[dict], floats: list[dict],
                 counts: Counter, bib: dict) -> None:
    """Everything the plots show, as JSON.

    A picture is for a person deciding what to revise. An agent asked to tighten
    the densest section, or to find the figure cited only once, should read the
    number rather than infer it from a chart or re-derive it with a different
    method and get a different answer. CLAUDE.md already tells agents to quote
    the pipeline's numbers instead of estimating; this is the file to quote.
    """
    import json

    cfg = prose_check.load_config(ROOT)
    limit = cfg.limit("max-sentence-words")
    sents = prose_check.sentences(main + " " + si)
    lens = sorted(len(s.split()) for s in sents)
    longest = sorted(sents, key=lambda s: -len(s.split()))[:10]

    report = {
        "_about": "Generated by viz.py (`just viz`). Diagnostics about the "
                  "draft, not content of it. Regenerate rather than edit.",
        "words": {
            "main": len(re.findall(r"[A-Za-z][A-Za-z'-]*", main)),
            "si": len(re.findall(r"[A-Za-z][A-Za-z'-]*", si)),
        },
        "sentences": {
            "count": len(lens),
            "median": lens[len(lens) // 2] if lens else 0,
            "p90": lens[int(len(lens) * 0.9)] if lens else 0,
            "longest": max(lens) if lens else 0,
            "limit": limit,
            "over_limit": sum(1 for n in lens if n > limit),
            "longest_sentences": [
                {"words": len(s.split()), "text": s[:300]} for s in longest],
        },
        "sections": rows,
        "floats": floats,
        "uncited_floats": [f["label"] for f in floats if not f["citations"]],
        "floats_cited_once": [f["label"] for f in floats if f["citations"] == 1],
        "bibliography": bib,
        "top_words": counts.most_common(40),
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("  viz/report.json  (the same numbers, for tools and agents)")


def main() -> int:
    main_text, si = prose()
    if not main_text.strip():
        print("no prose found in paper.typ", file=sys.stderr)
        return 1
    print("writing diagnostics to viz/ (not figures/ -- these are not manuscript figures)")

    main_src = (ROOT / "paper.typ").read_text()
    si_src_path = ROOT / "si-body.typ"
    si_src = si_src_path.read_text() if si_src_path.is_file() else ""

    sentence_lengths(main_text, si)
    section_budget(readability.slice_body(main_src), si_src)
    counts = word_counts(main_text, si)
    top_words(counts)
    word_cloud(counts)
    citation_years()

    rows = _section_rows(readability.slice_body(main_src), si_src)
    readability_by_section(rows)
    style_density(rows)

    floats = _float_map(main_src, si_src)
    float_map(floats)

    entries, mine = _bib_authors()
    bib = citation_authors(entries, mine)

    write_report(main_text, si, rows, floats, counts, bib)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
