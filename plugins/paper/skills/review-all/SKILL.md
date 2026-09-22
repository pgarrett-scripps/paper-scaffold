---
name: review-all
description: Run every review skill (claim-audit, methods-vs-code, figure-review, prose-review, peer-review) in parallel as a final sanity check and merge their findings into one ranked list with a ship verdict. Use before submission or before handing a draft to a coauthor. Read-only.
context: fork
agent: general-purpose
model: opus
---

# Run every review at once

Work from the manuscript root and follow AGENTS.md/CLAUDE.md. This skill is
read-only. It launches the five review skills as independent agents, waits
for all of them, and writes one merged report. It does not re-do any review
itself and does not edit the manuscript.

## Parameters

All optional, in plain words after the skill name. State the interpretation
at the top of the report.

- **which**: default all five. The user may drop one ("skip figures") or
  name a subset. `/paper:literature-check` is off by default because it needs
  the network and is slow; "with literature" adds it as a sixth agent.
- **model**: default is `opus`, passed as the Agent tool's `model`
  parameter on every launch. The user may name another for all reviews or
  per review ("peer-review on sonnet"). Do not edit any SKILL.md to do so.
- **scope** and any review-specific words ("pre-submission", "hostile
  Reviewer 2", "just the results section") are passed through verbatim to
  the review they apply to; scope goes to all of them.

## Before launching

1. `git status --short`: another session may be editing the tree. Note any
   uncommitted changes to the manuscript sources in the report; the reviews
   see the working tree, not HEAD.
2. `just verify` once, and record its verdict. Do not fix anything it
   reports; a failing gate is itself a finding for the merged list, and the
   reviews should still run.
3. Note the date and the commit (`git rev-parse --short HEAD`) so the
   report says what was reviewed.
4. `just review-text` once, so `paper.review.txt` is current. This is the
   shared reviewers' copy: prose with numbers resolved, captions numbered,
   citation keys bracketed, no images or table bodies. Generating it here
   means no agent re-runs it and the prose-facing reviews never open the
   Typst sources at all. Record its word count in the report.

## Launch

Start all selected reviews in a single turn so they run concurrently, one
Agent call each. Each agent's prompt is: invoke the named skill with the
pass-through words, write its findings file under `reviews/`, and reply
with only the verdict paragraph and the file path. Every prompt also says:
"`paper.review.txt` is current as of this launch; read it for the prose,
numbers and captions, do not regenerate it, and do not read paper.typ,
si-body.typ or the PDF unless your skill's job is to check the source."
That last clause applies to `claim-audit` and `methods-vs-code`, whose
findings are about source and code; `peer-review`, `prose-review` and the
caption half of `figure-review` work from the copy alone. The agents share
nothing with each other beyond that file. Do not start any of them sequentially and do not run one
inline to save time. Wait for every agent to finish before writing the
merged report; if one fails, say so in the report and do not invent its
findings.

## Merge

Read the five findings files (not the agents' replies) and build one list:

1. Deduplicate: the same sentence flagged by two reviews is one item that
   cites both. A `prose-review` wording finding on a sentence `claim-audit`
   calls overstated is one item owned by `claim-audit`.
2. Rank: blockers first (a claim the evidence contradicts, methods drift
   that changes a result, a figure that shows the opposite of the text, a
   failing `just verify`), then majors, then minors. Within a rank, order by
   how much of the manuscript the fix touches.
3. Route: every item keeps the owner its review assigned (`/paper:copy-edit`,
   `/paper:declare-number`, `/paper:fix-verify`, `/paper:new-figure`, "analysis change",
   "author decision"). Group the "author decision" items at the end as
   questions.
4. Verdict: one of "ready", "ready after the listed minors", or "not ready",
   with the items that decide it.

## Report

Write `reviews/<YYYY-MM-DD>-review-all.md`: the parameter interpretation,
what was reviewed (commit, tree state, `just verify` verdict), the verdict,
the ranked merged list, the author questions, and the paths of the five
underlying files. Print the verdict, the blockers, and the file path.
Nothing was edited, so do not run `just paper`.
