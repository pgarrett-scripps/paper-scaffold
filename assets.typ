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

// PENDING (assets.json `pending`, docs/evidence.md): an id, or a "prefix*",
// whose evidence is not in yet renders as a visible placeholder in every
// build, file or not; `just verify` and `just preflight` fail until the
// declaration is removed.
#let _pending(id) = paper-assets.at("pending", default: (:)).keys().any(key =>
  key == id or (key.ends-with("*") and id.starts-with(key.slice(0, key.len() - 1))))

#let _pending-block(id) = block(
  width: 100%, inset: 1.5em, fill: rgb("#fff1c2"), stroke: 0.5pt + rgb("#b36b00"),
  align(center, text(fill: rgb("#8a4b00"), weight: "bold", "[pending: " + id + "]")),
)

#let _entry(id) = {
  if type(paper-assets) != dictionary or "values" not in paper-assets {
    panic("assets.json has no `values` table; regenerate it with `just assets`")
  }
  if _pending(id) {
    "pending"
  } else if id not in paper-assets.values {
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
  if e == "pending" { _pending-block(id) } else if e == none { _placeholder(id) } else {
    if e.kind != "figure" {
      panic("'" + id + "' is declared as a " + e.kind + ", not a figure")
    }
    image(e.path, ..args)
  }
}

// SUPPLEMENTARY DATA FILES, numbered once (opt-in).
//
// Files supplied beside the SI rather than rendered in it (a TSV per table,
// say) are cited by number, "Supplementary Data File 2", and Typst's figure
// counter never sees them. Typing those numbers into sentences is the same
// mistake as typing a figure number: insert, drop or reorder a file and every
// mention that is now wrong stays silent. So the ORDER is declared once, in
// config.typ, as asset ids:
//
//   #let paper-data-files = ("tbl.data-depth", "tbl.data-resources")
//
// and `dfile("id")` / `dfile-short("id")` / `dfile-count()` render from it.
// An id outside the list, or not declared in assets.json, stops the build as
// an undeclared figure id does. The printed words are config.typ's
// `paper-data-file-name` and `paper-data-file-short` when set. The Word
// export, word count, readability report and narrator resolve the same calls
// from the same list (tools/typst_prose.py: resolve_data_files).
//
// config.typ is imported INSIDE the helpers, not at the top of this file, so
// a manuscript that never calls them never needs the binding, and a test or
// slide deck that uses fig() without a config.typ is unaffected. The one
// constraint: config.typ must not call dfile() itself (that import is a cycle).
#let _data-files() = {
  import "config.typ" as paper-config
  let c = dictionary(paper-config)
  (
    files: c.at("paper-data-files", default: ()),
    name: c.at("paper-data-file-name", default: "Supplementary Data File"),
    short: c.at("paper-data-file-short", default: "File"),
  )
}

// The number alone, or none in draft mode for an id the list lacks.
#let dfile-number(id) = {
  let i = _data-files().files.position(x => x == id)
  if i == none {
    if assets-draft-mode { return none }
    panic("'" + id + "' is not in paper-data-files in config.typ. Add it "
      + "there, in the order the files are supplied.")
  }
  i + 1
}

#let _dfile(id, word) = {
  let e = _entry(id)
  let n = dfile-number(id)
  if e == "pending" {
    box(fill: rgb("#fff1c2"), inset: (x: 2pt),
      text(fill: rgb("#8a4b00"), weight: "bold", "[pending: " + id + "]"))
  } else if e == none or n == none { _placeholder(id) } else [#word #n]
}

// "Supplementary Data File N": the full phrase, for a first mention.
#let dfile(id) = _dfile(id, _data-files().name)

// "File N": the short form, for a list that has already said what these are.
#let dfile-short(id) = _dfile(id, _data-files().short)

// How many data files there are, for "Supplementary Data Files 1–#dfile-count()".
#let dfile-count() = _data-files().files.len()

// A generated table. The file under si/ is a bare #table(...) with no caption
// and no label -- those live at the call site, in si-body.typ.
#let tbl(id) = {
  let e = _entry(id)
  if e == "pending" { _pending-block(id) } else if e == none { _placeholder(id) } else {
    if e.kind != "table" {
      panic("'" + id + "' is declared as a " + e.kind + ", not a table")
    }
    include e.path
  }
}
