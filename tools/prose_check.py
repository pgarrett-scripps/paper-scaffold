#!/usr/bin/env python3
"""Check the manuscript prose against the mechanical rules in STYLE.md.

Only the rules a machine can judge. "Simpler is better" is not checkable and is
not checked; a British spelling is, and so is an em dash. Everything here runs on
the same cleaned prose the word count and readability report use, so citations,
figures, tables, math, and code are already out of the way and cannot trigger a
false hit.

Two severities. ERRORS are rules with no legitimate exception in this manuscript,
and they exit non-zero so `just prose-check` can gate a commit. WARNINGS are
judgement calls, reported with counts and locations so they can be skimmed and
ignored. A style checker that fails the build over the word "very" gets disabled
within a week, so it does not.

Anything a particular project has earned an exception to goes in
`prose-check.toml`. See prose_rules.py for the rule ids and the file's shape, or
run with --list-rules.

Usage:
    python3 prose_check.py                    # main text + SI
    python3 prose_check.py --strict           # warnings become errors too
    python3 prose_check.py --show-suppressed  # list what the config is hiding
    python3 prose_check.py --list-rules       # rule ids and how to suppress each
"""
from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path

import readability
import typst_prose
from manuscript_sources import mask, si_bibliography
from prose_rules import Config, Finding, list_rules, load_config, report
import claim_rules

# The manuscript root, one level up: this file lives in tools/.
from paths import ROOT  # the manuscript (tools/paths.py)

# --- ERRORS: no legitimate exception --------------------------------------

# British -> American.
#
# An explicit list, NOT a general "-ise -> -ize" rule. The general rule looks
# tempting and is wrong: it fires on every domain word that happens to end in
# those letters, which in the manuscript this came from meant flagging the name of
# the software itself (dnoise, denoise) on every mention. A checker that cries
# wolf on the project's own vocabulary gets switched off. Add words as you hit
# them rather than trying to be clever.
_ISE = [
    "normalise", "analyse", "optimise", "characterise", "summarise", "recognise",
    "organise", "standardise", "minimise", "maximise", "utilise", "emphasise",
    "visualise", "realise", "categorise", "prioritise", "generalise",
    "specialise", "stabilise", "polymerise", "ionise", "oxidise", "neutralise",
    "localise", "randomise", "digitise", "hydrolyse", "catalyse", "paralyse",
    "criticise", "memorise", "familiarise", "harmonise", "synchronise",
    "hypothesise", "apologise", "colourise",
]


def _americanize(w: str) -> str:
    return w.replace("yse", "yze").replace("ise", "ize").replace("isation", "ization")


# Forms that collide with a correct American word and must never be flagged.
# "analyses" is the ordinary plural of "analysis"; only the verb sense is British,
# and nothing here can tell them apart.
_COLLIDES = {"analyses", "practises", "practising", "practised", "programmes"}


def _british_words() -> dict[str, str]:
    out = {}
    for w in _ISE:
        stem = w[:-1]                       # normalise -> normalis
        for form in (w, stem + "ed", stem + "ing", w + "s", stem + "ation"):
            if form in _COLLIDES:
                continue
            out[form] = _americanize(form)
    out.update({
        "colour": "color", "colours": "colors", "coloured": "colored",
        "behaviour": "behavior", "behaviours": "behaviors",
        "favour": "favor", "favours": "favors", "favoured": "favored",
        "labour": "labor", "centre": "center", "centres": "centers",
        "metre": "meter", "metres": "meters", "fibre": "fiber",
        "catalogue": "catalog", "grey": "gray", "artefact": "artifact",
        "artefacts": "artifacts", "modelling": "modeling", "modelled": "modeled",
        "labelling": "labeling", "labelled": "labeled",
        "signalling": "signaling", "signalled": "signaled",
        "towards": "toward", "whilst": "while", "amongst": "among",
        "learnt": "learned", "practise": "practice", "defence": "defense",
        "programme": "program", "sulphur": "sulfur", "haemoglobin": "hemoglobin",
        "oedema": "edema", "foetal": "fetal",
    })
    return out


BRITISH = _british_words()

# Misspellings, from codespell's dictionaries.
#
# NOT a dictionary spell-check. Those ask "is this word in the wordlist", which
# on a scientific manuscript flags the vocabulary rather than the errors: on the
# paper this was built for, pyspellchecker called out 418 words -- bruker,
# cerevisiae, centroider, ddapasef, carbamidomethyl -- and essentially no typos.
# A checker that is 99% noise gets switched off, which is the outcome every rule
# here is written to avoid.
#
# codespell instead ships curated confusion pairs (measurment -> measurement), so
# it only fires when it is confident. On that same manuscript it produced zero
# false positives across 15,175 words while catching every injected typo.
#
# `clear` and `rare` are codespell's own defaults. `en-GB_to_en-US` is
# deliberately excluded: BRITISH above is the curated list for that, and the two
# would disagree about the project's own vocabulary.
CODESPELL_DICTS = ("dictionary.txt", "dictionary_rare.txt")


@lru_cache(maxsize=1)
def _misspellings() -> dict[str, str]:
    """word -> suggested correction(s), lowercase.

    Read from the installed codespell package rather than vendored, so the list
    updates with the dependency. Entries are `wrong->right[, other]`; the ones
    with several suggestions are codespell's "uncertain" cases and are reported
    with all of them, since picking one is the author's call.
    """
    try:
        import codespell_lib
    except ImportError:
        return {}
    data = Path(codespell_lib.__file__).resolve().parent / "data"
    out: dict[str, str] = {}
    for name in CODESPELL_DICTS:
        f = data / name
        if not f.is_file():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if "->" not in line:
                continue
            wrong, right = line.split("->", 1)
            out.setdefault(wrong.strip().lower(),
                           ", ".join(p.strip() for p in right.split(",") if p.strip()))
    return out

# --- WARNINGS: judgement calls --------------------------------------------

VERBOSE = {
    "utilize": "use", "utilizes": "uses", "utilized": "used",
    "in order to": "to", "due to the fact that": "because",
    "it should be noted that": "(cut it)", "it is worth noting that": "(cut it)",
    "the fact that": "that", "a number of": "several",
    "in the event that": "if", "at this point in time": "now",
    "each and every": "every", "first and foremost": "first",
    "very": "(cut it)", "quite": "(cut it)", "clearly": "(cut it)",
    "obviously": "(cut it)", "importantly": "(cut it)",
    "basically": "(cut it)", "essentially": "(cut it)",
}
DOUBLE_HEDGE = re.compile(
    r"\b(may|might|could|can)\s+(possibly|potentially|perhaps|conceivably)\b", re.I
)
# Words common enough that repeating them is invisible; only flag beyond these.
COMMON = set("""
the a an and or but of in on at to for with from by as is are was were be been
this that these those it its we our they their he she them his her him us you your
not no if then than so such which who whom whose what when where while during
can could may might will would shall should must do does did have has had
one two three all both each any some more most other another same different
into over under between within across after before above below through
""".split())


def sentences(text: str) -> list[str]:
    """Split into sentences, protecting the abbreviations readability knows about."""
    t = readability.protect_periods(text)
    parts = re.split(r"(?<=[.!?])\s+", t)
    return [p.replace("\x00", ".").strip() for p in parts if len(p.split()) >= 2]


def _ctx(text: str, i: int, w: int = 45) -> str:
    return "..." + re.sub(r"\s+", " ", text[max(0, i - w):i + w]) + "..."


# Marks where clean() removed a construct. Not whitespace, so a duplicate-word
# pattern cannot match across it.
GAP = "\x00"


