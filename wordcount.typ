// Journal-style word-count driver for the manuscript.
//
// Reports the abstract, the main text, and the Supporting Information
// separately (with a main+SI total), counting only the parts that count toward
// a journal word limit. The abstract is reported on its own line because
// journals cap it under a separate limit; it is NOT part of the main+SI total.
//
// EXCLUDED (not counted): the title / author / affiliation block; the reference
// list and all in-text citations; figures, tables, and their captions; images;
// math / equations; and block code + config dumps (```...``` fences and
// `#raw(..., block: true)`). INCLUDED: body prose, section headings, and inline
// `code` terms (e.g. parameter names), which journals treat as ordinary words.
//
// Read the numbers with `wordcount.sh` (or `just wordcount`), which pulls the
// `<wc>` metadata out with `typst query`. Compiling this file directly also
// renders a small summary table.
//
// The main text lives inline in paper.typ, so it is sliced out between the
// BODY START / BODY END marker comments and evaluated as content; it is never
// laid out, so its cross-references and citations into the SI do not need to
// resolve. The SI is the standalone appendix body si-body.typ.

#import "@preview/wordometer:0.1.4": word-count-of
#import "config.typ": paper-title, paper-abstract

// Helper used inside the main text (defined in paper.typ's preamble); injected
// into the eval scope so the sliced body evaluates.
#let refn(l) = ref(l, supplement: none)

// The generated-number lookup, same as paper.typ imports. Injected below for the
// same reason as refn: the sliced body calls it, and an eval scope missing a
// helper fails the whole count rather than just that number.
#import "stats.typ": lit, n, s, todo

// The generated-asset lookup, for the same reason again: the sliced body calls
// fig() for every generated figure, and an eval scope missing it fails the whole
// count with `unknown variable: fig` pointing at the slice rather than at the
// figure. Imported under other names because `fig`/`tbl` would collide with the
// per-file word-count locals below.
#import "assets.typ": fig as asset-fig, tbl as asset-tbl

#let src = read("paper.typ")
#let start-m = src.match(regex("(?m)^// >>> BODY START.*$"))
#let end-m = src.match(regex("(?m)^// <<< BODY END.*$"))
#assert(
  start-m != none and end-m != none,
  message: "paper.typ is missing the `// >>> BODY START` / `// <<< BODY END` "
    + "marker comments; the word counter cannot tell prose from front/back matter.",
)
#let main-body = eval(
  src.slice(start-m.end, end-m.start),
  mode: "markup",
  scope: (refn: refn, s: s, n: n, lit: lit, todo: (msg) => none, fig: asset-fig, tbl: asset-tbl),
)
#let si-body = include "si-body.typ"

// wordometer already ignores citations, references, equations, images, and
// metadata by default; we additionally drop whole figures (caption + table +
// image) and block code / config dumps, while keeping inline `code`.
#let excludes = (figure, raw.where(block: true))
#let a = word-count-of(paper-abstract, exclude: excludes)
#let m = word-count-of(main-body, exclude: excludes)
#let s = word-count-of(si-body, exclude: excludes)

#metadata((
  abstract_words: a.words, abstract_chars: a.characters,
  main_words: m.words, main_chars: m.characters,
  si_words: s.words, si_chars: s.characters,
  total_words: m.words + s.words, total_chars: m.characters + s.characters,
)) <wc>

#set page(width: 13cm, height: auto, margin: 1.2cm)
#set text(11pt)
#align(center)[*#paper-title*]
#align(center)[_word count_]
#v(4pt)
#table(
  columns: (1fr, auto),
  align: (left, right),
  stroke: (x, y) => if y == 0 { (bottom: 0.6pt) },
  table.header([*Section*], [*Words*]),
  [Abstract], [#a.words],
  [Main text], [#m.words],
  [Supporting Information], [#s.words],
  [*Total (main + SI)*], [*#{ m.words + s.words }*],
)
#v(4pt)
#text(8pt, fill: gray)[Excludes references, citations, figures/tables and their
captions, math, images, and block code. Includes headings and inline `code`.]
