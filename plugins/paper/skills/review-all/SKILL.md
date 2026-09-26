---
name: review-all
description: Run every review skill (claim-audit, methods-vs-code, figure-review, prose-review, readability-review, intro-review, peer-review) in parallel as a final sanity check, merge their new findings into the action ledger reviews/ACTIONS.md, and give a ship verdict. Use before submission or before handing a draft to a coauthor. Read-only.
context: fork
agent: general-purpose
model: opus
---

# Run every review at once

Work from the manuscript root and follow AGENTS.md/CLAUDE.md. This skill is
read-only for the manuscript. It launches the seven review skills as
independent agents, waits for all of them, merges their findings into the
action ledger `reviews/ACTIONS.md`, and writes one short report with the ship
verdict. It does not re-do any review itself and does not edit the
manuscript.

## Parameters

All optional, in plain words after the skill name. State the interpretation
at the top of the report.

- **which**: default all seven. The user may drop one ("skip figures") or
  name a subset. `/paper:literature-check` is off by default because it needs
  the network and is slow; "with literature" adds it as an eighth agent.
- **no-ledger**: merge nothing into `reviews/ACTIONS.md`; the Merge section
  deduplicates across the reviews into the report only, and the report says
  the ledger was not updated.
- **model**: passed as the Agent tool's `model` parameter on every launch.
  Default is split by the kind of work: `claim-audit`, `methods-vs-code`,
  `figure-review` and `prose-review` are checklists against a fixed standard
  (the sources, the code, `assets.json`, STYLE.md) and run on `sonnet`;
  `peer-review`, `readability-review`, `intro-review` and `literature-check` are judgment calls and run on `opus`.
  The split exists because Opus draws down the plan's rate-limit window several
  times faster than Sonnet, and the checklists lose nothing on Sonnet. The
  user may name another model for all reviews ("all on opus") or per review
  ("prose-review on opus"). Do not edit any SKILL.md to do so.
- **scope** and any review-specific words ("pre-submission", "hostile
  Reviewer 2", "just the results section") are passed through verbatim to
  the review they apply to; scope goes to all of them.

## Before launching

1. `git status --short`: another session may be editing the tree. Note any
   uncommitted changes to the manuscript sources in the report; the reviews
   see the working tree, not HEAD.
2. `just verify` once, and record its verdict. Do not fix anything it
   reports; a failing gate is itself a finding for the ledger, and the
   reviews should still run.
3. Note the date and the commit (`git rev-parse --short HEAD`) so the
   report says what was reviewed.
4. Read `reviews/ACTIONS.md` and follow the rules in its header; if it is
   missing, create it with `just check-actions --init` (on a scaffold older
   than 3.24.0, write the header row
   `| id | severity | status | source | summary | fix | closed |` and its
   `|---|---|---|---|---|---|---|` separator by hand). Run
   `just check-actions` and record the open counts before this run.
5. `just review-text` once, so `paper.review.txt` is current. This is the
   shared reviewers' copy: prose with numbers resolved, captions numbered,
   citation keys bracketed, no images or table bodies. Generating it here
   means no agent re-runs it and the prose-facing reviews never open the
   Typst sources at all. Record its word count in the report.

## Launch

Start all selected reviews in a single turn so they run concurrently, one
Agent call each, with `model` set per the **model** parameter above. Each agent's prompt is: invoke the named skill with the
pass-through words, write its findings file under `reviews/`, and reply
with only the verdict paragraph and the file path. Every prompt also says:
"`paper.review.txt` is current as of this launch; read it for the prose,
numbers and captions, do not regenerate it, and do not read paper.typ,
si-body.typ or the PDF unless your skill's job is to check the source.
You were launched by /paper:review-all: read reviews/ACTIONS.md to skip
findings it already holds, but do not write it; review-all merges."
That last clause applies to `claim-audit` and `methods-vs-code`, whose
findings are about source and code; `peer-review`, `prose-review`, `readability-review`, `intro-review` and the
caption half of `figure-review` work from the copy alone. The agents share
nothing with each other beyond that file. Do not start any of them sequentially and do not run one
inline to save time. Wait for every agent to finish before writing the
merged report; if one fails, say so in the report and do not invent its
findings.

## Merge

Read the findings files (not the agents' replies) and merge them into the
action ledger. The ledger replaces the old separate ranked list: there is one
list of work, and it outlives this run.

1. Deduplicate across the reviews: the same sentence flagged by two reviews
   is one action whose `source` cites both files. A `prose-review` wording
   finding on a sentence `claim-audit` calls overstated is one action owned
   by `claim-audit`. A `peer-review` complaint about the Introduction and an
   `intro-review` finding on the same paragraph are one action owned by
   `intro-review`, whose fix is the more specific one. A `prose-review`
   and a `readability-review` finding on the same paragraph are one action
   owned by `readability-review`, whose rewrite covers the paragraph; where
   prose-review asks for a number and readability-review asks for fewer,
   the readability rewrite stands and the row says so. More generally, when
   several reviews raise the same problem on the same passage (a paragraph,
   a figure, a table), even in different words, merge them into one action:
   the owner is the review whose fix is most specific, and `source` cites
   every file.
2. Deduplicate against the ledger: a finding that matches an `open` or
   `wontfix` row adds nothing. One that matches a `done` row whose problem is
   back reopens that row in place: `status` to `open`, `closed` to
   `reopened <YYYY-MM-DD>: <what came back>`.
3. Append the rest with `just actions-add` (it takes the ledger lock and
   the next free id; `just actions-reserve N` first when the ids must be
   known before writing), blockers first (a claim the evidence
   contradicts, methods drift that changes a result, a figure that shows the
   opposite of the text, a failing `just verify`), then majors, then minors.
   Each row keeps the owner its review assigned as `fix` (`/paper:copy-edit`,
   `/paper:declare-number`, `/paper:fix-verify`, `/paper:new-figure`,
   "analysis change", "author decision"), `status` `open`, and an empty
   `closed`. A failing `just verify` is one blocker routed to
   `/paper:fix-verify`, sourced to this run's report. A
   `readability-review` finding is never a blocker: it is a suggestion the
   author may decline (`wontfix`), and it never makes the verdict "not
   ready" on its own.
4. Run `just check-actions` and repair any format error in the rows you
   wrote.
5. Verdict: one of "ready", "ready after the listed minors", or "not ready",
   decided by every `open` row in the ledger after the merge, including ones
   earlier reviews left open, with the ids that decide it.

## Report

Write `reviews/<YYYY-MM-DD>-review-all.md`: the parameter interpretation,
what was reviewed (commit, tree state, `just verify` verdict), the verdict
with the ids that decide it, the ids added and reopened by this run, the
open `author decision` rows as questions, the `just check-actions` counts
before and after, and the paths of the underlying files. Do not copy the
ledger's rows into the report; cite ids. Print the verdict, the open
blockers, and the file path. The manuscript was not edited, so do not run
`just paper`.
