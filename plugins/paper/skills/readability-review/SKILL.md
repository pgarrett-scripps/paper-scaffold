---
name: readability-review
description: Judge whether a reader can follow the Results and Discussion - each paragraph's point stated in words before its numbers, numbers kept to the ones the point rests on and interpreted against a yardstick, caveats gathered rather than attached to every claim - and propose a rewrite for the paragraphs that need it most. Use when a draft reads as number-dense or over-hedged. Read-only.
context: fork
agent: general-purpose
model: opus
---

# Review whether the results can be followed

Work from the manuscript root and follow AGENTS.md/CLAUDE.md and STYLE.md,
especially "Structure" and, where the paper's copy has it, "Results
paragraphs" (the questions below stand on their own if it does not). A
rule the paper's STYLE.md states differently wins. This skill is read-only: it
writes one findings file and routes every fix to `/paper:copy-edit`. The
question it answers is not "is this sentence well written" (that is
`/paper:prose-review`) or "is this claim supported" (`/paper:claim-audit`),
but "could a reader in the field say what each paragraph showed, after one
reading, without a calculator".

Scope defaults to the Results and any Discussion section in paper.typ
(including a separate "Discussion and limitations"), captions excluded. A Limitations subsection is in scope, but gathering caveats is its
job: do not count its concessions against it. The user may name a section, or say "whole paper" to add the
abstract, Introduction, Conclusions and si-body.typ.

## Everything here is a default, not a rule

Every threshold below is a prompt to reread, never a limit, and a finding
is a suggestion the author may decline. There are always exceptions: a
benchmark table summarised in prose, a paragraph whose job is to report a
parameter set, a comparison that genuinely needs four numbers, a caveat
that must sit next to the claim because it reverses it, a journal or field
that expects every value inline. When a passage breaks a default for a
reason you can see, it is not a finding. When you cannot tell, give the
finding as a question ("does the reader need both CVs here?"), not an
instruction. Never raise a readability finding as a blocker, and raise one
as major only when a reader could not say what the paragraph showed.

The fix is always to cut, move, merge or reword. Never ask for a new
figure, table, SI section or analysis to make room for a number: a dropped
number that is already in a cited table or figure is simply dropped, one
that is not stays (possibly in a shorter form), and the author decides
whether it is worth an existing table's extra column. See "Proportion" in
`.paper/docs/reviewer-lessons.md` (`docs/` in the scaffold itself).

## Read the action ledger first

`reviews/ACTIONS.md` records every finding earlier reviews raised and whether
it was fixed; its header states the rules. Read it before reviewing. If it is
missing, create it with `just check-actions --init`. A problem that matches
an `open`, `done` or `wontfix` row is not a new finding: cite the existing
id instead. A `wontfix` row means the author already declined it; do not
raise it again in other words. Appending to the ledger is the only write
this skill makes outside its findings file.

## Take the measurements as given

Run `just density` and copy three things into the report: the density table,
the section outliers, and the most number-dense sentences. They are relative
to this paper's own median, not absolute limits, and the report says so. A
section that is an outlier on numerals, the share of sentences with four or
more numerals, or concessions is where to read first; a section that is not
can still have one bad paragraph, and an outlier can be fine. If
`just density` fails, say why in one line and proceed on reading alone.

## Read each paragraph against these questions

Read `paper.review.txt` (run `just review-text` unless the caller says the
copy is current); open the source only to quote a `file:line`. For each
paragraph in scope:

