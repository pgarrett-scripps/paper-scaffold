// Example dissertation template; adapt to institutional requirements.
//
// Implements the layout required by the example layout:
//   - 1" margins on all sides
//   - double-spaced, 11pt Liberation Serif
//   - page numbers bottom-right, contiguous: Roman numerals on the front
//     matter (title + copyright), Arabic starting at 1 from the Abstract
//
// Per-chapter bibliographies are provided by the `alexandria` package. Each
// chapter cites with its own prefix and ends with its own reference list.

#import "@preview/alexandria:0.2.0": alexandria, bibliographyx, citegroup
#import "../code.typ": code-style
#import "chapters.typ": *
#import "supplements.typ": *

// The project font directory is supplied through TYPST_FONT_PATHS by just.
// Do not silently substitute a different running-text font.
#let body-font = "Liberation Serif"
#let sans-font = "Liberation Sans"

#let inclusion-confirmed = [All co-authors agreed that this work may be
  included in this dissertation.]

// ---------------------------------------------------------------------------
// Main document wrapper. Renders the title page, copyright page, and abstract,
// then the chapter `body`.
// ---------------------------------------------------------------------------
#let dissertation(
  title: "[TODO: Dissertation Title]",
  author: "[TODO: Full Legal Name]",
  year: datetime.today().year(),
  degree: "Doctor of Philosophy",
  graduate-school: [Graduate School],
  institution: "Example University",
  location: "Example City",
  submission-date: none,
  committee: (),
  acknowledgments: none,
  abbreviations: none,
  abstract: [],
  body,
) = {
  set document(title: title, author: author)

  set page(
    paper: "us-letter",
    margin: 1in,
    numbering: "i",
    number-align: bottom + right,
  )
  set text(font: body-font, size: 11pt, lang: "en")
  // Double spacing.
  set par(leading: 1.5em, spacing: 1.5em, justify: false)
  set heading(numbering: none)
  show ref: chapter-reference
  show: code-style

  // Legends: single-spaced 9 pt, below figures and above tables
  // (the example layout, "Figures" and "Tables").
  show figure.caption: set text(size: 9pt)
  show figure.caption: set par(leading: 0.65em, spacing: 0.65em)
  show figure.where(kind: table): set figure.caption(position: top)

  // ----- Title page (page i) -----
  set align(center)
  v(1fr)
  text(size: 14pt, weight: "bold", title)
  v(2em)
  text(size: 12pt)[
    A dissertation presented #linebreak()
    by #linebreak()
    #author #linebreak()
    to #linebreak()
    #graduate-school #linebreak()
    in partial fulfillment of the requirements #linebreak()
    for the degree of #linebreak()
    #degree #linebreak()
    for #linebreak()
    #institution #linebreak()
    #location #linebreak()
    #if submission-date != none { submission-date } else { [\[Month\] #str(year)] }
  ]
  v(1fr)
  set align(left)
  pagebreak()

  // ----- Copyright page (page ii) -----
  v(1fr)
  align(center)[#text(size: 12pt)[© #str(year) by #author #linebreak()
  All rights reserved.]]
  v(1fr)
  pagebreak()

  // ----- Front matter (Roman numerals continue): acknowledgments, table of
  // contents, lists of figures and tables, abbreviations. Mirrors the sample
  // dissertation (Lazear 2021). The guidelines require none of these but the
  // numbering split around the Abstract assumes front matter exists.
  if acknowledgments != none {
    heading(level: 1, outlined: true)[Acknowledgments]
    acknowledgments
    pagebreak(weak: true)
  }

  outline(title: "Table of Contents", depth: 2)
  pagebreak(weak: true)

  // Reuse the exact chapter declarations, so the two required locations agree.
  heading(level: 1)[Dissertation Co-Author Contributions]
  context {
    for entry in query(<chapter-contributions>) {
      let item = entry.value
      block(breakable: false)[
        #heading(level: 2, outlined: false)[Chapter #chapter-number(item.id). #item.title]
        #item.body
        #if item.inclusion != none {
          parbreak()
          text(style: "italic", item.inclusion)
        }
      ]
    }
  }
  pagebreak(weak: true)

  outline(title: "List of Figures", target: figure.where(kind: image))
  pagebreak(weak: true)

  outline(title: "List of Tables", target: figure.where(kind: table))
  pagebreak(weak: true)

  if abbreviations != none {
    heading(level: 1, outlined: true)[List of Abbreviations]
    abbreviations
    pagebreak(weak: true)
  }

  // ----- Switch to Arabic numbering, restart at 1 for the Abstract -----
  set page(numbering: "1")
  counter(page).update(1)

  // ----- Dissertation Abstract -----
  heading(level: 1, outlined: true)[Dissertation Abstract]
  abstract
  pagebreak(weak: true)

  // ----- Chapters -----
  body
  check-chapter-order()
}

