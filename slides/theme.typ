// =============================================================================
// SLIDE DECKS. The one place Touying is configured; every deck under slides/
// imports this file and nothing else from the package.
//
// WHAT A DECK GETS. The same declared material the manuscript uses, so a slide
// cannot quietly disagree with the paper it is about:
//
//   #s("id")            a number the analysis computed   (stats.json)
//   #fig("fig.id")      a generated figure, by id        (assets.json)
//   #tbl("tbl.id")      a generated table, by id         (assets.json)
//   @key                a citation, listed on a slide    (references.bib)
//   the title, authors, institution and date             (slides/config.typ)
//
// The first four are the manuscript's, by id, and are checked: a slide that
// restates a number gets the same number the paper prints. The identity is the
// TALKS' own, in slides/config.typ, because a talk title is usually not the
// paper title -- see that file for the reasoning and for what it costs.
//
// DECKS ARE OUTSIDE THE GATE, deliberately. A stale deck does not fail
// `just verify` or `just check`, and an unformatted one does not either: a talk
// falls behind the moment you edit a sentence, the fix costs one recompile, and
// a warning that is almost always present is one people learn to scroll past.
// Ask when you want to know: `just slides-check`. Same reasoning as `just viz`
// and the audiobooks.
//
// What IS checked, every time, because it is about correctness rather than
// currency: an id. A deck that reads `#s("effect.typo")` fails to compile, and
// `just check-stats` counts this deck as a reader of every id it does resolve,
// so a number used only in a talk stops being reported as dead.
//
// TO DELETE THE FEATURE: remove slides/, the `slides*` recipes in the justfile,
// tools/slides.py and tests/slide_cases.py. Nothing else depends on them.
// =============================================================================

#import "@preview/touying:0.6.1": *
#import themes.metropolis: *

// The decks' own identity, from the file beside this one.
#import "config.typ": (
  deck-aspect-ratio, deck-authors, deck-bib-style, deck-bibliography, deck-date,
  deck-institution, deck-subtitle, deck-title,
)

// Root-relative, because a deck lives one directory down and Typst resolves a
// leading "/" against the project root. This is also why every typst call in
// tools/slides.py passes `--root`: without it the root would be slides/ and
// each of these imports would fail.
#import "/stats.typ": lit, n, s, todo
#import "/assets.typ": fig, tbl

// Re-exported so a deck needs one import line. A deck still writes its own
// `#import "theme.typ": *`: an included file does not inherit the includer's
// imports, which is the gotcha CLAUDE.md records.
#let (
  slide,
  title-slide,
  new-section-slide,
  focus-slide,
  speaker-note,
  appendix,
  pause,
  uncover,
  only,
  alert,
) = (
  slide,
  title-slide,
  new-section-slide,
  focus-slide,
  speaker-note,
  appendix,
  pause,
  uncover,
  only,
  alert,
)

// Handout mode flattens each `#pause` group to its final state, so a deck built
// for the room prints as one page per idea instead of one page per reveal.
// Selected with `--input handout=true` (`just slides-handout <name>`), never by
// editing a deck -- the same idiom stats.typ uses for draft mode, and for the
// same reason: the file on disk must not have to change to change the output.
#let handout-mode = sys.inputs.at("handout", default: "") == "true"

// The references slide. Put it last: `#deck-references()`.
//
// Touying can instead footnote each citation on the slide that makes the claim
// (`config-common(show-bibliography-as-footnote: ...)`), which reads better in
// a talk. It is NOT used here because it is broken on this toolchain: touying
// 0.6.1 targets Typst 0.12 and recovers the entries by matching a `grid` show
// rule over the rendered bibliography, which Typst 0.14 no longer lays out that
// way. The failure is `array index out of bounds (index: 0, len: 0)` pointing
// into the package. Revisit when touying updates; the deck-side change is one
// line here and deleting the call from each deck.
//
// A deck is its own compilation, so this is the ordinary #bibliography and not
// Alexandria's. Alexandria is only needed in paper.typ, where the SI shares one
// compilation with the main text and Typst allows a single native call.
// Emits the list only; the deck supplies the slide, as `== References` above
// it. A helper that fabricated its own slide printed the heading twice, once as
// the slide title and once inside the body.
#let deck-references(
  path: deck-bibliography,
  style: deck-bib-style,
) = bibliography(path, title: none, style: style)

// The template every deck applies: `#show: deck.with(...)`.
//
// Every default comes from slides/config.typ, so a deck that passes nothing
// gets the project's talk identity, and one that differs says so at its own
// call site: `#show: deck.with(title: [Shorter], date: "12 March 2026")`.
//
// `extra-config` takes any further Touying config dictionaries a particular
// deck needs, without this file growing a parameter per talk.
#let deck(
  title: deck-title,
  subtitle: deck-subtitle,
  authors: deck-authors,
  institution: deck-institution,
  date: deck-date,
  aspect-ratio: deck-aspect-ratio,
  ..extra-config,
  body,
) = {
  show: metropolis-theme.with(
    aspect-ratio: aspect-ratio,
    // Section furniture: a progress bar in the footer, and a section slide
    // emitted by `= Heading`. Configured once here, not per deck.
    footer-progress: true,
    config-common(
      handout: handout-mode,
      new-section-slide-fn: new-section-slide,
    ),
    config-info(
      title: title,
      subtitle: subtitle,
      author: authors,
      institution: institution,
      date: date,
    ),
    ..extra-config,
  )
  body
}