def check(label: str, text: str, spellable: str | None = None,
          gapped: str | None = None, cfg: Config | None = None) -> list[Finding]:
    """`text` is the cleaned prose. `spellable` is the same prose with inline code
    removed rather than unwrapped, and is what the spelling check runs on.
    `gapped` is the same prose with a sentinel where constructs were removed, and
    is what the duplicate-word check runs on.

    They have to differ. readability.clean() turns `Ms1.Normalised` into a bare
    word, because journals count an inline-code term as a word. Spell-checking
    that word then flags a DIA-NN column name as a British spelling, which is not
    something the author can act on.

    `gapped` exists for the same class of reason. clean() replaces a removed
    construct with a space, so `and $N_"human"$ and` becomes a literal `and and`
    and the duplicate-word check reports a repetition the author never wrote.
    """
    spellable = text if spellable is None else spellable
    gapped = text if gapped is None else gapped
    cfg = Config() if cfg is None else cfg
    out: list[Finding] = []
    sents = sentences(text)

    # The shipped word lists with this project's additions and removals applied.
    # A field where "essentially" is load-bearing, or whose own vocabulary trips
    # the British list, needs to teach the checker rather than switch it off.
    british = cfg.vocabulary("british-spelling", BRITISH)
    verbose = cfg.vocabulary("verbose-phrase", VERBOSE)
    common = cfg.vocabulary("common-words", COMMON)

    def add(rule, message, subject="", context=""):
        from prose_rules import RULES
        out.append(Finding(rule, RULES[rule][0], message, subject, label, context))

    # --- errors ---
    for m in re.finditer(r"—", text):
        add("em-dash", "em dash", context=_ctx(text, m.start()))

    # Both spelling checks read `spellable`, not `text`. clean() unwraps an
    # inline-code span into a bare word because a journal counts it as one, and
    # spell-checking that flags a tool's own flags: `--reanalyse` is a DIA-NN
    # option, not a British spelling the author can act on.
    misspelled = _misspellings()
    for m in re.finditer(r"\b[A-Za-z]+\b", spellable):
        word = m.group(0)
        fix = british.get(word.lower())
        if fix:
            add("british-spelling", f"{word!r} -> {fix}", word,
                _ctx(spellable, m.start()))
            continue
        # A word inside a hyphenated compound is skipped HERE but not above.
        # codespell's list contains fragments that are only wrong standing
        # alone -- "mis" suggests "miss, mist", which is right for a bare "mis"
        # and wrong for the "mis" in "mis-transferred". The British list is
        # curated and has no such fragments, so it still flags the "colour" in
        # "colour-coded". Dropping this check reintroduces a false positive that
        # codespell itself does not make.
        if (m.start() and spellable[m.start() - 1] == "-") or \
                spellable[m.end():m.end() + 1] == "-":
            continue
        fix = misspelled.get(word.lower())
        if fix:
            add("misspelling", f"{word!r} -> {fix}", word,
                _ctx(spellable, m.start()))

    for m in re.finditer(r"\b(\w+)\s+\1\b", gapped, re.I):
        if m.group(1).lower() in {"had", "that"}:   # legitimately doubles
            continue
        # Window first, THEN drop the sentinels. Stripping them from the whole
        # string before indexing shifts every offset after the first removed
        # construct, which slid the reported context clean off the match.
        add("doubled-word", f"doubled word {m.group(0)!r}", m.group(1),
            _ctx(gapped, m.start()).replace(GAP, ""))

    # --- warnings ---
    for s in sents:
        n = len(s.split())
        if n > cfg.limit("max-sentence-words"):
            add("long-sentence", f"{n}-word sentence", context=f'"{s[:90]}..."')

    for phrase, fix in verbose.items():
        for m in re.finditer(rf"\b{re.escape(phrase)}\b", text, re.I):
            add("verbose-phrase", f"{phrase!r} -> {fix}", phrase,
                _ctx(text, m.start()))

    for m in DOUBLE_HEDGE.finditer(text):
        add("double-hedge", f"double hedge {m.group(0)!r}", m.group(0),
            _ctx(text, m.start()))

    # repeated sentence openers
    run, first = 1, 0
    for i in range(1, len(sents) + 1):
        same = (i < len(sents)
                and sents[i].split()[:1] == sents[i - 1].split()[:1]
                and sents[i].split()[:1])
        if same:
            run += 1
        else:
            if run >= cfg.limit("opener-run"):
                word = sents[first].split()[0]
                add("opener-run", f"{run} sentences in a row open with {word!r}", word)
            run, first = 1, i

    # A distinctive word repeated inside one sentence.
    #
    # Run on `spellable`, the prose with inline-code spans REMOVED rather than
    # unwrapped, for the same reason the spelling check does. A sentence listing
    # three reproducer scripts under one directory is not repetitive prose, but
    # unwrapping the backticks turns the directory name into an ordinary word
    # appearing three times. That was 12 of one manuscript's 18 findings, and a
    # checker whose warnings are mostly noise is a checker nobody reads.
    for s in sentences(spellable):
        seen: dict[str, int] = {}
        for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", s.lower()):
            if w in common:
                continue
            seen[w] = seen.get(w, 0) + 1
        for w, c in seen.items():
            if c >= cfg.limit("repeat-in-sentence"):
                add("word-repetition", f"{w!r} appears {c}x in one sentence", w,
                    f'"{s[:80]}..."')

    semis = text.count(";")
    if semis:
        add("semicolon-count",
            f"{semis} semicolon(s), STYLE.md asks for sparing use")

    return out


def no_code(src: str) -> str:
    """Drop inline-code spans outright, so identifiers are not spell-checked."""
    return re.sub(r"`[^`]*`", " ", src)


# Acronyms that are never expanded because expanding them would be absurd.
ACRONYM_OK = {
    # file formats and computing
    "PDF", "CSV", "TSV", "JSON", "HTML", "XML", "URL", "API", "CPU", "GPU",
    "RAM", "SSD", "OS", "ID", "IDS", "AI", "MIT", "BSD", "GNU",
    # units and quantities
    "GB", "MB", "KB", "TB", "MS", "NS", "PPM", "RPM", "SD", "SE", "CI", "CV",
    # places, orgs, identifiers
    "USA", "UK", "EU", "CA", "NY", "ORCID", "DOI", "ISO", "UTC", "PHD", "NIH",
    # near-universal in science
    "DNA", "RNA", "PCR", "FDR", "PCA",
}


KIND = {"fig": "Figure", "tbl": "Table", "tab": "Table", "eq": "Equation"}

# Label prefixes that name a float. `tbl:` and `tab:` are BOTH here because the
# prefix is a project convention, not a Typst rule. A manuscript using `tab:`
# throughout had all 37 of its tables silently exempted from the uncited-float
# and reference-order checks, while the checker reported cleanly. Add a prefix
# here rather than renaming a manuscript's labels.
FLOAT = r"(?:fig|tbl|tab|eq)"

# Where a float is DEFINED, as opposed to referenced.
#
# A bare `<fig:x>` cannot tell the two apart: `#ref(<fig:x>)` and `#refn(<fig:x>)`
# contain the identical token, so a bare-label scan counts every citation site as
# another figure and numbers each float by its LAST occurrence in the file. In the
# manuscript that found this, the checker believed the main text defined 15
# figures, in an order set by where they were cited, and named a "Figure 10" that
# does not exist. There are five.
#
# Typst attaches a label to the element it follows, so a definition is a label
# after the closing paren of the `#figure(...)` call. A reference is a label
# INSIDE a call's parentheses. Anchoring on the preceding `)` separates them
# exactly, and tolerates the line break typstyle may put in between.
DEFINITION = re.compile(rf"\)\s*<({FLOAT}:[A-Za-z0-9_-]+)>")


