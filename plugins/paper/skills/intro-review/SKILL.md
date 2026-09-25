---
name: intro-review
description: Review the Introduction as a reviewer reads it before any result. Checks that the problem and its size come from the literature, that each existing approach has its gap stated, that every term and format the paper relies on is defined, that the aim, scope and design are stated with reasons, and that no result is shown before the Results. Use before submission, after a reviewer calls the introduction thin, or after restructuring the opening. Read-only.
context: fork
agent: general-purpose
model: opus
---

# Review the Introduction

Work from the manuscript root and follow AGENTS.md/CLAUDE.md and STYLE.md.
This skill is read-only. It writes one findings file and edits nothing.

Reviewers form their view of a paper in the Introduction. If the goal is
unclear there, they read every later result in its least favourable light.
The skill asks one question: after reading only the abstract and the
Introduction, does an expert who has not seen this work know
- what the problem is,
- why current approaches leave it open,
- what this paper does about it, and
- how the paper will show it?

It also checks that the Introduction does this without spending the results.

Principles 1 and 7 of `.paper/docs/reviewer-lessons.md` (`docs/` in the
scaffold itself) give the reasoning. The failures below were all raised by
real reviewers of one methods paper and fixed in its revision.

Other skills cover neighbouring ground; do not repeat them:
- `/paper:prose-review` judges sentence register, and `/paper:claim-audit`
  judges whether a claim is supported. Route those findings to them.
- `/paper:literature-check` searches for missing citations over the network.
  This skill judges only whether the survey that is on the page does its job.
- `/paper:story-review` proposes restructuring the whole paper.

## Scope

By default the skill reads:
- the abstract (`config.typ`);
- every section from the first heading after `// >>> BODY START` up to the
  first Results or Methods heading (for a paper with Methods first, up to the
  first Results heading).

It also reads the last paragraph of the Discussion or Conclusions, and the
Limitations section, as the things the Introduction must agree with. The
user may name a different section as the introduction; this is common in a
dissertation chapter.

## Read the action ledger first

`reviews/ACTIONS.md` records every finding earlier reviews raised and whether
it was fixed; its header states the rules. Read it before reviewing. If it
is missing, create it with `just check-actions --init`.

A problem that matches an `open`, `done` or `wontfix` row is not a new
finding: cite the existing id instead. A `done` row whose problem is back in
the current text is reopened, not duplicated.

## Read

1. Read `paper.review.txt`, running `just review-text` unless the caller says
   it is current. Open the Typst source only to quote a `file:line`.
2. Read `reviews/` for any decision letter or response letter
   (`reviewer-response.typ`). A reviewer's earlier complaint about the
   Introduction is the first thing to re-check.
3. Read `just wordcount --sections` output for the Introduction's size
   relative to the paper.

## Check, in this order

1. **The problem, sized from the literature.**
   - The opening states the problem, who has it and what it costs them.
   - The size of the problem comes from cited sources before any number from
     this paper's own data.
   - An Introduction that opens with the authors' own measurements makes the
     problem look manufactured by the study.
   - A finding quotes the sentence and names what is missing: a citation, a
     number, or who is affected.
2. **The existing approaches and their gaps.**
   - Each approach or tool the field already uses is named and cited, with
     one clause on what it achieves and one on what it leaves unmet.
   - The unmet needs together make the gap this paper fills.
   - Flag each of these:
     - a list of tools with no limitation stated;
     - a limitation stated with no citation or evidence;
     - a known alternative a reviewer would expect that is missing (name it
       only if the paper's own sources or domain make it evident; otherwise
       route to `/paper:literature-check`);
     - a gap asserted ("no tool exists") rather than shown.
3. **Terms, formats and design choices defined.**
   - List every term, acronym, file format, instrument mode or data type
     that the Results depend on.
   - Each must be defined in one sentence at or before its first use in the
     Introduction.
   - If the paper rests on a design choice (keeping a native format, a
     particular output, a given parameterisation), the Introduction says why
     that choice matters to users.
   - Flag each undefined item with its first use.
