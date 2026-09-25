// The submission cover letter, built by `just cover-letter` into
// submission/cover-letter.pdf. Optional: delete this file and the recipe says
// so and moves on.
//
// The title, authors and affiliation are NOT typed here. They come from
// config.typ, the file the PDF, the Word front matter and the word counter
// read, because a letter quoting a title the manuscript no longer has is an
// easy failure to make impossible. A result quoted in the letter is read the
// same way as in the prose, `#s("id")`, so a re-run analysis cannot leave a
// stale number behind in it. The journal and article type come from the
// profile journal.toml selects, passed in by the build as `--input journal=`
// and `--input article-type=`; the defaults below apply without one.
//
// What the letter says: why the work matters, its broader impact, why this
// journal's readers, and whether an editor invited it, plus each item the
// profile's [cover-letter] `required` lists (`just journal` prints them).
// `/paper:cover-letter` drafts it that way; docs/submission.md has the why.
// Anything only the author knows (a phone number, suggested reviewers) is a
// `#todo("...")`, which stops `just cover-letter` until it is filled in.
#import "config.typ": paper-authors, paper-title
#import "stats.typ": s, todo

#let journal = sys.inputs.at("journal", default: "the journal")
#let article-type = sys.inputs.at("article-type", default: "Article")
// The date the letter is sent, not paper-date: that one versions the science.
#let letter-date = datetime.today().display("[month repr:long] [day], [year]")
#let corresponding = paper-authors.first()

#set page(paper: "us-letter", margin: 1in)
#set text(11pt)
#set par(justify: true)

#corresponding.name \
#corresponding.affiliation \
#link("mailto:" + corresponding.email)[#corresponding.email]

#v(1em)
#letter-date
#v(1em)

Dear Editors,

Please consider the enclosed manuscript, "#paper-title", for publication in
#emph(journal) (#article-type).

Replace this paragraph with what the paper shows, why it matters, and why it
suits this journal's readers. State results as the manuscript does: across #s(
  "cohort.n_conditions",
) conditions, the treated group scored #s("effect.treated_over_control") over
control.

This manuscript has not been published and is not under consideration elsewhere.
All authors have approved the submission and declare no competing financial
interest.

Sincerely,

#v(2em)
#corresponding.name, on behalf of all authors
