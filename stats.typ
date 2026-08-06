// Numbers read from the analysis rather than typed into the prose.
//
// si/stats.json is written by analysis/scripts/gen_stats.py from the same data
// the generated tables and figures come from, so a sentence and the table beside
// it cannot disagree. Declaring a value there also lets it carry a guard: a
// number the prose calls an increase fails the build the day it turns negative,
// rather than shipping a sentence that reads backwards.
//
// This lives in its own file because paper.typ is not the only consumer.
// wordcount.typ slices the body out and `eval`s it with an explicit scope, so it
// needs the same helper; defining it twice is the duplication this exists to
// remove. readability.py and audio/extract_prose.py resolve the same calls in
// Python, since they read the SOURCE rather than the compiled PDF.
//
// Usage:  #import "stats.typ": s
//         ... rose by #s("effect.treated_over_control") points ...
//
// Delete this file, si/stats.json and gen_stats.py if the project has no numbers
// worth generating. Nothing else depends on them.

#let paper-stats = json("si/stats.json")

// Look up one declared value. Panics at compile time on an unknown id, so a
// number that stops existing fails the build instead of rendering blank.
#let _entry(id) = {
  if type(paper-stats) != dictionary or "values" not in paper-stats {
    panic("si/stats.json has no `values` table; regenerate it with `just assets`")
  }
  if id not in paper-stats.values {
    panic("si/stats.json has no value '" + id + "'. Declare it in "
      + "analysis/scripts/gen_stats.py, or fix the id.")
  }
  paper-stats.values.at(id)
}

// The display string: already rounded, by the rule set next to the analysis.
#let s(id) = _entry(id).display

// The raw value, for arithmetic or a comparison in the document. Prefer `s` for
// anything a reader sees, so rounding stays in one place.
#let n(id) = _entry(id).value

// The unit, if one was declared. Kept separate from the display string so the
// prose owns spacing and placement.
#let s-unit(id) = _entry(id).unit