4. **The aim, scope and design, with reasons.** The last paragraph (the
   "Here we present" paragraph) states four things:
   - the aim, including what the method is not trying to do (reduction,
     not improvement; an addition, not a replacement);
   - the scope: what data, instruments and settings the conclusions cover,
     and what is out of scope;
   - the design: which datasets and comparisons test the aim;
   - why that design suits the aim. "Why only one dataset" is answered
     before a reviewer can ask it.

   Name each of the four that is missing.
5. **No results before the Results.**
   - The Introduction may state the headline outcome once, in the "Here we
     present" paragraph, as one or two numbers.
   - Flag each of these:
     - detailed results, figure or table callouts (`@fig:`, `@tbl:`) or
       per-condition numbers anywhere in the Introduction;
     - own-data numbers in the background paragraphs;
     - interpretation of results the reader has not seen yet;
     - any claim made again, with different numbers, in the Results.
   - Background numbers from cited work are not findings. Nor is a
     motivating number from the paper's own data that the text marks as
     motivation and that the Results then derive properly; still note that
     it should cite forward to where it is shown.
6. **Agreement with the rest of the paper.**
   - Read the Limitations section and the last paragraph of the
     Discussion or Conclusions against the Introduction. If the Limitations
     concedes something the Introduction's case rests on, that is a major
     finding; the fix is usually in the Introduction.
   - Every promise the Introduction makes ("we show", "we compare", "we
     test on") has a matching result. Flag a promise with none.
7. **Proportion.** Flag each of these:
   - an Introduction under about a tenth of the main text for a methods
     paper whose reviewers will not know the domain;
   - one so long that the gap arrives after the third paragraph;
   - a paragraph that belongs in the Methods (parameter values, pipeline
     steps).

For every finding give:
- the location as `file:line` and a short quote;
- which check it fails;
- what a reviewer would write about it, in one sentence in a reviewer's
  voice;
- the fix.

The fix is one of:
- a concrete rewrite the sources support;
- a move (to Methods, Results or the SI);
- "ask author: <question>", when the fact is not in the manuscript. Never
  invent a citation, a tool's limitation or a scope statement.

A fix that adds a number from the paper's data is routed to
`/paper:declare-number`; wording goes to `/paper:copy-edit`.

Severity:
- **major:** a missing aim, scope or gap; an undefined core term; a
  contradiction with the Limitations; detailed results in the Introduction.
- **minor:** anything else.

## Report

Write `reviews/<YYYY-MM-DD>-intro-review.md` (create the directory). Shape:

1. A verdict paragraph. Give the paper's aim in one sentence as a reader of
   the Introduction alone would state it, then say whether it matches the
   abstract and the Results.
2. The four answers from the opening question (problem, gap, contribution,
   how shown), each marked stated, partial or missing, with its location.
3. The findings table: severity, location, quote, check failed, the
   reviewer's sentence, fix, and routing.
4. The list of terms the Results rely on, each marked defined (with its
   location) or undefined.

Print the verdict paragraph and the file path. Nothing was edited, so do not
run `just paper` or `just verify`.

## Update the action ledger

After writing the findings file, and before the final print:

1. Every row of the findings table becomes one action.
2. Skip a finding that matches an `open` or `wontfix` row. Reopen a matching
   `done` row whose problem is back: set `status` to `open` and `closed` to
   `reopened <YYYY-MM-DD>: <what came back>`.
3. Append each remaining finding with
   `just actions-add <severity> "<source>" "<summary>" "<fix>"`:
   - the source is `<YYYY-MM-DD>-intro-review.md#<ref>`;
   - the summary is one line;
   - the fix is the routing.

   The command takes the ledger lock and the next free id; do not type new
   rows by hand.
4. Run `just check-actions` and repair any format error in the rows you
   reopened. Print the ids you added or reopened with the verdict.

Skip this section in two cases:
- `/paper:review-all` launched this review (its prompt says so): it merges
  every review into the ledger once, after all of them finish.
- The user passed `no-ledger`: the findings file is the whole output, and
  the final print says the ledger was not updated.
