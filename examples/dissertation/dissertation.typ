#import "lib/template.typ": *
#import "@preview/alexandria:0.2.0": alexandria
#show: alexandria(prefix: "first-", read: p => read(p))
#show: alexandria(prefix: "second-", read: p => read(p))
#show: dissertation.with(
  title: "Example Dissertation", author: "Example Author", year: 2026,
  submission-date: "September 2026",
  abstract: [
// >>> BODY START
This example demonstrates independent chapter bibliographies and editable Word exports.
The same sources generate the complete dissertation and individual chapters.
// <<< BODY END
  ],
)
#include "chapters/first.typ"
#include "chapters/second.typ"
