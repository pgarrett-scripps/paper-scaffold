// =============================================================================
// FILL THIS IN. Everything project-specific about the SLIDE DECKS lives here.
// The root config.typ is the manuscript's identity; this is the talks'.
//
// WHY IT IS SEPARATE. A talk is not the paper. The title is usually shorter and
// less hedged, the author line drops the affiliation superscripts that belong on
// a manuscript title block, and the date is the seminar's rather than the
// submission's. Deriving any of that from config.typ would mean editing the file
// that five manuscript tools read in order to rename a talk.
//
// It also lets a deck build in a project with no root config.typ at all, which a
// manuscript.toml project (see docs/multi-document.md) legitimately does not have:
// its front matter comes from its own template instead.
//
// THE TRADE, STATED PLAINLY. A deck can now disagree with the paper about the
// title, and nothing checks that. Numbers and figures are deliberately the
// opposite -- those still arrive by id from stats.json and assets.json, and are
// checked -- because a wrong number is a wrong claim, while a shorter title is
// just a title. If you want them locked together, say
// `#import "/config.typ": paper-title` in a deck and pass it to `deck()`.
//
// PER-DECK OVERRIDES DO NOT BELONG HERE. Every value below is a parameter of
// `deck()`, so one talk overrides it at its own call site:
//
//     #show: deck.with(title: [A shorter title], date: "12 March 2026")
//
// This file is what a deck gets when it says nothing. Reach for an override
// when one talk differs; edit this file when the project does.
// =============================================================================

#let deck-title = "A Scaffold for Writing Papers in Typst"

#let deck-subtitle = "A Reusable Typst Manuscript and Build Pipeline"

// A plain line of names. Not paper-authors: that list carries emails and
// affiliations for a manuscript title block, and their superscript markers read
// as noise under a talk title.
#let deck-authors = "Ada Lovelace, Grace Hopper"

#let deck-institution = "Example University"

// The date of the talk, not of the submission.
#let deck-date = "January 2026"

// "16-9" for a modern projector, "4-3" for the one bolted to the ceiling of the
// seminar room that has been there since 2004.
#let deck-aspect-ratio = "16-9"

// The references slide reads the manuscript's own bibliography file, so a key
// cited in a talk is a key the paper could cite. Root-relative: a deck lives one
// directory down. A project whose bibliography lives elsewhere changes it here.
#let deck-bibliography = "/references.bib"

// Typst ships CSL styles by name. A talk often wants a different one from the
// paper -- numeric citations are hard to read on a slide from the back of a
// room, so an author-date style is usually kinder.
#let deck-bib-style = "american-chemical-society"