1. **Can the point be found in words?** The first sentence says what the
   paragraph showed ("MS1 denoising left diaPASEF identifications
   unchanged"), before the evidence. Read only the first sentences of a
   section in order: they should tell its story. One short clause of
   set-up before the point is normal in a methods paper and is not a
   finding; a paragraph whose point arrives only after two or more
   sentences of set-up, numbers or caveats, or only in its last sentence,
   is.
2. **Does each number carry the point?** For each sentence, ask which
   numbers the claim rests on; usually one or two. The others are
   candidates to drop (if a cited table or figure holds them), fold into a
   range or a single summary ("below 0.5% in every condition"), or keep.
   Look hardest at: every condition listed where one summary would do;
   before-and-after pairs that say "no change" (0.068 against 0.068);
   precision past what the comparison can resolve; a number the adjacent
   figure already shows; the same value restated in a later section.
3. **Is each kept number interpreted?** The reader should learn whether it
   is large, small, good or bad without doing arithmetic: against the
   tolerance the Methods define, a baseline, replicate spread, or a
   practical consequence. Once a tolerance is defined, "within the
   tolerance" can stand in for restating it. A bare number with no
   yardstick in the sentence or the one before is a finding; a number
   whose meaning is obvious to the field is not. Use a yardstick the paper
   already has (a declared tolerance, baseline or spread). If none exists,
   the fix is a word of interpretation or a question to the author; a new
   derived value is the author's choice, never this review's request.
4. **Are the caveats gathered?** Count the concessions ("however",
   "although", "but", "despite", "while", "whereas") and limitation clauses
   per paragraph. A caveat stays beside its claim when it reverses or
   bounds the claim a reader would otherwise take away. The rest are
   candidates to collect: into one closing sentence of the paragraph, into
   the Limitations, or, for a mechanism aside, into the Discussion. A
   paragraph that alternates claim and counter-claim so the reader cannot
   say which way it came out is a major finding.
5. **Does the paragraph end on its point?** A paragraph that ends on a
   qualifier, a minor exception or a pointer to the SI leaves the reader
   with the wrong last impression. Suggest reordering, not deleting.
6. **Is the load bearable?** Acronyms per sentence, a parenthetical inside
   a sentence already carrying numbers, a sentence over about 35 words that
   holds more than one comparison. Suggest a split where one helps.

Where these questions and another skill's rule pull in different
directions (prose-review's "a number, not an adjective", claim-audit's
"state the tolerance"), prefer the version the reader can follow: one
number with its yardstick, in the sentence making the claim, and the rest
in the table it cites. Say so in the finding so the author can choose.

## Rewrite the worst paragraphs

Choose up to eight paragraphs; the cap is a ceiling, not a quota, and
three strong rewrites beat eight marginal ones. Weight them by where a
reader forms their view: the first paragraph of each Results subsection, the paragraph behind
each abstract claim, and the density outliers. For each, write a proposed
rewrite under the original:

- Keep every `#s()`, `#ci()`, `#lit()`, citation, `@fig`/`@tbl` reference
  and label it retains, in source form, so `/paper:copy-edit` can apply it
  and `just edit-check` can confirm nothing was invented. Dropping an id is
  allowed, and so is swapping a pair of ids for an already declared id
  that summarises them (a range, a maximum). Adding a number that is not
  already declared is not. Plain-language summaries ("essentially
  unchanged", "about three quarters") are fine when a declared value in the
  sentence or its cited table supports them and they do not make the claim
  stronger; say which value supports each. A summary phrase never carries
  a number of its own: "about a third" or "2 to 4 times" is a new number
  unless an id declares it.
- A citation or cross-reference may move to a neighbouring sentence, and a
  sentence whose only content is a pointer may be folded into the one
  before; the reference survives, the stub does not.
- A number that exists only in the prose (no table or figure holds it)
  stays. The rewrite can still move it after the point or into a closing
  sentence.
- Name each dropped number and where the reader can still find it (table,
  figure, SI section). Judge a figure by its caption and its `assets.json`
  description; do not open plotting scripts. If unsure, write "check
  figure N" and let the author decide. If it would be found nowhere, keep
  it or ask the author.
- Do not change a claim's meaning, scope or strength. If the rewrite would,
  route it to `/paper:claim-audit` instead.
- Aim for one or two numbers per sentence, the ones the claim rests on;
  a sentence that genuinely compares more keeps them (see the defaults
  above). Under each rewrite give the numerals per sentence before and
  after (e.g. "numerals/sentence: 4.3 -> 1.8, max 7 -> 3"), counting a
  `#s()`/`#ci()` as the numerals it renders.
- Say what the rewrite gives up, in one line, so the author can weigh it.
- Give each rewrite a severity (major / minor) by the same test as the
  table.

A move is a fix in its own right: a definition or reading rule placed
before the first paragraph that uses it, a caveat moved to the
Limitations, a mechanism aside moved to the Discussion. Give it as a
table row naming the source and destination.

Other findings go in a table without rewrites. List up to 12 rows, a
ceiling like the others; leave word-level problems (a repeated value, a
one-sentence paragraph, a vague word) to `/paper:prose-review` unless they
block the paragraph's point. Count the rest by habit in the verdict.

## Propose house rules for paper-wide habits

A habit that recurs across sections (e.g. "every Results paragraph gives
both gradients", "each comparison restates the tolerance", "every
identification count carries its CV") is cheaper to fix once than
paragraph by paragraph. Propose up to five house rules, each one sentence
the author could adopt into their STYLE.md ("Give the 60-min gradient in
prose; the 30-min values stay in Table 2"), with its count, locations and
the paragraphs it would shorten. A house rule is a proposal: the author
adopts, adapts or declines it, and a declined one is not raised again.
Each becomes one ledger action; its individual instances do not get table
rows of their own.

## Report

Write `reviews/<YYYY-MM-DD>-readability-review.md` (create the directory):

1. A verdict paragraph: whether a reader can follow the Results on one
   reading, the two or three habits that most get in the way, and the
   sections to start with. State plainly that every finding is a
   suggestion. Give the numerals per sentence across the rewritten
   paragraphs, before and after, as one line.
2. The `just density` output under its own heading.
3. The first-sentence skim: each Results subsection's first sentences in
   order, and whether they tell the story.
4. The rewrites, original above proposal, each with the numbers dropped
   and where they remain.
5. The proposed house rules.
6. The findings table: severity (major / minor), location, what gets in the
   reader's way, suggested fix, routed to `/paper:copy-edit`,
   `/paper:claim-audit` or "ask author".

Print the verdict paragraph and the file path. Nothing was edited, so do
not run `just paper` or `just verify`.

## Update the action ledger

After writing the findings file, and before the final print:

1. Each rewrite, each house rule and each table row becomes one action.
2. Skip a finding that matches an `open` or `wontfix` row. Reopen a
   matching `done` row whose problem is back: `status` to `open`, `closed`
   to `reopened <YYYY-MM-DD>: <what came back>`.
3. Append each remaining finding with
   `just actions-add <severity> "<source>" "<summary>" "<fix>"`: source
   `<YYYY-MM-DD>-readability-review.md#<ref>`, a one-line summary, the
   routed fix. Do not type new rows.
4. Run `just check-actions` and repair any format error in the rows you
   reopened. Print the ids you added or reopened with the verdict.

When `/paper:review-all` launched this review (its prompt says so), skip
this section: review-all merges every review into the ledger once. When the
user passes `no-ledger`, skip it too, and say the ledger was not updated.
