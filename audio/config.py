#!/usr/bin/env python3
"""Narration configuration. Everything project-specific about the audiobook.

The identity of the manuscript (title, authors, institution, cover wordmark) is
NOT duplicated here. It is read out of ../config.typ, because hardcoding a title
in the narrator is exactly how a finished audiobook ends up announcing a title
the paper no longer has. Only genuinely audio-specific settings live below.

Edit the FILL THIS IN block. The reader at the bottom needs no changes.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# =============================================================================
# FILL THIS IN
# =============================================================================

# Piper voice. `just audio-setup` resolves this name against piper's own voice
# index and downloads it; browse the options at
# https://huggingface.co/rhasspy/piper-voices
#
# The name alone is enough. There used to be a second setting here holding the
# path under the voices repo ("en/en_US/lessac/medium"), because setup built a
# download URL by hand -- so the two had to be kept in step, and a mismatch
# arrived as a 404 that read like a network problem.
VOICE_NAME = "en_US-lessac-medium"

YEAR = "2026"
GENRE = "Audiobook"

# Blurbs written into the .m4b metadata. Keep them to a couple of sentences.
MAIN_DESC = (
    "Audiobook narration of the manuscript. Prose only; figures, tables, and "
    "block code are omitted. Narrated with Piper text-to-speech."
)
SI_DESC = (
    "Audiobook narration of the Supporting Information. Prose sections only "
    "(tables and figures omitted). Narrated with Piper text-to-speech."
)

# Words the voice mangles. Regex -> what to say instead. Applied to the title and
# to the body. A coined name, an acronym meant to be spelled out, and any term
# whose spelling defeats the phonemizer belong here.
#   r"\bdnoise\b": "d noise"        (a nonword the voice runs together)
#   r"\bLC-MS/MS\b": "L C mass spec"
PRONUNCIATION: dict[str, str] = {}

# Inline math, verbatim as it appears in the source, mapped to spoken English.
# Longest keys are applied first, so a specific expression can override a general
# one. Anything left over has its dollar signs stripped and is read as-is, which
# is usually wrong for real equations, so add every equation that appears in
# running prose. Display equations are dropped rather than read.
MATH: dict[str, str] = {
    r"$m/z$": "m slash z",
    r"$alpha$": "alpha",
    r'$t_"obs" <= t_"max"$': "t observed is at most t max",
}

# Typst symbol tokens. These are generic; extend rather than replace.
SYM: dict[str, str] = {
    r"#sym.minus": "minus ",
    r"#sym.plus.minus": "plus or minus ",
    r"#sym.gt.eq": "greater than or equal to ",
    r"#sym.lt.eq": "less than or equal to ",
    r"#sym.dash.en": "to ",
    r"#sym.tilde": "approximately ",
    r"#sym.space": " ",
    r"#sym.times": "times ",
    r"#sym.arrow.r": "to ",
    r"#sym.arrow.l": "from ",
    r"#sym.arrow.lr": "versus ",
}

# Cover art palette. The default is a dark slate with a cyan accent.
COVER_BG = "#0d1b2a"
COVER_ACCENT = "#38bdf8"
COVER_ACCENT2 = "#5eead4"
COVER_FG = "#f8fafc"
COVER_MUTED = "#94a3b8"

# =============================================================================
# Derived from ../config.typ. Nothing to edit below here.
# =============================================================================

HERE = Path(__file__).resolve().parent
PAPER_DIR = HERE.parent
CONFIG_TYP = PAPER_DIR / "config.typ"
PAPER_TYP = PAPER_DIR / "paper.typ"
SI_TYP = PAPER_DIR / "si-body.typ"

_cfg = CONFIG_TYP.read_text() if CONFIG_TYP.exists() else ""


def typst_str(name: str) -> str:
    """Read a `#let <name> = "..."` binding out of config.typ, or fail loudly."""
    m = re.search(rf'#let\s+{re.escape(name)}\s*=\s*"([^"]*)"', _cfg)
    if not m:
        sys.exit(f'error: could not find `#let {name} = "..."` in {CONFIG_TYP}')
    return m.group(1)


def _author_names() -> list[str]:
    """Every `name: "..."` inside the paper-authors block, in order."""
    m = re.search(r"#let\s+paper-authors\s*=\s*\((.*?)\n\)", _cfg, re.S)
    if not m:
        sys.exit(f"error: could not find `#let paper-authors = (...)` in {CONFIG_TYP}")
    return re.findall(r'name:\s*"([^"]+)"', m.group(1))


def speakable(text: str) -> str:
    """Apply the pronunciation fixes to a piece of text."""
    for pattern, spoken in PRONUNCIATION.items():
        text = re.sub(pattern, spoken, text)
    return text


TITLE = typst_str("paper-title")
WORDMARK = typst_str("paper-wordmark")
COVER_SUBTITLE = typst_str("paper-cover-subtitle").replace("\\n", "\n")
INSTITUTION = typst_str("paper-institution")

# Generational and post-nominal suffixes, so the family name of
# "John R. Yates III" is "Yates" and not "III". Kept in step with `name-suffixes`
# in config.typ, which does the same job for the PDF side.
NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "phd", "md", "dphil",
                 "dsc", "esq"}


def surname_of(full: str) -> str:
    """The family name: the last token that is not a suffix."""
    parts = full.split()
    i = len(parts) - 1
    while i > 0 and parts[i].lower().replace(".", "") in NAME_SUFFIXES:
        i -= 1
    return parts[i]


AUTHOR_NAMES = _author_names()
SURNAMES = [surname_of(n) for n in AUTHOR_NAMES]
AUTHOR = ", ".join(SURNAMES)                 # .m4b artist tag
COVER_AUTHORS = "  ·  ".join(SURNAMES)  # "Lovelace · Hopper"

SI_TITLE = f"{TITLE}: Supporting Information"


def spoken_title() -> str:
    """The title read aloud: pronunciation fixes applied, and punctuation that no
    voice renders as a pause turned into a sentence break."""
    title = speakable(TITLE)
    title = title.replace(":", ".").replace("–", " ").replace("-", " ")
    return re.sub(r"\s+", " ", title).strip().rstrip(".") + "."
