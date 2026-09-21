// Supplemental headings use native Typst counters and references. Stable
// labels identify sections even after sections are removed or reordered.
// Scope numbering to the supplement so ordinary chapter headings stay plain.
#let supplemental-content(body) = {
  set heading(
    numbering: (..numbers) => numbering("S1.1", ..numbers.pos().slice(2)),
    supplement: [Supplemental Section],
  )
  // Unnumbered chapter headings do not advance Typst's heading counter.
  // Reset the supplemental levels explicitly for full and standalone builds.
  context {
    let current = counter(heading).get()
    counter(heading).update((current.at(0, default: 0), current.at(1, default: 0), 0))
  }
  body
}
