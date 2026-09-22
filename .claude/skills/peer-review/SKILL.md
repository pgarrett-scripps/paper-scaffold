---
name: peer-review
description: Run a simulated peer review of the manuscript with a small panel of reviewer personas and produce reviewer reports plus an editor's recommendation. Use when asked to review, referee, or critique the paper as a journal would. Loose parameters; read-only.
context: fork
agent: general-purpose
model: opus
---

# Peer-review the manuscript

Work from the manuscript root and follow AGENTS.md/CLAUDE.md. This skill is
read-only: it writes reviewer reports and never edits the manuscript. It is
self-contained and does not use any external review pipeline or plugin.

## Parameters

All optional, given in plain words after the skill name. Interpret them
loosely and state the interpretation at the top of the report.

- **scope**: whole manuscript (default, main text plus SI), or a section,
  the abstract, the SI, or a named figure.
- **panel**: which reviewers to convene. Default is three: a domain expert
  in the manuscript's field, a methods-and-statistics reviewer, and a
  careful non-specialist reader. The user may add, replace, or name others,
  for example "a hostile Reviewer 2", "an editor deciding on desk
  rejection", "a reproducibility reviewer", or "someone from a competing
  group".
- **journal**: defaults to the profile `journal.toml` selects, read from
  `journals/<profile>.toml` for its scope, limits, and notes. The user may
  name a different target; then say what you know of that venue and flag it
  as from memory, not from a profile.
- **depth**: "quick" reads the review text once and writes one page per
  reviewer; "full" (default) also follows the numbers and figures below.
- **stance**: "as submitted" (default) judges the paper as is; "pre-submission"
  ranks fixes by cost so the author can decide what to do before sending.

## Inputs

1. `just review-text` writes `paper.review.txt`: the prose with numbers
   resolved, captions numbered, and citation keys in brackets. This is the
   reviewers' copy. Run it; it does not need a current PDF.
2. `references.bib` for what the bracketed keys refer to.
3. In full depth, where a reviewer's point turns on a number: `just trace
   <id> --json` and the generator it names. Where it turns on a figure: view
   the file under `figures/` named by `assets.json`. Do not rebuild the PDF
   for this.
4. STYLE.md "Claims" and "Scientific terms and concrete claims" as the house
   standard for what counts as an overstatement.

Do not run `/claim-audit`, `/methods-vs-code`, or `/figure-review` inside
this pass. If one of them has a recent file under `reviews/`, the editor may
cite it; otherwise recommend it where a reviewer's point would be settled by
it.

## Run the panel

Give each reviewer the review text and their brief, and have them write
independently, without seeing the other reports. Run each as its own agent
when agents are available, so they do not share conclusions; otherwise write
them one at a time from a fresh reading. Each reviewer writes in the form a
journal expects:

1. A summary of the paper in their own words (two to four sentences), so the
   author can see whether the message landed.
2. Overall assessment: significance, novelty as far as the reviewer can tell
   from the manuscript and its references, and whether the conclusions
   follow from the evidence.
3. Major points, numbered. Each names the location (section, figure, or
   quoted sentence), says what is wrong or missing, and says what would
   satisfy the reviewer. A point the reviewer cannot resolve from the text
   is a request for clarification, not a verdict.
4. Minor points, numbered, in the same shape, briefly.
5. A recommendation: accept, minor revision, major revision, or reject, with
   one sentence of reasoning.

Reviewers judge the paper, not the pipeline: mechanical matters that
`just verify` already enforces (spelling, formatting, uncited floats) are
out of scope unless they change meaning. Reviewers do not invent literature;
a "this was done before" point must name a source or be phrased as a
question to the author. Reviewers do not guess at data they cannot see.

## Editor's decision

After the reports, write an editor's section:

1. The decision (accept / minor / major / reject), and the two or three
   points that drove it.
2. Where the reviewers agree, where they disagree, and which side the
   evidence in the manuscript supports.
3. A consolidated, deduplicated list of required changes, each routed to the
   owner that would make it: `/copy-edit` for wording, `/declare-number` for
   an undeclared value, `/fix-verify` for a pipeline finding, `/new-figure`
   for a missing or changed asset, "analysis change", or "author decision"
   with the question stated. In pre-submission stance, order this list by
   cost and mark which items block submission.

## Report

Write `reviews/<YYYY-MM-DD>-peer-review.md` (create the directory) holding
the parameter interpretation, each reviewer's report, and the editor's
section, in that order. Print the decision, the top three required changes,
and the file path. Nothing was edited, so do not run `just paper` or
`just verify`.
