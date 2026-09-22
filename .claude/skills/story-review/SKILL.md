---
name: story-review
description: Read the paper as a coauthor would before anyone polishes a sentence and propose what should change so it gets published: the message, the structure, which figures to add, merge, move, or cut, and what analysis or experiment is missing. Ranked by cost against acceptance. Read-only.
context: fork
agent: general-purpose
model: opus
---

# Review the paper's story and propose the plan to publish it

Work from the manuscript root and follow AGENTS.md/CLAUDE.md and STYLE.md.
This skill is read-only: it writes one plan and edits nothing. The other
review skills judge what is on the page; this one asks what should be on
the page. Its reader is the author deciding what to do next, not a journal.

## The stance: land the plane

The goal is a paper that is defensible and gets published, not the best
paper this data could support. Apply that to every suggestion:

- Rank by what it does to the odds of acceptance at the target venue
  against what it costs in days. Read `journal.toml` and its profile for
  the venue and its limits.
- The default recommendation is the smallest set of changes that makes
  the main claim defensible. Everything else is listed under "would make
  it better" and can be declined.
- Prefer narrowing or cutting a claim over doing new work to support it.
  A weaker claim the evidence carries beats a stronger one that needs
  another month.
- Propose a new experiment only when the main claim fails without it, and
  say so in those words. Separate "computable from data in hand" from
  "needs new data" by reading `analysis/data/`, the generators under
  `analysis/scripts/`, and `stats.json`.
- A paper that is done is better than a paper that is perfect. If the
  draft is already defensible, say that first and keep the list short.

## Read the whole thing

Read config.typ (title, abstract, keywords), paper.typ between the BODY
markers, si-body.typ, every caption, and `assets.json` for what the floats
are. Use `just review-text` for a copy with numbers resolved if the build
is not current, and `just wordcount --sections` for the section sizes.
Read `viz/report.json` for floats cited once or never. Do not rebuild the
PDF.

## Then answer, in this order

1. **The message.** Write the paper's contribution in one sentence from
   the abstract. Check that the title, the last paragraph of the
   introduction, the order of the results, the first paragraph of the
   discussion, and the conclusions all serve that sentence. Where they
   pull in different directions, name which version the evidence supports
   and propose the one sentence to align them to. If the message the
   evidence supports is smaller than the one the abstract claims, say so;
   that is usually the cheapest fix in the whole plan.
2. **Structure.** Propose a section and paragraph order: what moves,
   merges, splits, or goes to the SI, and why in one line each. Flag a
   result presented before the reader can interpret it, methods detail
   in the results, discussion that repeats results instead of saying what
   they mean, and any section over the venue's limit.
3. **Figures and tables.** For each float: what it proves, whether the
   message needs it, whether it would merge with another, and whether it
   belongs in the SI. Propose a new figure only where a load-bearing claim
   rests on a number the reader cannot see, and give it the data it would
   plot and the existing inputs it would read. Count against the profile's
   `figures-max`.
4. **What is missing.** The controls, comparisons, sensitivity checks, or
   experiments a reviewer will ask for before believing the main claim.
   For each: what it would show, whether it is computable from data in
   hand, the cost in days, and whether the paper can be published without
   it by narrowing the claim instead. Most items should end up in the
   narrow-the-claim column.
5. **What to cut.** Claims, floats, paragraphs, and SI material the
   message does not need. Cutting is free and usually the largest single
   improvement available.

Ground every point in the text: quote the sentence or name the float and
`file:line`. Do not invent results, data, or literature; a comparison you
think exists is a question, not a recommendation.

## Report

Write `reviews/<YYYY-MM-DD>-story-review.md` (create the directory).
Shape:

1. A one-paragraph verdict: the one-sentence message, whether the draft is
   already defensible, and the smallest set of changes that would make it
   so, with a total cost in days.
2. **To publish**: the required changes, numbered, each with its cost and
   its owner: `/copy-edit`, `/new-figure`, "analysis change", "new
   experiment", "cut", or "author decision" with the question stated.
3. **Would make it better**: the rest, same shape, explicitly optional.
4. The five sections above as the supporting detail.

Print the verdict paragraph and the file path. Nothing was edited, so do
not run `just paper` or `just verify`. This skill is not part of
`/review-all`; its output is a plan to discuss, not a fix list.
