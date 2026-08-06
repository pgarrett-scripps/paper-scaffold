// Numbers read from the analysis rather than typed into the prose.
//
// stats.json is a file YOU own that the analysis contributes to. Each entry
// records `origin.by`: the script that generated it, or "hand" for one you typed
// in yourself with a note saying where it came from. A generator replaces only
// its own entries, so `just assets` never clobbers a hand-written value, and
// `just check-stats` re-runs every guard against whatever is in the file.
//
// Most of it is written by analysis/scripts/gen_stats.py from the same data
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
// Delete this file, stats.json and gen_stats.py if the project has no numbers
// worth generating. Nothing else depends on them.

#let paper-stats = json("stats.json")

// DRAFT MODE (`just draft`, i.e. --input draft=true). An unknown id renders a
// loud placeholder instead of stopping the compile.
//
// The case this exists for: renaming a value mid-draft breaks every call site at
// once, and until the last one is fixed there is no PDF at all -- not even to
// read the paragraph you were in the middle of writing. Draft mode keeps the
// document compiling while the ids are in flux.
//
// It writes paper-draft.pdf, never paper.pdf, so a placeholder cannot reach a
// PDF anyone would mistake for the real one. That is why this needs no
// interaction with `just check`.
#let draft-mode = sys.inputs.at("draft", default: "") == "true"

#let _missing(id) = {
  if not draft-mode {
    panic("stats.json has no value '" + id + "'. Declare it in "
      + "analysis/scripts/gen_stats.py, or add it to stats.json by hand with "
      + "origin.by = \"hand\" and a note. Or fix the id. "
      + "To keep writing with it unresolved: just draft")
  }
  none
}

#let _entry(id) = {
  if type(paper-stats) != dictionary or "values" not in paper-stats {
    panic("stats.json has no `values` table; regenerate it with `just assets`")
  }
  if id not in paper-stats.values {
    _missing(id)
  } else {
    paper-stats.values.at(id)
  }
}

// The display string: already rounded, by the rule set next to the analysis.
// In draft mode an unknown id becomes a placeholder that is hard to overlook and
// trivial to grep for.
#let s(id) = {
  let e = _entry(id)
  if e == none {
    box(fill: yellow, inset: (x: 2pt), text(fill: red, weight: "bold", "?" + id + "?"))
  } else {
    e.display
  }
}

// The raw value, for arithmetic or a comparison in the document. Prefer `s` for
// anything a reader sees, so rounding stays in one place.
//
// This panics even in draft mode. There is no placeholder that can stand in for
// a number inside an expression: substituting zero would let a comparison or a
// sum quietly produce a wrong answer, which is worse than not compiling.
#let n(id) = {
  if id not in paper-stats.values {
    panic("stats.json has no value '" + id + "', and `n` cannot be drafted "
      + "around: a placeholder number would make the arithmetic that reads it "
      + "silently wrong. Declare it, or use `s` if the value is only displayed.")
  }
  paper-stats.values.at(id).value
}

// The unit, if one was declared. Kept separate from the display string so the
// prose owns spacing and placement.
#let s-unit(id) = {
  let e = _entry(id)
  if e == none { "" } else { e.unit }
}
