// =============================================================================
// PLACEHOLDER DECK. Replace it, the way you replace the placeholder prose in
// paper.typ. Every construct the pipeline handles specially appears once, so a
// fresh clone builds something and the wiring is visible: a figure by id, a
// number by id, a citation, a speaker note, a section slide, an appendix.
//
// Coverage of those constructs for the CHECKERS does not live here -- it lives
// in tests/slide_cases.py, which builds its own decks in a temporary root.
// This file gets deleted the moment a real talk starts, and anything relying
// on it for coverage would be tested once and never again.
//
// Build: just slides talk     Handout: just slides-handout talk
// Notes: just slides-notes talk      Check: just slides-check
// =============================================================================

#import "theme.typ": *

// The title, author line, institution, date and aspect ratio come from
// slides/config.typ. Override one here when THIS talk differs; edit that file
// when the project does.
#show: deck.with(subtitle: [A worked example])

#title-slide()

= Results

== What the analysis found

#figure(fig("fig.example", width: 68%), caption: [
  Replace this. The figure is pulled from `assets.json` by id, so regenerating
  it with `just assets` updates the talk as well as the paper.
])

Across #s("cohort.n_conditions") conditions, the treated group scored #s(
  "effect.treated_over_control",
) over control @lovelace1843.

#speaker-note[
  Thirty seconds here. Say what the comparison was before quoting the number,
  and do not read the figure axes aloud.
]

== A claim with a reveal

- The number above is read from the analysis, never typed.
#pause
- So is this one: a #s("effect.treated_fold")-fold change.
#pause
- `just slides-handout talk` flattens these reveals to one page.

== References

#deck-references()

#show: appendix

== Backup: the question you will be asked

Replace this with the slide you hope not to need. The appendix keeps the slide
counter frozen, so the footer still reads the length of the talk you gave.