def check_reference_order(sources: dict[str, str]) -> list[Finding]:
    """Figures and tables should be first cited in numerical order.

    Typst numbers them by order of appearance in the source, so the number a
    reader sees is fixed by where the #figure sits. Journals then require the text
    to reach them in that order, and citing Figure 3 before Figure 2 is a
    copy-editing return at many publishers. Reordering prose during revision is
    exactly how it happens.

    A WARNING rather than an error, because there is one defensible exception: a
    conventions or overview paragraph that legitimately forward-references a later
    figure. Take it seriously anyway, since a journal will.

    Two details make this correct rather than approximately right. A reference
    inside a figure's own caption does not count as the text reaching it, so
    figure blocks are stripped before looking for citations. And each document is
    scored on its own sequence, because the SI restarts at S1.

    Reported one line per offending EARLY citation, not one per figure it jumps
    ahead of. A single early mention of Figure 7 puts six later figures out of
    order, and six near-identical messages describing one edit is noise.
    """
    out = []
    for name, src in sources.items():
        # Numbering order: where each #figure/#table actually sits.
        defined = [m.group(1) for m in DEFINITION.finditer(src)]
        number, label_of = {}, {}
        for kind in ("fig", "tbl", "tab"):
            seq = [d for d in defined if d.startswith(kind + ":")]
            for i, label in enumerate(seq):
                number[label] = i + 1
                label_of[(kind, i + 1)] = label

        # Citation order, ignoring cross-references made from inside a caption.
        prose = readability._strip_balanced(src, "#figure(")
        cited: list[str] = []
        for m in re.finditer(
                rf"(?:@|#refn?\(\s*<)({FLOAT}:[A-Za-z0-9_-]+)", prose):
            if m.group(1) not in cited:
                cited.append(m.group(1))

        for kind in ("fig", "tbl", "tab"):
            seq = [c for c in cited if c.startswith(kind + ":") and c in number]
            jumped: dict[int, list[int]] = {}
            highest = 0
            for label in seq:
                n = number[label]
                if n < highest:
                    jumped.setdefault(highest, []).append(n)
                else:
                    highest = n
            for early, skipped in jumped.items():
                lo, hi = min(skipped), max(skipped)
                span = f"{KIND[kind]} {lo}" if lo == hi else \
                    f"{KIND[kind]}s {lo}–{hi}"
                label = label_of[(kind, early)]
                out.append(Finding(
                    "reference-order", "warn",
                    f"{KIND[kind]} {early} (<{label}>) is cited before {span}, "
                    f"either move its first mention later or move the "
                    f"{KIND[kind].lower()} earlier",
                    subject=label, where=name))
    return out


# A citation of a float or section, in both reference forms.
XREF = rf"(?:@|#refn?\(\s*<)((?:sec|{FLOAT}):[A-Za-z0-9_-]+)"


def check_cross_reference_order(sources: dict[str, str]) -> list[Finding]:
    """SI floats should be first reached from the main text in S-order.

    check_reference_order scores each document on its own sequence, which is
    right for numbering but blind to the order that matters most for an SI:
    the order the MAIN text sends a reader into it. A manuscript reached
    Table S16 second and Figure S6 first with every check clean. So: number
    the SI's floats by where they sit in the SI, take each one's first
    citation in the main text, and require that sequence to rise per kind.
    A jump is one finding, on the label cited early, like the single-document
    rule. A float reached only from inside the SI is not reported here; that
    is uncited-figure's territory.
    """
    main, si = sources.get("main"), sources.get("SI")
    if main is None or si is None:
        return []
    defined = [m.group(1) for m in DEFINITION.finditer(si)]
    number: dict[str, int] = {}
    for kind in ("fig", "tbl", "tab"):
        for i, label in enumerate(d for d in defined if d.startswith(kind + ":")):
            number[label] = i + 1

    # A citation from inside a main-text caption does not send the reader.
    prose = readability._strip_balanced(main, "#figure(")
    cited: list[str] = []
    for m in re.finditer(XREF, prose):
        if m.group(1) in number and m.group(1) not in cited:
            cited.append(m.group(1))

    out = []
    for kind in ("fig", "tbl", "tab"):
        highest, early_label = 0, ""
        jumped: dict[str, list[int]] = {}
        for label in (c for c in cited if c.startswith(kind + ":")):
            n = number[label]
            if n < highest:
                jumped.setdefault(early_label, []).append(n)
            else:
                highest, early_label = n, label
        for label, skipped in jumped.items():
            lo, hi = min(skipped), max(skipped)
            span = f"{KIND[kind]} S{lo}" if lo == hi else \
                f"{KIND[kind]}s S{lo}–S{hi}"
            out.append(Finding(
                "cross-reference-order", "warn",
                f"the main text reaches {KIND[kind]} S{number[label]} "
                f"(<{label}>) before {span}: move the float earlier in the "
                f"SI, or its first main-text mention later",
                subject=label, where="main"))
    return out


# A level-1 SI heading and its label, which typstyle may wrap onto the next
# line when the title is long. An unlabeled heading is not checked: nothing
# can cite it by name, and the back-matter headings are unlabeled on purpose.
SI_SECTION = re.compile(
    r"(?m)^=[ \t]+([^\n<]+?)\s*\n?\s*<(sec:[A-Za-z0-9_-]+)>")


def check_unreached_si_sections(sources: dict[str, str]) -> list[Finding]:
    """Every level-1 SI section should be reachable from the main text.

    An SI is read from the main text, not front to back, so a section that no
    main-text sentence points at, by its label or by any float or subsection
    inside it, is one the reader is never sent to. A warning, because a
    section can be reached through a sibling's prose and still be fine; read
    it rather than silence it.
    """
    main, si = sources.get("main"), sources.get("SI")
    if main is None or si is None:
        return []
    refs = set(re.findall(XREF, main))
    heads = list(SI_SECTION.finditer(si))
    out = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(si)
        block = si[h.end():end]
        inside = {h.group(2)} | set(DEFINITION.findall(block)) | set(
            re.findall(r"<(sec:[A-Za-z0-9_-]+)>", block))
        if not inside & refs:
            out.append(Finding(
                "unreached-si-section", "warn",
                f"SI section \"{h.group(1)}\" (<{h.group(2)}>) is cited from "
                f"nowhere in the main text, by section or by a float inside it",
                subject=h.group(2), where="SI"))
    return out


# An `image("...")` call and whatever arguments follow it, which may include a
# `width:`. `[^)]` rather than `.` so a reflowed multi-line call still matches.
IMAGE_CALL = re.compile(r'image\(\s*"([^"]+)"([^)]*)\)')
# A generated figure by id. The path comes from assets.json, which is how the
# compile finds it too; without this the scaffold's own figures -- every one of
# which goes through fig() -- were never measured, while the comment in the
# generator said they were.
FIG_CALL = re.compile(r'\bfig\(\s*"([^"]+)"([^)]*)\)')
WIDTH_PCT = re.compile(r"width:\s*([\d.]+)%")
# An absolute width, as a TOC graphic placed at the journal's box size is.
WIDTH_ABS = re.compile(r"width:\s*([\d.]+)\s*(in|cm|mm|pt)\b")
_TO_INCHES = {"in": 1.0, "cm": 1 / 2.54, "mm": 1 / 25.4, "pt": 1 / 72}

# Formats with no pixels to count. A DPI figure for them is meaningless.
VECTOR_SUFFIXES = {".svg", ".pdf", ".eps"}


def _png_size(p: Path) -> tuple[int, int] | None:
    """Pixel dimensions from a PNG header, without decoding the image.

    Done by hand rather than through Pillow so this check runs anywhere the rest
    of prose_check does, including a bare `python3 tests/run.py`.
    """
    with p.open("rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return (int.from_bytes(head[16:20], "big"),
            int.from_bytes(head[20:24], "big"))


def _pixel_width(p: Path) -> int | None:
    if p.suffix.lower() == ".png":
        size = _png_size(p)
        return size[0] if size else None
    try:                              # JPEG, TIFF and friends, if Pillow is here
        from PIL import Image
        with Image.open(p) as im:
            return im.size[0]
    except Exception:
        return None


