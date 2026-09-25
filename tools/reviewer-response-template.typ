// Response to reviewers. Written by `just response-init`; this file is yours.
// NOT part of the manuscript and not included by paper.typ.
//
// Build:  just response        (writes reviewer-response.pdf)
// Check:  just check-response  (inside `just verify` while this file exists)
//
// Each reviewer point is one #point(...). Its `actions` name the rows of
// reviews/ACTIONS.md that carry the work, so the letter and the ledger cannot
// drift apart. check-response holds them together:
//   - a point marked "done" names at least one row, and every row it names is
//     done in reviews/ACTIONS.md with a commit hash in `closed`;
//   - every row a point names exists;
//   - point ids are unique.
// Numbers are #s("id"), exactly as in the manuscript: never typed.
//
// Statuses:
//   done    changed in the manuscript; the rows name the commits
//   partly  partly changed; say what remains
//   rebut   we disagree, and say why (no change)
//   todo    not answered yet
//   decide  needs an author decision
#import "stats.typ": lit, s
#import "config.typ": paper-title

#let journal-id = "MANUSCRIPT-ID"
#let draft = true // false before sending: hides the status chips

#set page(paper: "us-letter", margin: 1in, numbering: "1")
#set text(size: 10.5pt)
#set par(justify: true, leading: 0.65em)

#let status-colors = (
  done: rgb("#2e7d32"),
  partly: rgb("#558b2f"),
  rebut: rgb("#ef6c00"),
  todo: rgb("#c62828"),
  decide: rgb("#37474f"),
)
#let chip(label, fill) = box(fill: fill, inset: (x: 4pt, y: 2pt), radius: 2pt)[
  #text(size: 8pt, fill: white, weight: "bold")[#label]
]

// One reviewer point. `id` is the point's name ("R1.3"), unique in the file.
#let point(id, comment, response, status: "todo", actions: (), change: none) = {
  assert(status in status-colors, message: "point " + id + ": unknown status " + status)
  [#metadata((id: id, status: status, actions: actions)) <response-point>]
  block(breakable: true, above: 1.1em)[
    #text(weight: "bold")[#id]
    #if draft [
      #h(4pt) #chip(upper(status), status-colors.at(status))
      #for a in actions [#h(3pt) #chip(a, luma(110))]
    ]
    #block(inset: (left: 8pt, y: 4pt), stroke: (left: 1.5pt + luma(180)))[
      #text(size: 9.5pt, style: "italic")[#comment]
    ]
    *Response.* #response

    #if change != none [*Change.* #change]
  ]
}

#align(center)[
  #text(size: 15pt, weight: "bold")[Response to Reviewers] \
  #v(3pt)
  #text(size: 11pt)[#paper-title] \
  #text(size: 9.5pt)[Manuscript #journal-id]
]

We thank the reviewers for their reading of the manuscript. Each comment is
quoted, followed by our response and the change made.

= Reviewer 1

#point(
  "R1.1",
  [The reviewer's comment, quoted or condensed in their words.],
  [Our response.],
  status: "todo",
  actions: (),
  change: [Where the manuscript changed, by section.],
)
