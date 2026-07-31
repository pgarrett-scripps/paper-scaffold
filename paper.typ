// =============================================================================
// Manuscript skeleton. Edit config.typ for the title/authors/abstract, then
// replace the placeholder sections below with real prose.
//
// DO NOT delete the "BODY START" / "BODY END" marker comments. Three separate
// tools slice the prose out of this file at those markers -- the word counter,
// the readability report, and the audiobook narrator -- and each fails loudly
// rather than guessing if they go missing.
//
// The docx-mode machinery in this preamble is load-bearing for `just docx` and
// is inert on the PDF path. Read the comments before changing it.
// =============================================================================

#import "@preview/arkheion:0.1.0": arkheion, arkheion-appendices
#import "config.typ": *

// Word-export path (`just docx`): compiling with --input docx=true bypasses the
// arkheion template. Its front matter and heading styling are built from layout-only
// primitives (page/pad/line/block) that Typst's HTML export discards, which silently
// drops every section heading and the abstract. In docx mode we skip the template and
// emit plain front matter instead, so headings survive as real <h2>/<h3> elements.
// With the flag absent this is inert and the PDF is byte-for-byte unchanged.
#let docx-mode = sys.inputs.at("docx", default: "") == "true"

#let _template = arkheion.with(
  title: paper-title,
  authors: paper-authors,
  abstract: paper-abstract,
  keywords: paper-keywords,
  date: paper-date,
)

// Apply the template for PDF; in docx mode pass the document through untouched.
#show: if docx-mode { doc => doc } else { _template }

// arkheion normally supplies heading numbering; without it the `@sec:` cross-references
// fail to resolve, so restore it on the docx path only. The SI's own "S1"-style
// numbering is set later in the file and still overrides this for the appendix.
#set heading(numbering: "1.") if docx-mode

// Typst's HTML export drops equations outright, which would gut any sentence built
// around inline math. html.frame keeps each one as an SVG that typst2docx.py then
// rasterizes back inline. Identity on the PDF path, so print output is unchanged.
#show math.equation: it => if docx-mode { html.frame(it) } else { it }

// Front matter for the Word/HTML path only (the template would normally supply it).
// The author line comes from config.typ, built from the same author list the PDF
// template uses, so the superscript affiliation markers cannot drift.
#if docx-mode {
  text(17pt, weight: "bold", paper-title)
  parbreak()
  text(11pt, paper-author-line)
  parbreak()
  for (i, affil) in paper-affiliations.enumerate() {
    text(9pt, style: "italic", super(str(i + 1)) + " " + affil)
    linebreak()
  }
  parbreak()
  text(10pt, strong("Abstract.") + " " + paper-abstract)
  parbreak()
  text(9pt, strong("Keywords: ") + paper-keywords.join(", "))
}

// Print just a cross-reference's number (e.g. "3") with no "Figure"/"Table"/
// "Section" prefix, for enumerations like "Figures 2 and 3".
#let refn(l) = ref(l, supplement: none)

// >>> BODY START -- everything from here to BODY END is counted as prose and narrated.

= Introduction

This paragraph exists so that the pipeline has something to compile, count,
narrate, and check. Replace it. What matters is that the sections below use
every construct the surrounding tooling treats specially, because a construct
that appears nowhere in the skeleton is a construct whose handling silently rots
until the first real manuscript trips over it.

Citations are one such construct. The word counter excludes them, the
readability report drops them, and the narrator deletes them rather than reading
a key aloud, so the skeleton carries two @lovelace1843 @hopper1952 to prove all
three still work. Cross-references are another, both the ordinary kind that
resolves to @sec:methods and the bare-number kind that prints as Section #refn(
  <sec:methods>,
) through the helper defined above.

= Methods <sec:methods>

Inline mathematics is the construct most likely to break, because Typst's HTML
export discards equations outright and the Word path only survives them by way
of the `html.frame` show rule in this file's preamble. A sentence that leans on
a symbol such as $alpha$ or a small expression such as $t_"obs" <= t_"max"$
would be gutted without it, which is exactly the failure that is easy to miss
until a co-author opens the .docx.

