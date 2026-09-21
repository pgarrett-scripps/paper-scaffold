// Section inventory for wordcount.typ. Count evaluated Typst content with the
// same wordometer rules as the existing journal counts, never source tokens.
#import "@preview/wordometer:0.1.4": (
  IGNORED_ELEMENTS, extract-text, word-count-of,
)

#let count-excludes = (figure, raw.where(block: true))

// Only open a wrapper if it contains a section heading. Keeping other content
// intact preserves wordometer's handling of adjacent text and inline markup.
#let section-children(node) = {
  let fn = repr(node.func())
  if fn in IGNORED_ELEMENTS or fn in ("figure", "raw", "heading") {
    ()
  } else if node.has("children") {
    node.children
  } else if fn == "styled" {
    (node.child,)
  } else if node.has("body") {
    (node.body,)
  } else {
    ()
  }
}

#let has-heading(node) = {
  node.func() == heading or section-children(node).any(has-heading)
}

#let split-headings(node) = {
  if node.func() == heading or not has-heading(node) {
    (node,)
  } else {
    section-children(node).map(split-headings).flatten()
  }
}

#let section-counts(body, region) = {
  let rows = ()
  let parents = ()
  let current = region
  let is-heading = false
  let chunk = []
  for node in split-headings(body) {
    if node.func() == heading {
      let count = word-count-of(chunk, exclude: count-excludes)
      rows.push((
        id: current,
        heading: is-heading,
        words: count.words,
        chars: count.characters,
      ))
      let title = extract-text(node.body).trim().replace(regex("\s+"), " ")
      // Escape path separators in titles, so hierarchy stays unambiguous.
      title = title.replace("%", "%25").replace("/", "%2F")
      let level = node.at("level", default: none)
      if level == none { level = node.at("depth", default: 1) }
      parents = parents.filter(p => p.level < level)
      parents.push((level: level, title: title))
      current = region + "/" + parents.map(p => p.title).join("/")
      is-heading = true
      chunk = []
    }
    chunk += node
  }
  let count = word-count-of(chunk, exclude: count-excludes)
  rows.push((
    id: current,
    heading: is-heading,
    words: count.words,
    chars: count.characters,
  ))
  // A new wrapper must not silently change how the established counter counts.
  let total = word-count-of(body, exclude: count-excludes)
  assert(
    rows.map(r => r.words).sum() == total.words,
    message: "section word counts disagree with the journal total for "
      + region,
  )
  rows
}
