// Stable chapter identities. manuscript.toml supplies dissertation numbering.
// Keep literal includes in dissertation.typ for the manuscript source tools.
// The full document asserts that their rendered order matches the manifest.
#let chapter-manifest = toml("../manuscript.toml")
#let chapter-order = chapter-manifest.documents.dissertation.parts.filter(
  id => chapter-manifest.parts.at(id).source != chapter-manifest.documents.dissertation.entrypoint,
)

#let chapter-number(id) = {
  assert(id in chapter-order, message: "Unknown dissertation chapter: " + id)
  chapter-order.position(item => item == id) + 1
}

#let chapter-target(id) = label("chap-" + id)

// Write Chapter #ref(<chap-koth>) or Chapters #ref(<chap-koth>) and ... .
// Link when the target is present. References to other chapters in standalone
// PDFs retain the dissertation number without creating a broken PDF link.
#let chapter-reference(it) = {
  let name = str(it.target)
  if name.starts-with("chap-") {
    let number = chapter-number(name.slice(5))
    context {
      let targets = query(it.target)
      if targets.len() > 0 {
        link(targets.first().location(), str(number))
      } else {
        str(number)
      }
    }
  } else {
    it
  }
}

#let check-chapter-order() = context {
  let actual = query(heading.where(level: 1))
    .filter(it => it.has("label") and str(it.label).starts-with("chap-"))
    .map(it => str(it.label).slice(5))
  assert(actual == chapter-order,
    message: "Chapter includes must match documents.dissertation.parts in manuscript.toml")
}
