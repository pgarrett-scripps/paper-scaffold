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

## Read the action ledger first

`reviews/ACTIONS.md` records every finding earlier reviews raised and whether
it was fixed; its header states the rules. Read it before reviewing. If it is
missing, create it with `just check-actions --init` (a paper on a scaffold
older than 3.24.0 has no such recipe: write a file whose table header is
`| id | severity | status | source | summary | fix | closed |` with a
`|---|---|---|---|---|---|---|` separator under it). A problem that matches an
`open`, `done` or `wontfix` row is not a new finding: cite the existing id in
the findings file instead of raising it again. A `done` row whose problem is
back in the current text is reopened, not duplicated. Appending to the ledger
is the only write this skill makes outside its findings file; it still never
edits the manuscript. The ledger is the editor's input, not the reviewers':
reviewer agents judge the paper independently and are not given it; the
editor marks which required changes are already on it.

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
   reviewers' copy. Run it unless the caller says it is already current
   (`/paper:review-all` generates it once for every review); it does not need a
   current PDF. Reviewers read this file and nothing else of the manuscript:
   not paper.typ, not si-body.typ, not the PDF. Everything a referee sees
   is in the copy, and the sources cost several times the tokens to say the
   same thing.
2. `references.bib` for what the bracketed keys refer to.
3. In full depth, where a reviewer's point turns on a number: `just trace
   <id> --json` and the generator it names. Where it turns on a figure: view
   the file under `figures/` named by `assets.json`. Do not rebuild the PDF
   for this.
4. STYLE.md "Claims" and "Scientific terms and concrete claims" as the house
   standard for what counts as an overstatement.

Do not run `/paper:claim-audit`, `/paper:methods-vs-code`, or `/paper:figure-review` inside
this pass. If one of them has a recent file under `reviews/`, the editor may
cite it; otherwise recommend it where a reviewer's point would be settled by
it.

## Run the panel

Give each reviewer the path to `paper.review.txt` and their brief, and have
them write independently, without seeing the other reports. Run each as its
own agent when agents are available, so they do not share conclusions;
otherwise write them one at a time from a fresh reading. A reviewer agent's
prompt names the file and says not to regenerate it or open the sources;
its whole reading is that one file plus `references.bib` on demand. Each reviewer writes in the form a
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

## What a skeptical methods reviewer presses on

Put this in the methods-and-statistics reviewer's brief, and in any
reviewer's brief when the paper presents a method, tool or pipeline. These
are the points referees of methods papers raise independently of each
other; the reasons and worked examples are in
`.paper/docs/reviewer-lessons.md` (`docs/` in the scaffold itself). They
are what the reviewer reads for, not sections of the report: a gap becomes a
major or minor point in the usual shape, and a paper that handles one well
earns no comment.

- **"Good enough" defined in advance.** Every "preserved", "negligible",
  "comparable" or "high agreement" needs a metric, a tolerance with its
  source (replicate spread, a field convention, a user requirement) and a
  number with its direction and spread. Without them the word reads as
  advertising.
- **A comparator other than the input.** Showing the output resembles what
  went in does not show the method is useful. Ask for an existing tool and
  a naive baseline (a fixed threshold, random removal at matched size); if
  the baseline does as well, the method is not the contribution.
- **Generalisation.** Were parameters tuned on the data used to report
  performance? Is there held-out data, and more than one instrument, lab or
  setting? Why was the main dataset chosen?
- **Parameters and settings.** Every exposed parameter with its purpose,
  default, range and effect; downstream software settings justified when a
  metric depends on them; parameters in physical units or with the
  conversion; a sensitivity check for those that matter.
- **Contribution versus plumbing.** What is new, in one sentence, with
  upstream libraries credited for the rest. The reviewer writes that
  sentence; if they cannot, that is a major point. Ask whether the core
  algorithm is reusable outside the file format or tool it ships in. Engineering others have already
  done is not a contribution; breadth of validation is.
- **Every algorithm step questioned.** For each step of the method, ask
  in turn: what instrument or physical assumption it makes (window edges,
  overlap, calibration); what it does to near-duplicates, isomers or
  neighbouring signals when it pools or merges data; which downstream
  consumer used the data it removes, and what the user gains from removing
  it. A step whose answers are not in the text is a point.
- **Shown, not only described.** The method is drawn on a small annotated
  toy example and given as pseudo-code, and every artifact or phenomenon the
  text names is pictured. A method described only in prose is a major point
  (principle 3).
- **Physical assumptions.** A rule that treats the instrument or sample as
  ideal needs evidence (a calibration, a measurement, a citation) or a
  margin shown not to matter. What the method discards permanently, and who
  would need it, is stated and scoped.
- **Downstream benefit.** A gain users care about, not only the metric the
  method optimises.
- **Availability.** Code version, DOI and data accessions in the
  Availability section. For a software or tool paper, the licence and the
  archive DOI also belong in the abstract, where a reader deciding whether
  to use the tool looks first.

The careful non-specialist reader's brief adds one task: after the
section that describes the study design, list the questions it leaves open
(why this dataset, why these settings, what was held out). Each unanswered
question is a point.

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
   owner that would make it: `/paper:copy-edit` for wording, `/paper:declare-number` for
   an undeclared value, `/paper:fix-verify` for a pipeline finding, `/paper:new-figure`
   for a missing or changed asset, "analysis change", or "author decision"
   with the question stated. In pre-submission stance, order this list by
   cost and mark which items block submission.

## Report

Write `reviews/<YYYY-MM-DD>-peer-review.md` (create the directory) holding
the parameter interpretation, each reviewer's report, and the editor's
section, in that order. Print the decision, the top three required changes,
and the file path. Nothing was edited, so do not run `just paper` or
`just verify`.

## Update the action ledger

After writing the findings file, and before the final print:

1. Every item in the editor's consolidated list of required
   changes becomes one action: `blocker` for an item that blocks submission
   or drove a reject or major-revision decision, otherwise `major` or `minor`
   as the reviewers ranked it. Individual reviewers' points are not added
   separately.
2. Skip a finding that matches an `open` or `wontfix` row. Reopen a matching
   `done` row whose problem is back: `status` to `open`, `closed` to
   `reopened <YYYY-MM-DD>: <what came back>`.
3. Append each remaining finding with
   `just actions-add <severity> "<source>" "<summary>" "<fix>"`: source
   `<YYYY-MM-DD>-peer-review.md#<ref>` naming the finding, a one-line summary, the
   routed fix. It takes the ledger lock and the next free id and prints the
   id, so two sessions never write the same one; do not type new rows.
4. Run `just check-actions` and repair any format error in the rows you
   reopened. Print the ids you added or reopened with the verdict.

When `/paper:review-all` launched this review (its prompt says so), skip
this section: review-all merges every review into the ledger once, after all
of them finish, so parallel reviews never write the file at the same time.
When the user passes `no-ledger`, skip this section too: the findings file
is the whole output, and the final print says the ledger was not updated.
