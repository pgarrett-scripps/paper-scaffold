// Figures and tables referenced by id rather than by filename.
//
// assets.json is written by the scripts in analysis/scripts/ (see _assets.py
// there for the contract). Each entry records the file's path, a hash of its
// contents, the script that produced it, and what that script read.
//
// The point of going through an id is that it makes the manifest LOAD-BEARING.
// A manifest that merely sits next to the files it describes drifts, because
// nothing reads it. This one is on the path the compile takes: an id that is not
// declared stops the build, exactly as an undeclared #s("id") does. So the
// manifest cannot quietly stop being true.
//
// Usage:  #import "assets.typ": fig, tbl
//
//         #figure(
//           fig("fig.example"),
//           caption: [What the reader needs to know.],
//         ) <fig:example>
//
// The caption and the label stay here, in the prose, because that is what they
// are. Only the path moves into the manifest.
//
// Delete this file, assets.json, and the record() calls in analysis/scripts/ if
// the project has no generated figures or tables. Nothing else depends on them.

#let paper-assets = json("assets.json")

// DRAFT MODE (`just draft`), the same bargain stats.typ makes: an unknown id
// renders a loud placeholder instead of stopping the compile, and writes only
// paper-draft.pdf, so a placeholder can never reach a file anyone mistakes for
// the finished paper.
#let assets-draft-mode = sys.inputs.at("draft", default: "") == "true"

#let _entry(id) = {
  if type(paper-assets) != dictionary or "values" not in paper-assets {
    panic("assets.json has no `values` table; regenerate it with `just assets`")
  }
  if id not in paper-assets.values {
    if not assets-draft-mode {
      panic("assets.json has no asset '" + id + "'. Declare it with "
        + "record() in the script that writes it, or fix the id. "
        + "To keep writing with it unresolved: just draft")
    }
    none
  } else {
    paper-assets.values.at(id)
  }
}

#let _placeholder(id) = box(
  fill: yellow,
  inset: (x: 2pt),
  text(fill: red, weight: "bold", "?" + id + "?"),
)

// A generated figure. Extra named arguments are forwarded to `image`, so the
// usual `width: 70%` still works at the call site where it belongs.
#let fig(id, ..args) = {
  let e = _entry(id)
  if e == none { _placeholder(id) } else {
    if e.kind != "figure" {
      panic("'" + id + "' is declared as a " + e.kind + ", not a figure")
    }
    image(e.path, ..args)
  }
}

// A generated table. The file under si/ is a bare #table(...) with no caption
// and no label -- those live at the call site, in si-body.typ.
#let tbl(id) = {
  let e = _entry(id)
  if e == none { _placeholder(id) } else {
    if e.kind != "table" {
      panic("'" + id + "' is declared as a " + e.kind + ", not a table")
    }
    include e.path
  }
}
