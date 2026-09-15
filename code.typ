// Shared code presentation. Apply after the document template with
// #import "code.typ": code-style
// #show: code-style
// Ordinary language-tagged fences remain native raw elements, so the prose
// extractors, word counter, and Word exporter keep their existing behavior.
#let code-style(body) = {
  show raw: set text(font: "DejaVu Sans Mono")
  show raw.where(block: true): set text(size: 9pt)
  show raw.where(block: true): it => block(
    width: 100%,
    fill: rgb("f4f6f8"),
    inset: 8pt,
    radius: 3pt,
    breakable: true,
    above: 0.8em,
    below: 0.8em,
  )[
    #set par(leading: 0.55em, spacing: 0pt)
    #it
  ]
  body
}