// ---------------------------------------------------------------------------
// Chapter title page. Every chapter (Introduction, research chapters, and the
// Conclusion) begins with one of these.
//   - id:       stable part ID from manuscript.toml (also used by chap-ID refs)
//   - title:    chapter title
//   - authors:  author list (string or content), omitted for the Introduction
//   - citation: publication / preprint citation + DOI, if published
//   - label:    chapter-type note, e.g. "First-author manuscript"
// ---------------------------------------------------------------------------
#let chapter-title-page(
  id: none,
  title: "[TODO: Chapter Title]",
  authors: none,
  citation: none,
  label: none,
  contributions: [],
  inclusion: inclusion-confirmed,
) = {
  let number = chapter-number(id)
  pagebreak(weak: true)
  {
    show heading: none
    [#heading(level: 1, outlined: true)[Chapter #number. #title]#chapter-target(id)]
  }
  [#metadata((id: id, title: title, body: contributions, inclusion: inclusion)) <chapter-contributions>]
  // Keep the title and declaration in one compact, double-spaced title page.
  align(center)[
    #text(size: 12pt, weight: "bold")[CHAPTER #number]
    #v(0.4em)
    #text(size: 14pt, weight: "bold", title)
    #if authors != none {
      v(0.6em)
      text(size: 11pt, authors)
    }
    #if citation != none {
      v(0.7em)
      text(size: 11pt, style: "italic", citation)
    }
  ]
  v(0.8em)
  heading(level: 2, outlined: false)[Co-Author Contributions]
  contributions
  if inclusion != none {
    parbreak()
    text(style: "italic", inclusion)
  }
  pagebreak()
}

// "Contributions of Co-First Authors" statement (2-3 sentences).
// Not outlined: it belongs to the chapter title page, not the ToC.
#let cofirst-contributions(body) = {
  heading(level: 2, outlined: false)[Contributions of Co-First Authors]
  body
}

// "Co-author Contributions" section. Must describe co-author contributions
// to the Figures and Tables (the example layout). Not outlined.
#let coauthor-contributions(body) = {
  heading(level: 2, outlined: false)[Co-author Contributions]
  body
}

// Per-chapter reference list. Call at the end of a chapter with the same
// `prefix` used for that chapter's citations (e.g. `@intro-smith2020`).
#let chapter-references(bib, prefix: none) = {
  // Offset so the References heading nests under the chapter in the ToC.
  set heading(offset: 1)
  bibliographyx(bib, prefix: prefix, title: "References", style: "american-chemical-society")
}

// Standalone chapters keep dissertation typography and chapter numbering,
// with Arabic page numbers starting at 1 and no dissertation front matter.
#let chapter-document(body) = {
  set page(paper: "us-letter", margin: 1in, numbering: "1", number-align: bottom + right)
  set text(font: body-font, size: 11pt, lang: "en")
  set par(leading: 1.5em, spacing: 1.5em, justify: false)
  set heading(numbering: none)
  show ref: chapter-reference
  show: code-style
  show figure.caption: set text(size: 9pt)
  show figure.caption: set par(leading: 0.65em, spacing: 0.65em)
  show figure.where(kind: table): set figure.caption(position: top)
  body
}
