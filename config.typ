// =============================================================================
// FILL THIS IN. Everything project-specific about the manuscript lives here.
//
// This is the single source of truth for the manuscript's identity. paper.typ
// imports it for the PDF and the Word front matter, wordcount.typ counts the
// abstract out of it, and audio/config.py reads the title straight out of this
// file so the narration can never announce a title the paper no longer has.
//
// Nothing below this block should need editing to start a new paper.
// =============================================================================

#let paper-title = "A Scaffold for Writing Papers in Typst"

// Short form used on the audiobook cover art. Keep it to a couple of words.
#let paper-wordmark = "scaffold"

// Shown under the wordmark on the cover; \n breaks the line.
#let paper-cover-subtitle = "A Reusable Typst Manuscript\nand Build Pipeline"

#let paper-authors = (
  (
    name: "Ada Lovelace",
    email: "ada@example.edu",
    affiliation: "Department of Analytical Engines, Example University, 1 Example Way, Exampleton, EX 00000, USA",
  ),
  (
    name: "Grace Hopper",
    email: "grace@example.edu",
    affiliation: "Department of Compilers, Example University, 1 Example Way, Exampleton, EX 00000, USA",
  ),
)

#let paper-keywords = ("typst", "manuscript", "reproducibility", "scaffold")

#let paper-date = "January 2026"

// Shown on the audiobook cover under the author line.
#let paper-institution = "Example University"

// The bibliography style. Typst ships CSL styles by name, e.g.
// "american-chemical-society", "ieee", "nature", "apa".
#let paper-bib-style = "american-chemical-society"

// The abstract. Kept as its own binding, rather than inline in the template
// call, because three separate consumers slice it out of this file by name: the
// Word export path, the word counter (journals cap the abstract separately), and
// the audiobook narrator.
#let paper-abstract = [
  This document is a working skeleton, not a paper. It exercises every Typst
  construct the surrounding build pipeline depends on, so that a fresh clone can
  be compiled, exported to Word, narrated, and staleness-checked before a single
  real sentence has been written. Replace this abstract, delete the placeholder
  sections in paper.typ and si-body.typ, and keep the machinery. The skeleton
  deliberately includes one figure, one display equation, one inline equation,
  one table, one auto-generated Supporting Information table, two citations, and
  one cross-reference, because each of those is a construct that some part of
  the toolchain handles specially and would otherwise go untested until the
  manuscript was already long.
]

// -----------------------------------------------------------------------------
// Derived values. Nothing to edit below here.
// -----------------------------------------------------------------------------

// Unique affiliations in first-appearance order, so the Word front matter can
// number them the way the PDF template does. Deriving this rather than typing a
// second author line by hand removes the drift that a duplicated list invites.
#let paper-affiliations = {
  let seen = ()
  for a in paper-authors {
    if a.affiliation not in seen { seen.push(a.affiliation) }
  }
  seen
}

#let affiliation-number(affil) = (
  paper-affiliations.position(x => x == affil) + 1
)

// "Ada Lovelace^1, Grace Hopper^2" for the Word front matter, which has no
// template to build an author line for it. Derived rather than retyped, so the
// superscript markers cannot drift out of step with the PDF.
// Wrapped in a code block because a method chain broken across lines after
// `#let x =` would otherwise end at the first newline.
#let paper-author-line = {
  paper-authors
    .map(a => a.name + super(str(affiliation-number(a.affiliation))))
    .join(", ")
}

// Generational and post-nominal suffixes, so a surname lookup does not return
// "III" for "John R. Yates III". Compared case- and period-insensitively.
#let name-suffixes = (
  "jr",
  "sr",
  "ii",
  "iii",
  "iv",
  "v",
  "phd",
  "md",
  "dphil",
  "dsc",
  "esq",
)

// The family name: the last token that is not a suffix. "John R. Yates III"
// gives "Yates". Used for the audiobook artist tag and the cover art.
#let surname-of(full) = {
  let parts = full.split(" ").filter(p => p.trim() != "")
  let i = parts.len() - 1
  while i > 0 and lower(parts.at(i).replace(".", "")) in name-suffixes {
    i -= 1
  }
  parts.at(i)
}

// "Lovelace, Hopper" -- used as the audiobook artist tag and on the cover.
#let paper-surnames = paper-authors.map(a => surname-of(a.name))

// Restated on the Supporting Information title page.
#let si-authors = paper-authors.map(a => a.name).join(", ")