Display equations take a different path through the same machinery, since
`typst2docx.py` keeps anything taller than a line box as its own block rather
than stitching it back into the surrounding paragraph:

$ E = sum_(i=1)^n w_i (x_i - mu)^2 $

Block code and configuration dumps are exempt from the word count and are
skipped by the narrator, so the skeleton includes one:

```python
def example(threshold: float = 0.5) -> bool:
    return threshold > 0
```

Inline `code` terms, by contrast, are counted as ordinary words, because
journals treat a parameter name in running text as a word like any other.

= Results

Figures are excluded from the word count together with their captions, are
skipped wholesale by the narrator, and are the one asset class the staleness
checker compares byte-for-byte against an upstream analysis tree. @fig:example
is here to exercise all three.

#figure(
  image("figures/example_figure.png", width: 70%),
  caption: [
    A placeholder figure. Captions are excluded from the journal word count and
    are not narrated. This image is regenerated by
    `scripts/gen_example_figure.py` and is listed in `figures.map`, so
    `just check` will report it as stale if the upstream copy changes.
  ],
) <fig:example>

Tables behave the same way in the word count, but unlike figures they survive
the Word export as real Word tables rather than as images. @tbl:example is a
hand-written one.

#figure(
  table(
    columns: 3,
    align: (left, right, right),
    table.header([Condition], [Observed], [Expected]),
    [Control], [1.02], [1.00],
    [Treated], [2.11], [2.00],
  ),
  caption: [A hand-written table. Compare with the auto-generated one in the
    Supporting Information, which is written by a script and must never be
    edited by hand.],
) <tbl:example>

= Conclusions

Delete this section along with the rest of the placeholder prose. Keep the
preamble, the marker comments, the back matter below, and the Supporting
Information transition at the foot of this file.

// <<< BODY END

#heading(numbering: none)[Associated Content]

*Supporting Information*

The Supporting Information is appended to this document and is available free of
charge.

*Author Contributions*

Describe each author's contribution here. Replace this sentence.

*Notes*

The authors declare no competing financial interest.

#heading(numbering: none)[Acknowledgment]

Funding sources and acknowledgments go here. If any part of the work used
generative AI tooling, disclose it in this paragraph.

#bibliography("references.bib", title: [References], style: paper-bib-style)

// ===================== Supporting Information (appendix) =====================
// The SI is appended here as an appendix so the whole manuscript is a single
// compilation with one label namespace -- every @fig/@tbl/@sec resolves across
// the main text and the SI, and numbers can never drift out of sync.
// From this point on, figures and tables restart at S1, S2, ... and SI headings
// number S1, S2, ...  (page and line numbering stay continuous.)
#pagebreak()

#counter(figure.where(kind: image)).update(0)
#counter(figure.where(kind: table)).update(0)
#counter(heading).update(0)
#show figure.where(kind: image): set figure(numbering: n => "S" + str(n))
#show figure.where(kind: table): set figure(numbering: n => "S" + str(n))
#set heading(numbering: (..n) => "S" + n.pos().map(str).join("."))

// Same trap as any centred block: HTML export discards the align/block wrapper AND
// its contents, so on the Word path this whole title block vanishes and the main
// text runs straight into Section S1 with nothing marking the boundary. Emit it as
// plain content there -- a real heading, so it also lands in Word's navigation pane
// -- and keep the centred layout for the PDF.
#if docx-mode [
  #heading(level: 1, numbering: none, outlined: false)[Supporting Information]

  #text(13pt)[#paper-title]

  #text(10pt, style: "italic")[#si-authors]
] else [
  #align(center)[
    #text(15pt, weight: "bold")[Supporting Information]
    #v(2pt)
    #text(13pt)[#paper-title]
    #v(2pt)
    #text(10pt, style: "italic")[#si-authors]
  ]

  #v(1em)
]

#include "si-body.typ"
