---
name: reviewer-response
description: Answer journal reviewers in a revision round. Turns the decision letter's comments into reviews/ACTIONS.md rows and a response letter (reviewer-response.typ) whose points cite those rows, then keeps the two consistent as fixes land. Use when a decision letter arrives, when drafting or updating the response to reviewers, or before resubmitting.
---

# Answer the reviewers

Work from the manuscript root and follow AGENTS.md/CLAUDE.md and STYLE.md.
The why behind this skill is in `.paper/docs/submission.md` ("A revision
round"; in the scaffold, `docs/submission.md`).

The response letter is `reviewer-response.typ` (or the `[response] file` in
`project.toml`). Each reviewer comment is one `#point(...)`, and its
`actions:` name the `reviews/ACTIONS.md` rows that carry the work. The
ledger stays the one list of work: the letter answers the reviewer, the rows
record what changed and in which commit. `just check-response` (inside
`just verify` while the letter exists) fails when a point marked `done`
cites no row, or cites a row that is not done with a commit hash, or cites a
row that does not exist.

## Start the round

1. Confirm the submission was recorded: `git tag -l 'submitted/*'`. If the
   version the reviewers read is not tagged, ask the user which commit it
   was; do not tag a later commit as the submitted one. On a new
   submission, `just tag-submission <name>` (clean tree, current paper.pdf)
   records it.
2. `just response-init` writes the letter from the template (it never
   overwrites). Set `journal-id`.
3. Record an edit baseline for the round: `just edit-baseline revision`.

## Turn comments into points and rows

For each reviewer comment, in the reviewer's order:

1. Quote or closely condense the comment in the point's first argument. Do
   not soften it. Number points `R<reviewer>.<n>`.
2. Decide what it needs and route it, as the review skills do:
   `/paper:copy-edit`, `/paper:declare-number`, `/paper:new-figure`,
   `/paper:fix-verify`, "analysis change" or "author decision". A comment
   that needs no change is `rebut`, with the reason in the response.
3. For each piece of work add a ledger row:
   `just actions-add <severity> "decision letter R<r>.<n>" "<summary>" "<fix>"`.
   It prints the id; put it in the point's `actions:`. Severity follows
   the ledger: a comment that challenges a result or a claim is at least
   `major`.
4. Status: `todo` until the work is done; `decide` when only the author can
   choose (a new experiment, a claim to withdraw). List every `decide`
   point for the user; never answer one yourself.

## Write the responses

- Answer what the reviewer asked, first sentence first. Say what changed and
  where (section, figure, SI table), in the `change:` argument.
- Numbers are `#s("id")`, as in the manuscript; a new result is declared
  first (`/paper:declare-number`). Never type one.
- A rebuttal gives the evidence (a result, a citation, a control) and stays
  courteous. Do not claim a change the manuscript does not contain.
- Do not promise work that is not done; `partly` says what remains.

## As fixes land

1. The editing skill makes the change. Its commit message carries
   `Closes: A-0012` for each row it completes.
2. `just close-actions` writes each commit's hash into the named rows.
3. Set the point's status to `done` (or `partly`).
4. `just edit-check revision --revision`: new `#s()` ids, citations, floats
   and headings are notes in a revision; a numeral typed into the prose
   still fails.
5. `just check-response`, then `just gate`.

## Before resubmitting

1. Every point is `done`, `partly` or `rebut`; no `todo` or `decide` left.
2. `just check-response` and `just verify` pass.
3. `just diff-pdf <submitted-name>` writes `.review/diff-<name>.pdf`: the
   text-level changes since the submitted PDF, for the authors to read and,
   if the journal asks for a marked-up copy, to attach. `just review
   <name>` is the structural comparison.
4. Set `draft = false` in the letter to hide the status chips, then
   `just response` builds `reviewer-response.pdf`.

Report: the points by status, the ledger ids added and closed, each
`decide` point as a question for the user, and the `check-response`
verdict. Do not commit unless asked.
