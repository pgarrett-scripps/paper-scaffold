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

// The RENDERED file, not stats.json. Typst has no format-spec and its str()
// rounds floats where Python's does not, so the strings a reader sees are built
// by tools/render_stats.py -- the only formatter in the pipeline -- and this
// reads the result. `just paper`, `just docx`, `just draft` and `just wordcount`
// all regenerate it first, so it cannot be stale.
//
// It is a build artifact and gitignored. If Typst reports it missing, the
// compile was run by hand rather than through a recipe: run `just render-stats`.
#let paper-stats = json("stats-rendered.json")

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
    panic("stats-rendered.json has no `values` table; run: just render-stats")
  }
  if id not in paper-stats.values {
    _missing(id)
  } else {
    paper-stats.values.at(id)
  }
}

// The display string: already rounded, by the rule set next to the analysis.
//
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

// A literal number the author VOUCHES for, in place. Renders as plain text;
// exists so the vouching is a statement in the source rather than an entry in
// a config file far from the sentence.
//
// The contract, from weakest claim to strongest: #lit("40") says "this literal
// is deliberate prose" and silences only the unaccounted-number warning at
// this spot. A number that deserves an explanation belongs in stats.json as a
// hand entry with a note. A number the analysis computes must be #s("id") --
// and stays flagged by derivable-number even inside lit, on purpose: vouching
// is not a bypass of the stronger rule.
//
// Takes a STRING ("2.2"), not a bare number: Typst's str() rounds floats its
// own way, and the digits a reader sees should be exactly the digits typed.
#let lit(v) = {
  if type(v) != str {
    panic("lit() takes a string, e.g. lit(\"2.2\"): Typst renders bare "
      + "numbers with its own rounding, and a vouched literal should read "
      + "exactly as typed.")
  }
  v
}

// A note to self that CANNOT ship. In draft mode it renders as a loud inline
// marker; in a real build (`just paper`, `just docx`) it PANICS, so a final
// PDF with an unresolved note in it is not producible. A `// FIXME` comment
// makes the opposite trade: silent everywhere, it survives to submission.
//
// The extractors strip it -- a note is not prose, so it is not counted,
// scored, or narrated even while drafting.
#let todo(msg) = {
  if draft-mode {
    box(fill: orange, inset: (x: 3pt, y: 1pt),
      text(fill: white, weight: "bold", size: 0.8em, "TODO: " + msg))
  } else {
    panic("unresolved #todo: \"" + msg + "\". Resolve it and delete the call, "
      + "or keep working with `just draft`. A note that could ship silently "
      + "is the reason this is not a comment.")
  }
}
