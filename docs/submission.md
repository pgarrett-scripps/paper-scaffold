# Submission outputs

The journal upload set built by `just submission`.

## The upload set: `just submission`

A journal's form wants the manuscript, the SI, the graphical abstract and a
cover letter as separate files. `just submission` writes them to `submission/`
with a `manifest.json` (each file's role, hash, and the manuscript it came
from), after a fresh `just paper`:

- `manuscript.pdf` and `supporting-information.pdf` are page ranges of ONE
  compile of the captured manuscript, cut at the `<si-start>` probe in
  `paper.typ`. The SI is still an appendix of the same document, so its
  numbering and every cross-reference match `paper.pdf`. The graphical
  abstract lands per `[placement].submission` in `journal.toml` (default
  `journal`: the last page of the main text).
- `manuscript.docx` and `supporting-information.docx` are the Word projection
  split at its SI heading, each converted by the ordinary Word export.
- `toc-graphic.<fmt>` is the declared `toc-graphic` in the profile's
  `[graphical-abstract] file-format`, flattened to RGB, with its resolution set
  so it fits the journal's box, and refused below `min-dpi`.
- `cover-letter.pdf` is `cover-letter.typ`, which reads the title and authors
  from `config.typ`, numbers through `#s()`, and the journal name from the
  profile. Delete the file and the step is skipped. The build measures its
  words and pages (see "The cover letter" below).

Where the SI lives is read, never configured. When `paper.typ` does not
include `si-body.typ`, the manuscript files are the whole capture. If
`manuscript.toml` then declares a separate SI document target (not
`paper.typ`, and named `si` or carrying the `si-body.typ` part), that
target's PDF is `supporting-information.pdf` and no SI Word file is written.
With no such target the SI steps write nothing, note why, and remove any
stale SI file.

An SI that cites the main list's keys (no `@si-` list of its own) cannot ship
as a page range: its citation numbers would point at a list in the other
file. Then both SI files are compiled on their own from the SI half of the
Word projection, closed by the main `#bibliography` call, so the SI carries a
local list of only the works it cites, numbered from 1 in SI order, and a
bare "Figure 3" or "Section 2.4" becomes "... of the main text". The main
files and their full list are unchanged.

The split files refuse to build while the source differs from the last
`just paper` capture. Each output is recorded in `.build-state/submission.json`.
The set is outside `verify` for the audiobooks' reason: `just check` notes a
stale set, `just check-submission` fails on it, and `just preflight` rebuilds
and checks it. `just check-submission` then runs `just check-layout
--submission` over `paper.pdf` and the set's PDFs: text past the margins,
and each figure's resolution as placed, size, smallest type and colour mode
against the profile's `[figures]` limits ([journals.md](journals.md)). Those
are warnings; the journal's production office has the last word on layout.

## The cover letter

Editors read the cover letter to decide whether a paper is significant
enough to send out. Reviewers mostly judge the technical work, and clarity
can be fixed in revision while significance cannot, so the letter is where
the case for significance is made, in plain language. John Yates's editorial
"The Cover Letter" (J. Proteome Res. 2017, 16, 367,
[doi:10.1021/acs.jproteome.6b01068](https://doi.org/10.1021/acs.jproteome.6b01068))
asks a letter to answer four questions concisely: why the work is important
(it makes a process faster or more sensitive, measures what could not be
measured, finds something new about a biological process, or its finding is
validated), what its broader impacts are, who will be interested and so why
this journal, and whether an editor encouraged the submission. It should not
restate what the submission forms already collect.

Journals add their own required items. A profile's `[cover-letter]` table
records them with the URL and date they were read:

```toml
[cover-letter]
required = ["title", "corresponding-author", "journal-fit", "suggested-reviewers"]
reviewers-min = 4        # only with "suggested-reviewers"
# max-words = 500        # only when the guidelines state a limit
# max-pages = 1
source = "https://..."
guidelines-dated = "2026-08-27"
checked = "2026-09-25"
```

`required` takes the keys `title`, `corresponding-author`, `other-authors`,
`journal-fit`, `supporting-information`, `suggested-reviewers`, `preprint`,
`prior-work`, `length` and `editor-discussion`; an unknown key, a
non-positive limit or a malformed date does not load. The shipped JPR and
JASMS profiles (guidelines dated 2026-08-27) state no word or page limit for
the letter, so they set none. Both ask for the corresponding author's full
contact details, the other authors, the title, why the paper suits the
journal, a description of the SI, any preprint with what changed since,
length issues, and whether an editor was consulted; JASMS adds four or more
suggested reviewers with contact details and any related or prior work to
disclose. `[notes]` quotes their wording.

What is checked where:

- `just cover-letter` prints the letter's words (wordometer, as the
  manuscript is counted: everything the letter prints, `#s()` numbers
  resolved) and pages, records both in `.build-state/submission.json` and
  `manifest.json`, and prints a `LIMIT:` line for a profile limit exceeded.
- `just check-submission`, and so `just preflight`, fails on a limit
  exceeded, alongside a stale letter. `just check` only notes it.
- `just journal` shows the letter's last-built counts, the limit (or that
  the guidelines state none) and the required items.
- `just verify` does not look at the letter beyond `fmt-check`: it is an
  upload-set file, and a paper with no `cover-letter.typ` checks nothing.
- Whether the letter gives each required item is not a gate check: a
  keyword cannot tell "why this journal" from a sentence naming it.
  `/paper:cover-letter` drafts the letter from the manuscript and the
  profile, and goes through the list item by item; anything only the author
  knows is left as a `#todo`, which stops `just cover-letter` until filled.