def check_figure_resolution(root: Path | None = None,
                            cfg: Config | None = None) -> list[Finding]:
    """Flag a raster figure whose resolution AS PRINTED falls below the limit.

    The number that matters is not what the file stores, it is pixels divided by
    the width the figure is actually rendered at. A 1000-pixel plot placed at
    `width: 70%` of a 160 mm text block prints at about 227 dpi and looks soft on
    paper however crisp it was on screen. Journals reject for this late, after
    acceptance, when regenerating figures is most annoying.

    The rendered width comes from the `width:` in the `image(...)` or `fig(...)`
    call: a percentage of the text block, or an absolute length. A call with no
    width is treated as spanning the full text block, which is what Typst does
    when it scales an image to its container. A fig("id") call is resolved to
    its file through assets.json, exactly as the compile resolves it.

    Vector formats are skipped: they have no resolution to be below.
    """
    r = root or ROOT
    c = cfg or Config()
    min_dpi = c.limit("min-figure-dpi")
    width_mm = c.limit("figure-text-width-mm")
    text_in = width_mm / 25.4

    declared: dict[str, str] = {}
    manifest = r / "assets.json"
    if manifest.is_file():
        try:
            values = json.loads(manifest.read_text()).get("values", {})
            declared = {id: rec["path"] for id, rec in values.items()
                        if isinstance(rec, dict) and isinstance(rec.get("path"), str)}
        except (OSError, ValueError):
            declared = {}

    def printed(args: str) -> tuple[float, str]:
        a = WIDTH_ABS.search(args)
        if a:
            return (float(a.group(1)) * _TO_INCHES[a.group(2)],
                    f"{a.group(1)} {a.group(2)}")
        w = WIDTH_PCT.search(args)
        pct = float(w.group(1)) / 100 if w else 1.0
        return text_in * pct, f"{pct * 100:.0f}% of a {width_mm} mm text block"

    out: list[Finding] = []
    seen: set[str] = set()
    for src in sorted(r.glob("*.typ")):
        # Comment lines are dropped first: assets.typ documents its own usage
        # with a `fig("fig.example")` in a comment, which is not a placement.
        text = "\n".join(line for line in src.read_text().splitlines()
                         if not line.lstrip().startswith("//"))
        sites = [(m.group(1), m.group(2)) for m in IMAGE_CALL.finditer(text)]
        sites += [(declared[m.group(1)], m.group(2)) for m in FIG_CALL.finditer(text)
                  if m.group(1) in declared]
        for rel, args in sites:
            p = r / rel.lstrip("/")
            if not p.is_file() or p.suffix.lower() in VECTOR_SUFFIXES:
                continue
            inches, how = printed(args)
            key = f"{rel}@{inches:.4f}"
            if key in seen:
                continue
            seen.add(key)
            px = _pixel_width(p)
            if px is None:
                out.append(Finding(
                    "low-resolution-figure", "warn",
                    f"{rel} could not be measured (unreadable header, and Pillow "
                    f"is not available for this format), so its print resolution "
                    f"is unchecked",
                    subject=Path(rel).name, where=src.name))
                continue
            dpi = px / inches
            if dpi < min_dpi:
                out.append(Finding(
                    "low-resolution-figure", "warn",
                    f"{rel} prints at ~{dpi:.0f} dpi ({px} px across {how}), "
                    f"below the {min_dpi} dpi limit -- regenerate it at a higher "
                    f"savefig dpi, or place it smaller",
                    subject=Path(rel).name, where=src.name))
    return out


TABLE_CALL = re.compile(r"#table\(")
# `columns: 5`, `columns: (left, right)`, or the repeat form `columns: (1fr,) * 5`.
# The repeat has to be understood: read as a bare tuple it counts one column, and
# the row count derived from it is then wrong by that factor.
TABLE_COLUMNS = re.compile(r"columns:\s*(\d+|\([^)]*\)(?:\s*\*\s*\d+)?)")


def _column_count(spec: str) -> int:
    """Columns from a `columns:` value: a count, a tuple, or a repeated tuple."""
    spec = spec.strip()
    if spec.isdigit():
        return int(spec)
    mult = 1
    rep = re.search(r"\)\s*\*\s*(\d+)$", spec)
    if rep:
        mult = int(rep.group(1))
        spec = spec[:rep.start() + 1]
    inner = spec.strip().strip("()")
    return len([x for x in inner.split(",") if x.strip()]) * mult


def _balanced_from(src: str, i: int) -> str:
    """The text of the call whose opening paren is at or after `i`."""
    depth, start = 0, src.index("(", i)
    for j in range(start, len(src)):
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if depth == 0:
                return src[start + 1:j]
    return src[start + 1:]


def _cells(src: str) -> list[str]:
    """Every top-level `[...]` span, which is how Typst writes a table cell.

    Depth-tracked rather than regex-matched: a cell legitimately contains
    brackets of its own (`[#link(..)[text]]`), and a non-greedy `\\[.*?\\]` cuts
    it at the first inner close.
    """
    out, depth, start = [], 0, None
    for i, ch in enumerate(src):
        if ch == "[":
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0 and start is not None:
                out.append(src[start:i])
                start = None
    return out


