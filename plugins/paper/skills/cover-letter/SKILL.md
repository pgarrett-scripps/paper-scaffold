---
name: cover-letter
description: Draft or revise the submission cover letter (cover-letter.typ) from the manuscript and the selected journal profile, stating the paper's significance in plain language and every item the journal requires. Use when preparing a submission or when asked to write, check, or tighten the cover letter.
---

# Draft or revise the cover letter

Work from the manuscript root and follow AGENTS.md/CLAUDE.md and STYLE.md.
The letter is `cover-letter.typ`; `just cover-letter` builds it into
`submission/cover-letter.pdf`. The why behind this skill is in
`.paper/docs/submission.md` ("The cover letter"; in the scaffold,
`docs/submission.md`).

## What the letter is for

Editors read the letter to judge significance before any reviewer sees the
paper. Reviewers tend to press on technical points, and a paper can be made
clearer in revision but not more significant. So the letter states, in plain
language an editor outside the subfield follows, why the work matters. It
does not repeat what the submission form already collects (title fields,
the sole-submission statement, the reviewer list) unless the journal asks
for it in the letter. Keep it short: about one page. The four questions
(Yates, J. Proteome Res. 2017, 16, 367, doi:10.1021/acs.jproteome.6b01068):

1. **Why is the work important?** For example, it makes an important process
   faster or more sensitive, measures something that could not be measured
   before, finds something new about a biological process, or its finding
   has been validated and verified.
2. **What are the broader impacts?**
3. **Who will be interested?** Why this journal's readers.
4. **Did an editor encourage the submission?** If so, say so.

## Gather before writing

1. Run `just journal` and read the "Cover letter" block and the
   `cover-letter*` lines under "In the journal's words". The profile's
   `[cover-letter] required` list names what this journal asks the letter to
   give; `reviewers-min` is the least number of suggested reviewers. A limit
   (`max-words`, `max-pages`) appears only when the guidelines state one. With
   no profile selected, write to the four questions alone and say so.
2. Read the abstract (`paper-abstract` in config.typ), the Introduction's
   statement of the gap, the Conclusions, and the Supporting Information's
   headings (`si-body.typ`) for the SI description.
3. For each result the letter will quote, find its id in `stats.json` (or
   `just trace <id> --json`). Quote only results the paper states, with the
   comparison the paper makes.
4. Run `just check-actions --open` and note open rows that bear on the
   letter, such as an overstated claim the letter would repeat.

## Write

- **Numbers:** never type a result. Use `#s("id")`, as the prose does; the
  letter imports `s` from `stats.typ`. A number no script computes is
  declared first (`/paper:declare-number`), never typed.
- **Title, authors, journal:** keep them bound, not typed: `paper-title` and
  `paper-authors` from config.typ, the journal name and article type from
  `sys.inputs` (the build passes the profile's).
- **Significance** answers the four questions from what the manuscript
  shows. Do not add a claim, application or audience the paper does not
  support; if the paper's own case for significance is thin, say that to the
  user rather than inventing one in the letter.
- **Required items:** write each item the profile lists. An item only the
  author can supply is a `#todo("...")` in the letter, never a guess:
  corresponding-author phone and mailing address, suggested reviewers and
  their contact details, a preprint link and what changed since deposition,
  prior or related work to disclose, whether an editor was consulted,
  conflicts of interest. `#todo` needs `todo` imported from `stats.typ`
  (`#import "stats.typ": s, todo`). `just cover-letter` refuses to build
  while one is open, which is the point.
- **Conditional items** (`preprint`, `length`, `editor-discussion`,
  `prior-work`): ask, or leave a `#todo` asking the author, rather than
  asserting "none". `length` matters when `just check-words` shows the main
  text over the journal's limit.
- Follow STYLE.md for wording. No promotional adjectives where a number
  exists.

## Check

1. `just fmt`, then `just cover-letter`: it prints the letter's words and
   pages, and a `LIMIT:` line for any profile limit exceeded. With open
   `#todo`s the build stops on the first; report them all instead (search the
   file for `#todo(`).
2. Go through the profile's `required` list item by item and say, for each,
   the sentence that gives it or the `#todo` that stands for it. The gate
   does not check these; this list is the check.
3. `just check-submission` holds the built letter to the profile's limits
   (and `just preflight` runs it). A letter is outside `just verify`.
4. Read the built PDF's text (`pdftotext submission/cover-letter.pdf -`) for
   the resolved numbers and the journal name.

Report: the word and page count as built, each required item with where it
is met or the open `#todo`, the `#s()` ids quoted, and anything in the
significance paragraph the manuscript does not yet support. Do not commit
unless asked.