def check_table_size(root: Path | None = None,
                     cfg: Config | None = None) -> list[Finding]:
    """Flag a table that will not lay out well at the page width.

    None of this is visible from the source. A generated table grows a column
    per condition or a row per run, and the first sign is a proof where the
    columns are unreadably narrow, a header stranded on the previous page, or one
    long cell wrapping to three lines and dragging its row with it. All three are
    found late, in the PDF, after the analysis is finished.

    Cell length is measured on the visible text, with Typst markup stripped, so
    `[#emph[Treated]]` counts as the seven characters a reader sees rather than
    the eighteen the source spends.
    """
    r = root or ROOT
    c = cfg or Config()
    max_cols = c.limit("max-table-columns")
    max_rows = c.limit("max-table-rows")
    max_chars = c.limit("max-cell-chars")

    out: list[Finding] = []
    for src in sorted(list(r.glob("*.typ")) + list((r / "si").glob("*.typ"))):
        text = src.read_text()
        where = src.name if src.parent == r else f"si/{src.name}"
        for m in TABLE_CALL.finditer(text):
            body = _balanced_from(text, m.start())
            cm = TABLE_COLUMNS.search(body)
            if not cm:
                continue
            cols = _column_count(cm.group(1))
            if cols < 1:
                continue

            cells = _cells(body)
            rows = -(-len(cells) // cols)      # ceil: a short last row still counts

            if cols > max_cols:
                out.append(Finding(
                    "oversized-table", "warn",
                    f"{where} has {cols} columns (limit {max_cols}); at this "
                    f"width every column is cramped -- split it, move detail to "
                    f"the SI, or transpose it",
                    subject=src.name, where=where))
            if rows > max_rows:
                out.append(Finding(
                    "oversized-table", "warn",
                    f"{where} has {rows} rows (limit {max_rows}); it will break "
                    f"across pages -- repeat the header with "
                    f"`table.header(repeat: true)`, or summarize it",
                    subject=src.name, where=where))

            longest = ""
            for cell in cells:
                plain = re.sub(r"#[a-z][a-z0-9.]*", "", cell)
                plain = re.sub(r"[\[\]*_`$]", "", plain).strip()
                if len(plain) > len(longest):
                    longest = plain
            if len(longest) > max_chars:
                out.append(Finding(
                    "oversized-table", "warn",
                    f"{where} has a {len(longest)}-character cell (limit "
                    f"{max_chars}): {longest[:40]!r}... -- it will wrap to "
                    f"several lines and unbalance the row; shorten it or move it "
                    f"to the caption",
                    subject=src.name, where=where))
    return out


# Entry types where a DOI is expected. A thesis, a manual, or a piece of software
# often has none, and reporting those is how a useful check becomes a wall of
# noise nobody reads.
DOI_EXPECTED = {"article", "inproceedings", "incollection", "inbook"}

# Nothing before this is expected to have one. DOIs were introduced in 2000 and
# older work was only retrofitted patchily, so demanding one from a foundational
# 1952 citation reports an absence the author cannot fix. Papers cite their
# field's origins routinely, which would make this the noisiest rule here.
DOI_ERA = 2000


def _bib_entries(path: Path) -> list[dict]:
    from bibliography import entries
    return entries(path)


def _normalize_doi(doi: str) -> str:
    d = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d.strip()


def single_bibliography(root: Path) -> bool:
    """project.toml's [bibliography] single; False when it cannot be read
    (project_sources reports the config error)."""
    from project_hooks import load
    try:
        return load(root).single_bibliography
    except (OSError, ValueError):
        return False


def check_si_bibliography(root: Path | None = None,
                          cfg: Config | None = None) -> list[Finding]:
    """The Supporting Information's own reference list, checked for routing.

    A manuscript whose SI ships to the journal as its own file needs its own
    reference list, and Typst allows only one native #bibliography per
    document. The SI's is set by Alexandria instead, which routes a citation
    to it by PREFIX: `@si-key` in si-body.typ goes to the SI list, `@key`
    goes to the main one.

    That is the whole failure mode. A bare `@key` in the SI compiles, renders
    a perfectly ordinary superscript, and quietly adds the work to the MAIN
    reference list -- where a reader of the separately submitted SI cannot
    follow it, and where it inflates the main text's numbering. Nothing about
    the rendered page says so, which is why it is checked here.

    The second rule is the prefix in paper.typ's `#show: alexandria(...)`
    against the one in si-body.typ's `#bibliographyx(...)`. Typst does refuse
    to compile them when they disagree, but from inside the Alexandria
    package ("cannot access fields on type none"), pointing at neither line.
    """
    r = root or ROOT
    si = si_bibliography(r)
    if single_bibliography(r):
        # project.toml says the SI has no list of its own: its @key citations
        # are meant for the one list, and the submission split gives the SI
        # file a local list of the works it cites (docs/submission.md). A
        # left-over Alexandria setup contradicts that declaration.
        if si is None:
            return []
        return [Finding(
            "si-bibliography-mode", "error",
            "project.toml declares one reference list ([bibliography] "
            "single = true), but the sources still set up the SI's own: "
            "remove the `#show: alexandria(...)` line from paper.typ and the "
            "#bibliographyx call from si-body.typ, or drop the declaration",
            where="project.toml")]
    if si is None:
        return []
    out: list[Finding] = []
    prefix, list_prefix = si["prefix"], si["list_prefix"]
    if prefix is None:
        out.append(Finding(
            "si-bibliography-prefix", "error",
            f"si-body.typ sets its own reference list with #bibliographyx("
            f"prefix: {list_prefix!r}), but paper.typ has no matching "
            f'`#show: alexandria(prefix: "{list_prefix}", read: p => read(p))`, '
            f"so no citation can reach it",
            subject=str(list_prefix), where="paper.typ"))
        return out
    if list_prefix is None:
        out.append(Finding(
            "si-bibliography-prefix", "error",
            f"paper.typ routes @{prefix}... citations to an Alexandria "
            f"bibliography, but si-body.typ has no #bibliographyx call to "
            f"print one",
            subject=prefix, where="si-body.typ"))
        return out
    if prefix != list_prefix:
        out.append(Finding(
            "si-bibliography-prefix", "error",
            f"paper.typ routes @{prefix}... to the SI list but si-body.typ "
            f"prints one for @{list_prefix}...; the two prefixes must match",
            subject=prefix, where="si-body.typ"))
        return out

    bibs = sorted(r.glob("*.bib"))
    try:
        known = {e["_key"] for b in bibs for e in _bib_entries(b)}
    except (OSError, ValueError):
        return out                      # check_bibliography reports the parse
    src = (r / si["file"]).read_text()
    code = mask(src, strings=True)
    for m in re.finditer(r"(?<![\w\\:./-])" + typst_prose.CITE, mask(src)):
        if not code[m.start():m.start() + 1].strip():
            continue                    # inside a string, not a citation
        key = m.group(0)[1:]
        if key.startswith(prefix) or key not in known:
            continue
        out.append(Finding(
            "misrouted-citation", "error",
            f"@{key} in the SI has no {prefix!r} prefix, so it prints in the "
            f"MAIN reference list, not the SI's own; write @{prefix}{key}",
            subject=key, where="SI",
            context=f'{si["file"]}:{src.count(chr(10), 0, m.start()) + 1}'))
    return out


# The rules a SLIDE is held to, and only these.
#
# Slide text is fragments: a bullet has no terminal punctuation, so
# readability's sentence splitter reads a whole slide as one enormous
# "sentence". Every rule that judges sentences therefore misfires on a deck --
# long-sentence on a bullet list, opener-run on the parallel verbs that make a
# list readable, unexpanded-acronym on the shorthand a talk is allowed. Those
# rules are not relaxed for slides; they are simply not asked.
#
# What is left is the three that are about correctness rather than style, plus
# the one that keeps a number on a slide tied to the analysis the paper's
# number came from. That last is the reason any of this runs at all: a talk
# quoting 2.1-fold while the paper says 2.07-fold is the failure slides in this
# pipeline exist to prevent.
SLIDE_RULES = ("em-dash", "british-spelling", "doubled-word", "derivable-number")


def check_slides(sources: dict[str, str],
                 cfg: Config | None = None) -> list[Finding]:
    """SLIDE_RULES over each deck. `sources` maps path -> Typst source.

    Runs the EXISTING check() and check_derivable_numbers() and filters their
    output, rather than reimplementing four rules. That is the point: the rule
    ids, subjects, vocabularies and severities are the same objects, so
    `[allow].british-spelling`, `[severity].em-dash` and `[disable]` in
    prose-check.toml apply to a slide exactly as they apply to the paper, with
    nothing to keep in step and no new ids to document.

    Not called from main(): `just prose-check`, and therefore `just verify`,
    never looks at slides/. `just slides-check` asks.
    """
    cfg = Config() if cfg is None else cfg
    out: list[Finding] = []
    for label, src in sorted(sources.items()):
        out += [f for f in check(label, readability.clean(src),
                                 readability.clean(no_code(src)),
                                 readability.clean(src, gap=GAP), cfg)
                if f.rule in SLIDE_RULES]
    out += [f for f in check_derivable_numbers(sources)
            if f.rule in SLIDE_RULES]
    return out


def check_bibliography(root: Path | None = None,
                       cfg: Config | None = None, *, bib_paths=None,
                       cited_keys: set[str] | None = None) -> list[Finding]:
    """Checks on references.bib, the last artifact here nothing read.

    Typst already fails on a citation with no entry, so that direction is
    covered. The reverse is not: an entry nobody cites survives every rebuild,
    and so does the same paper entered twice under two keys, which is how a
    manuscript ends up citing one work inconsistently.

    Deliberately NOT a duplicate-title check. Tried against a real bibliography,
    it flagged a dataset and the preprint describing it, which share a title and
    are correctly cited as two things. Duplicate DOI is the signal that means
    what it looks like.

    Everything here is offline. Checking that a DOI resolves, or that a cited
    paper has been retracted, needs the network and lives in `just bib-audit`.
    """
    import datetime

    r = root or ROOT
    bibs = sorted(r.glob("*.bib")) if bib_paths is None else list(bib_paths)
    if not bibs:
        return []
    try:
        entries = [e for b in bibs for e in _bib_entries(b)]
    except (OSError, ValueError) as exc:
        return [Finding("bibliography-parse", "error", str(exc))]
    if not entries:
        return []

    cited: set[str] = set() if cited_keys is None else cited_keys
    if cited_keys is None:
        for src in sorted(r.glob("*.typ")):
            cited |= set(re.findall(r"@([A-Za-z0-9_:-]+)", src.read_text()))
        # A work cited only in the SI is written @si-key, and the entry it
        # refers to is `key`. Without this every SI-only reference reads as
        # uncited -- the warning that says "delete this, nothing prints it".
        si = si_bibliography(r)
        prefix = (si or {}).get("prefix")
        if prefix:
            cited |= {k[len(prefix):] for k in cited if k.startswith(prefix)}

    out: list[Finding] = []
    where = bibs[0].name

    by_doi: dict[str, list[str]] = {}
    for e in entries:
        if e.get("doi"):
            by_doi.setdefault(_normalize_doi(e["doi"]), []).append(e["_key"])
    for doi, keys in sorted(by_doi.items()):
        if len(keys) > 1:
            out.append(Finding(
                "duplicate-reference", "error",
                f"{' and '.join(sorted(keys))} share the DOI {doi}, so the same "
                f"work is in the bibliography twice and will be cited "
                f"inconsistently",
                subject=doi, where=where))

    next_year = datetime.date.today().year + 1
    for e in sorted(entries, key=lambda x: x["_key"]):
        key = e["_key"]
        if key not in cited:
            out.append(Finding(
                "uncited-reference", "warn",
                f"{key} is in the bibliography but never cited, so it is carried "
                f"into every rebuild and printed by nothing",
                subject=key, where=where))
        year = e.get("year", "")
        digits = re.fullmatch(r"\d{4}", year)
        modern = bool(digits) and int(year) >= DOI_ERA
        if e["_type"] in DOI_EXPECTED and not e.get("doi") and modern:
            out.append(Finding(
                "missing-doi", "warn",
                f"{key} is a {year} @{e['_type']} with no DOI; most journals now "
                f"require one for every reference that has one",
                subject=key, where=where))
        if year and (not digits or not 1500 <= int(year) <= next_year):
            out.append(Finding(
                "implausible-year", "warn",
                f"{key} has year {year!r}; expected a four-digit year no later "
                f"than {next_year}",
                subject=key, where=where))
    return out


def check_orphaned_assets(root: Path | None = None) -> list[Finding]:
    """Flag a generated table or figure that no source file mentions.

    `uncited-figure` catches the other direction: a float the manuscript defines
    but never references. This catches the one nothing can see. A table dropped
    from si-body.typ, or a figure whose `image(...)` line was rewritten, keeps
    being regenerated by `just assets` forever while appearing nowhere. It costs
    build time, it survives into the repository looking current, and every
    staleness check happily reports it up to date -- because it is. It is simply
    not in the paper.

    Matched on filename anywhere in the Typst sources rather than by parsing an
    include, so a project that reads an asset in some way this does not model
    still counts as using it. A false negative here is much cheaper than telling
    someone to delete a file the manuscript needs.

    Anything declared in assets.json is skipped, because that file answers the
    same question properly: tools/check_assets.py reports an id nothing
    references AND a file no entry claims. A filename scan cannot see either once
    the manuscript refers to assets by id -- the name never appears in the prose,
    so every declared asset would look orphaned. This rule now covers only the
    assets that are not in the manifest.
    """
    r = root or ROOT
    sources = " ".join(p.read_text() for p in sorted(r.glob("*.typ")))

    declared: set[str] = set()
    manifest = r / "assets.json"
    if manifest.is_file():
        try:
            declared = {rec.get("path") for rec
                        in json.loads(manifest.read_text()).get("values", {}).values()}
        except json.JSONDecodeError:
            pass

    out: list[Finding] = []
    for kind, folder, pattern in (("table", "si", "*.typ"),
                                  ("figure", "figures", "*")):
        d = r / folder
        if not d.is_dir():
            continue
        for f in sorted(d.glob(pattern)):
            if f.name.startswith(".") or not f.is_file():
                continue
            # stats.json is read through stats.typ by id, never by filename.
            if f.name == "stats.json":
                continue
            # Declared in assets.json: check_assets.py owns this question.
            if f.relative_to(r).as_posix() in declared:
                continue
            if f.name not in sources:
                out.append(Finding(
                    "orphaned-asset", "warn",
                    f"{folder}/{f.name} is generated but no .typ source mentions "
                    f"it, so this {kind} is rebuilt on every `just assets` and "
                    f"appears nowhere in the manuscript",
                    subject=f.name, where=folder))
    return out


def check_bypassed_assets(sources: dict[str, str],
                          assets_path: Path | None = None) -> list[Finding]:
    """Flag a generated file pulled in by filename instead of by id.

    assets.json is only trustworthy because the compile goes through it: an
    undeclared id stops the build. Writing `#image("figures/x.png")` directly
    goes around that, and the manifest quietly stops describing the manuscript.
    So this is the rule that makes the rest of the mechanism hold, and it is an
    error rather than a warning for the same reason an uncited figure is.

    Only DECLARED paths are flagged. A logo, a schematic drawn by hand, a
    photograph -- none of those come from the analysis and none belong in the
    manifest, so naming one directly is exactly right.
    """
    p = assets_path or (ROOT / "assets.json")
    if not p.is_file():
        return []
    try:
        values = json.loads(p.read_text()).get("values", {})
    except json.JSONDecodeError:
        return []
    by_path = {rec.get("path"): id for id, rec in values.items()}

    out: list[Finding] = []
    pat = re.compile(r'#?(?:image|include)\s*\(?\s*"((?:figures|si)/[^"]+)"')
    for name, src in sources.items():
        for m in pat.finditer(re.sub(r"//[^\n]*", " ", src)):
            path = m.group(1)
            id = by_path.get(path)
            if not id:
                continue          # not a declared asset; nothing to bypass
            helper = "tbl" if values[id].get("kind") == "table" else "fig"
            out.append(Finding(
                "bypassed-asset", "error",
                f"{path} is named directly, but it is a generated asset declared "
                f"as '{id}'. Reference it as {helper}(\"{id}\") so assets.json "
                f"stays the thing the manuscript actually reads",
                subject=path, where=name, context=_ctx(src, m.start())))
    return out


def check_derivable_numbers(sources: dict[str, str],
                            stats_path: Path | None = None) -> list[Finding]:
    """Flag a numeral typed into the prose that the analysis already computes.

    This is the check that makes "do not hard-code numbers" enforceable rather
    than aspirational. `#s("id")` guarantees the numbers it covers; nothing
    otherwise notices the sentence that was typed by hand and now disagrees with
    the table beside it.

    Only DISTINCTIVE values are compared: a display string with a decimal point
    or a thousands separator, or four characters or more. A declared "3" would
    otherwise match every "3" in the manuscript, and a checker whose warnings are
    mostly noise is one nobody reads.

    `#s(...)` calls are removed before the scan, so a number the prose already
    derives is not reported as if it were typed.
    """
    p = stats_path or typst_prose.STATS_JSON
    if not p.is_file():
        return []
    values = json.loads(p.read_text()).get("values", {})
    # Rendered, not read from the file, by the function render_stats uses.
    wanted = claim_rules.derivable_index(values)

    out: list[Finding] = []
    for name, src in sources.items():
        # Drop the derived calls first, then inline code (a parameter value is
        # not a result), then everything else that is not prose. A lit() that
        # names every stat it collides with (`unlike:`) is vouched at this
        # site; a plain one is not (claim_rules.drop_named_vouches).
        stripped = re.sub(typst_prose.STATS, " ", src)
        stripped = re.sub(typst_prose.CI, " ", stripped)
        stripped = claim_rules.drop_named_vouches(stripped, wanted)
        prose = readability.clean(no_code(stripped))
        for bare, ids in sorted(wanted.items()):
            for m in re.finditer(rf"(?<![\d.,]){re.escape(bare)}(?![\d.,])", prose):
                out.append(Finding(
                    "derivable-number", "warn",
                    f"'{bare}' is typed here but the analysis computes it as "
                    f"{' / '.join(ids)} -- read it with #s(\"{ids[0]}\") so the "
                    f"sentence cannot drift from the data",
                    subject=bare, where=name, context=_ctx(prose, m.start())))
    return out


def check_unaccounted_numbers(sources: dict[str, str],
                              stats_path: Path | None = None) -> list[Finding]:
    """Flag a distinctive numeral in the prose that matches NOTHING declared.

    The other half of derivable-number, and the worse case: that check catches
    a typed copy of a value the analysis computes, but a distinctive number
    matching nothing at all -- mistyped, stale from an earlier draft, or from
    a source nobody recorded -- is the least traceable number in the paper,
    and used to be the only silent one. "A number worth stating is worth
    tracing" (README) is only a fact about the pipeline if this fires.

    A warning, never an error: some numbers are legitimately literal. The path
    for each is (a) compute it -> gen_stats.py, (b) no script can -> stats.json
    with origin.by = "hand" and a note, (c) genuinely just prose -> suppress it
    in prose-check.toml with a comment. All three leave a trail, which is the
    point.

    Same distinctiveness bar as derivable-number (a decimal point, a thousands
    separator, or four-plus digits), because a flagged "3" would bury the real
    findings. Bare integers 1500-2100 are additionally skipped as probable
    years -- "since 2019" is prose, not a result -- accepting that a real
    result landing in that range slips through; the alternative flags every
    year in the background section, and a checker whose warnings are mostly
    noise is one nobody reads. Runs only when stats.json exists: the mechanism
    is optional, and without it there is nowhere to trace a number TO.
    """
    p = stats_path or typst_prose.STATS_JSON
    if not p.is_file():
        return []
    values = json.loads(p.read_text()).get("values", {})

    declared: set[str] = set()
    for rec in values.values():
        try:
            declared.add(typst_prose.display_of(rec).strip().lstrip("+-"))
        except (TypeError, ValueError):
            pass
        declared.add(str(rec.get("value")).lstrip("+-"))

    # The numeral itself. Two constraints learned from the first real
    # manuscript this ran against (dnoise, 189 findings on the first pass):
    # a letter on either side means the digits are part of an identifier
    # ("PXD070049" is an accession, not six typed results), and a comma only
    # continues the number as a thousands group -- greedy [\d,]* ate the
    # clause comma in "median 1, mean 2.67" and reported '1,'. A comma AFTER
    # the match is therefore ordinary punctuation, not a reason to reject it.
    NUM = re.compile(r"(?<![\w.,])\d+(?:,\d{3})*(?:\.\d+)?(?![\w.])")
    # A real Results section can owe dozens of numbers at once. Show enough to
    # act on and say how many more there are; a 189-line wall is a report
    # nobody reads, which this repository has written down more than once.
    SHOW = 8

    out: list[Finding] = []
    for name, src in sources.items():
        stripped = re.sub(typst_prose.STATS, " ", src)
        stripped = re.sub(typst_prose.STATS_N, " ", stripped)
        stripped = re.sub(typst_prose.CI, " ", stripped)
        # #lit("...") is the author vouching for the literal AT THIS SPOT, so
        # the wrapped occurrence is removed before the scan -- the fourth way
        # out, and the only inline one. A bare occurrence of the same value
        # elsewhere is still unvouched and still reports. check_derivable_numbers
        # drops only a lit() that names every stat it collides with (unlike:):
        # a value the analysis computes must be #s(), and a plain lit() must
        # not silence that rule.
        stripped = re.sub(typst_prose.LIT, " ", stripped)
        prose = readability.clean(no_code(stripped))
        hits: list[Finding] = []
        seen: set[str] = set()
        for m in NUM.finditer(prose):
            bare = m.group(0)
            if not ("." in bare or "," in bare or len(bare) >= 4):
                continue                  # too common to flag without noise
            if re.fullmatch(r"\d{4}", bare) and 1500 <= int(bare) <= 2100:
                continue                  # probably a year
            if bare in declared:
                continue                  # derivable-number's case, not ours
            if bare in seen:
                continue                  # one report per value per document
            seen.add(bare)
            hits.append(Finding(
                "unaccounted-number", "warn",
                f"'{bare}' matches nothing in stats.json. If the analysis "
                f"computes it, declare it in gen_stats.py; if no script can, "
                f"add it by hand with an origin note; if it is deliberate "
                f'prose, vouch for it in place with #lit("{bare}") or '
                f"suppress the value in prose-check.toml",
                subject=bare, where=name, context=_ctx(prose, m.start())))
        out += hits[:SHOW]
        if len(hits) > SHOW:
            rest = ", ".join(f.subject for f in hits[SHOW:][:12])
            out.append(Finding(
                "unaccounted-number", "warn",
                f"...and {len(hits) - SHOW} more distinctive numerals match "
                f"nothing in stats.json ({rest}{', ...' if len(hits) - SHOW > 12 else ''}). "
                f"Same three ways out for each.",
                subject=f"({len(hits) - SHOW} more)", where=name))
    return out


def check_todos(sources: dict[str, str]) -> list[Finding]:
    """Unresolved #todo() notes, surfaced by the gate rather than only by the
    build. `just paper` PANICS on one -- that is the enforcement -- but verify
    rebuilds nothing, so without this a note is invisible until the next real
    build fails on it. A warning, because the draft workflow lives with open
    notes on purpose; the panic is what stops one from shipping."""
    out: list[Finding] = []
    for name, src in sources.items():
        for m in re.finditer(typst_prose.TODO, src):
            out.append(Finding(
                "unresolved-todo", "warn",
                f"#todo({m.group(1)!r}) is unresolved -- `just paper` will "
                f"refuse to build until it is deleted",
                subject=m.group(1)[:40], where=name))
    return out


# A list item: `- ` (bulleted) or `+ ` (numbered) opening a line.
LIST_ITEM = re.compile(r"(?m)^[ \t]*([-+])[ \t]+(\S+(?:[ \t]+\S+)?)")


def check_house_style(sources: dict[str, str]) -> list[Finding]:
    """Lists and bold in running prose, for a house style that forbids them.

    Opt-in (`enable` in prose-check.toml): some journals want every list turned
    into connected prose and bold kept off emphasis, and the rest do not care.
    Judged on the RAW source, because lists and bold are exactly the markup
    readability.clean() has already unwrapped by the time check() sees the text.

    Bold survives in two places: a span alone on its line, and a run-in label
    opening a line and ending in a period or colon (`*Early stopping.* It
    halts when...`), which is a paragraph's mini-heading, not emphasis. A
    genuinely tabular enumeration in the SI earns an [allow] entry.
    """
    out: list[Finding] = []
    for name, src in sources.items():
        body = re.sub(r"(?m)^\s*//.*$", " ", src)
        body = re.sub(r"```.*?```", " ", body, flags=re.S)
        # Math: a display equation broken so a line opens with "- x" is not a
        # list, and `a * b` inside it is not bold.
        body = re.sub(r"(?<!\\)\$[^$]*(?<!\\)\$", " ", body)
        for opener in ("#raw(", "#figure(", "#table("):
            body = typst_prose.strip_balanced(body, opener)

        for m in LIST_ITEM.finditer(body):
            kind = "bulleted" if m.group(1) == "-" else "numbered"
            out.append(Finding(
                "list-in-prose", "error",
                f"{kind} list item in running prose; write it as sentences",
                subject=m.group(2), where=name,
                context=_ctx(body, m.start())))

        for m in re.finditer(typst_prose.markup("*"), body):
            start = body.rfind("\n", 0, m.start()) + 1
            end = body.find("\n", m.end())
            line = body[start:end if end >= 0 else len(body)]
            opens_line = not body[start:m.start()].strip()
            if line.strip() == m.group(0).strip():
                continue                          # alone on its line
            if opens_line and m.group(1).rstrip().endswith((".", ":")):
                continue                          # run-in paragraph label
            text = " ".join(m.group(1).split())[:40]
            out.append(Finding(
                "bold-in-prose", "error",
                f"bold {text!r} in running prose; let word order carry the "
                f"emphasis",
                subject=text, where=name, context=_ctx(body, m.start())))
    return out


def check_structure(sources: dict[str, str]) -> list[Finding]:
    """Checks that need the Typst source rather than the extracted prose.

    A figure or table nobody points to is the one defect here with no honest
    defence: most journals require every one to be cited in the text, in order,
    and a reader who is never sent to a figure will not look at it. So that is an
    error. Undefined acronyms are a warning, because deciding what counts as
    common knowledge in a given field is not something this script can do.
    """
    out: list[Finding] = []
    joined = "\n".join(sources.values())

    labels, refs = {}, set()
    for name, src in sources.items():
        # Definitions only -- see DEFINITION. A bare-label scan also matched
        # every `#ref(<fig:x>)`, attributing a float to whichever document cited
        # it first rather than to the one that contains it.
        for m in DEFINITION.finditer(src):
            labels.setdefault(m.group(1), name)
    for m in re.finditer(rf"@({FLOAT}:[A-Za-z0-9_-]+)", joined):
        refs.add(m.group(1))
    for m in re.finditer(rf"#refn?\(\s*<({FLOAT}:[A-Za-z0-9_-]+)>", joined):
        refs.add(m.group(1))

    for label, where in sorted(labels.items()):
        if label not in refs:
            kind = {"fig": "figure", "tbl": "table", "tab": "table",
                    "eq": "equation"}[label.split(":")[0]]
            out.append(Finding(
                "uncited-figure", "error",
                f"{kind} <{label}> is never referenced in the text "
                f"(most journals require every figure and table to be cited)",
                subject=label, where=where))

    out += check_reference_order(sources)
    out += check_cross_reference_order(sources)
    out += check_unreached_si_sections(sources)

    # An acronym used more than once but never followed by, or preceded by, a
    # parenthetical expansion anywhere in the manuscript.
    prose = re.sub(r"`[^`]*`", " ", joined)
    counts: dict[str, int] = {}
    # Hyphenated acronyms (DIA-NN, LC-MS) count as one token, not two fragments.
    for m in re.finditer(r"\b[A-Z]{2,}[0-9]*(?:-[A-Z0-9]{2,})*\b", prose):
        counts[m.group(0)] = counts.get(m.group(0), 0) + 1
    for acr, n in sorted(counts.items()):
        if n < 2 or acr.upper() in ACRONYM_OK:
            continue
        # Counted as defined if it appears inside a parenthetical that also
        # contains ordinary words, or is itself followed by one. That covers the
        # bare "(HYE)" and the forms an author actually writes:
        # "(human, yeast and E. coli, abbreviated HYE)", "(HYE, see Methods)".
        # Requiring the bare form alone reported a defined acronym as undefined.
        esc = re.escape(acr)
        defined = (
            re.search(rf"\([^()]*\b{esc}s?\b[^()]*\)", prose)
            or re.search(rf"\b{esc}s?\s*\([A-Za-z]", prose)
        )
        if not defined:
            out.append(Finding(
                "unexpanded-acronym", "warn",
                f"{acr!r} used {n}x but never expanded", subject=acr))

    return out


def project_sources(root: Path | None = None) -> tuple[dict[str, str], list[Finding]]:
    """The extra hand-written sources project.toml declares ([sources] typst).

    A reviewer-response letter or a shared macro file gets the sentence rules
    and the #todo check, and nothing that assumes a manuscript half: its
    "line 212" and "Reviewer 2" are not results to trace, and it has no
    figures, sections or reference list of its own. See docs/hooks.md.
    """
    from project_hooks import typst_sources
    r = root or ROOT
    try:
        names = typst_sources(r)
    except (OSError, ValueError) as exc:
        return {}, [Finding("project-config", "error", str(exc), where="project.toml")]
    return {name: (r / name).read_text() for name in names}, []


def claim_checks(root: Path, cfg: Config, sources: dict[str, str]
                 ) -> tuple[list[Finding], frozenset[str]]:
    """Wording held to the numbers, the claim registry, the cover letter (5.0.0).

    The letter restates the paper's results to an editor and drifted from them
    in practice (spectrl 96c13b8), so it gets the sentence and number rules
    too. Its findings are capped at warnings unless project.toml's [prose]
    cover_letter says "error" (or "off"); the second value names what to cap.
    """
    from project_hooks import load as load_project
    stats = root / "stats.json"
    found = claim_rules.claim_findings(sources, stats)
    found += claim_rules.check_retired_claims(root)
    try:
        mode = load_project(root).cover_letter
    except (OSError, ValueError):
        mode = "warn"            # project.toml's own error is reported elsewhere
    letter = root / claim_rules.COVER
    if mode == "off" or not letter.is_file():
        return found, frozenset()
    src = claim_rules.cover_letter_prose(letter.read_text())
    label = claim_rules.COVER
    found += check(label, readability.clean(src), readability.clean(no_code(src)),
                   readability.clean(src, gap=GAP), cfg)
    found += check_derivable_numbers({label: src}, stats_path=stats)
    found += check_unaccounted_numbers({label: src}, stats_path=stats)
    found += claim_rules.claim_findings({label: src}, stats)
    return found, frozenset({label}) if mode == "warn" else frozenset()


def main_documents() -> int:
    """A manuscript.toml project (docs/multi-document.md): every declared part.

    Each part is checked once, inside the fewest documents that hold them all
    (document_check.covering), plus project.toml's [sources] typst files.
    """
    from document_check import covering, findings as document_findings
    from document_project import load_project

    cfg = load_config(ROOT)
    readability.add_abbreviations(sorted(cfg.vocabulary("abbreviations", set())))
    project = load_project(ROOT)
    extra, findings = project_sources()
    for label, src in extra.items():
        findings += check(label, readability.clean(src),
                          readability.clean(no_code(src)),
                          readability.clean(src, gap=GAP), cfg)
    findings += check_todos(extra)
    for doc in covering(project):
        findings += document_findings(project, doc, cfg)
    # A paper.typ + si-body.typ pair kept under manuscript.toml still gets
    # the SI routing rule; with neither file this finds nothing.
    findings += check_si_bibliography(cfg=cfg)
    claims, cap = claim_checks(ROOT, cfg, extra)
    findings += claims
    return report(list(dict.fromkeys(findings)), cfg,
                  show_suppressed="--show-suppressed" in sys.argv,
                  strict="--strict" in sys.argv, cap_warn=cap)


def main() -> int:
    if "--list-rules" in sys.argv:
        return list_rules()
    if (ROOT / "manuscript.toml").is_file():
        return main_documents()

    cfg = load_config(ROOT)
    # Before any text is split into sentences: the splitter compiles the
    # abbreviation list once, so a later addition would not take effect.
    readability.add_abbreviations(sorted(cfg.vocabulary("abbreviations", set())))
    body = readability.slice_body((ROOT / "paper.typ").read_text())
    si = (ROOT / "si-body.typ").read_text()
    targets = {"main": body, "SI": si}
    extra, findings = project_sources()

    for label, src in {**targets, **extra}.items():
        findings += check(label, readability.clean(src),
                          readability.clean(no_code(src)),
                          readability.clean(src, gap=GAP), cfg)
    findings += check_structure(targets)
    findings += check_derivable_numbers(targets)
    findings += check_unaccounted_numbers(targets)
    findings += check_todos({**targets, **extra})
    if cfg.runs("list-in-prose") or cfg.runs("bold-in-prose"):
        findings += check_house_style(targets)
    findings += check_bypassed_assets(targets)
    findings += check_orphaned_assets()
    findings += check_figure_resolution(cfg=cfg)
    findings += check_table_size(cfg=cfg)
    findings += check_bibliography(cfg=cfg)
    findings += check_si_bibliography(cfg=cfg)
    claims, cap = claim_checks(ROOT, cfg, {**targets, **extra})
    findings += claims

    rc = report(findings, cfg,
                show_suppressed="--show-suppressed" in sys.argv,
                strict="--strict" in sys.argv, cap_warn=cap)
    # Inline vouches carry no written reason, so at least the COUNT stays
    # visible: a number that quietly grows here is the same smell as a
    # suppression list nobody re-reads. A vouch that names the stats it is
    # not (`unlike:`) silences derivable-number there, so it is counted apart.
    plain, named = claim_rules.vouch_counts(targets)
    if plain:
        print(f'  {plain} numeral(s) vouched inline with #lit("...")')
    if named:
        print(f'  {named} numeral(s) vouched against named stats with '
              f'#lit("...", unlike: ...)')
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
